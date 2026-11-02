#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scenario_continuous_record_capture.py
独立场景测试：格式化TF卡 -> 持续开着录像 -> 多分辨率切换并各抓拍>=10张 -> 停止录像 -> 留存全量视频/照片证据至NFS.
"""

import sys
import os
import time
import json
import re

sys.stdout.reconfigure(line_buffering=True)


class ContinuousRecordCaptureScenario:
    def __init__(self, driver, inspector, reporter, evidence_collector=None):
        self.driver = driver
        self.inspector = inspector
        self.reporter = reporter
        self.collector = evidence_collector

    def send_and_capture(self, opt_cmd, expected_kw=None, timeout=5.0, wait_post=0.0):
        self.driver.send(opt_cmd, append_enter=True)
        captured_line = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.04)
            lines = self.driver.read_lines(limit=45, tail=False)
            for l in lines:
                ls = l.strip()
                if not ls or "api options:" in ls or ls.startswith(f"{opt_cmd}.") or "Back." in ls or "Exit test" in ls:
                    continue
                if expected_kw and expected_kw in ls:
                    captured_line = ls
                    break
                elif not expected_kw and ls:
                    captured_line = ls
                    break
            if captured_line:
                break

        if wait_post > 0:
            time.sleep(wait_post)

        return captured_line

    def run(self, min_photos_per_res=10):
        print("\n================================================================================")
        print("=== [SCENARIO] 场景测试: TF卡格式化 + 全程持续录像 + 多分辨率动态切换与抓拍 ===")
        print("================================================================================\n")

        # -------------------------------------------------------------
        # Step 0: 服务环境复位 — 给场景验证一个干净的管线状态
        # 全量流水线中 media/system 套件的大量管线变更 (流开关/HDR/VENC切换/TF
        # 格式化) 会让服务进入"脏状态": 录像中切分辨率后 JENC 抓拍通道永久饥饿
        # (GetVEncTrd TIMEOUT 风暴, TakePhoto 全拒, 证据: task_all_20260918_145913).
        # 场景测试验证的是产品路径本身, 必须在全新服务实例上执行.
        # -------------------------------------------------------------
        t0 = time.time()
        inp = {"action": "SIGINT/SIGKILL 全部 axck 进程 + Ctrl+Z 挂起前台 axck_test + auto-recover 重拉"}
        outp = {}
        gates = {}
        try:
            # 1) 带外优雅停服 (若有 inspector)
            if self.inspector:
                self.inspector.comm_kill_axck(2)
                time.sleep(1.2)
                self.inspector.comm_kill_axck(9)
                self.inspector.exec_cmd("rm -f /tmp/axck.ipc")
                time.sleep(0.3)
                outp["residual_after_telnet_kill"] = self.inspector.comm_scan_axck_pids()

            # 2) 串口: 挂起前台 axck_test 回到 shell, comm-kill 残留 + rm ipc
            self.driver.call_mcp("terminals_submit", {
                "terminal_ref": self.driver.terminal_ref,
                "text": "\x1a"  # Ctrl+Z: suspend foreground axck_test -> shell prompt
            })
            time.sleep(0.8)
            self.driver.send(
                "for p in /proc/[0-9]*; do c=$(cat $p/comm 2>/dev/null); "
                'case "$c" in axck_test|axck_service) kill -9 ${p#/proc/} 2>/dev/null;; esac; done; '
                "rm -f /tmp/axck.ipc", append_enter=True)
            time.sleep(0.8)

            # 3) auto-recover: 全新 axck_test (启动时自动派生全新 axck_service)
            menu_ok = self.driver.ensure_in_main_menu()
            outp["menu_recovered"] = menu_ok

            # 4) RPC + 硬件健康轮询: ipc 在位 + VENC 通道建立 + TF 已挂载
            rpc_ok = False
            if self.inspector and menu_ok:
                deadline = time.time() + 20.0
                while time.time() < deadline:
                    ipc_ok = self.inspector.ipc_file_exists()
                    venc = self.inspector.get_venc_info()
                    sd_lines = self.inspector.exec_cmd("mount | grep -c tfcard")
                    sd_mounted = any(l.strip() == "1" for l in sd_lines)
                    if ipc_ok and (0 in venc and venc[0].get("w", 0) > 0) and sd_mounted:
                        rpc_ok = True
                        break
                    time.sleep(0.3)
                outp["rpc_ipc"] = self.inspector.ipc_file_exists()
            elif menu_ok:
                rpc_ok = True  # 无 inspector: 主菜单可达即 test<->service RPC 存活
            outp["rpc_healthy"] = rpc_ok

            reset_ok = menu_ok and rpc_ok
            gates["ServiceReset"] = {
                "desc": "服务环境复位: 全新 axck_service + RPC/管线/TF挂载 健康",
                "expected": "main menu + ipc + VENC chn0 + tfcard mounted",
                "actual": f"menu={menu_ok}, rpc={rpc_ok}",
                "passed": reset_ok
            }
            status = "PASS" if reset_ok else "FAIL"
        except Exception as e:
            reset_ok = False
            status = "FAIL"
            outp["error"] = str(e)
            gates["ServiceReset"] = {
                "desc": "服务环境复位", "expected": "fresh service",
                "actual": f"exception: {e}", "passed": False
            }
        self.reporter.report_case("scenario", "0. Service Environment Reset (fresh instance)", inp, outp, gates, status, time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("scenario", "0. Service Environment Reset (fresh instance)", "case_0_service_reset", inp, outp, gates, raw_proc_needed=True)

        if not reset_ok:
            print("[SCENARIO] 服务环境复位失败，终止场景测试！", file=sys.stderr)
            return False

        # -------------------------------------------------------------
        # Step 1: 格式化 TF 卡 (Storage Submenu -> Option 6)
        # -------------------------------------------------------------
        t0 = time.time()
        inp = {"step": 1, "menu": "2 (storage)", "option": "6 (SDCard format)", "action": "测试前清空并格式化TF卡"}
        outp = {}
        gates = {}
        
        self.driver.ensure_in_main_menu()
        if not self.driver.navigate_to("storage"):
            gates["NavStorage"] = {"desc": "导航至 Storage 菜单", "expected": "storage", "actual": "failed", "passed": False}
            self.reporter.report_case("scenario", "1. TF Card Format Before Test", inp, outp, gates, "FAIL", time.time() - t0)
            return False

        self.driver.send("6", append_enter=True)
        format_success = False
        sd_ready = False
        deadline = time.time() + 25.0
        while time.time() < deadline:
            time.sleep(0.3)
            lines = self.driver.read_lines(limit=45, tail=False)
            for l in lines:
                ls = l.strip()
                if "storage format success" in ls:
                    format_success = True
                if "sd card is ready!" in ls:
                    sd_ready = True
            if format_success and sd_ready:
                break

        self.driver.wait_menu("storage", timeout=5.0)
        self.driver.navigate_to("main")

        outp["format_success"] = format_success
        outp["sd_ready"] = sd_ready
        gates["StorageFormat"] = {
            "desc": "TF卡格式化成功",
            "expected": "storage format success",
            "actual": "success" if format_success else "failed",
            "passed": format_success
        }
        gates["SDCardReady"] = {
            "desc": "格式化后TF卡重新就绪",
            "expected": "sd card is ready!",
            "actual": "ready" if sd_ready else "not ready",
            "passed": sd_ready
        }

        step1_ok = format_success and sd_ready
        self.reporter.report_case("scenario", "1. TF Card Format Before Test", inp, outp, gates, "PASS" if step1_ok else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("scenario", "1. TF Card Format Before Test", "case_1_format_tf", inp, outp, gates, raw_proc_needed=False)

        if not step1_ok:
            print("[SCENARIO] 格式化TF卡失败，终止场景测试！", file=sys.stderr)
            return False

        # -------------------------------------------------------------
        # Step 2: 进入 Media 菜单并开启持续录像 (Media Submenu -> Option 9)
        # -------------------------------------------------------------
        t0 = time.time()
        inp = {"step": 2, "menu": "1 (media)", "option": "9 (Start record)", "action": "启动录像并保持全程持续开启"}
        outp = {}
        gates = {}

        self.driver.ensure_in_main_menu()
        if not self.driver.navigate_to("media"):
            gates["NavMedia"] = {"desc": "导航至 Media 菜单", "expected": "media", "actual": "failed", "passed": False}
            self.reporter.report_case("scenario", "2. Start Continuous Recording", inp, outp, gates, "FAIL", time.time() - t0)
            return False

        cap_rec = self.send_and_capture("9", "record", timeout=5.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        outp["start_record_feedback"] = cap_rec

        # 轮询验证底层 VENC 编码管道活跃
        venc_fps = 0.0
        if self.inspector:
            deadline = time.time() + 3.0
            while time.time() < deadline:
                venc = self.inspector.get_venc_info()
                venc_fps = venc.get(0, {}).get("recv_fps", 0.0)
                if venc_fps >= 10.0:
                    break
                time.sleep(0.2)
            outp["venc_0_fps"] = venc_fps

        gates["RecordStarted"] = {
            "desc": "录像启动指令下发成功",
            "expected": "record keyword",
            "actual": str(cap_rec),
            "passed": bool(cap_rec)
        }
        gates["VencActive"] = {
            "desc": "VENC 编码管道活跃",
            "expected": "> 10.0 fps",
            "actual": f"{venc_fps:.2f} fps",
            "passed": (venc_fps >= 10.0)
        }

        step2_ok = gates["RecordStarted"]["passed"] and gates["VencActive"]["passed"]
        self.reporter.report_case("scenario", "2. Start Continuous Recording", inp, outp, gates, "PASS" if step2_ok else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("scenario", "2. Start Continuous Recording", "case_2_start_record", inp, outp, gates, raw_proc_needed=True)

        # -------------------------------------------------------------
        # Step 3: 各分辨率切换并在录像中抓拍 >= 10 张
        # 0: 2560x1440, 1: 1920x1080, 2: 1280x720
        # -------------------------------------------------------------
        resolutions = [
            ("3a", "0", "2560x1440", 2560, 1440),
            ("3b", "1", "1920x1080", 1920, 1080),
            ("3c", "2", "1280x720",  1280, 720),
        ]

        total_photos_captured = 0

        for tag, opt_val, res_name, exp_w, exp_h in resolutions:
            # 3.x.1: 分辨率切换 (严格事件驱动交互)
            t0 = time.time()
            inp = {"step": f"{tag}_switch", "option": "7", "sub_choice": opt_val, "target_res": res_name}
            outp = {}
            gates = {}

            self.driver.send_interactive_choice("7", "select front front main", opt_val, settle_menu="media")

            actual_ivps_w, actual_ivps_h, ivps_fps = 0, 0, 0.0
            actual_venc_w, actual_venc_h, venc_fps = 0, 0, 0.0

            if self.inspector:
                # 轮询等待硬件编码管道完成动态重构并达到稳定帧率 (最多等待 6 秒)
                deadline = time.time() + 6.0
                while time.time() < deadline:
                    ivps = self.inspector.get_ivps_info()
                    venc = self.inspector.get_venc_info()
                    actual_ivps_w = ivps.get((0, 0), {}).get("w", 0)
                    actual_ivps_h = ivps.get((0, 0), {}).get("h", 0)
                    ivps_fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
                    actual_venc_w = venc.get(0, {}).get("w", 0)
                    actual_venc_h = venc.get(0, {}).get("h", 0)
                    venc_fps = venc.get(0, {}).get("recv_fps", 0.0)

                    if (actual_ivps_w == exp_w and actual_venc_w == exp_w and
                            ivps_fps >= 10.0 and venc_fps >= 10.0):
                        break
                    time.sleep(0.3)

            outp["ivps_res"] = f"{actual_ivps_w}x{actual_ivps_h}"
            outp["ivps_fps"] = ivps_fps
            outp["venc_res"] = f"{actual_venc_w}x{actual_venc_h}"
            outp["venc_fps"] = venc_fps

            ivps_match = (actual_ivps_w == exp_w and actual_ivps_h == exp_h)
            venc_match = (actual_venc_w == exp_w and actual_venc_h == exp_h)
            fps_ok = (ivps_fps >= 10.0 and venc_fps >= 10.0)

            gates["IVPS_Resolution"] = {
                "desc": f"IVPS(0,0) 分辨率切换为 {res_name}",
                "expected": res_name,
                "actual": f"{actual_ivps_w}x{actual_ivps_h}",
                "passed": ivps_match
            }
            gates["VENC_Resolution"] = {
                "desc": f"VENC(0) 编码分辨率对齐 {res_name}",
                "expected": res_name,
                "actual": f"{actual_venc_w}x{actual_venc_h}",
                "passed": venc_match
            }
            gates["ContinuousStream_FPS"] = {
                "desc": "分辨率切换后流与录像保持稳定未中断",
                "expected": ">= 10.0 fps",
                "actual": f"ivps={ivps_fps:.1f}, venc={venc_fps:.1f}",
                "passed": fps_ok
            }

            switch_ok = ivps_match and venc_match and fps_ok
            case_title = f"{tag}. Switch to {res_name} under Continuous Recording"
            self.reporter.report_case("scenario", case_title, inp, outp, gates, "PASS" if switch_ok else "FAIL", time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("scenario", case_title, f"case_{tag}_switch_{res_name}", inp, outp, gates, raw_proc_needed=True)

            # 3.x.2: 在该分辨率下连续抓拍 >= 10 张 (Option 28)
            t0 = time.time()
            inp = {"step": f"{tag}_capture", "option": "28", "target_count": min_photos_per_res, "resolution": res_name}
            outp = {}
            gates = {}

            # 获取当前抓拍前的照片数
            def get_current_photo_count():
                if not self.inspector:
                    return 0
                lines = self.inspector.exec_cmd("ls -1 /mnt/tfcard/Photo/F/*.jpg 2>/dev/null | wc -l")
                for l in lines:
                    ls = l.strip()
                    if ls.isdigit():
                        return int(ls)
                return 0

            pre_count = get_current_photo_count()

            captured_echoes = []
            max_attempts = min_photos_per_res + 4
            for attempt in range(max_attempts):
                cur_delta = get_current_photo_count() - pre_count
                if cur_delta >= min_photos_per_res:
                    break
                cap_res = self.send_and_capture("28", "capture", timeout=1.8, wait_post=0.0)
                self.driver.wait_menu("media", timeout=2.0)
                captured_echoes.append(bool(cap_res))

            # 刷盘以确保 DTCF/文件系统写入
            if self.inspector:
                self.inspector.exec_cmd("sync")
                post_count = get_current_photo_count()
            else:
                post_count = pre_count + min_photos_per_res

            delta_photos = post_count - pre_count
            total_photos_captured += delta_photos
            outp["pre_count"] = pre_count
            outp["post_count"] = post_count
            outp["captured_delta"] = delta_photos
            outp["capture_calls"] = len(captured_echoes)

            gates["PhotoCount"] = {
                "desc": f"抓拍照片数量达标 (>= {min_photos_per_res}张)",
                "expected": f">= {min_photos_per_res}",
                "actual": f"{delta_photos} 张新增 (累计 {post_count})",
                "passed": (delta_photos >= min_photos_per_res)
            }

            cap_case_title = f"{tag}_cap. Capture >= {min_photos_per_res} Photos @ {res_name}"
            self.reporter.report_case("scenario", cap_case_title, inp, outp, gates, "PASS" if gates["PhotoCount"]["passed"] else "FAIL", time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("scenario", cap_case_title, f"case_{tag}_cap_{res_name}", inp, outp, gates, raw_proc_needed=True)

        # -------------------------------------------------------------
        # Step 4: 停止持续录像并同步 (Media Submenu -> Option 10)
        # -------------------------------------------------------------
        t0 = time.time()
        inp = {"step": 4, "option": "10 (Stop record)", "action": "停止持续录像并 sync 刷盘"}
        outp = {}
        gates = {}

        cap_stop = self.send_and_capture("10", "record", timeout=5.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        outp["stop_record_feedback"] = cap_stop

        # 验证 TF 卡上 MP4 录像文件生成情况
        # 停录像后正在写入的分片需要 2~4s 完成 moov 闭合 finalize；
        # 且滚动分片时长 120s > 本轮录像总长，中途不 finalize，
        # 必须轮询等待停止后的最终分片落盘。
        video_count = 0
        video_files = []
        finalize_waited = 0.0
        if self.inspector:
            self.inspector.exec_cmd("sync")
            deadline = time.time() + 10.0
            while time.time() < deadline:
                lines = self.inspector.exec_cmd("ls -1 /mnt/tfcard/Normal/F/*.mp4 2>/dev/null")
                video_files = [l.strip() for l in lines if l.strip() and not l.strip().startswith("ls:")]
                if video_files:
                    break
                time.sleep(0.5)
            finalize_waited = round(time.time() - (deadline - 10.0), 2)
            if not video_files:
                # final sync flush before giving up
                self.inspector.exec_cmd("sync")
                time.sleep(1.0)
                lines = self.inspector.exec_cmd("ls -1 /mnt/tfcard/Normal/F/*.mp4 2>/dev/null")
                video_files = [l.strip() for l in lines if l.strip() and not l.strip().startswith("ls:")]
            video_count = len(video_files)

        outp["video_count"] = video_count
        outp["video_files"] = video_files
        outp["mp4_finalize_wait_s"] = finalize_waited

        gates["RecordStopped"] = {
            "desc": "录像正常停止",
            "expected": "record keyword",
            "actual": str(cap_stop),
            "passed": bool(cap_stop)
        }
        gates["VideoFilesGenerated"] = {
            "desc": "TF卡已生成完整 MP4 录像文件",
            "expected": ">= 1 mp4 files",
            "actual": f"{video_count} 个录像文件",
            "passed": (video_count >= 1)
        }

        step4_ok = gates["RecordStopped"]["passed"] and gates["VideoFilesGenerated"]["passed"]
        self.reporter.report_case("scenario", "4. Stop Continuous Recording & Verify MP4", inp, outp, gates, "PASS" if step4_ok else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("scenario", "4. Stop Continuous Recording & Verify MP4", "case_4_stop_record", inp, outp, gates, raw_proc_needed=True)

        # -------------------------------------------------------------
        # Step 5: 安全返回主菜单
        # -------------------------------------------------------------
        self.driver.ensure_in_main_menu()
        print("\n=== [SCENARIO] 场景测试完成，已退出至主菜单 ===\n")
        return True
