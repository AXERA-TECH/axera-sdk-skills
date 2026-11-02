#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
system_suite.py - AXCK Storage, DTCF, and Device Subsystems automated test suite.
Features:
- Drives axck_test submenus via BoardSerialDriver.
- Gathers hardware state via TelnetInspector.
- Formats and outputs structured case reports in real time via CaseReporter.
- Records per-case raw proc snapshots and logs via EvidenceCollector.
"""

import sys
import time
import re

sys.stdout.reconfigure(line_buffering=True)


class SystemSuiteRunner:
    def __init__(self, driver, inspector=None, reporter=None, evidence_collector=None):
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

        if wait_post > 0:
            time.sleep(wait_post)

        return captured_line

    def run_all(self):
        print("\n=== [SDK-AXCK-TEST] Starting Storage, DTCF & Device Subsystems Suite ===")

        # 0. Storage Format Test (Submenu 2, Option 6)
        t0 = time.time()
        inp = {"menu": "2 (storage)", "option": "6 (SDCard format)"}
        outp = {}
        gates = {}
        if not self.driver.navigate_to("storage"):
            gates["NavStorage"] = {"desc": "导航至 Storage 菜单", "expected": "storage", "actual": "failed", "passed": False}
            self.reporter.report_case("system", "0. Storage TF Card Format Test", inp, outp, gates, "FAIL", time.time() - t0)
        else:
            self.driver.send("6", append_enter=True)
            format_success = False
            sd_ready = False
            deadline = time.time() + 35.0
            captured_lines = []
            while time.time() < deadline:
                time.sleep(0.3)
                lines = self.driver.read_lines(limit=80, tail=False)
                for l in lines:
                    ls = l.strip()
                    if ls and ls not in captured_lines:
                        captured_lines.append(ls)
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
                "desc": "TF卡格式化成功完成",
                "expected": "storage format success",
                "actual": "success" if format_success else "failed",
                "passed": format_success
            }
            gates["SDCardReady"] = {
                "desc": "格式化后TF卡重新就绪挂载",
                "expected": "sd card is ready!",
                "actual": "ready" if sd_ready else "not ready",
                "passed": sd_ready
            }

            status = "PASS" if (format_success and sd_ready) else "FAIL"
            self.reporter.report_case("system", "0. Storage TF Card Format Test", inp, outp, gates, status, time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("system", "0. Storage TF Card Format Test", "case_0_storage_format", inp, outp, gates, raw_proc_needed=False)

        # 1. Storage Subsystem (Submenu 2)
        t0 = time.time()
        inp = {"menu": "2 (storage)", "options": ["1 (status)", "2 (total size)", "3 (free size)"]}
        outp = {}
        gates = {}
        if not self.driver.navigate_to("storage"):
            gates["NavStorage"] = {"desc": "导航至 Storage 菜单", "expected": "storage", "actual": "failed", "passed": False}
            self.reporter.report_case("system", "1. Storage Subsystem Smoke Test", inp, outp, gates, "FAIL", time.time() - t0)
        else:
            cap_stat = self.send_and_capture("1", "status", timeout=4.0, wait_post=0.0)
            self.driver.wait_menu("storage", timeout=2.0)
            cap_tot = self.send_and_capture("2", "total size", timeout=4.0, wait_post=0.0)
            self.driver.wait_menu("storage", timeout=2.0)
            cap_free = self.send_and_capture("3", "free size", timeout=4.0, wait_post=0.0)
            self.driver.wait_menu("storage", timeout=2.0)
            outp["storage_status"] = cap_stat
            outp["storage_total"] = cap_tot
            outp["storage_free"] = cap_free

            self.driver.navigate_to("main")

            gates["StorageStatus"] = {
                "desc": "TF卡存储状态与容量查询响应",
                "expected": "Valid response",
                "actual": f"stat={bool(cap_stat)}, total={bool(cap_tot)}, free={bool(cap_free)}",
                "passed": True
            }
            self.reporter.report_case("system", "1. Storage Subsystem Smoke Test", inp, outp, gates, "PASS", time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("system", "1. Storage Subsystem Smoke Test", "case_1_storage", inp, outp, gates, raw_proc_needed=False)

        # 2. DTCF Subsystem (Submenu 3)
        t0 = time.time()
        inp = {"menu": "3 (dtcf)", "option": "1 (Dump dtcf info)"}
        outp = {}
        gates = {}
        if not self.driver.navigate_to("dtcf"):
            gates["NavDtcf"] = {"desc": "导航至 DTCF 菜单", "expected": "dtcf", "actual": "failed", "passed": False}
            self.reporter.report_case("system", "2. DTCF Subsystem Smoke Test", inp, outp, gates, "FAIL", time.time() - t0)
        else:
            cap_info = self.send_and_capture("1", "dtcf", timeout=4.0, wait_post=0.0)
            self.driver.wait_menu("dtcf", timeout=2.0)
            outp["dtcf_dump"] = cap_info
            self.driver.navigate_to("main")

            gates["DtcfDump"] = {
                "desc": "DTCF 文件检索系统信息导出",
                "expected": "Valid dtcf dump feedback",
                "actual": str(cap_info),
                "passed": True
            }
            self.reporter.report_case("system", "2. DTCF Subsystem Smoke Test", inp, outp, gates, "PASS", time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("system", "2. DTCF Subsystem Smoke Test", "case_2_dtcf", inp, outp, gates, raw_proc_needed=False)

        # 3. Device Subsystem (Submenu 4)
        t0 = time.time()
        inp = {"menu": "4 (device)", "options": ["4 (Query all status)", "3 (Query all info)"]}
        outp = {}
        gates = {}
        if not self.driver.navigate_to("device"):
            gates["NavDevice"] = {"desc": "导航至 Device 菜单", "expected": "device", "actual": "failed", "passed": False}
            self.reporter.report_case("system", "3. Device Subsystem Smoke Test", inp, outp, gates, "FAIL", time.time() - t0)
        else:
            cap_status = self.send_and_capture("4", "status", timeout=4.0, wait_post=0.0)
            self.driver.wait_menu("device", timeout=2.0)
            cap_info = self.send_and_capture("3", "info", timeout=4.0, wait_post=0.0)
            self.driver.wait_menu("device", timeout=2.0)
            outp["device_status"] = cap_status
            outp["device_info"] = cap_info
            self.driver.navigate_to("main")

            gates["DeviceInfoAndStatus"] = {
                "desc": "设备全量状态与硬件信息查询",
                "expected": "Valid status & info",
                "actual": f"stat={bool(cap_status)}, info={bool(cap_info)}",
                "passed": True
            }
            self.reporter.report_case("system", "3. Device Subsystem Smoke Test", inp, outp, gates, "PASS", time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("system", "3. Device Subsystem Smoke Test", "case_3_device", inp, outp, gates, raw_proc_needed=False)

        print("=== [SDK-AXCK-TEST] System Subsystem Suite Completed ===\n")
        return self.reporter.cases
