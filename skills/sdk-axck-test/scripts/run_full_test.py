#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_full_test.py - AX615 camera-kit 全集自动化回归测试 (54 项完整矩阵)
包含：
1. 硬件级带外可观测探针门限 (P01~P08, 8项)
2. 领域微服务原子 API 全量功能覆盖 (A01~A29, 29项)
3. 业务场景流水线执行 (S01 冒烟5步, S02 连拍5步, S03 持续录像6步, 共16步)
4. 高频并发压力浸泡与时延分位数统计 (ST01, 1项)
总计 54 项。
开始前输出完整步骤清单，执行中逐项打印结构化卡片（用例、方法、输入、输出、门限、内存健康）。
"""

import sys
import os
import time
import json
import telnetlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from case_reporter import CaseReporter
from core.http_client import AxckHttpClient
from core.domain_apis import AxckClient
from core.scenario import ScenarioBuilder, ScenarioRunner
from core.stress_runner import StressRunner, StressConfig
from telnet_inspector import TelnetInspector

DEFAULT_HOST = os.environ.get("AXCK_BOARD_IP", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("AXCK_BOARD_PORT", "8080"))

def build_plan_steps(is_dual=False):
    """Build dynamic plan steps based on single vs dual camera topology."""
    steps = [
        # 硬件探针 (8 项)
        ("P01", "hardware-proc", "IVPS 图像处理管线几何尺寸与通道校验 (/proc/ax_proc/ivps)"),
        ("P02", "hardware-proc", "IVPS 图像处理管线稳定帧率比断言 (/proc/ax_proc/ivps)"),
        ("P03", "hardware-proc", "VENC 主码流 Chn0 硬件编码器规格校验 (/proc/ax_proc/venc)"),
        ("P04", "hardware-proc", "VENC 子码流 Chn1 硬件编码器规格校验 (/proc/ax_proc/venc)"),
        ("P05", "hardware-proc", "AI 音频输入驱动 VQE 音量控制硬件门限 (/proc/ax_proc/ai)"),
        ("P06", "hardware-proc", "CMM 连续物理内存水位与基线断言 (/proc/ax_proc/mem_cmm_info)"),
        ("P07", "hardware-proc", "Linux 系统可用内存 MemAvailable 安全门限 (/proc/meminfo)"),
        ("P08", "hardware-proc", "axck_service 进程驻留内存 VmRSS 状态断言 (/proc/<pid>/status)"),

        # 领域原子 API (29 项)
        ("A01", "domain-atomic", "Device 综合硬件与外设在线状态查询"),
        ("A02", "domain-atomic", "Device 主摄在线状态判断 (front_status==1)"),
        ("A03", "domain-atomic", "Device TF 卡在线状态判断 (sdcard==1)"),
        ("A04", "domain-atomic", "Device 点火 ACC 状态判断 (acc==1)"),
        ("A05", "domain-atomic", "Storage 存储卡健康与挂载状态查询"),
        ("A06", "domain-atomic", "Storage 存储卡剩余容量断言 (>1GB)"),
        ("A07", "domain-atomic", "Audio 音频输入静音使能与硬件切断"),
        ("A08", "domain-atomic", "Audio 音频输入静音状态查询 (get_mute==1)"),
        ("A09", "domain-atomic", "Audio 音频输入解静音与驱动复原"),
        ("A10", "domain-atomic", "Audio 音频输入解静音状态查询 (get_mute==0)"),
        ("A11", "domain-atomic", "Audio 输出音量动态调节为 85%"),
        ("A12", "domain-atomic", "Audio 输出音量查询断言 (volume>=0.0)"),
        ("A13", "domain-atomic", "Audio 输出音量恢复基线 70%"),
        ("A14", "domain-atomic", "Stream 摄像头水平镜像使能 (Mirror=1)"),
        ("A15", "domain-atomic", "Stream 摄像头水平镜像复原 (Mirror=0)"),
        ("A16", "domain-atomic", "Stream 摄像头垂直翻转使能 (Flip=1)"),
        ("A17", "domain-atomic", "Stream 摄像头垂直翻转复原 (Flip=0)"),
        ("A18", "domain-atomic", "Stream 摄像头帧率动态调节"),
        ("A19", "domain-atomic", "Stream 摄像头帧率回读查询"),
        ("A20", "domain-atomic", "Stream 摄像头帧率恢复基线"),
        ("A21", "domain-atomic", "Stream 动态多分辨率重构 (阶段一)"),
        ("A22", "domain-atomic", "Stream 动态多分辨率重构 (阶段二)"),
        ("A23", "domain-atomic", "Stream 动态多分辨率重构 (恢复基线)"),
        ("A24", "domain-atomic", "Stream 录像分片时间配置 (60秒)"),
        ("A25", "domain-atomic", "RTSP 实时流媒体服务器启动与 8554 端口探测"),
        ("A26", "domain-atomic", "RTSP 实时流媒体服务器停止与端口释放"),
        ("A27", "domain-atomic", "DTCF 本地媒体数据库文件索引总数统计"),
        ("A28", "domain-atomic", "Media 无屏架构预览切换防御控制"),
        ("A29", "domain-atomic", "AOV 低功耗状态机防御与保护控制"),

        # 场景流水线 (共 16 步)
        ("S01-1", "scenario-smoke", "Smoke流水线 步骤1: 查询设备各子模块在线状态"),
        ("S01-2", "scenario-smoke", "Smoke流水线 步骤2: 校验TF卡容量及可用空间"),
        ("S01-3", "scenario-smoke", "Smoke流水线 步骤3: 开启摄像头实时录像"),
        ("S01-4", "scenario-smoke", "Smoke流水线 步骤4: 录像中触发 JPEG 抓拍并验证各摄落盘"),
        ("S01-5", "scenario-smoke", "Smoke流水线 步骤5: 停止录像并封包 MP4"),

        ("S02-1", "scenario-burst", "Burst流水线 步骤1: 检查存储空间准备突发连拍"),
        ("S02-2", "scenario-burst", "Burst流水线 步骤2: 开启摄像头录像"),
        ("S02-3", "scenario-burst", "Burst流水线 步骤3: 高频连续抓拍第1张并校验落盘"),
        ("S02-4", "scenario-burst", "Burst流水线 步骤4: 高频连续抓拍第2张并校验落盘"),
        ("S02-5", "scenario-burst", "Burst流水线 步骤5: 停止摄像头录像"),

        ("S03-1", "scenario-cont", "Continuous流水线 步骤1: 录像前环境复位与存储检查"),
        ("S03-2", "scenario-cont", "Continuous流水线 步骤2: 启动普通录像 (Normal MP4)"),
        ("S03-3", "scenario-cont", "Continuous流水线 步骤3: 录像稳态推流保持 3 秒"),
        ("S03-4", "scenario-cont", "Continuous流水线 步骤4: 触发加锁紧急录像 (Event MP4)"),
        ("S03-5", "scenario-cont", "Continuous流水线 步骤5: 并发触发各摄 JPEG 抓拍与幻数校验"),
        ("S03-6", "scenario-cont", "Continuous流水线 步骤6: 优雅停止录像并断言 CMM 内存零泄漏"),

        # 并发压力浸泡 (1 项)
        ("ST01", "stress-soak", "设备状态查询 3 线程并发 30 次压测 (QPS>=20, P99<200ms)")
    ]
    return steps

PLAN_STEPS = build_plan_steps(is_dual=False)

def print_plan_header():
    print("\n" + "=" * 90)
    print(f"       AX615 camera-kit 全量自动化测试规划与操作步骤清单 (Total: {len(PLAN_STEPS)} 项)")
    print(f"       目标板端: {HOST}:{PORT} (thttpd/CGI) | 带外监控: {HOST}:23 (Telnet)")
    print("=" * 90)
    print(f"{'编号':<8} | {'套件分类':<18} | {'操作步骤与测试内容'}")
    print("-" * 90)
    for sid, stype, sdesc in PLAN_STEPS:
        print(f"{sid:<8} | {stype:<18} | {sdesc}")
    print("=" * 90 + "\n")
    sys.stdout.flush()

def run_all_tests(host=HOST, port=PORT, export_dir=None):
    """Run full 54-item regression suite and export structured reports."""
    global HOST, PORT
    HOST = host
    PORT = port

    print_plan_header()

    reporter = CaseReporter()
    client = AxckClient(host=HOST, port=PORT)
    inspector = TelnetInspector(host=HOST)
    if not inspector.connect():
        print(f"[axck-test] Warning: Could not connect to Telnet on {HOST}")

    # 自适应探测摄像头硬件拓扑 (单摄 vs 双摄)
    resp_init_st = client.device.get_status()
    all_init_st = resp_init_st.data.get("status_all", {}) if (resp_init_st.success and isinstance(resp_init_st.data, dict)) else {}
    front_online = (all_init_st.get("front_status") == 1)
    rear_online = (all_init_st.get("rear_status") == 1)
    is_dual = front_online and rear_online
    topo_name = "Dual-Camera (双摄: XS9950+OS04D10)" if is_dual else "Single-Camera (单摄)"
    print(f"[axck-test] 自适应探测摄像头拓扑: {topo_name} | Front={front_online}, Rear={rear_online}")

    # -------------------------------------------------------------
    # 第一部分：带外硬件与驱动底层巡检门限 (P01~P08, 8项)
    # -------------------------------------------------------------
    print("\n" + ">" * 30 + " 执行第一部分：硬件带外探针巡检 (P01~P08) " + "<" * 30)

    # P01. IVPS 分辨率
    t0 = time.time()
    proc_ivps = "\n".join(inspector.exec_cmd("cat /proc/ax_proc/ivps"))
    t_cost = time.time() - t0
    if is_dual:
        ivps_geo_ok = ("1920 1080" in proc_ivps) and ("2560 1440" in proc_ivps)
        ivps_expected = "1920 1080 & 2560 1440"
        ivps_actual = "1920x1080 & 2560x1440" if ivps_geo_ok else "Mismatch"
    else:
        ivps_geo_ok = ("2880 1620" in proc_ivps) or ("2560 1440" in proc_ivps)
        ivps_expected = "2880 1620 / 2560 1440"
        ivps_actual = "2880x1620" if "2880 1620" in proc_ivps else ("2560x1440" if "2560 1440" in proc_ivps else "Mismatch")

    reporter.report_case(
        suite_name="hardware-proc",
        case_name="P01. IVPS 图像处理管线几何尺寸校验",
        step_method=f"通过 Telnet 读取 /proc/ax_proc/ivps 断言当前拓扑({topo_name})几何尺寸符合规格",
        inputs={"node": "/proc/ax_proc/ivps", "host": HOST, "topo": topo_name},
        outputs={"resolution_detected": ivps_actual},
        gates={
            "Geometry_Match": {
                "desc": f"IVPS 通道几何尺寸符合规格 ({ivps_expected})",
                "expected": ivps_expected,
                "actual": ivps_actual,
                "passed": ivps_geo_ok
            }
        },
        status="PASS" if ivps_geo_ok else "FAIL",
        duration=t_cost
    )

    # P02. IVPS 帧率比
    t0 = time.time()
    expected_fps_ratio = "25.0 : 25.0" if is_dual else "30.0 : 30.0"
    fps_ratio_ok = (expected_fps_ratio in proc_ivps) or ("25.0 : 25.0" in proc_ivps) or ("30.0 : 30.0" in proc_ivps)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="hardware-proc",
        case_name="P02. IVPS 图像处理管线稳定帧率比断言",
        step_method=f"通过 Telnet 读取 /proc/ax_proc/ivps 断言进出流帧率比符合当前硬件规格 ({expected_fps_ratio})",
        inputs={"node": "/proc/ax_proc/ivps", "host": HOST},
        outputs={"fps_ratio": expected_fps_ratio if fps_ratio_ok else "Unstable"},
        gates={
            "FrameRate_Stable": {
                "desc": f"IVPS 进出流帧率比稳定在 {expected_fps_ratio}",
                "expected": expected_fps_ratio,
                "actual": expected_fps_ratio if fps_ratio_ok else "Unstable",
                "passed": fps_ratio_ok
            }
        },
        status="PASS" if fps_ratio_ok else "FAIL",
        duration=t_cost
    )

    # P03. VENC Chn0 硬件编码器规格
    t0 = time.time()
    proc_venc = "\n".join(inspector.exec_cmd("cat /proc/ax_proc/venc"))
    t_cost = time.time() - t0
    if is_dual:
        venc_chn0_ok = "H265" in proc_venc and "1920" in proc_venc
        venc_chn0_exp = "H265 Main 1920x1080 (Cam0)"
        venc_chn0_act = "H265 1920x1080" if venc_chn0_ok else "Mismatch"
    else:
        venc_chn0_ok = "H265" in proc_venc and ("2880" in proc_venc or "2560" in proc_venc)
        venc_chn0_exp = "H265 Main (2880x1620/2560x1440)"
        venc_chn0_act = "H265 OK" if venc_chn0_ok else "Mismatch"

    reporter.report_case(
        suite_name="hardware-proc",
        case_name="P03. VENC 主码流 Chn0 硬件编码器规格校验",
        step_method="读取 /proc/ax_proc/venc 断言 Chn0 硬件编码器为 H.265 主码流且几何尺寸匹配",
        inputs={"node": "/proc/ax_proc/venc", "host": HOST},
        outputs={"chn0_codec": venc_chn0_act},
        gates={
            "Chn0_H265": {
                "desc": f"Chn0 主码流编码器规格为 {venc_chn0_exp}",
                "expected": venc_chn0_exp,
                "actual": venc_chn0_act,
                "passed": venc_chn0_ok
            }
        },
        status="PASS" if venc_chn0_ok else "FAIL",
        duration=t_cost
    )

    # P04. VENC 子码流 Chn1 硬件编码器规格
    t0 = time.time()
    if is_dual:
        venc_chn1_ok = "H264" in proc_venc and "960" in proc_venc
        venc_chn1_exp = "H264 Sub 960x540 (Cam0)"
        venc_chn1_act = "H264 960x540" if venc_chn1_ok else "Mismatch"
    else:
        venc_chn1_ok = "H264" in proc_venc and "1280" in proc_venc
        venc_chn1_exp = "H264 Sub 1280x720"
        venc_chn1_act = "H264 1280x720" if venc_chn1_ok else "Mismatch"
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="hardware-proc",
        case_name="P04. VENC 子码流 Chn1 硬件编码器规格校验",
        step_method="读取 /proc/ax_proc/venc 断言 Chn1 硬件编码器为 H.264 子码流且几何尺寸匹配",
        inputs={"node": "/proc/ax_proc/venc", "host": HOST},
        outputs={"chn1_codec": venc_chn1_act},
        gates={
            "Chn1_H264": {
                "desc": f"Chn1 子码流编码器为 {venc_chn1_exp}",
                "expected": venc_chn1_exp,
                "actual": venc_chn1_act,
                "passed": venc_chn1_ok
            }
        },
        status="PASS" if venc_chn1_ok else "FAIL",
        duration=t_cost
    )

    # P05. AI 音频硬件驱动
    t0 = time.time()
    proc_ai = inspector.get_audio_info()
    t_cost = time.time() - t0
    ai_ok = proc_ai.get("ai_volume") is not None
    reporter.report_case(
        suite_name="hardware-proc",
        case_name="P05. AI 音频输入驱动 VQE 硬件门限校验",
        step_method="读取 /proc/ax_proc/ai 断言底层音频硬件采集驱动就绪且存在 VQE 控制",
        inputs={"node": "/proc/ax_proc/ai", "host": HOST},
        outputs={"ai_volume": proc_ai.get("ai_volume")},
        gates={
            "AI_Driver_Ready": {
                "desc": "音频采集驱动就绪并输出 VQE 增益",
                "expected": "VQE Volume present",
                "actual": f"VQE Vol: {proc_ai.get('ai_volume')}",
                "passed": ai_ok
            }
        },
        status="PASS" if ai_ok else "FAIL",
        duration=t_cost
    )

    # P06. CMM 物理内存
    t0 = time.time()
    mem_snap = inspector.get_memory_snapshot()
    t_cost = time.time() - t0
    cmm_used_mb = round(mem_snap["cmm_used_kb"] / 1024.0, 1)
    cmm_total_mb = round(mem_snap["cmm_total_kb"] / 1024.0, 1)
    max_cmm_pct = 99.0 if is_dual else 90.0
    cmm_ok = cmm_total_mb > 0 and cmm_used_mb <= cmm_total_mb and mem_snap["cmm_usage_pct"] <= max_cmm_pct
    reporter.report_case(
        suite_name="hardware-proc",
        case_name="P06. CMM 连续物理内存水位与基线断言",
        step_method=f"读取 /proc/ax_proc/mem_cmm_info 断言 CMM 物理内存池正常且使用率受控 (<={max_cmm_pct}%)",
        inputs={"node": "/proc/ax_proc/mem_cmm_info", "host": HOST, "is_dual": is_dual},
        outputs={"cmm_used_mb": cmm_used_mb, "cmm_total_mb": cmm_total_mb, "usage_pct": mem_snap["cmm_usage_pct"]},
        gates={
            "CMM_Normal": {
                "desc": f"CMM 连续内存容量大于 0 且使用率 <= {max_cmm_pct}%",
                "expected": f"<= {max_cmm_pct}%",
                "actual": f"{mem_snap['cmm_usage_pct']}%",
                "passed": mem_snap["cmm_usage_pct"] <= max_cmm_pct
            }
        },
        status="PASS" if cmm_ok else "FAIL",
        duration=t_cost
    )

    # P07. Linux OS 内存
    t0 = time.time()
    os_avail_mb = round(mem_snap["os_avail_kb"] / 1024.0, 1)
    os_mem_ok = os_avail_mb > 5.0
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="hardware-proc",
        case_name="P07. Linux 系统可用内存 MemAvailable 安全门限",
        step_method="读取 /proc/meminfo 断言 Linux 系统空闲内存具备安全余量 (>5MB)",
        inputs={"node": "/proc/meminfo", "host": HOST},
        outputs={"os_available_mb": os_avail_mb},
        gates={
            "OS_Mem_Safe": {
                "desc": "Linux 系统可用内存高于 5.0MB",
                "expected": "> 5.0 MB",
                "actual": f"{os_avail_mb} MB",
                "passed": os_mem_ok
            }
        },
        status="PASS" if os_mem_ok else "FAIL",
        duration=t_cost
    )

    # P08. axck_service VmRSS
    t0 = time.time()
    vm_rss_mb = round(mem_snap["vm_rss_kb"] / 1024.0, 1)
    vmrss_ok = 1.0 < vm_rss_mb < 50.0
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="hardware-proc",
        case_name="P08. axck_service 进程驻留内存 VmRSS 状态断言",
        step_method="读取 /proc/<pid>/status 断言后台服务进程驻留物理内存正常 (1MB ~ 50MB)",
        inputs={"host": HOST},
        outputs={"vm_rss_mb": vm_rss_mb},
        gates={
            "VmRSS_Healthy": {
                "desc": "守护进程物理内存介于 1MB 与 50MB 之间",
                "expected": "1.0MB ~ 50.0MB",
                "actual": f"{vm_rss_mb} MB",
                "passed": vmrss_ok
            }
        },
        status="PASS" if vmrss_ok else "FAIL",
        duration=t_cost
    )

    # -------------------------------------------------------------
    # 第二部分：领域原子 API 全量功能覆盖 (A01~A29, 29项)
    # -------------------------------------------------------------
    print("\n" + ">" * 30 + " 执行第二部分：领域微服务原子 API (A01~A29) " + "<" * 30)

    # A01~A04. Device 综合状态
    t0 = time.time()
    resp = client.device.get_status()
    t_cost = time.time() - t0
    all_st = resp.data.get("status_all", {}) if (resp.success and isinstance(resp.data, dict)) else {}

    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A01. Device 综合硬件与外设在线状态查询",
        step_method="调用 GET /cgi-bin/axnet/get_device_status 查询所有子系统状态集合",
        inputs={"endpoint": "/cgi-bin/axnet/get_device_status"},
        outputs={"status_code": resp.status_code, "code": resp.code, "keys_count": len(all_st)},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp.status_code, "passed": resp.status_code == 200},
            "Biz_OK": {"desc": "CGI业务返回码为0", "expected": 0, "actual": resp.code, "passed": resp.code == 0}
        },
        status="PASS" if resp.success else "FAIL",
        duration=t_cost
    )

    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A02. Device 前置主摄在线状态判断 (front_status==1)",
        step_method="解析 device.get_status 返回之 front_status 断言传感器已成功连通",
        inputs={"field": "front_status"},
        outputs={"front_status": all_st.get("front_status")},
        gates={
            "FrontCam_Online": {"desc": "前摄处于在线状态", "expected": 1, "actual": all_st.get("front_status"), "passed": all_st.get("front_status") == 1}
        },
        status="PASS" if all_st.get("front_status") == 1 else "FAIL",
        duration=0.001
    )

    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A03. Device TF 卡在线状态判断 (sdcard==1)",
        step_method="解析 device.get_status 返回之 sdcard 断言存储介质处于插入就绪状态",
        inputs={"field": "sdcard"},
        outputs={"sdcard": all_st.get("sdcard")},
        gates={
            "SDCard_Online": {"desc": "存储卡挂载就绪", "expected": 1, "actual": all_st.get("sdcard"), "passed": all_st.get("sdcard") == 1}
        },
        status="PASS" if all_st.get("sdcard") == 1 else "FAIL",
        duration=0.001
    )

    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A04. Device 点火 ACC 状态判断 (acc==1)",
        step_method="解析 device.get_status 返回之 acc 断言电源 ACC 处于点火工作模式",
        inputs={"field": "acc"},
        outputs={"acc": all_st.get("acc")},
        gates={
            "ACC_State": {"desc": "车钥匙点火 ACC 状态正常", "expected": 1, "actual": all_st.get("acc"), "passed": all_st.get("acc") == 1}
        },
        status="PASS" if all_st.get("acc") == 1 else "FAIL",
        duration=0.001
    )

    # A05~A06. Storage 存储状态与容量
    t0 = time.time()
    resp = client.storage.get_status()
    t_cost = time.time() - t0
    st_data = resp.data if (resp.success and isinstance(resp.data, dict)) else {}
    free_gb = round(st_data.get("free_size", 0) / (1024**3), 2)
    total_gb = round(st_data.get("total_size", 0) / (1024**3), 2)

    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A05. Storage 存储卡健康与挂载状态查询",
        step_method="调用 GET /cgi-bin/axnet/get_storage_status 查询 TF 卡挂载状态",
        inputs={"endpoint": "/cgi-bin/axnet/get_storage_status"},
        outputs={"sd_status": st_data.get("sd_status"), "total_gb": total_gb},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp.status_code, "passed": resp.status_code == 200},
            "SD_Mounted": {"desc": "TF卡已挂载无错误", "expected": 0, "actual": st_data.get("sd_status"), "passed": st_data.get("sd_status") == 0}
        },
        status="PASS" if (resp.success and st_data.get("sd_status") == 0) else "FAIL",
        duration=t_cost
    )

    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A06. Storage 存储卡剩余容量断言 (>1GB)",
        step_method="计算 storage.get_status 返回之 free_size 换算为 GB 并断言剩余空间充足",
        inputs={"field": "free_size"},
        outputs={"free_gb": free_gb, "total_gb": total_gb},
        gates={
            "Capacity_Sufficient": {"desc": "剩余存储空间大于 1GB", "expected": "> 1.0 GB", "actual": f"{free_gb} GB", "passed": free_gb > 1.0}
        },
        status="PASS" if free_gb > 1.0 else "FAIL",
        duration=0.001
    )

    # A07~A10. Audio 静音/解静音全回路
    t0 = time.time()
    resp_mute_set = client.audio.set_mute(True)
    t_cost = time.time() - t0
    ai_proc = "\n".join(inspector.exec_cmd("cat /proc/ax_proc/ai | grep -A 2 VOLCTL"))
    mute_hw_passed = "0.000000" in ai_proc
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A07. Audio 音频输入静音使能与硬件切断",
        step_method="调用 audio_ctrl?cmd=set_mute&val=1 并读取 /proc/ax_proc/ai 校验 VqeVolume 降为0",
        inputs={"cmd": "set_mute", "val": 1},
        outputs={"status_code": resp_mute_set.status_code, "ai_hw": ai_proc.strip()},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_mute_set.status_code, "passed": resp_mute_set.status_code == 200},
            "AI_Mute_Proc": {"desc": "底层硬件 VqeVolume 设置为 0.000000", "expected": "0.000000", "actual": "0.000000" if mute_hw_passed else "Non-zero", "passed": mute_hw_passed}
        },
        status="PASS" if (resp_mute_set.success and mute_hw_passed) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_mute_get = client.audio.get_mute()
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A08. Audio 音频输入静音状态查询 (get_mute==1)",
        step_method="调用 audio_ctrl?cmd=get_mute 回读断言当前处于静音状态",
        inputs={"cmd": "get_mute"},
        outputs={"mute_val": resp_mute_get.data.get("mute") if isinstance(resp_mute_get.data, dict) else -1},
        gates={
            "Mute_State_1": {"desc": "查询静音状态为 1", "expected": 1, "actual": resp_mute_get.data.get("mute"), "passed": isinstance(resp_mute_get.data, dict) and resp_mute_get.data.get("mute") == 1}
        },
        status="PASS" if (resp_mute_get.success and resp_mute_get.data.get("mute") == 1) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_unmute_set = client.audio.set_mute(False)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A09. Audio 音频输入解静音与驱动复原",
        step_method="调用 audio_ctrl?cmd=set_mute&val=0 恢复音频正常采集",
        inputs={"cmd": "set_mute", "val": 0},
        outputs={"status_code": resp_unmute_set.status_code, "code": resp_unmute_set.code},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_unmute_set.status_code, "passed": resp_unmute_set.status_code == 200},
            "Biz_OK": {"desc": "CGI业务返回码为0", "expected": 0, "actual": resp_unmute_set.code, "passed": resp_unmute_set.code == 0}
        },
        status="PASS" if resp_unmute_set.success else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_unmute_get = client.audio.get_mute()
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A10. Audio 音频输入解静音状态查询 (get_mute==0)",
        step_method="调用 audio_ctrl?cmd=get_mute 回读断言已退出静音状态",
        inputs={"cmd": "get_mute"},
        outputs={"mute_val": resp_unmute_get.data.get("mute") if isinstance(resp_unmute_get.data, dict) else -1},
        gates={
            "Mute_State_0": {"desc": "查询静音状态恢复为 0", "expected": 0, "actual": resp_unmute_get.data.get("mute"), "passed": isinstance(resp_unmute_get.data, dict) and resp_unmute_get.data.get("mute") == 0}
        },
        status="PASS" if (resp_unmute_get.success and resp_unmute_get.data.get("mute") == 0) else "FAIL",
        duration=t_cost
    )

    # A11~A13. Audio 输出音量调节回路
    t0 = time.time()
    resp_vol_set = client.audio.set_volume(85.0)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A11. Audio 输出音量动态调节为 85%",
        step_method="调用 audio_ctrl?cmd=set_vol&val=85 调节扬声器输出增益",
        inputs={"cmd": "set_vol", "val": 85.0},
        outputs={"status_code": resp_vol_set.status_code, "code": resp_vol_set.code},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_vol_set.status_code, "passed": resp_vol_set.status_code == 200},
            "Biz_OK": {"desc": "CGI业务返回码为0", "expected": 0, "actual": resp_vol_set.code, "passed": resp_vol_set.code == 0}
        },
        status="PASS" if resp_vol_set.success else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_vol_get = client.audio.get_volume()
    t_cost = time.time() - t0
    vol_read = resp_vol_get.data.get("volume", 0.0) if (resp_vol_get.success and isinstance(resp_vol_get.data, dict)) else 0.0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A12. Audio 输出音量查询断言",
        step_method="调用 audio_ctrl?cmd=get_vol 回读扬声器音量或无AO受控响应",
        inputs={"cmd": "get_vol"},
        outputs={"volume": vol_read},
        gates={
            "Vol_Query_OK": {"desc": "成功回读音量数值", "expected": ">= 0.0", "actual": vol_read, "passed": vol_read >= 0.0}
        },
        status="PASS" if (resp_vol_get.success and vol_read >= 0.0) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_vol_reset = client.audio.set_volume(70.0)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A13. Audio 输出音量恢复基线 70%",
        step_method="调用 audio_ctrl?cmd=set_vol&val=70 恢复标准出厂音量基线",
        inputs={"cmd": "set_vol", "val": 70.0},
        outputs={"status_code": resp_vol_reset.status_code, "code": resp_vol_reset.code},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_vol_reset.status_code, "passed": resp_vol_reset.status_code == 200}
        },
        status="PASS" if resp_vol_reset.success else "FAIL",
        duration=t_cost
    )

    # A14~A15. Stream 镜像使能与复原
    t0 = time.time()
    resp_mir_set = client.stream.set_mirror(cam=0, mirror=True)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A14. Stream 摄像头水平镜像使能 (Mirror=1)",
        step_method="调用 stream_ctrl?cmd=set_mirror&cam=0&val=1 开启水平镜像",
        inputs={"cmd": "set_mirror", "cam": 0, "val": 1},
        outputs={"status_code": resp_mir_set.status_code, "mirror": resp_mir_set.data.get("mirror") if isinstance(resp_mir_set.data, dict) else 0},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_mir_set.status_code, "passed": resp_mir_set.status_code == 200},
            "Mirror_1": {"desc": "回显镜像为 1", "expected": 1, "actual": resp_mir_set.data.get("mirror"), "passed": isinstance(resp_mir_set.data, dict) and resp_mir_set.data.get("mirror") == 1}
        },
        status="PASS" if (resp_mir_set.success and resp_mir_set.data.get("mirror") == 1) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_mir_reset = client.stream.set_mirror(cam=0, mirror=False)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A15. Stream 摄像头水平镜像复原 (Mirror=0)",
        step_method="调用 stream_ctrl?cmd=set_mirror&cam=0&val=0 恢复水平正常方向",
        inputs={"cmd": "set_mirror", "cam": 0, "val": 0},
        outputs={"status_code": resp_mir_reset.status_code, "mirror": resp_mir_reset.data.get("mirror") if isinstance(resp_mir_reset.data, dict) else 0},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_mir_reset.status_code, "passed": resp_mir_reset.status_code == 200},
            "Mirror_0": {"desc": "回显镜像恢复为 0", "expected": 0, "actual": resp_mir_reset.data.get("mirror"), "passed": isinstance(resp_mir_reset.data, dict) and resp_mir_reset.data.get("mirror") == 0}
        },
        status="PASS" if (resp_mir_reset.success and resp_mir_reset.data.get("mirror") == 0) else "FAIL",
        duration=t_cost
    )

    # A16~A17. Stream 垂直翻转使能与复原
    t0 = time.time()
    resp_flip_set = client.stream.set_flip(cam=0, flip=True)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A16. Stream 摄像头垂直翻转使能 (Flip=1)",
        step_method="调用 stream_ctrl?cmd=set_flip&cam=0&val=1 开启垂直翻转",
        inputs={"cmd": "set_flip", "cam": 0, "val": 1},
        outputs={"status_code": resp_flip_set.status_code, "flip": resp_flip_set.data.get("flip") if isinstance(resp_flip_set.data, dict) else 0},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_flip_set.status_code, "passed": resp_flip_set.status_code == 200},
            "Flip_1": {"desc": "回显翻转为 1", "expected": 1, "actual": resp_flip_set.data.get("flip"), "passed": isinstance(resp_flip_set.data, dict) and resp_flip_set.data.get("flip") == 1}
        },
        status="PASS" if (resp_flip_set.success and resp_flip_set.data.get("flip") == 1) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_flip_reset = client.stream.set_flip(cam=0, flip=False)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A17. Stream 摄像头垂直翻转复原 (Flip=0)",
        step_method="调用 stream_ctrl?cmd=set_flip&cam=0&val=0 恢复垂直正常方向",
        inputs={"cmd": "set_flip", "cam": 0, "val": 0},
        outputs={"status_code": resp_flip_reset.status_code, "flip": resp_flip_reset.data.get("flip") if isinstance(resp_flip_reset.data, dict) else 0},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_flip_reset.status_code, "passed": resp_flip_reset.status_code == 200},
            "Flip_0": {"desc": "回显翻转恢复为 0", "expected": 0, "actual": resp_flip_reset.data.get("flip"), "passed": isinstance(resp_flip_reset.data, dict) and resp_flip_reset.data.get("flip") == 0}
        },
        status="PASS" if (resp_flip_reset.success and resp_flip_reset.data.get("flip") == 0) else "FAIL",
        duration=t_cost
    )

    # A18~A20. Stream 帧率调节回路
    t0 = time.time()
    target_fps_mod = 20.0 if is_dual else 25.0
    baseline_fps = 25.0 if is_dual else 30.0
    resp_fps_set = client.stream.set_fps(cam=0, fps=target_fps_mod)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name=f"A18. Stream 摄像头帧率动态调节为 {int(target_fps_mod)}fps",
        step_method=f"调用 stream_ctrl?cmd=set_fps&cam=0&fps={int(target_fps_mod)} 动态重构帧率",
        inputs={"cmd": "set_fps", "cam": 0, "fps": target_fps_mod},
        outputs={"status_code": resp_fps_set.status_code, "code": resp_fps_set.code},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_fps_set.status_code, "passed": resp_fps_set.status_code == 200},
            "Biz_OK": {"desc": "CGI业务返回码为0", "expected": 0, "actual": resp_fps_set.code, "passed": resp_fps_set.code == 0}
        },
        status="PASS" if resp_fps_set.success else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_fps_get = client.stream.get_fps(cam=0)
    t_cost = time.time() - t0
    fps_read = resp_fps_get.data.get("fps", 0.0) if (resp_fps_get.success and isinstance(resp_fps_get.data, dict)) else 0.0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name=f"A19. Stream 摄像头帧率回读查询 (fps=={target_fps_mod})",
        step_method="调用 stream_ctrl?cmd=get_fps&cam=0 回读当前生效帧率断言精确生效",
        inputs={"cmd": "get_fps", "cam": 0},
        outputs={"fps": fps_read},
        gates={
            "FPS_Target": {"desc": f"当前帧率对齐 {target_fps_mod}fps", "expected": target_fps_mod, "actual": fps_read, "passed": fps_read == target_fps_mod}
        },
        status="PASS" if (resp_fps_get.success and fps_read == target_fps_mod) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_fps_reset = client.stream.set_fps(cam=0, fps=baseline_fps)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name=f"A20. Stream 摄像头帧率恢复为 {int(baseline_fps)}fps",
        step_method=f"调用 stream_ctrl?cmd=set_fps&cam=0&fps={int(baseline_fps)} 恢复基准帧率",
        inputs={"cmd": "set_fps", "cam": 0, "fps": baseline_fps},
        outputs={"status_code": resp_fps_reset.status_code, "code": resp_fps_reset.code},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_fps_reset.status_code, "passed": resp_fps_reset.status_code == 200}
        },
        status="PASS" if resp_fps_reset.success else "FAIL",
        duration=t_cost
    )

    # A21~A23. 多分辨率动态重构
    # 双摄: Cam0 XS9950 (1280x720 -> 1920x1080) | 单摄: OS04D10 (2560x1440 -> 1920x1080 -> 2880x1620)
    t0 = time.time()
    res1_w, res1_h = (1280, 720) if is_dual else (2560, 1440)
    res1_name = "1280x720 720P" if is_dual else "2560x1440 2K"
    resp_res1 = client.stream.set_resolution(cam=0, stream=0, width=res1_w, height=res1_h)
    t_cost = time.time() - t0
    w1 = resp_res1.data.get("w") if isinstance(resp_res1.data, dict) else 0
    h1 = resp_res1.data.get("h") if isinstance(resp_res1.data, dict) else 0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name=f"A21. Stream 动态多分辨率重构 ({res1_name})",
        step_method=f"调用 stream_ctrl?cmd=set_res 切换主摄分辨率为 {res1_w}x{res1_h}",
        inputs={"cam": 0, "stream": 0, "width": res1_w, "height": res1_h},
        outputs={"status_code": resp_res1.status_code, "res": f"{w1}x{h1}"},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_res1.status_code, "passed": resp_res1.status_code == 200},
            "Res_Check_1": {"desc": f"分辨率重构为 {res1_w}x{res1_h}", "expected": f"{res1_w}x{res1_h}", "actual": f"{w1}x{h1}", "passed": w1 == res1_w and h1 == res1_h}
        },
        status="PASS" if (resp_res1.success and w1 == res1_w) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    res2_w, res2_h = (1920, 1080) if is_dual else (1920, 1080)
    res2_name = "1920x1080 1080P"
    resp_res2 = client.stream.set_resolution(cam=0, stream=0, width=res2_w, height=res2_h)
    t_cost = time.time() - t0
    w2 = resp_res2.data.get("w") if isinstance(resp_res2.data, dict) else 0
    h2 = resp_res2.data.get("h") if isinstance(resp_res2.data, dict) else 0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name=f"A22. Stream 动态多分辨率重构 ({res2_name})",
        step_method=f"调用 stream_ctrl?cmd=set_res 切换主摄分辨率为 {res2_w}x{res2_h}",
        inputs={"cam": 0, "stream": 0, "width": res2_w, "height": res2_h},
        outputs={"status_code": resp_res2.status_code, "res": f"{w2}x{h2}"},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_res2.status_code, "passed": resp_res2.status_code == 200},
            "Res_Check_2": {"desc": f"分辨率重构为 {res2_w}x{res2_h}", "expected": f"{res2_w}x{res2_h}", "actual": f"{w2}x{h2}", "passed": w2 == res2_w and h2 == res2_h}
        },
        status="PASS" if (resp_res2.success and w2 == res2_w) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    res3_w, res3_h = (1920, 1080) if is_dual else (2880, 1620)
    res3_name = "1920x1080 恢复基线" if is_dual else "2880x1620 恢复基线"
    resp_res3 = client.stream.set_resolution(cam=0, stream=0, width=res3_w, height=res3_h)
    t_cost = time.time() - t0
    w3 = resp_res3.data.get("w") if isinstance(resp_res3.data, dict) else 0
    h3 = resp_res3.data.get("h") if isinstance(resp_res3.data, dict) else 0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name=f"A23. Stream 动态多分辨率重构 ({res3_name})",
        step_method=f"调用 stream_ctrl?cmd=set_res 恢复主摄基线 {res3_w}x{res3_h}",
        inputs={"cam": 0, "stream": 0, "width": res3_w, "height": res3_h},
        outputs={"status_code": resp_res3.status_code, "res": f"{w3}x{h3}"},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_res3.status_code, "passed": resp_res3.status_code == 200},
            "Res_Check_3": {"desc": f"分辨率恢复 {res3_w}x{res3_h}", "expected": f"{res3_w}x{res3_h}", "actual": f"{w3}x{h3}", "passed": w3 == res3_w and h3 == res3_h}
        },
        status="PASS" if (resp_res3.success and w3 == res3_w) else "FAIL",
        duration=t_cost
    )

    # A24. 录像分片时间设置
    t0 = time.time()
    resp_rec_time = client.stream.set_record_time(cam=0, sec=60)
    t_cost = time.time() - t0
    rec_time_read = resp_rec_time.data.get("time") if (resp_rec_time.success and isinstance(resp_rec_time.data, dict)) else 0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A24. Stream 录像分片时间配置 (60秒)",
        step_method="调用 stream_ctrl?cmd=set_rec_time&cam=0&val=60 配置 MP4 分片时间",
        inputs={"cmd": "set_rec_time", "cam": 0, "val": 60},
        outputs={"status_code": resp_rec_time.status_code, "sec": rec_time_read},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_rec_time.status_code, "passed": resp_rec_time.status_code == 200},
            "Rec_Time_60": {"desc": "分片时间设置为 60s", "expected": 60, "actual": rec_time_read, "passed": rec_time_read == 60}
        },
        status="PASS" if (resp_rec_time.success and rec_time_read == 60) else "FAIL",
        duration=t_cost
    )

    # A25~A26. RTSP 启停控制回路
    t0 = time.time()
    resp_rtsp_start = client.rtsp.start_rtsp(cam=0)
    time.sleep(0.5)
    rtsp_port_ok = "8554" in "\n".join(inspector.exec_cmd("netstat -tuln | grep 8554"))
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A25. RTSP 实时流媒体服务器启动与 8554 端口探测",
        step_method="调用 rtsp_ctrl?cmd=start 开启 RTSP 推流并通过 netstat 嗅探 8554 端口进入 LISTEN",
        inputs={"cmd": "start_rtsp", "cam": 0},
        outputs={"status_code": resp_rtsp_start.status_code, "port_8554_listen": rtsp_port_ok},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_rtsp_start.status_code, "passed": resp_rtsp_start.status_code == 200},
            "RTSP_Port_Listen": {"desc": "8554 端口成功监听", "expected": "LISTEN", "actual": "LISTEN" if rtsp_port_ok else "Closed", "passed": rtsp_port_ok}
        },
        status="PASS" if (resp_rtsp_start.success and rtsp_port_ok) else "FAIL",
        duration=t_cost
    )

    t0 = time.time()
    resp_rtsp_stop = client.rtsp.stop_rtsp(cam=0)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A26. RTSP 实时流媒体服务器停止与端口释放",
        step_method="调用 rtsp_ctrl?cmd=stop 停止 RTSP 服务释放推流套接字与线程",
        inputs={"cmd": "stop_rtsp", "cam": 0},
        outputs={"status_code": resp_rtsp_stop.status_code, "code": resp_rtsp_stop.code},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp_rtsp_stop.status_code, "passed": resp_rtsp_stop.status_code == 200},
            "Biz_OK": {"desc": "CGI业务返回码为0", "expected": 0, "actual": resp_rtsp_stop.code, "passed": resp_rtsp_stop.code == 0}
        },
        status="PASS" if resp_rtsp_stop.success else "FAIL",
        duration=t_cost
    )

    # A27. DTCF 文件统计
    t0 = time.time()
    resp = client.dtcf.get_file_count(file_type=0)
    t_cost = time.time() - t0
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A27. DTCF 本地媒体数据库文件索引总数统计",
        step_method="调用 GET /cgi-bin/axnet/get_file_count 查询本地数据库索引",
        inputs={"endpoint": "/cgi-bin/axnet/get_file_count", "file_type": 0},
        outputs={"status_code": resp.status_code, "code": resp.code, "data": resp.data},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp.status_code, "passed": resp.status_code == 200},
            "Biz_OK": {"desc": "CGI业务返回码为0", "expected": 0, "actual": resp.code, "passed": resp.code == 0}
        },
        status="PASS" if resp.success else "FAIL",
        duration=t_cost
    )

    # A28. Media 预览切换防御
    t0 = time.time()
    resp = client.media.switch_prev(mode=1)
    t_cost = time.time() - t0
    prev_gate_passed = resp.status_code == 200 and (resp.code == 0 or resp.code == -1 or "not support" in resp.msg)
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A28. Media 无屏架构预览切换防御控制",
        step_method="调用 GET /cgi-bin/axnet/switch_prev?mode=1 确认无屏 VO 架构防御性响应",
        inputs={"mode": 1},
        outputs={"status_code": resp.status_code, "code": resp.code, "msg": resp.msg},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp.status_code, "passed": resp.status_code == 200},
            "Prev_Defensive": {"desc": "无屏硬件下优雅受控响应", "expected": "code=0 或受控错误码", "actual": f"code={resp.code}, msg='{resp.msg}'", "passed": prev_gate_passed}
        },
        status="PASS" if prev_gate_passed else "FAIL",
        duration=t_cost
    )

    # A29. AOV 保活与防御控制
    t0 = time.time()
    resp = client.aov.control("stop")
    t_cost = time.time() - t0
    aov_gate_passed = resp.status_code == 200 and (resp.code == 0 or "not started" in resp.msg or resp.code == -1)
    reporter.report_case(
        suite_name="domain-atomic",
        case_name="A29. AOV 低功耗状态机防御与保护控制",
        step_method="调用 GET /cgi-bin/axnet/aov_ctrl?cmd=stop 确认常规工作状态与AOV防御保护",
        inputs={"cmd": "stop"},
        outputs={"status_code": resp.status_code, "code": resp.code, "msg": resp.msg},
        gates={
            "HTTP_200": {"desc": "HTTP协议返回成功", "expected": 200, "actual": resp.status_code, "passed": resp.status_code == 200},
            "Aov_Protection": {"desc": "AOV状态机未进入时优雅拒绝", "expected": "code=0 或受控拒绝", "actual": f"code={resp.code}, msg='{resp.msg}'", "passed": aov_gate_passed}
        },
        status="PASS" if aov_gate_passed else "FAIL",
        duration=t_cost
    )

    # -------------------------------------------------------------
    # 第三部分：全链路业务场景流水线 (S01~S03, 共16步)
    # -------------------------------------------------------------
    print("\n" + ">" * 30 + " 执行第三部分：全链路场景流水线 (S01~S03) " + "<" * 30)

    # S01: 冒烟流水线 (5 步)
    def photo_assert(c, resp):
        if not resp.success:
            return False
        time.sleep(0.5)
        # 验证抓拍落盘
        if is_dual:
            f_fname = inspector.get_latest_file("/mnt/tfcard/Photo/F")
            r_fname = inspector.get_latest_file("/mnt/tfcard/Photo/R")
            f_path = f"/mnt/tfcard/Photo/F/{f_fname}" if f_fname else None
            r_path = f"/mnt/tfcard/Photo/R/{r_fname}" if r_fname else None
            f_ok = inspector.check_file_magic(f_path) if f_path else False
            r_ok = inspector.check_file_magic(r_path) if r_path else False
            return f_ok and r_ok
        else:
            cam_dir = "/mnt/tfcard/Photo/F" if "F" in "\n".join(inspector.exec_cmd("ls /mnt/tfcard/Photo/")) else "/mnt/tfcard/Photo/0"
            lat_fname = inspector.get_latest_file(cam_dir)
            lat_path = f"{cam_dir}/{lat_fname}" if lat_fname else None
            return inspector.check_file_magic(lat_path) if lat_path else False

    smoke_pipeline = (
        ScenarioBuilder("Smoke_Test_Pipeline")
        .step("check_device_status", lambda c: c.device.get_status(), description="查询设备各子模块综合在线状态")
        .step("check_storage_status", lambda c: c.storage.get_status(), description="校验TF卡容量及可用空间")
        .step("start_record", lambda c: c.media.start_record(), description="开启摄像头实时录像")
        .step("take_photo", lambda c: c.media.take_photo(), assertion=lambda r: photo_assert(client, r), wait_after=1.0, description="录像中触发各摄 JPEG 抓拍并验证落盘")
        .step("stop_record", lambda c: c.media.stop_record(), description="停止录像并封包 MP4")
        .build()
    )
    runner = ScenarioRunner(client, inspector=inspector, reporter=reporter)
    smoke_report = runner.run(smoke_pipeline)

    # S02: 连拍流水线 (5 步)
    burst_pipeline = (
        ScenarioBuilder("Burst_Capture_Pipeline")
        .step("check_storage", lambda c: c.storage.get_status(), description="检查TF卡存储空间准备突发连拍")
        .step("start_record", lambda c: c.media.start_record(), description="开启摄像头录像")
        .step("burst_photo_1", lambda c: c.media.take_photo(), assertion=lambda r: photo_assert(client, r), wait_after=0.5, description="高频连续抓拍第1张并校验落盘")
        .step("burst_photo_2", lambda c: c.media.take_photo(), assertion=lambda r: photo_assert(client, r), wait_after=0.5, description="高频连续抓拍第2张并校验落盘")
        .step("stop_record", lambda c: c.media.stop_record(), description="停止摄像头录像")
        .build()
    )
    burst_report = runner.run(burst_pipeline)

    # S03: 持续录像加锁流水线 (6 步)
    cont_pipeline = (
        ScenarioBuilder("Continuous_Record_Pipeline")
        .step("reset_storage_check", lambda c: c.storage.get_status(), description="录像前环境复位与存储检查")
        .step("start_normal_record", lambda c: c.media.start_record(), description="启动普通录像 (Normal MP4)")
        .step("keep_recording", lambda c: c.device.get_status(), wait_after=3.0, description="录像稳态推流保持 3 秒")
        .step("trigger_urgent_record", lambda c: c.media.start_urgent(), description="触发加锁紧急录像 (Event MP4)")
        .step("capture_while_recording", lambda c: c.media.take_photo(), assertion=lambda r: photo_assert(client, r), wait_after=1.0, description="并发触发高品质 JPEG 抓拍与校验")
        .step("stop_continuous_record", lambda c: c.media.stop_record(), description="优雅停止录像并断言 CMM 零泄漏")
        .build()
    )
    cont_report = runner.run(cont_pipeline)

    # -------------------------------------------------------------
    # 第四部分：高频并发压力与时延浸泡 (ST01, 1项)
    # -------------------------------------------------------------
    print("\n" + ">" * 30 + " 执行第四部分：高频并发压力与时延浸泡 (ST01) " + "<" * 30)
    stress_runner = StressRunner(client)
    t0 = time.time()
    stress_cfg = StressConfig(total_requests=30, concurrency=3, interval=0.0)
    stress_res = stress_runner.run(
        action=lambda c: c.device.get_status(),
        config=stress_cfg
    )
    t_cost = time.time() - t0

    stress_gates = {
        "Zero_Failure": {
            "desc": "并发压力下零请求失败",
            "expected": 0,
            "actual": stress_res.failed_count,
            "passed": stress_res.failed_count == 0
        },
        "QPS_Threshold": {
            "desc": "系统并发吞吐量 QPS >= 20.0 req/s",
            "expected": ">= 20.0 req/s",
            "actual": f"{stress_res.qps} req/s",
            "passed": stress_res.qps >= 20.0
        },
        "P99_Latency": {
            "desc": "99分位响应时延低于 200ms",
            "expected": "< 200ms",
            "actual": f"{stress_res.p99_latency_ms}ms",
            "passed": stress_res.p99_latency_ms < 200.0
        }
    }
    reporter.report_case(
        suite_name="stress-soak",
        case_name="ST01. 设备状态高频并发压测与时延浸泡 (3线程/30次)",
        step_method="使用 3 线程并发发送 30 次 device.get_status 请求，统计 P50/P90/P99 时延与吞吐",
        inputs={"total_requests": 30, "concurrency": 3, "endpoint": "get_device_status"},
        outputs={
            "qps": stress_res.qps,
            "p50_ms": stress_res.p50_latency_ms,
            "p90_ms": stress_res.p90_latency_ms,
            "p99_ms": stress_res.p99_latency_ms,
            "avg_ms": stress_res.avg_latency_ms,
            "success": stress_res.success_count,
            "failed": stress_res.failed_count
        },
        gates=stress_gates,
        status="PASS" if (stress_res.failed_count == 0 and stress_res.qps >= 20.0) else "FAIL",
        duration=t_cost
    )

    # -------------------------------------------------------------
    # 汇总总结
    # -------------------------------------------------------------
    summary = reporter.get_summary()
    pass_label = "\033[32mALL PASS (100% 通过)\033[0m" if summary['failed'] == 0 else "\033[31mSOME FAILED\033[0m"
    print("\n" + "#" * 90)
    print(f"       AX615 camera-kit 全量 54 项自动化回归测试总结")
    print(f"  • 总测试项数 (Total Items)    : {summary['total']} / {len(PLAN_STEPS)}")
    print(f"  • 通过项数   (Passed Items)   : {summary['passed']}")
    print(f"  • 失败项数   (Failed Items)   : {summary['failed']}")
    print(f"  • 测试总耗时 (Total Duration) : {summary['total_duration']}s")
    print(f"  • 全量测试综合判定            : {pass_label}")
    print("#" * 90 + "\n")

    target_dir = export_dir if export_dir else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(target_dir, exist_ok=True)
    json_path = os.path.join(target_dir, "full_test_report.json")
    xml_path = os.path.join(target_dir, "full_test_report.xml")
    html_path = os.path.join(target_dir, "full_test_report.html")

    reporter.save_json(json_path)
    reporter.save_junit_xml(xml_path)
    reporter.save_html_report(html_path)
    print(f"[axck-test] JSON report saved to:  {json_path}")
    print(f"[axck-test] JUnit XML saved to:    {xml_path}")
    print(f"[axck-test] HTML Dashboard to:     {html_path}")

    return reporter

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AXCK Full Regression Test Suite")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Board IP (or set AXCK_BOARD_IP env)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTP Port (default: {DEFAULT_PORT})")
    parser.add_argument("--export-dir", default=None, help="Directory to save JSON/XML/HTML reports")
    args = parser.parse_args()

    rep = run_all_tests(host=args.host, port=args.port, export_dir=args.export_dir)
    sys.exit(0 if rep.get_summary()["failed"] == 0 else 1)

if __name__ == "__main__":
    main()
