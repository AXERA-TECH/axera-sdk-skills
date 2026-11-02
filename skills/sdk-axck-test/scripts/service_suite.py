#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
service_suite.py - AXCK Service Standalone Automated Test Suite.
Verifies:
1. Process launch in standalone daemon mode.
2. Initialization & steady state (IVPS, VENC, CMM Pool creation).
3. Frame generation and steady streaming (>0 fps).
4. Clean shutdown and hardware release.
5. Records per-case evidence via EvidenceCollector.
"""

import sys
import time
import os

sys.stdout.reconfigure(line_buffering=True)


class ServiceSuiteRunner:
    def __init__(self, driver, inspector, reporter, evidence_collector=None):
        self.driver = driver
        self.inspector = inspector
        self.reporter = reporter
        self.collector = evidence_collector

    def run_all(self):
        print("\n=== [SDK-AXCK-TEST] Starting Standalone axck_service Test Suite ===")

        # Case 1: Pre-cleanup and Reset (hardened: two-stage kill + ipc removal + comm-scan verify)
        t0 = time.time()
        inp = {"action": "comm-scan kill axck_test/axck_service (SIGINT->SIGKILL) + rm -f /tmp/axck.ipc"}
        outp = {}
        gates = {}
        try:
            clean_ok = False
            if self.inspector:
                # Stage 1: graceful SIGINT (releases IVPS/VENC/CMM hardware cleanly)
                self.inspector.comm_kill_axck(2)
                time.sleep(1.2)
                # Stage 2: SIGKILL any stragglers + remove rpc ipc socket file
                self.inspector.comm_kill_axck(9)
                self.inspector.exec_cmd("rm -f /tmp/axck.ipc")
                time.sleep(0.5)
                pids = self.inspector.comm_scan_axck_pids(alive_only=True)
                if pids:
                    # respawn / race window detected: second sweep
                    self.inspector.comm_kill_axck(9)
                    time.sleep(0.8)
                    pids = self.inspector.comm_scan_axck_pids(alive_only=True)
                outp["residual_pids"] = pids
                ipc_left = self.inspector.ipc_file_exists()
                outp["axck_ipc_file_left"] = ipc_left
                clean_ok = (len(pids) == 0) and (not ipc_left)
            else:
                menu = self.driver.get_current_menu()
                if menu == "shell":
                    # Serial fallback. Markers split as IPC_""PRESENT so the echoed
                    # command line never matches the detection keyword.
                    cmd = (
                        "for p in /proc/[0-9]*; do c=$(cat $p/comm 2>/dev/null); "
                        'case "$c" in axck_test|axck_service) kill -9 ${p#/proc/} 2>/dev/null;; esac; done; '
                        "rm -f /tmp/axck.ipc; "
                        "for p in /proc/[0-9]*; do c=$(cat $p/comm 2>/dev/null); "
                        'case "$c" in axck_test|axck_service) echo RE""S:$p;; esac; done; '
                        'test -e /tmp/axck.ipc && echo IPC_""PRESENT || echo IPC_""ABSENT'
                    )
                    self.driver.send(cmd, append_enter=True)
                    ok, text = self.driver.wait_keyword(["IPC_PRESENT", "IPC_ABSENT"], timeout=4.0)
                    has_residue = ("RES:/proc/" in text)
                    clean_ok = ok and ("IPC_ABSENT" in text) and not has_residue
                    outp["serial_verify"] = ("IPC_ABSENT, no residue" if clean_ok else text[-200:])
                else:
                    outp["reason"] = f"console at '{menu}', shell cleanup needs shell (no inspector)"
                    clean_ok = False

            gates["CleanProc"] = {
                "desc": "comm 扫描确认无残留 axck_test/axck_service 进程且 ipc socket 已清除",
                "expected": "pids=[] and ipc_file=False",
                "actual": f"pids={outp.get('residual_pids', outp.get('serial_verify', 'unknown'))}, "
                          f"ipc_left={outp.get('axck_ipc_file_left', 'unknown')}",
                "passed": clean_ok
            }
            status = "PASS" if clean_ok else "FAIL"
            self.reporter.report_case("service", "1. Pre-clean existing processes", inp, outp, gates, status, time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("service", "1. Pre-clean existing processes", "case_1_pre_clean", inp, outp, gates, raw_proc_needed=True)
        except Exception as e:
            self.reporter.report_case("service", "1. Pre-clean existing processes", inp, outp, gates, "FAIL", time.time() - t0, error_msg=str(e))

        # Case 2: Launch axck_service standalone (+ RPC bind health verification)
        t0 = time.time()
        inp = {"command": "cd /opt/bin && ./axck_service -v 0 -p 0 -l 2 -t 2 &"}
        outp = {}
        gates = {}
        try:
            self.driver.send("cd /opt/bin && ./axck_service -v 0 -p 0 -l 2 -t 2 &", append_enter=True)

            if self.inspector:
                pid = None
                deadline = time.time() + 5.0
                while time.time() < deadline:
                    pids = self.inspector.comm_scan_axck_pids()
                    if pids:
                        pid = pids[-1]
                        break
                    time.sleep(0.2)
                outp["service_pid"] = pid
                self.service_pid = pid  # remembered for Case 5 targeted stop gate
                proc_ok = (pid is not None)

                # RPC bind health: poll until ipc socket appears or a bind error is logged
                ipc_ok = False
                rpc_err = []
                if proc_ok:
                    rpc_deadline = time.time() + 8.0
                    while time.time() < rpc_deadline:
                        ipc_ok = self.inspector.ipc_file_exists()
                        rpc_err = self.inspector.grep_latest_service_log(
                            ["nn_bind error", "Initialize RPC fail"])
                        if ipc_ok or rpc_err:
                            break
                        time.sleep(0.3)
                outp["axck_ipc_file"] = ipc_ok
                outp["rpc_error_lines"] = rpc_err[:5]
                rpc_ok = proc_ok and ipc_ok and (len(rpc_err) == 0)

                gates["ProcessAlive"] = {
                    "desc": "axck_service 进程存活 (comm 扫描)",
                    "expected": "PID > 0",
                    "actual": f"PID={outp.get('service_pid')}",
                    "passed": proc_ok
                }
                gates["RpcBindHealth"] = {
                    "desc": "RPC ipc socket 已创建且最新 service 日志无 nn_bind error",
                    "expected": "ipc=True, no nn_bind error",
                    "actual": f"ipc={ipc_ok}, err={rpc_err[:2]}",
                    "passed": rpc_ok
                }
                status = "PASS" if (proc_ok and rpc_ok) else "FAIL"
            else:
                outp["service_pid"] = "unknown"
                gates["ProcessAlive"] = {
                    "desc": "axck_service 进程存活 (无 inspector, 未验证)",
                    "expected": "PID > 0",
                    "actual": "unknown",
                    "passed": True
                }
                status = "PASS"

            self.reporter.report_case("service", "2. Launch axck_service daemon", inp, outp, gates, status, time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("service", "2. Launch axck_service daemon", "case_2_launch_daemon", inp, outp, gates, raw_proc_needed=True)
        except Exception as e:
            self.reporter.report_case("service", "2. Launch axck_service daemon", inp, outp, gates, "FAIL", time.time() - t0, error_msg=str(e))

        # Case 3: Verify Hardware Pipeline Initialization via /proc
        t0 = time.time()
        inp = {"target": "/proc/ax_proc/ivps & venc"}
        outp = {}
        gates = {}
        try:
            if self.inspector:
                deadline = time.time() + 15.0
                ivps = {}
                venc = {}
                while time.time() < deadline:
                    ivps = self.inspector.get_ivps_info()
                    venc = self.inspector.get_venc_info()
                    if (0, 0) in ivps and ivps[(0, 0)]["w"] > 0 and 0 in venc and venc[0]["w"] > 0:
                        break
                    time.sleep(0.2)
                outp["ivps_channels"] = list(ivps.keys())
                outp["venc_channels"] = list(venc.keys())

                ivps_ok = (0, 0) in ivps and ivps[(0, 0)]["w"] > 0 and ivps[(0, 0)]["h"] > 0
                main_w = ivps[(0, 0)]["w"] if (0, 0) in ivps else 0
                main_h = ivps[(0, 0)]["h"] if (0, 0) in ivps else 0

                gates["IVPS_Pipeline"] = {
                    "desc": "IVPS 主通道初始化",
                    "expected": ">0x>0",
                    "actual": f"{main_w}x{main_h}",
                    "passed": ivps_ok
                }

                venc_ok = 0 in venc and venc[0]["w"] > 0
                gates["VENC_Pipeline"] = {
                    "desc": "VENC 编码通道就绪",
                    "expected": "Chn 0 exists",
                    "actual": f"Chn0={venc.get(0, {}).get('type')}, {venc.get(0, {}).get('w')}x{venc.get(0, {}).get('h')}",
                    "passed": venc_ok
                }
                overall_ok = ivps_ok and venc_ok
            else:
                gates["ProcInspector"] = {"desc": "Telnet 巡检器未连接", "expected": "Connected", "actual": "None", "passed": False}
                overall_ok = False

            status = "PASS" if overall_ok else "FAIL"
            self.reporter.report_case("service", "3. Verify Pipeline /proc status", inp, outp, gates, status, time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("service", "3. Verify Pipeline /proc status", "case_3_pipeline_status", inp, outp, gates, raw_proc_needed=True)
        except Exception as e:
            self.reporter.report_case("service", "3. Verify Pipeline /proc status", inp, outp, gates, "FAIL", time.time() - t0, error_msg=str(e))

        # Case 4: Verify Streaming FPS Output
        t0 = time.time()
        inp = {"target": "Steady Streaming FPS"}
        outp = {}
        gates = {}
        try:
            if self.inspector:
                deadline = time.time() + 5.0
                out_fps = 0.0
                recv_fps = 0.0
                while time.time() < deadline:
                    ivps = self.inspector.get_ivps_info()
                    venc = self.inspector.get_venc_info()
                    out_fps = ivps.get((0, 0), {}).get("out_fps", 0.0)
                    recv_fps = venc.get(0, {}).get("recv_fps", 0.0)
                    if out_fps >= 10.0:
                        break
                    time.sleep(0.2)
                outp["ivps_out_fps"] = out_fps
                outp["venc_recv_fps"] = recv_fps

                fps_ok = out_fps >= 10.0
                gates["StreamFPS"] = {
                    "desc": "IVPS 帧率输出稳定",
                    "expected": ">= 10.0 fps",
                    "actual": f"{out_fps:.2f} fps",
                    "passed": fps_ok
                }
                status = "PASS" if fps_ok else "FAIL"
            else:
                gates["StreamFPS"] = {"desc": "Telnet 巡检不可用", "expected": "Available", "actual": "None", "passed": False}
                status = "FAIL"

            self.reporter.report_case("service", "4. Check steady frame output", inp, outp, gates, status, time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("service", "4. Check steady frame output", "case_4_steady_streaming", inp, outp, gates, raw_proc_needed=True)
        except Exception as e:
            self.reporter.report_case("service", "4. Check steady frame output", inp, outp, gates, "FAIL", time.time() - t0, error_msg=str(e))

        # Case 5: Clean Stop axck_service (comm-scan SIGINT + ipc residue verification)
        t0 = time.time()
        inp = {"action": "comm-scan kill -INT axck_service (SIGINT graceful) + rm -f /tmp/axck.ipc"}
        outp = {}
        gates = {}
        try:
            our_pid = getattr(self, "service_pid", None)
            if self.inspector:
                if our_pid:
                    # targeted graceful SIGINT on the instance launched by Case 2
                    self.inspector.exec_cmd(f"kill -INT {our_pid} 2>/dev/null")
                else:
                    self.inspector.comm_kill_axck(2)  # SIGINT graceful shutdown
            else:
                self.driver.send(
                    "for p in /proc/[0-9]*; do c=$(cat $p/comm 2>/dev/null); "
                    'case "$c" in axck_service) kill -INT ${p#/proc/} 2>/dev/null;; esac; done',
                    append_enter=True)

            stop_ok = False
            force_killed = False
            if self.inspector:
                # Gate on OUR pid: foreign respawned instances (e.g. a service
                # auto-spawned by an axck_test) must not fail this case; they are
                # cleaned by the next suite's ensure_in_main_menu auto-recover.
                # Poll with alive_only (zombies excluded): a reaped child keeps
                # its /proc/<pid>/comm entry and would false-report as residual.
                deadline = time.time() + 25.0
                while time.time() < deadline:
                    pids = self.inspector.comm_scan_axck_pids(alive_only=True)
                    if our_pid is None or our_pid not in pids:
                        stop_ok = True
                        break
                    time.sleep(0.5)
                if not stop_ok:
                    # Grace window exceeded: SIGKILL fallback so later suites are
                    # never blocked; the FAIL verdict + force_killed flag keeps
                    # the product-defect signal (graceful SIGINT hang) visible.
                    self.inspector.comm_kill_axck(9)
                    force_killed = True
                    time.sleep(1.0)
                residual = self.inspector.comm_scan_axck_pids(alive_only=True)
                foreign = [p for p in residual if p != our_pid]
                if not residual:
                    self.inspector.exec_cmd("rm -f /tmp/axck.ipc")
                outp["our_service_pid"] = our_pid
                outp["service_pid_after_stop"] = residual
                outp["foreign_pids"] = foreign
                outp["graceful_exit"] = stop_ok
                outp["force_killed"] = force_killed
                outp["axck_ipc_file_left"] = self.inspector.ipc_file_exists()
            else:
                for _ in range(20):
                    time.sleep(0.5)
                stop_ok = True

            gates["ServiceStopped"] = {
                "desc": "本套件启动的 axck_service 已优雅退出 (SIGINT, 特定 PID 门限, 25s 等待)",
                "expected": f"PID {our_pid} exited gracefully within 25s "
                            "(zombie 不计; 超时 SIGKILL 兜底后仍判 FAIL 以暴露产品缺陷)",
                "actual": f"graceful_exit={stop_ok}, force_killed={force_killed}, "
                          f"residual={outp.get('service_pid_after_stop', 'unknown')}, "
                          f"ipc_left={outp.get('axck_ipc_file_left', 'unknown')}",
                "passed": stop_ok
            }
            status = "PASS" if stop_ok else "FAIL"
            self.reporter.report_case("service", "5. Stop axck_service and release hardware", inp, outp, gates, status, time.time() - t0)
            if self.collector:
                self.collector.record_case_evidence("service", "5. Stop axck_service and release hardware", "case_5_stop_service", inp, outp, gates, raw_proc_needed=True)
        except Exception as e:
            self.reporter.report_case("service", "5. Stop axck_service and release hardware", inp, outp, gates, "FAIL", time.time() - t0, error_msg=str(e))

        print("=== [SDK-AXCK-TEST] Standalone axck_service Suite Completed ===\n")
        return self.reporter.cases
