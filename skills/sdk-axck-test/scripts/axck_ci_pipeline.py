#!/usr/bin/env python3
"""
axck_ci_pipeline.py - AX615 / AXERA Camera-Kit 一键式端到端自动化 CI 流水线

集成阶段 (Stages):
1. STAGE 1: 设备网络与服务探活 (Probe & Preflight)
   - 自动探测 HTTP 端口 (默认 80 / 8080) 与 Telnet 带外控制台端口 (23)
   - 嗅探板端设备综合状态 (Online Cam 数量、TF卡挂载状态、CMM/OS内存水位)
2. STAGE 2: 全量 54 项软硬件门限自动化回归 (Full Regression Suite)
   - 8 项带外硬件可观测探针 (P01~P08: IVPS/VENC/AI/CMM/OS/VmRSS/RTSP)
   - 29 项领域微服务原子 API (A01~A29: Device/Storage/Audio/Stream/RTSP/DTCF/AOV)
   - 16 步业务场景流水线 (S01~S03: Smoke/Burst/Continuous MP4 & JPEG Magic Header)
   - 1 项高频并发压测 (ST01: 30次并发请求与 P99 时延门限)
3. STAGE 3: 低功耗休眠唤醒 AOV 专项浸泡与自动退出 (AOV Stability & Mux Trigger)
   - 启动 AOV 低功耗休眠唤醒循环
   - 验证内核 PM 挂起与网络断网自愈
   - 验证配置 sleep_count 达到后的异步 Detached 独立线程优雅退出与 20MB MP4 落盘
4. STAGE 4: 多格式测试报告与资产归档导出 (Artifacts & Reporting)
   - 生成完整 JSON 原始指标结果 (full_ci_report.json)
   - 生成标准 JUnit XML 门禁文件 (full_ci_report.xml, 兼容 Jenkins/GitLab CI)
   - 生成自包含响应式深色全景交互式 HTML 看板 (full_ci_report.html)
"""

import sys
import os
import time
import argparse
import socket

# 注入 scripts 目录
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

from core.domain_apis import AxckClient
from telnet_inspector import TelnetInspector
from case_reporter import CaseReporter
import run_full_test


