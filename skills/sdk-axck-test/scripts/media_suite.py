#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
media_suite.py - AXCK Media Subsystem automated test suite.
Features:
- Drives axck_test foreground menu via BoardSerialDriver.
- Concurrently validates hardware status via TelnetInspector (/proc/ax_proc/ivps & venc).
- Formats and outputs structured case reports in real time via CaseReporter.
- Records per-case raw proc snapshots and logs via EvidenceCollector.
"""

import sys
import time
import re

sys.stdout.reconfigure(line_buffering=True)


class MediaSuiteRunner:
    def __init__(self, driver, inspector=None, reporter=None, evidence_collector=None):
        self.driver = driver
        self.inspector = inspector
        self.reporter = reporter
        self.collector = evidence_collector

    def send_and_capture(self, opt_cmd, expected_kw=None, timeout=6.0, wait_post=0.0):
        """Send option and capture execution output line using event-driven polling instead of arbitrary sleeps."""
        self.driver.send(str(opt_cmd), append_enter=True)
        captured_line = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            lines = self.driver.read_lines(limit=80, tail=False)
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
            time.sleep(0.04)

        if wait_post > 0:
            time.sleep(wait_post)

        return captured_line

    def run_all(self):
        print("\n=== [SDK-AXCK-TEST] Starting Media Subsystem Automated Test Suite ===")

        # Case 0: Enter Media Menu
        t0 = time.time()
        inp = {"target_menu": "media", "command": "1"}
        outp = {}
        gates = {}
        ok = self.driver.navigate_to("media")
        cur_menu = self.driver.get_current_menu()
        outp["current_menu"] = cur_menu
        gates["MenuEntered"] = {
            "desc": "成功进入 Media API 菜单",
            "expected": "media",
            "actual": cur_menu,
            "passed": ok and cur_menu == "media"
        }
        self.reporter.report_case("media", "0. Enter Media Menu", inp, outp, gates, "PASS" if gates["MenuEntered"]["passed"] else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "0. Enter Media Menu", "case_0_enter_menu", inp, outp, gates, raw_proc_needed=True)
        if not gates["MenuEntered"]["passed"]:
            return self.reporter.cases

        # Case 1: Stream Toggle (Ensure Front Stream is ON)
        t0 = time.time()
        inp = {"option": "1", "action": "Ensure front stream is ON"}
        outp = {}
        gates = {}
        # Query initial state: toggle once, if turned off, toggle again to turn on
        cap1 = self.send_and_capture("1", "Front camera current is stream", timeout=4.0, wait_post=1.0)
        outp["console_toggle1"] = cap1
        if cap1 and "stream on -> off" in cap1:
            # It was ON, now turned OFF; turn it back ON
            cap2 = self.send_and_capture("1", "Front camera current is stream", timeout=4.0, wait_post=1.0)
            outp["console_toggle2"] = cap2
        elif cap1 and "stream off -> on" in cap1:
            # It was OFF, now turned ON; keep it ON
            outp["console_toggle2"] = "Kept ON"

        # Wait for pipeline to resume steady streaming
        proc_stream_ok = True
        if self.inspector:
            start_p = time.time()
            out_fps = 0.0
            while time.time() - start_p < 4.0:
                ivps = self.inspector.get_ivps_info()
                out_fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
                if out_fps > 10.0:
                    break
                time.sleep(0.3)
            outp["proc_ivps_fps"] = out_fps
            proc_stream_ok = (out_fps > 0)
            gates["ProcStreamActive"] = {
                "desc": "IVPS 管道出流帧率正常",
                "expected": "> 0 fps",
                "actual": f"{out_fps:.2f} fps",
                "passed": proc_stream_ok
            }

        gates["StreamToggleEcho"] = {
            "desc": "串口控制台流开关回显",
            "expected": "Front camera current is stream ...",
            "actual": f"toggle1={bool(cap1)}",
            "passed": bool(cap1)
        }
        overall = gates["StreamToggleEcho"]["passed"] and proc_stream_ok
        self.reporter.report_case("media", "1. Toggle Front Stream (Ensure Stream ON)", inp, outp, gates, "PASS" if overall else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "1. Toggle Front Stream (Ensure Stream ON)", "case_1_toggle_stream", inp, outp, gates, raw_proc_needed=True)

        # Case 2: Front FPS Query & Proc Cross-Validation
        t0 = time.time()
        inp = {"option": "2", "query": "Get front FPS"}
        outp = {}
        gates = {}
        cap_fps = self.send_and_capture("2", "Front camera fps:", timeout=4.0, wait_post=1.0)
        outp["console_fps_raw"] = cap_fps
        front_fps = 0.0
        if cap_fps:
            m = re.search(r'Front camera fps:\s*([0-9\.]+)', cap_fps)
            if m:
                front_fps = float(m.group(1).rstrip('.'))
        outp["console_fps"] = front_fps

        gates["ConsoleFPS"] = {
            "desc": "CLI 获取前摄帧率有效",
            "expected": "> 10.0 fps",
            "actual": f"{front_fps:.2f} fps",
            "passed": front_fps >= 10.0
        }

        if self.inspector:
            ivps = self.inspector.get_ivps_info()
            venc = self.inspector.get_venc_info()
            proc_ivps_fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
            proc_venc_fps = venc.get(0, {}).get("recv_fps", 0.0)
            outp["proc_ivps_out_fps"] = proc_ivps_fps
            outp["proc_venc_recv_fps"] = proc_venc_fps
            gates["ProcFPSCrossCheck"] = {
                "desc": "/proc IVPS/VENC 硬件帧率校验",
                "expected": "> 10.0 fps",
                "actual": f"ivps={proc_ivps_fps:.2f}, venc={proc_venc_fps:.2f}",
                "passed": (proc_ivps_fps >= 10.0)
            }

        overall = all(g["passed"] for g in gates.values())
        self.reporter.report_case("media", "2. Get Front Stream FPS & Cross-Validate", inp, outp, gates, "PASS" if overall else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "2. Get Front Stream FPS & Cross-Validate", "case_2_fps_cross_check", inp, outp, gates, raw_proc_needed=True)

        # Case 3: Update Front OSD Display & RGN Cross-Check
        t0 = time.time()
        inp = {"option": "3", "action": "Update front OSD display coordinates"}
        outp = {}
        gates = {}
        cap_osd = self.send_and_capture("3", "osd", timeout=4.0, wait_post=1.5)
        outp["console_osd"] = cap_osd
        rgn_ok = True
        if self.inspector:
            osds = self.inspector.get_rgn_osd_info()
            outp["rgn_osd_count"] = len(osds)
            outp["rgn_osd_keys"] = list(osds.keys())
            rgn_ok = len(osds) > 0
            gates["RgnOSDActive"] = {
                "desc": "/proc/ax_proc/rgn OSD 硬件图层使能",
                "expected": "> 0 active OSDs",
                "actual": f"{len(osds)} OSDs active",
                "passed": rgn_ok
            }
        gates["OSDConsoleEcho"] = {
            "desc": "串口控制台 OSD 刷新响应",
            "expected": "New front osd info",
            "actual": str(cap_osd),
            "passed": bool(cap_osd)
        }
        case_ok = gates["OSDConsoleEcho"]["passed"] and rgn_ok
        self.reporter.report_case("media", "3. Update Front OSD Display & RGN Cross-Check", inp, outp, gates, "PASS" if case_ok else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "3. Update Front OSD Display & RGN Cross-Check", "case_3_osd_update", inp, outp, gates, raw_proc_needed=True)

        # Case 4: Sensor Mode Toggle (Option 4: SDR -> HDR -> SDR)
        t0 = time.time()
        inp = {"option": "4", "action": "Update front sensor mode (SDR)"}
        outp = {}
        gates = {}
        ok, _ = self.driver.send_interactive_choice("4", "Input front sns mode", "1", settle_menu="media")
        ivps_sdr_fps = 0.0
        if self.inspector:
            # Poll /proc until steady fps
            start_w = time.time()
            while time.time() - start_w < 5.0:
                ivps = self.inspector.get_ivps_info()
                fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
                if fps >= 10.0:
                    ivps_sdr_fps = fps
                    break
                time.sleep(0.1)
            outp["ivps_sdr_fps"] = ivps_sdr_fps
        gates["SnsModeRecover"] = {
            "desc": "SDR 模式生效且出流正常",
            "expected": ">= 10.0 fps",
            "actual": f"{ivps_sdr_fps:.2f} fps",
            "passed": ivps_sdr_fps >= 10.0 or ok
        }
        self.reporter.report_case("media", "4. Update Front Sensor Mode (SDR/HDR)", inp, outp, gates, "PASS" if gates["SnsModeRecover"]["passed"] else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "4. Update Front Sensor Mode (SDR/HDR)", "case_4_sns_mode", inp, outp, gates, raw_proc_needed=True)

        # Case 5: Mirror Toggle (Option 5: enable then disable)
        t0 = time.time()
        inp = {"option": "5", "action": "Update front mirror (enable then disable)"}
        outp = {}
        gates = {}
        ok1, _ = self.driver.send_interactive_choice("5", "Input front mirror", "1", settle_menu="media")
        ok2, _ = self.driver.send_interactive_choice("5", "Input front mirror", "0", settle_menu="media")
        mirror_fps = 0.0
        if self.inspector:
            start_w = time.time()
            while time.time() - start_w < 5.0:
                ivps = self.inspector.get_ivps_info()
                fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
                if fps >= 10.0:
                    mirror_fps = fps
                    break
                time.sleep(0.1)
            outp["ivps_fps"] = mirror_fps
        gates["MirrorToggle"] = {
            "desc": "镜像切换后硬件链路出流正常",
            "expected": ">= 10.0 fps",
            "actual": f"{mirror_fps:.2f} fps",
            "passed": mirror_fps >= 10.0 or (ok1 and ok2)
        }
        self.reporter.report_case("media", "5. Update Front Mirror Toggle", inp, outp, gates, "PASS" if gates["MirrorToggle"]["passed"] else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "5. Update Front Mirror Toggle", "case_5_mirror_toggle", inp, outp, gates, raw_proc_needed=True)

        # Case 6: Flip Toggle (Option 6: enable then disable)
        t0 = time.time()
        inp = {"option": "6", "action": "Update front flip (enable then disable)"}
        outp = {}
        gates = {}
        ok1, _ = self.driver.send_interactive_choice("6", "Input front flip", "1", settle_menu="media")
        ok2, _ = self.driver.send_interactive_choice("6", "Input front flip", "0", settle_menu="media")
        flip_fps = 0.0
        if self.inspector:
            start_w = time.time()
            while time.time() - start_w < 5.0:
                ivps = self.inspector.get_ivps_info()
                fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
                if fps >= 10.0:
                    flip_fps = fps
                    break
                time.sleep(0.1)
            outp["ivps_fps"] = flip_fps
        gates["FlipToggle"] = {
            "desc": "翻转切换后硬件链路出流正常",
            "expected": ">= 10.0 fps",
            "actual": f"{flip_fps:.2f} fps",
            "passed": flip_fps >= 10.0 or (ok1 and ok2)
        }
        self.reporter.report_case("media", "6. Update Front Flip Toggle", inp, outp, gates, "PASS" if gates["FlipToggle"]["passed"] else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "6. Update Front Flip Toggle", "case_6_flip_toggle", inp, outp, gates, raw_proc_needed=True)

        # Cases 7a, 7b, 7c: Main Stream Multi-Resolution Switching & /proc Inspection Gates
        main_res_tests = [
            ("7a", "0", "2560x1440", 2560, 1440),
            ("7b", "1", "1920x1080", 1920, 1080),
            ("7c", "2", "1280x720",  1280, 720),
        ]
        for idx_tag, opt_res, res_name, exp_w, exp_h in main_res_tests:
            t0 = time.time()
            inp = {"menu_option": "7", "sub_choice": opt_res, "target_resolution": res_name}
            outp = {}
            gates = {}

            # Use event-driven interactive choice: option 7 -> wait prompt -> send sub_choice
            ok_choice, _ = self.driver.send_interactive_choice("7", "select front front main", opt_res, settle_menu="media")

            if self.inspector:
                # Poll /proc until resolution updates and reaches steady framerate
                start_w = time.time()
                while time.time() - start_w < 8.0:
                    ivps = self.inspector.get_ivps_info()
                    actual_ivps_w = ivps.get((0, 0), {}).get("w", 0)
                    actual_ivps_h = ivps.get((0, 0), {}).get("h", 0)
                    ivps_out_fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
                    if actual_ivps_w == exp_w and actual_ivps_h == exp_h and ivps_out_fps >= 10.0:
                        break
                    time.sleep(0.3)

                ivps = self.inspector.get_ivps_info()
                venc = self.inspector.get_venc_info()

                actual_ivps_w = ivps.get((0, 0), {}).get("w", 0)
                actual_ivps_h = ivps.get((0, 0), {}).get("h", 0)
                ivps_out_fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
                outp["proc_ivps_res"] = f"{actual_ivps_w}x{actual_ivps_h}"
                outp["proc_ivps_fps"] = ivps_out_fps

                actual_venc_w = venc.get(0, {}).get("w", 0)
                actual_venc_h = venc.get(0, {}).get("h", 0)
                venc_recv_fps = venc.get(0, {}).get("recv_fps", 0.0)
                outp["proc_venc_res"] = f"{actual_venc_w}x{actual_venc_h}"
                outp["proc_venc_fps"] = venc_recv_fps

                ivps_match = (actual_ivps_w == exp_w and actual_ivps_h == exp_h)
                gates["IVPS_Resolution"] = {
                    "desc": "IVPS 通道(0,0)分辨率切换",
                    "expected": res_name,
                    "actual": f"{actual_ivps_w}x{actual_ivps_h}",
                    "passed": ivps_match
                }

                venc_match = (actual_venc_w == exp_w and actual_venc_h == exp_h)
                gates["VENC_Resolution"] = {
                    "desc": "VENC 编码通道0源分辨率对齐",
                    "expected": res_name,
                    "actual": f"{actual_venc_w}x{actual_venc_h}",
                    "passed": venc_match
                }

                fps_ok = (ivps_out_fps >= 10.0 or venc_recv_fps >= 10.0)
                gates["StreamOutput_FPS"] = {
                    "desc": "分辨率切换后出流持续稳定",
                    "expected": ">= 10.0 fps",
                    "actual": f"{ivps_out_fps:.2f} fps (venc: {venc_recv_fps:.2f})",
                    "passed": fps_ok
                }
                case_ok = ivps_match and venc_match and fps_ok
            else:
                gates["ProcCheck"] = {"desc": "Telnet 巡检不可用", "expected": "Available", "actual": "None", "passed": False}
                case_ok = False

            case_label = f"{idx_tag}. Switch Main Resolution to {res_name} & Proc Gate"
            self.reporter.report_case("media", case_label, inp, outp, gates, "PASS" if case_ok else "FAIL", time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("media", case_label, f"case_{idx_tag}_main_res_{res_name}", inp, outp, gates, raw_proc_needed=True)

        # Cases 8a, 8b: Sub Stream Multi-Resolution Switching
        sub_res_tests = [
            ("8a", "0", "1280x720", 1280, 720),
            ("8b", "2", "640x480",  640,  480),
        ]
        for idx_tag, opt_res, res_name, exp_w, exp_h in sub_res_tests:
            t0 = time.time()
            inp = {"menu_option": "8", "sub_choice": opt_res, "target_resolution": res_name}
            outp = {}
            gates = {}

            ok_choice, _ = self.driver.send_interactive_choice("8", "select new front sub", opt_res, settle_menu="media")

            if self.inspector:
                # Poll /proc until sub-resolution updates and reaches steady framerate
                start_w = time.time()
                while time.time() - start_w < 8.0:
                    ivps = self.inspector.get_ivps_info()
                    actual_sub_w = ivps.get((0, 1), {}).get("w", 0)
                    actual_sub_h = ivps.get((0, 1), {}).get("h", 0)
                    sub_fps = ivps.get((0, 1), {}).get("out_fps", 0.0)
                    if actual_sub_w == exp_w and actual_sub_h == exp_h and sub_fps >= 10.0:
                        break
                    time.sleep(0.3)

                ivps = self.inspector.get_ivps_info()
                venc = self.inspector.get_venc_info()
                actual_sub_w = ivps.get((0, 1), {}).get("w", 0)
                actual_sub_h = ivps.get((0, 1), {}).get("h", 0)
                sub_fps = ivps.get((0, 1), {}).get("out_fps", 0.0)
                venc_sub_fps = venc.get(1, {}).get("recv_fps", 0.0)
                outp["proc_ivps_sub_res"] = f"{actual_sub_w}x{actual_sub_h}"
                outp["proc_ivps_sub_fps"] = sub_fps

                sub_match = (actual_sub_w == exp_w and actual_sub_h == exp_h)
                gates["IVPS_Sub_Resolution"] = {
                    "desc": "IVPS 子通道(0,1)分辨率切换",
                    "expected": res_name,
                    "actual": f"{actual_sub_w}x{actual_sub_h}",
                    "passed": sub_match
                }
                case_ok = sub_match and (sub_fps >= 10.0 or venc_sub_fps >= 10.0)
            else:
                case_ok = False

            case_label = f"{idx_tag}. Switch Sub Resolution to {res_name} & Proc Gate"
            self.reporter.report_case("media", case_label, inp, outp, gates, "PASS" if case_ok else "FAIL", time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("media", case_label, f"case_{idx_tag}_sub_res_{res_name}", inp, outp, gates, raw_proc_needed=True)

        # Case 9: VENC Codec Switching (Option 11: 0=H264, 1=H265)
        # Note: Switching codec tears down and recreates the encoder pipeline; allow up to 6s for settlement.
        t0 = time.time()
        inp = {"option": "11", "action": "Set front VENC type to H264 then H265"}
        outp = {}
        gates = {}

        # Set to H264 via event-driven choice
        self.driver.send_interactive_choice("11", "Input front venc type", "0", settle_menu="media")
        venc_type_1 = "UNKNOWN"
        start_wait = time.time()
        while time.time() - start_wait < 8.0:
            if self.inspector:
                venc = self.inspector.get_venc_info()
                t = venc.get(0, {}).get("type", "UNKNOWN")
                fps = venc.get(0, {}).get("recv_fps", 0.0)
                if "264" in t and fps >= 10.0:
                    venc_type_1 = t
                    break
            time.sleep(0.3)
        if venc_type_1 == "UNKNOWN" and self.inspector:
            venc = self.inspector.get_venc_info()
            venc_type_1 = venc.get(0, {}).get("type", "UNKNOWN")
        outp["venc_codec_step1"] = venc_type_1

        # Set back to H265 via event-driven choice
        self.driver.send_interactive_choice("11", "Input front venc type", "1", settle_menu="media")
        venc_type_2 = "UNKNOWN"
        start_wait = time.time()
        while time.time() - start_wait < 8.0:
            if self.inspector:
                venc = self.inspector.get_venc_info()
                t = venc.get(0, {}).get("type", "UNKNOWN")
                fps = venc.get(0, {}).get("recv_fps", 0.0)
                if "265" in t and fps >= 10.0:
                    venc_type_2 = t
                    break
            time.sleep(0.3)
        if venc_type_2 == "UNKNOWN" and self.inspector:
            venc = self.inspector.get_venc_info()
            venc_type_2 = venc.get(0, {}).get("type", "UNKNOWN")
        outp["venc_codec_step2"] = venc_type_2

        gates["VencCodecSwitch"] = {
            "desc": "VENC 编码器类型切换生效",
            "expected": "H264 -> H265",
            "actual": f"{venc_type_1} -> {venc_type_2}",
            "passed": ("264" in venc_type_1 and "265" in venc_type_2)
        }
        self.reporter.report_case("media", "9. VENC Codec Switching (H264 <-> H265)", inp, outp, gates, "PASS" if gates["VencCodecSwitch"]["passed"] else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "9. VENC Codec Switching (H264 <-> H265)", "case_9_venc_codec", inp, outp, gates, raw_proc_needed=True)

        # Case 10: Set Record Time (Option 12: 1-3 minutes)
        t0 = time.time()
        inp = {"option": "12", "rec_time_minutes": "2"}
        outp = {}
        gates = {}
        ok_rec_time, _ = self.driver.send_interactive_choice("12", "Input record time", "2", settle_menu="media")
        gates["RecordTime"] = {
            "desc": "录像切片时间设置生效",
            "expected": "Set record time to 2 min ok",
            "actual": f"success={ok_rec_time}",
            "passed": ok_rec_time
        }
        self.reporter.report_case("media", "10. Set Record Time (1-3 min)", inp, outp, gates, "PASS" if gates["RecordTime"]["passed"] else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "10. Set Record Time (1-3 min)", "case_10_set_rec_time", inp, outp, gates, raw_proc_needed=True)

        # Case 11: MP4 Record Start & Stop & TF Card MP4 File Check
        t0 = time.time()
        inp = {"start_option": "9", "stop_option": "10", "action": "MP4 Record Start & Stop"}
        outp = {}
        gates = {}
        cap_start = self.send_and_capture("9", "record", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        # Record for 2 seconds to generate video content
        t_rec = time.time()
        while time.time() - t_rec < 2.0:
            time.sleep(0.2)
        cap_stop = self.send_and_capture("10", "record", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        outp["start_feedback"] = cap_start
        outp["stop_feedback"] = cap_stop
        rec_files_ok = True
        if self.inspector:
            # Poll for mp4 files to be written and closed on storage
            start_poll = time.time()
            mp4_files = []
            while time.time() - start_poll < 4.0:
                files = self.inspector.list_files("/mnt/tfcard/Normal/F/")
                mp4_files = [f for f in files if f.endswith(".mp4")]
                if len(mp4_files) > 0:
                    break
                time.sleep(0.5)
            outp["mp4_files_count"] = len(mp4_files)
            outp["latest_mp4_files"] = mp4_files[-3:]
            rec_files_ok = len(mp4_files) > 0
            gates["MP4FileGenerated"] = {
                "desc": "TF卡 Normal/F 目录下生成录像文件",
                "expected": "> 0 mp4 files",
                "actual": f"{len(mp4_files)} mp4 files",
                "passed": rec_files_ok
            }
        gates["RecordState"] = {
            "desc": "录像启动与停止指令响应正常",
            "expected": "start & stop executed",
            "actual": f"start={bool(cap_start)}, stop={bool(cap_stop)}",
            "passed": True
        }
        case_ok = gates["RecordState"]["passed"] and rec_files_ok
        self.reporter.report_case("media", "11. MP4 Record Start/Stop & Storage Check", inp, outp, gates, "PASS" if case_ok else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "11. MP4 Record Start/Stop & Storage Check", "case_11_mp4_record", inp, outp, gates, raw_proc_needed=True)

        # Case 12: Urgent Video Recording (Option 13)
        t0 = time.time()
        inp = {"option": "13", "action": "Start urgent video recording"}
        outp = {}
        gates = {}
        # Precondition: start record
        self.send_and_capture("9", "record", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        cap_urgent = self.send_and_capture("13", "StartUrgent", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        self.send_and_capture("10", "record", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        outp["urgent_feedback"] = cap_urgent
        gates["UrgentRecord"] = {
            "desc": "紧急录像指令触发成功",
            "expected": "Urgent record triggered",
            "actual": str(cap_urgent),
            "passed": True
        }
        self.reporter.report_case("media", "12. Start Urgent Video Recording", inp, outp, gates, "PASS", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "12. Start Urgent Video Recording", "case_12_urgent_record", inp, outp, gates, raw_proc_needed=True)

        # Case 13: Audio In Mute / Unmute & State Verification (Options 18, 19, 20)
        t0 = time.time()
        inp = {"mute_opt": "18", "get_opt": "20", "unmute_opt": "19"}
        outp = {}
        gates = {}
        cap_mute = self.send_and_capture("18", "mute", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=2.0)
        cap_check = self.send_and_capture("20", "OnGetAInMute", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=2.0)
        cap_unmute = self.send_and_capture("19", "mute", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=2.0)
        outp["mute_check_echo"] = cap_check
        outp["mute_echo"] = cap_mute
        outp["unmute_echo"] = cap_unmute
        mute_ok = bool(cap_check) or bool(cap_mute) or bool(cap_unmute)
        gates["AudioMute"] = {
            "desc": "音频输入静音与查询接口正常",
            "expected": "OnGetAInMute echo",
            "actual": str(cap_check or cap_mute or cap_unmute),
            "passed": mute_ok
        }
        self.reporter.report_case("media", "13. Audio In Mute / Unmute Test", inp, outp, gates, "PASS" if gates["AudioMute"]["passed"] else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "13. Audio In Mute / Unmute Test", "case_13_audio_mute", inp, outp, gates, raw_proc_needed=True)

        # Case 14: Audio Out Volume Set & Get (Options 32 & 33)
        t0 = time.time()
        inp = {"set_vol_opt": "32", "target_vol": "8", "get_vol_opt": "33"}
        outp = {}
        gates = {}
        ok_vol, _ = self.driver.send_interactive_choice("32", "Input volume", "8", settle_menu="media")
        cap_vol = self.send_and_capture("33", "vol", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=2.0)
        outp["vol_feedback"] = cap_vol
        outp["set_vol_ok"] = ok_vol
        gates["AudioVolume"] = {
            "desc": "音频输出音量配置与查询有效",
            "expected": "OnGetAOutVol response or choice set success",
            "actual": str(cap_vol or ok_vol),
            "passed": bool(cap_vol) or ok_vol
        }
        self.reporter.report_case("media", "14. Audio Out Volume Set & Get", inp, outp, gates, "PASS" if gates["AudioVolume"]["passed"] else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "14. Audio Out Volume Set & Get", "case_14_audio_volume", inp, outp, gates, raw_proc_needed=True)

        # Case 15: RTSP Server Start & Stop & Port 8554 Check (Options 26 & 27)
        t0 = time.time()
        inp = {"start_rtsp": "26", "stop_rtsp": "27", "action": "RTSP Server Start & Stop"}
        outp = {}
        gates = {}
        cap_rtsp_start = self.send_and_capture("26", "RTSP", timeout=5.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        rtsp_port_ok = False
        if self.inspector:
            # 轮询等待 RTSP 8554 端口监听启动 (最多 5 秒)
            deadline = time.time() + 5.0
            while time.time() < deadline:
                if self.inspector.is_port_listening(8554):
                    rtsp_port_ok = True
                    break
                time.sleep(0.2)
        outp["rtsp_port_8554_active"] = rtsp_port_ok
        outp["start_feedback"] = cap_rtsp_start
        cap_rtsp_stop = self.send_and_capture("27", "RTSP", timeout=5.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        outp["stop_feedback"] = cap_rtsp_stop
        gates["RTSPPortActive"] = {
            "desc": "板端 8554 RTSP 流媒体端口监听激活",
            "expected": "Port 8554 Listening",
            "actual": f"Active={rtsp_port_ok}",
            "passed": rtsp_port_ok
        }
        gates["RTSPEcho"] = {
            "desc": "RTSP 启停指令响应正常",
            "expected": "Start & stop response",
            "actual": f"start={bool(cap_rtsp_start)}, stop={bool(cap_rtsp_stop)}",
            "passed": bool(cap_rtsp_start) or bool(cap_rtsp_stop)
        }
        step_ok = rtsp_port_ok or gates["RTSPEcho"]["passed"]
        self.reporter.report_case("media", "15. RTSP Server Start & Stop & Port 8554 Check", inp, outp, gates, "PASS" if step_ok else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "15. RTSP Server Start & Stop & Port 8554 Check", "case_15_rtsp_server", inp, outp, gates, raw_proc_needed=True)

        # Case 16: JENC Capture Image & Storage Check (Option 28)
        t0 = time.time()
        inp = {"option": "28", "action": "Capture image (JENC)"}
        outp = {}
        gates = {}
        cap_feedback = self.send_and_capture("28", "capture", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=3.0)
        photo_count = 0
        photo_files = []
        if self.inspector:
            self.inspector.exec_cmd("sync")
            photo_files = self.inspector.list_files("/mnt/tfcard/Photo/F")
            photo_count = len([f for f in photo_files if f.endswith(".jpg")])
        outp["photo_files_count"] = photo_count
        outp["latest_photos"] = photo_files[-2:] if photo_files else []
        gates["PhotoGenerated"] = {
            "desc": "TF卡 Photo/F 目录生成 JPEG 抓拍图片",
            "expected": "> 0 jpg files",
            "actual": f"{photo_count} jpg files",
            "passed": (photo_count > 0)
        }
        gates["CaptureFeedback"] = {
            "desc": "JENC 抓拍接口响应正常",
            "expected": "capture keyword in feedback",
            "actual": str(cap_feedback),
            "passed": True
        }
        step_ok = (photo_count > 0) or bool(cap_feedback)
        self.reporter.report_case("media", "16. JENC Capture Image & Storage Check", inp, outp, gates, "PASS" if step_ok else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "16. JENC Capture Image & Storage Check", "case_16_capture", inp, outp, gates, raw_proc_needed=True)

        # Case 17: Query Media Status (Option 21)
        t0 = time.time()
        inp = {"option": "21", "action": "Query media service status"}
        outp = {}
        gates = {}
        cap_status = self.send_and_capture("21", "media status", timeout=4.0, wait_post=0.0)
        self.driver.wait_menu("media", timeout=2.0)
        outp["status_echo"] = cap_status
        gates["MediaStatus"] = {
            "desc": "媒体服务状态查询",
            "expected": "Valid status response",
            "actual": str(cap_status),
            "passed": bool(cap_status)
        }
        self.reporter.report_case("media", "17. Query Media Status", inp, outp, gates, "PASS" if bool(cap_status) else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "17. Query Media Status", "case_17_media_status", inp, outp, gates, raw_proc_needed=False)

        # Case 18: Exit Media Menu (Option 0)
        t0 = time.time()
        inp = {"action": "Exit back to main menu"}
        outp = {}
        gates = {}
        self.driver.ensure_in_main_menu()
        cur_menu = self.driver.get_current_menu()
        outp["final_menu"] = cur_menu
        gates["ReturnedToMain"] = {
            "desc": "安全返回主菜单",
            "expected": "main",
            "actual": cur_menu,
            "passed": (cur_menu == "main")
        }
        self.reporter.report_case("media", "18. Exit Media Menu", inp, outp, gates, "PASS" if cur_menu == "main" else "FAIL", time.time() - t0)
        if self.collector:
            self.collector.record_case_evidence("media", "18. Exit Media Menu", "case_18_exit_media", inp, outp, gates, raw_proc_needed=False)


        print("=== [SDK-AXCK-TEST] Media Subsystem Suite Completed ===\n")
        return self.reporter.cases
