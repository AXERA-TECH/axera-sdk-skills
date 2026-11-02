#!/usr/bin/env python3
"""
Dual-Camera AOV (All-Online-Video) Long-Run Stability & Mux Trigger Test

Workflow:
1. Pre-check: Device status (Dual-Cam online), baseline AOV file count
2. Trigger AOV: Send HTTP 'start' to axck_service
3. Soak Monitor: 60-90s monitoring window, tracking kernel PM suspend/exit events via Telnet
4. Stop AOV: Send HTTP 'stop' with retry to flush and close MP4 containers
5. Post-validation: Check /mnt/tfcard/AOV/F and /mnt/tfcard/AOV/R for AOV*.mp4 files
6. Self-healing check: Trigger dual-cam photo capture to confirm pipeline recovery
"""

import sys
import os
import time
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from core.domain_apis import AxckClient
from telnet_inspector import TelnetInspector

def run_aov_long_test(host=None, port=None, soak_seconds=60):
    target_host = host or os.environ.get("AXCK_BOARD_IP", "127.0.0.1")
    target_port = port or int(os.environ.get("AXCK_BOARD_PORT", "80"))
    print("=" * 70)
    print(f"🚀 启动双摄 AOV 长周期稳定性与落盘触发压测 (目标: {target_host}:{target_port}, 持续: {soak_seconds}s)")
    print("=" * 70)

    client = AxckClient(target_host, target_port)
    inspector = TelnetInspector(target_host, 23, 'root', '12345')
    inspector.connect()

    # Step 1: Pre-check
    print("\n[Step 1] 前置环境检查与基线捕获...")
    try:
        dev_status = client.device.get_status()
        print(f"  • 设备状态: code={dev_status.code}, front={dev_status.data.get('status_all', {}).get('front_status')}, rear={dev_status.data.get('status_all', {}).get('rear_status')}")
    except Exception as e:
        print(f"  ❌ 无法获取设备状态: {e}")
        return False

    out = inspector.exec_cmd("ls -1 /mnt/tfcard/AOV/F /mnt/tfcard/AOV/R 2>/dev/null")
    baseline_str = "\n".join(out) if isinstance(out, list) else str(out)
    print(f"  • 当前 AOV 目录文件基线:\n{baseline_str.strip() or '  (空)'}")

    # 清空 dmesg 缓冲区便于统计
    inspector.exec_cmd("dmesg -c > /dev/null")
    print("  • 已清空内核 dmesg 环形缓冲区，准备捕获休眠事件")

    # Step 2: Trigger AOV Start
    print("\n[Step 2] 通过 HTTP 下发 AOV 启动指令...")
    start_resp = client.aov.control('start')
    print(f"  • AOV Start 响应: code={start_resp.code}, msg={start_resp.msg}, data={start_resp.data}")
    if start_resp.code != 0:
        print("  ❌ AOV 启动失败！")
        return False

    # Step 3: Soak monitoring
    print(f"\n[Step 3] 正在进行 AOV 长周期浸泡运行 ({soak_seconds} 秒)...")
    start_time = time.time()
    last_print = start_time
    suspend_count = 0
    resume_count = 0

    while time.time() - start_time < soak_seconds:
        elapsed = int(time.time() - start_time)
        time.sleep(5)
        
        # 嗅探内核休眠唤醒事件
        try:
            dmesg_part = inspector.exec_cmd("dmesg -c")
            s_entries = len(re.findall(r"PM: suspend entry", dmesg_part))
            r_entries = len(re.findall(r"PM: suspend exit", dmesg_part))
            suspend_count += s_entries
            resume_count += r_entries
            
            cur_time = time.time()
            if cur_time - last_print >= 10:
                print(f"  ⏱️ [{elapsed:02d}s/{soak_seconds}s] 累计捕获休眠周期: suspend={suspend_count}, resume={resume_count}")
                last_print = cur_time
        except Exception as e:
            # 休眠期间 Telnet 可能会出现微小抖动，属正常现象
            pass

    print(f"\n  ✅ 浸泡完成！总计捕获休眠次数: {suspend_count}, 唤醒次数: {resume_count}")

    # Step 4: Stop AOV
    print("\n[Step 4] 通过 HTTP 下发 AOV 停止指令 (带重试以避开休眠窗口)...")
    stop_ok = False
    for attempt in range(1, 10):
        try:
            stop_resp = client.aov.control('stop')
            if stop_resp.code == 0:
                print(f"  • [尝试 {attempt}] AOV Stop 成功响应: {stop_resp.data}")
                stop_ok = True
                break
            else:
                print(f"  • [尝试 {attempt}] 返回非0: {stop_resp.msg}")
        except Exception as e:
            print(f"  • [尝试 {attempt}] 网络重试等待 (板端可能正处于800ms休眠态): {e}")
        time.sleep(1.0)

    if not stop_ok:
        print("  ⚠️ HTTP Stop 重试超时，尝试带外恢复...")
        return False

    # 等待录像容器 flush 落盘完成
    print("  • 等待 3 秒使板端完成 MP4 尾部索引 (moov box) 写入...")
    time.sleep(3)

    # Step 5: Post-validation
    print("\n[Step 5] 校验 /mnt/tfcard/AOV 录像落盘情况...")
    out_f = inspector.exec_cmd("ls -la /mnt/tfcard/AOV/F/ 2>/dev/null")
    out_r = inspector.exec_cmd("ls -la /mnt/tfcard/AOV/R/ 2>/dev/null")
    str_f = "\n".join(out_f) if isinstance(out_f, list) else str(out_f)
    str_r = "\n".join(out_r) if isinstance(out_r, list) else str(out_r)

    print(f"  • 前摄 AOV/F 目录列表:\n{str_f}")
    print(f"  • 后摄 AOV/R 目录列表:\n{str_r}")

    # 提取 mp4 文件
    mp4_f = [line for line in str_f.splitlines() if '.mp4' in line]
    mp4_r = [line for line in str_r.splitlines() if '.mp4' in line]

    f_ok = len(mp4_f) > 0
    r_ok = len(mp4_r) > 0

    print(f"\n  📊 落盘判定:")
    print(f"    - 前摄 AOV 录像: {'✅ 成功生成 (' + mp4_f[-1].split()[-1] + ')' if f_ok else '❌ 未生成'}")
    print(f"    - 后摄 AOV 录像: {'✅ 成功生成 (' + mp4_r[-1].split()[-1] + ')' if r_ok else '❌ 未生成'}")

    # Step 6: Pipeline self-healing verification
    print("\n[Step 6] 校验媒体管线恢复状态 (双摄抓拍自愈探测)...")
    photo_resp = client.media.take_photo()
    print(f"  • 拍照响应: code={photo_resp.code}, msg={photo_resp.msg}")
    time.sleep(2)
    latest_f = inspector.get_latest_file('/mnt/tfcard/Photo/F')
    latest_r = inspector.get_latest_file('/mnt/tfcard/Photo/R')
    magic_f = inspector.check_file_magic(latest_f, "ffd8") if latest_f else False
    magic_r = inspector.check_file_magic(latest_r, "ffd8") if latest_r else False
    print(f"  • 前摄最新照片: {latest_f} (Magic 校验: {'PASS' if magic_f else 'FAIL'})")
    print(f"  • 后摄最新照片: {latest_r} (Magic 校验: {'PASS' if magic_r else 'FAIL'})")

    print("\n" + "=" * 70)
    if f_ok and r_ok and magic_f and magic_r:
        print("🎉 恭喜！双摄 AOV 稳定性压测与录像落盘验证全部通过！")
    else:
        print("⚠️ 测试完成，存在部分项未达预期，请查看上方输出。")
    print("=" * 70)

    inspector.close()
    return f_ok and r_ok

if __name__ == '__main__':
    soak = 60
    target_host = None
    if len(sys.argv) > 1:
        soak = int(sys.argv[1])
    if len(sys.argv) > 2:
        target_host = sys.argv[2]
    run_aov_long_test(host=target_host, soak_seconds=soak)