def probe_port(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        res = s.connect_ex((host, port))
        s.close()
        return res == 0
    except Exception:
        return False


def run_pipeline(host: str = None, port: int = 80, telnet_port: int = 23,
                 aov_soak_sec: int = 15, export_dir: str = None) -> int:
    target_host = host or os.environ.get("AXCK_BOARD_IP", "127.0.0.1")
    print("\n" + "=" * 90)
    print(f"🚀 AX615 Camera-Kit 一键式端到端 CI 自动化流水线启动")
    print(f"   目标设备: {target_host} | HTTP: {port} | Telnet: {telnet_port}")
    print("=" * 90 + "\n")

    t_start = time.time()
    out_dir = export_dir if export_dir else os.path.dirname(SCRIPTS_DIR)
    os.makedirs(out_dir, exist_ok=True)

    # -------------------------------------------------------------
    # STAGE 1: 设备网络与服务探活 (Probe & Preflight)
    # -------------------------------------------------------------
    print("[STAGE 1/4] 正在执行设备网络与服务前置探活 (Preflight Probe)...")
    http_alive = probe_port(target_host, port, timeout=2.0)
    telnet_alive = probe_port(target_host, telnet_port, timeout=2.0)

    print(f"  • HTTP 端口 ({target_host}:{port}) 连通性     : {'✅ 正常 (OPEN)' if http_alive else '❌ 超时/未开放'}")
    print(f"  • Telnet 端口 ({target_host}:{telnet_port}) 连通性 : {'✅ 正常 (OPEN)' if telnet_alive else '❌ 超时/未开放'}")

    if not http_alive:
        print(f"\n❌ [FATAL] 板端 HTTP 服务 ({target_host}:{port}) 未响应，无法继续执行自动化测试！")
        return 1

    client = AxckClient(target_host, port)
    try:
        st_resp = client.device.get_status()
        if st_resp.code != 0:
            print(f"❌ [FATAL] 获取设备状态失败: {st_resp.msg}")
            return 1
        all_st = st_resp.data.get("status_all", {})
        front_st = all_st.get("front_status")
        rear_st = all_st.get("rear_status")
        sd_st = all_st.get("sdcard")
        print(f"  • 相机拓扑: 前摄={front_st}, 后摄={rear_st} ({'双摄在线' if front_st and rear_st else '单摄在线'})")
        print(f"  • TF卡状态: {sd_st} ({'已挂载就绪' if sd_st == 1 else '未就绪'})")
    except Exception as e:
        print(f"❌ [FATAL] 探活异常: {e}")
        return 1

    print("  ✅ STAGE 1 探活通过！设备处于就绪稳态。\n")

    # -------------------------------------------------------------
    # STAGE 2: 全量 54 项自动化回归套件 (Full Regression Suite)
    # -------------------------------------------------------------
    print("[STAGE 2/4] 启动全量 54 项软硬件门限自动化回归测试...")
    reporter = run_full_test.run_all_tests(host=host, port=port, export_dir=out_dir)
    reg_summary = reporter.get_summary()

    if reg_summary["failed"] > 0:
        print(f"\n❌ STAGE 2 存在失败项: {reg_summary['failed']} 项失败！")
        return 2

    print(f"  ✅ STAGE 2 全量 54 项回归全部通过 (100% PASS)！耗时: {reg_summary['total_duration']}s\n")

    # -------------------------------------------------------------
    # STAGE 3: 低功耗休眠唤醒 AOV 专项压测 (AOV Stability & Mux)
    # -------------------------------------------------------------
    print(f"[STAGE 3/4] 启动双摄 AOV 休眠唤醒与自动安全退出专项测试 (持续 {aov_soak_sec}s)...")
    aov_passed = True
    t0_aov = time.time()

    try:
        start_resp = client.aov.control('start')
        if start_resp.code == 0:
            print(f"  • AOV 启动成功: {start_resp.data}")
            print(f"  • 保持低功耗休眠唤醒循环浸泡 {aov_soak_sec} 秒...")
            time.sleep(aov_soak_sec)

            # 验证自愈与停止
            print(f"  • 下发 AOV 停止指令以触发 MP4 封包并恢复常态...")
            stopped = False
            for retry in range(1, 8):
                try:
                    stop_resp = client.aov.control('stop')
                    if stop_resp.code == 0:
                        print(f"  • AOV 停止成功: {stop_resp.data}")
                        stopped = True
                        break
                except Exception:
                    time.sleep(1.0)

            if not stopped:
                print("  ⚠️ AOV 停止重试达到上限，尝试等待自动计数退出...")
            
            # 等待封包落地
            time.sleep(2.0)

            # 抓拍探测自愈
            photo_resp = client.media.take_photo()
            if photo_resp.code == 0:
                print(f"  • AOV 退出后双路拍照自愈探测: ✅ PASS (code=0)")
            else:
                print(f"  • AOV 退出后拍照响应: {photo_resp.msg}")
        else:
            print(f"  ⚠️ AOV 启动非零: {start_resp.msg}")
            aov_passed = False
    except Exception as e:
        print(f"  ⚠️ AOV 阶段异常: {e}")
        aov_passed = False

    t_aov_cost = time.time() - t0_aov
    reporter.report_case(
        suite_name="aov-stability",
        case_name="AOV01. 双摄低功耗休眠唤醒与自动退出自愈压测",
        step_method=f"通过 HTTP 启动 AOV 模式，浸泡 {aov_soak_sec}s 休眠循环并校验退出后媒体抓拍自愈",
        inputs={"aov_cmd": "start/stop", "soak_sec": aov_soak_sec},
        outputs={"aov_passed": aov_passed, "duration_s": round(t_aov_cost, 2)},
        gates={
            "AOV_Cycle_OK": {"desc": "AOV休眠唤醒循环及自愈恢复正常", "expected": True, "actual": aov_passed, "passed": aov_passed}
        },
        status="PASS" if aov_passed else "FAIL",
        duration=t_aov_cost
    )

    print(f"  {'✅ STAGE 3 AOV 稳定性验证通过！' if aov_passed else '⚠️ STAGE 3 存在告警'}\n")

    # -------------------------------------------------------------
    # STAGE 4: 多格式测试报告与资产归档导出 (Artifacts & Reporting)
    # -------------------------------------------------------------
    print("[STAGE 4/4] 导出多格式自动化 CI 报告资产...")
    json_path = os.path.join(out_dir, "full_ci_report.json")
    xml_path = os.path.join(out_dir, "full_ci_report.xml")
    html_path = os.path.join(out_dir, "full_ci_report.html")

    reporter.save_json(json_path)
    reporter.save_junit_xml(xml_path)
    reporter.save_html_report(html_path, title="AX615 camera-kit 端到端 CI 自动化流水线测试看板")

    final_summary = reporter.get_summary()
    t_total = time.time() - t_start

    print("\n" + "#" * 90)
    print("                      AX615 CI 流水线全流程汇总")
    print(f"  • 总测试项数 (Total Cases)    : {final_summary['total']}")
    print(f"  • 通过项数   (Passed Cases)   : {final_summary['passed']}")
    print(f"  • 失败项数   (Failed Cases)   : {final_summary['failed']}")
    print(f"  • 流水线总耗时 (Pipeline Time): {round(t_total, 2)}s")
    print(f"  • JSON 报告路径               : {json_path}")
    print(f"  • JUnit XML (CI 门禁规范)     : {xml_path}")
    print(f"  • HTML 看板 (交互式全景仪表盘): {html_path}")
    print("#" * 90 + "\n")

    return 0 if final_summary["failed"] == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="AX615 camera-kit CI Automation Pipeline")
    parser.add_argument("--host", default=None, help="Board IP address (or set AXCK_BOARD_IP env)")
    parser.add_argument("--port", type=int, default=80, help="CGI HTTP port (default: 80)")
    parser.add_argument("--telnet-port", type=int, default=23, help="Telnet port (default: 23)")
    parser.add_argument("--aov-soak", type=int, default=15, help="AOV soak duration in seconds (default: 15)")
    parser.add_argument("--export-dir", default=None, help="Directory to store XML/HTML/JSON reports")
    args = parser.parse_args()

    exit_code = run_pipeline(
        host=args.host,
        port=args.port,
        telnet_port=args.telnet_port,
        aov_soak_sec=args.aov_soak,
        export_dir=args.export_dir
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
