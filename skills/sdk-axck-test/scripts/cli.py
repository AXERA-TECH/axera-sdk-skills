#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cli.py - Unified command-line interface for SDK-AXCK-TEST.
Features:
- Subcommands: run, list-suites, inspect-proc, single-case, run-scenario, stress.
- Supports dual drivers:
  * http (HttpRpcDriver layered architecture: single API, scenario DSL, stress engine)
  * uart (legacy serial axck_test menu automation)
- Out-of-band Telnet concurrent hardware inspection (/proc/ax_proc/ivps & venc).
- Standardized structured real-time reporting & evidence archiving.
"""

import sys
import os
import argparse
import json
import time

# Ensure scripts directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from board_driver import BoardSerialDriver
from telnet_inspector import TelnetInspector
from case_reporter import CaseReporter
from evidence_collector import EvidenceCollector
from service_suite import ServiceSuiteRunner
from media_suite import MediaSuiteRunner
from system_suite import SystemSuiteRunner
from scenario_continuous_record_capture import ContinuousRecordCaptureScenario

# New Layered HTTP Driver modules
from core.domain_apis import AxckClient
from core.scenario import ScenarioBuilder, ScenarioRunner
from core.stress_runner import StressRunner, StressConfig


def build_parser():
    parser = argparse.ArgumentParser(
        prog="axck-test",
        description="AXCK Automated Test CLI - supports HTTP RPC Driver (layered/scenario/stress) and UART Menu automation"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: list-suites
    subparsers.add_parser("list-suites", help="List available test suites")

    # Subcommand: inspect-proc
    inspect_parser = subparsers.add_parser("inspect-proc", help="Inspect board /proc hardware pipelines via Telnet")
    inspect_parser.add_argument("--host", default=None, help="Board IP address (auto-detected if omitted)")

    # Subcommand: single-case (HTTP direct API execution)
    single_parser = subparsers.add_parser("single-case", help="Execute single domain API call via HTTP RPC Driver")
    single_parser.add_argument("--case", required=True,
                               choices=[
                                   "media.start_record", "media.stop_record", "media.take_photo",
                                   "media.start_urgent", "media.switch_prev",
                                   "audio.set_mute", "audio.get_mute", "audio.set_vol", "audio.get_vol",
                                   "stream.set_stream_on", "stream.get_stream_on",
                                   "stream.set_mirror", "stream.set_flip",
                                   "stream.set_fps", "stream.get_fps", "stream.set_res", "stream.set_venc_type",
                                   "rtsp.start", "rtsp.stop",
                                   "storage.get_status", "storage.format", "storage.mount", "storage.unmount",
                                   "dtcf.get_file_count", "dtcf.get_file_list",
                                   "device.get_status", "aov.start", "aov.stop"
                               ],
                               help="Target API case to execute")
    single_parser.add_argument("--host", default=None, help="Board IP address (or set AXCK_BOARD_IP env)")
    single_parser.add_argument("--port", type=int, default=80, help="HTTP port (default: 80)")
    single_parser.add_argument("--param", default=None, help="Optional param (e.g. mode=1 for switch_prev)")

    # Subcommand: run-scenario (HTTP chainable pipeline)
    scen_parser = subparsers.add_parser("run-scenario", help="Execute chainable scenario pipeline via HTTP RPC Driver")
    scen_parser.add_argument("--scenario", choices=["smoke", "burst-capture", "continuous-record"], default="smoke",
                             help="Scenario pipeline preset to run")
    scen_parser.add_argument("--host", default=None, help="Board IP address (or set AXCK_BOARD_IP env)")
    scen_parser.add_argument("--port", type=int, default=80, help="HTTP port (default: 80)")
    scen_parser.add_argument("--report", default=None, help="Path to save report JSON")

    # Subcommand: stress (HTTP concurrency/latency profiling)
    stress_parser = subparsers.add_parser("stress", help="Execute stress and latency soak test via HTTP RPC Driver")
    stress_parser.add_argument("--target", choices=["media.take_photo", "device.get_status", "storage.get_status"],
                               default="media.take_photo", help="Target API to stress test")
    stress_parser.add_argument("--host", default=None, help="Board IP address (or set AXCK_BOARD_IP env)")
    stress_parser.add_argument("--port", type=int, default=80, help="HTTP port (default: 80)")
    stress_parser.add_argument("--requests", type=int, default=50, help="Total requests to send (default: 50)")
    stress_parser.add_argument("--concurrency", type=int, default=5, help="Concurrent worker threads (default: 5)")
    stress_parser.add_argument("--interval", type=float, default=0.0, help="Delay between requests per worker in seconds")

    # Subcommand: run-pipeline (End-to-end CI Automation Pipeline: probe + 54-item + AOV soak + reports)
    pipeline_parser = subparsers.add_parser("run-pipeline", help="Run end-to-end CI automation pipeline (probe + full 54 + AOV soak + report exports)")
    pipeline_parser.add_argument("--host", default=None, help="Board IP address (or set AXCK_BOARD_IP env)")
    pipeline_parser.add_argument("--port", type=int, default=80, help="HTTP port (default: 80)")
    pipeline_parser.add_argument("--telnet-port", type=int, default=23, help="Telnet port (default: 23)")
    pipeline_parser.add_argument("--aov-soak", type=int, default=15, help="AOV soak duration in seconds (default: 15)")
    pipeline_parser.add_argument("--export-dir", default=None, help="Directory to export test reports")

    # Subcommand: run-full (Full 54-item regression suite with JUnit XML / HTML reports)
    full_parser = subparsers.add_parser("run-full", help="Run full 54-item end-to-end regression suite with JSON/XML/HTML reports")
    full_parser.add_argument("--host", default=None, help="Board IP address (or set AXCK_BOARD_IP env)")
    full_parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    full_parser.add_argument("--export-dir", default=None, help="Directory to export test reports")

    # Subcommand: run-venc (VENC encoder discontinuous/continuous switching specialist tests)
    venc_parser = subparsers.add_parser("run-venc", help="Run VENC encoder discontinuous/continuous switching specialist tests")
    venc_parser.add_argument("--host", default=None, help="Board IP address (or set AXCK_BOARD_IP env)")
    venc_parser.add_argument("--port", type=int, default=80, help="HTTP port (default: 80)")
    venc_parser.add_argument("--export-dir", default=None, help="Directory to export test reports")

    # Subcommand: run (Legacy or Full Suite)
    run_parser = subparsers.add_parser("run", help="Run automated test suite with evidence archive")
    run_parser.add_argument("--driver", choices=["http", "uart"], default="http",
                            help="Driver type: http (default, clean RPC) or uart (legacy axck_test menu)")
    run_parser.add_argument("--suite", choices=["service", "media", "system", "all", "scenario-record-capture"], default="all",
                            help="Test suite or scenario to run")
    run_parser.add_argument("--token", default=None,
                            help="OxideTerm auth token (or env OXIDETERM_TOKEN)")
    run_parser.add_argument("--url", default=None,
                            help="OxideTerm MCP URL (or env OXIDETERM_URL, default: http://127.0.0.1:3412/mcp)")
    run_parser.add_argument("--connection-ref", default=None,
                            help="Connection reference (or env OXIDETERM_CONNECTION_REF)")
    run_parser.add_argument("--terminal-ref", default=None,
                            help="Existing terminal reference (or env OXIDETERM_TERMINAL_REF)")
    run_parser.add_argument("--host", default=None,
                            help="Board IP address for out-of-band Telnet inspection (auto-discovered if omitted)")
    run_parser.add_argument("--report", default=None,
                            help="JSON output path for test report")
    run_parser.add_argument("--nfs-path", default=None,
                            help="Base path on board NFS mount for evidence archive (or env AXCK_NFS_MOUNT_POINT)")
    run_parser.add_argument("--no-archive", action="store_true",
                            help="Disable evidence archiving to NFS")

    return parser


def handle_single_case(args):
    client = AxckClient(host=args.host, port=args.port)
    print(f"[axck-test] Executing single case '{args.case}' on {args.host}:{args.port}...")

    reporter = CaseReporter()

    # 初始化带外内存嗅探器
    inspector = None
    initial_mem = None
    try:
        inspector = TelnetInspector(host=args.host)
        if inspector.connect(retries=1):
            initial_mem = inspector.get_memory_snapshot()
    except Exception:
        inspector = None

    t0 = time.time()

    case_definitions = {
        "media.start_record": ("启动录像", "调用 HTTP CGI media_ctrl?cmd=start_record 开启实时录像流", lambda: client.media.start_record()),
        "media.stop_record": ("停止录像", "调用 HTTP CGI media_ctrl?cmd=stop_record 停止录像并封包 MP4", lambda: client.media.stop_record()),
        "media.take_photo": ("抓拍照片", "调用 HTTP CGI media_ctrl?cmd=take_photo 触发 JENC 抓拍", lambda: client.media.take_photo()),
        "media.start_urgent": ("紧急录像", "调用 HTTP CGI media_ctrl?cmd=start_urgent 触发加锁保护录像", lambda: client.media.start_urgent()),
        "media.switch_prev": ("切换预览", f"调用 HTTP CGI switch_prev?mode={args.param or 1} 切换屏幕预览模式", lambda: client.media.switch_prev(int(args.param) if args.param else 1)),
        
        # Audio domain
        "audio.set_mute": ("设置音频输入静音", f"调用 HTTP CGI audio_ctrl?cmd=set_mute&val={args.param or 1}", lambda: client.audio.set_mute(bool(int(args.param) if args.param else 1))),
        "audio.get_mute": ("获取音频输入静音", "调用 HTTP CGI audio_ctrl?cmd=get_mute", lambda: client.audio.get_mute()),
        "audio.set_vol": ("设置音频输出音量", f"调用 HTTP CGI audio_ctrl?cmd=set_vol&val={args.param or 80}", lambda: client.audio.set_volume(float(args.param) if args.param else 80.0)),
        "audio.get_vol": ("获取音频输出音量", "调用 HTTP CGI audio_ctrl?cmd=get_vol", lambda: client.audio.get_volume()),
        
        # Stream domain
        "stream.set_stream_on": ("开流/关流控制", f"调用 HTTP CGI stream_ctrl?cmd=set_stream_on&val={args.param or 1}", lambda: client.stream.set_stream_on(0, bool(int(args.param) if args.param else 1))),
        "stream.get_stream_on": ("获取开流状态", "调用 HTTP CGI stream_ctrl?cmd=get_stream_on", lambda: client.stream.get_stream_on(0)),
        "stream.set_mirror": ("水平镜像设置", f"调用 HTTP CGI stream_ctrl?cmd=set_mirror&val={args.param or 1}", lambda: client.stream.set_mirror(0, bool(int(args.param) if args.param else 1))),
        "stream.set_flip": ("垂直翻转设置", f"调用 HTTP CGI stream_ctrl?cmd=set_flip&val={args.param or 1}", lambda: client.stream.set_flip(0, bool(int(args.param) if args.param else 1))),
        "stream.set_fps": ("动态设置帧率", f"调用 HTTP CGI stream_ctrl?cmd=set_fps&val={args.param or 25}", lambda: client.stream.set_fps(0, float(args.param) if args.param else 25.0)),
        "stream.get_fps": ("获取当前帧率", "调用 HTTP CGI stream_ctrl?cmd=get_fps", lambda: client.stream.get_fps(0)),
        "stream.set_res": ("调整主码流分辨率", "调用 HTTP CGI stream_ctrl?cmd=set_res&w=2560&h=1440", lambda: client.stream.set_resolution(0, 0, 2560, 1440)),
        "stream.set_venc_type": ("切换VENC编码格式", f"调用 HTTP CGI stream_ctrl?cmd=set_venc_type&val={args.param or 0}", lambda: client.stream.set_venc_type(0, 0, bool(int(args.param) if args.param else 0))),
        
        # RTSP domain
        "rtsp.start": ("启动RTSP推流", "调用 HTTP CGI rtsp_ctrl?cmd=start", lambda: client.rtsp.start(0)),
        "rtsp.stop": ("停止RTSP推流", "调用 HTTP CGI rtsp_ctrl?cmd=stop", lambda: client.rtsp.stop(0)),
        
        # Storage domain
        "storage.get_status": ("存储状态查询", "调用 HTTP CGI get_storage_status 查询 TF 卡挂载与剩余容量", client.storage.get_status),
        "storage.format": ("格式化TF卡", "调用 HTTP CGI storage_ctrl?cmd=format 格式化 TF 卡", client.storage.format),
        "storage.mount": ("挂载TF卡", "调用 HTTP CGI storage_ctrl?cmd=mount 挂载 TF 卡", lambda: client.storage.mount(True)),
        "storage.unmount": ("卸载TF卡", "调用 HTTP CGI storage_ctrl?cmd=unmount 卸载 TF 卡", lambda: client.storage.unmount(False)),
        
        # DTCF domain
        "dtcf.get_file_count": ("DTCF文件统计", "调用 HTTP CGI get_file_count 查询媒体库索引计数", lambda: client.dtcf.get_file_count(int(args.param) if args.param else 0)),
        "dtcf.get_file_list": ("DTCF文件列表", "调用 HTTP CGI get_file_list 分页拉取录像及照片分片", lambda: client.dtcf.get_file_list(0, 0, 20)),
        "device.get_status": ("设备综合状态", "调用 HTTP CGI get_device_status 查询前后摄、TF卡、ACC等硬件状态", client.device.get_status),
        "aov.start": ("启动AOV模式", "调用 HTTP CGI aov_ctrl?cmd=start 进入低功耗保活模式", lambda: client.aov.control("start")),
        "aov.stop": ("退出AOV模式", "调用 HTTP CGI aov_ctrl?cmd=stop 恢复常规工作模式", lambda: client.aov.control("stop"))
    }

    title, method_desc, action = case_definitions.get(args.case, ("未命名用例", "直接执行 API 调用", lambda: None))
    resp = action()
    duration = time.time() - t0

    # 采集用例执行后的内存并计算差值
    mem_info = None
    delta_cmm_kb = 0
    delta_rss_kb = 0
    if inspector:
        try:
            cur_mem = inspector.get_memory_snapshot()
            if cur_mem and cur_mem.get("cmm_total_kb", 0) > 0:
                if initial_mem:
                    delta_cmm_kb = cur_mem.get("cmm_used_kb", 0) - initial_mem.get("cmm_used_kb", 0)
                    delta_rss_kb = cur_mem.get("vm_rss_kb", 0) - initial_mem.get("vm_rss_kb", 0)
                mem_info = dict(cur_mem)
                mem_info["delta_cmm_kb"] = delta_cmm_kb
                mem_info["delta_rss_kb"] = delta_rss_kb
        except Exception:
            pass
        finally:
            inspector.close()

    # 门限判断 Gates
    gates = {
        "HTTP_Status": {
            "desc": "HTTP协议状态码",
            "expected": "200",
            "actual": str(resp.status_code),
            "passed": resp.status_code == 200
        },
        "Biz_Code": {
            "desc": "业务执行返回码",
            "expected": "0 (ok)",
            "actual": f"{resp.code} ({resp.msg})",
            "passed": resp.code == 0
        }
    }
    if mem_info:
        gates["CMM_Leak_Check"] = {
            "desc": "单步物理CMM泄露门限 (<1MB)",
            "expected": "<1024KB",
            "actual": f"{delta_cmm_kb:+d}KB",
            "passed": delta_cmm_kb < 1024
        }
    if args.case == "storage.get_status" and resp.success and isinstance(resp.data, dict):
        gates["SD_Status"] = {
            "desc": "TF卡就绪状态",
            "expected": "0 (Mounted/Normal)",
            "actual": str(resp.data.get("sd_status")),
            "passed": resp.data.get("sd_status") == 0
        }
        gates["Free_Capacity"] = {
            "desc": "剩余可用空间大于0",
            "expected": "> 0 Byte",
            "actual": f"{resp.data.get('free_size')} Byte",
            "passed": resp.data.get("free_size", 0) > 0
        }
    elif args.case == "device.get_status" and resp.success and isinstance(resp.data, dict):
        all_st = resp.data.get("status_all", {})
        gates["Front_Camera"] = {
            "desc": "前置摄像头在线",
            "expected": "1 (Online)",
            "actual": str(all_st.get("front_status")),
            "passed": all_st.get("front_status") == 1
        }
        gates["SD_Card"] = {
            "desc": "SD存储卡在线",
            "expected": "1 (Online)",
            "actual": str(all_st.get("sdcard")),
            "passed": all_st.get("sdcard") == 1
        }

    inputs = {"host": args.host, "port": args.port, "case": args.case, "param": args.param}
    outputs = {"status_code": resp.status_code, "code": resp.code, "msg": resp.msg, "data": resp.data}

    reporter.report_case(
        suite_name="http-api",
        case_name=f"{args.case} ({title})",
        step_method=method_desc,
        inputs=inputs,
        outputs=outputs,
        gates=gates,
        memory_info=mem_info,
        status="PASS" if resp.success else "FAIL",
        duration=duration,
        error_msg=resp.error
    )

    sys.exit(0 if resp.success else 1)


def handle_run_scenario(args):
    client = AxckClient(host=args.host, port=args.port)
    print(f"[axck-test] Executing scenario pipeline '{args.scenario}' on {args.host}:{args.port}...")

    reporter = CaseReporter()

    # 初始化带外内存嗅探器
    inspector = None
    try:
        inspector = TelnetInspector(host=args.host)
        inspector.connect(retries=1)
    except Exception:
        inspector = None

    if args.scenario == "smoke":
        pipeline = (
            ScenarioBuilder("Smoke_Test")
            .step("check_device_status", lambda c: c.device.get_status(),
                  description="查询前后摄、TF卡及外设硬件综合状态")
            .step("check_storage_status", lambda c: c.storage.get_status(),
                  description="检查TF卡挂载状态、总容量与剩余空间")
            .step("start_record", lambda c: c.media.start_record(),
                  description="下发开启实时录像指令")
            .step("take_photo", lambda c: c.media.take_photo(), wait_after=1.0,
                  description="录像状态下触发动态 JPEG 抓拍")
            .step("stop_record", lambda c: c.media.stop_record(),
                  description="停止录像并校验 MP4 文件落盘封装")
            .build()
        )
    elif args.scenario == "burst-capture":
        pipeline = (
            ScenarioBuilder("Burst_Capture_Scenario")
            .step("check_storage", lambda c: c.storage.get_status(),
                  description="检查TF卡存储空间")
            .step("start_record", lambda c: c.media.start_record(),
                  description="开启主摄录像")
            .repeat("burst_photo", times=5, interval=0.5, action=lambda c: c.media.take_photo(),
                    description_prefix="触发突发连拍")
            .step("stop_record", lambda c: c.media.stop_record(),
                  description="停止录像")
            .build()
        )
    elif args.scenario == "continuous-record":
        pipeline = (
            ScenarioBuilder("Continuous_Record_Scenario")
            .step("start_record", lambda c: c.media.start_record(), wait_after=2.0,
                  description="开启主摄录像并持续推流")
            .step("switch_prev_stream", lambda c: c.media.switch_prev(1), wait_after=1.0,
                  description="录像过程中动态切换屏幕预览流")
            .step("take_photo", lambda c: c.media.take_photo(), wait_after=1.0,
                  description="动态抓拍高质量照片")
            .step("stop_record", lambda c: c.media.stop_record(),
                  description="停止录像并等待文件安全写盘")
            .build()
        )
    else:
        print(f"Unknown scenario: {args.scenario}")
        sys.exit(1)

    runner = ScenarioRunner(client, reporter=reporter, inspector=inspector)
    report = runner.run(pipeline)
    if inspector:
        inspector.close()

    print("\n" + "=" * 80)
    summary = reporter.get_summary()
    print(f"【场景测试完成】 场景: {report.scenario_name} | 总步骤: {summary['total']} | 成功: {summary['passed']} | 失败: {summary['failed']} | 总耗时: {summary['total_duration']}s")
    print("=" * 80 + "\n")

    if args.report:
        reporter.save_json(args.report)
        print(f"[axck-test] Report saved to {args.report}")

    sys.exit(0 if report.success else 1)


def handle_stress(args):
    client = AxckClient(host=args.host, port=args.port)
    print(f"[axck-test] Executing stress test against '{args.target}' (total={args.requests}, concurrency={args.concurrency})...")

    target_map = {
        "media.take_photo": lambda c: c.media.take_photo(),
        "device.get_status": lambda c: c.device.get_status(),
        "storage.get_status": lambda c: c.storage.get_status()
    }
    action = target_map[args.target]

    cfg = StressConfig(
        name=f"stress_{args.target}",
        total_requests=args.requests,
        concurrency=args.concurrency,
        interval=args.interval
    )

    runner = StressRunner(client)
    res = runner.run(action, cfg)

    out = {
        "name": res.name,
        "total_requests": res.total_requests,
        "success_count": res.success_count,
        "failed_count": res.failed_count,
        "duration_seconds": round(res.duration_seconds, 3),
        "qps": round(res.qps, 2),
        "latency_ms": {
            "min": res.min_latency_ms,
            "avg": res.avg_latency_ms,
            "p50": res.p50_latency_ms,
            "p90": res.p90_latency_ms,
            "p95": res.p95_latency_ms,
            "p99": res.p99_latency_ms,
            "max": res.max_latency_ms
        },
        "errors": res.error_summary
    }
    print(json.dumps(out, indent=2))
    sys.exit(0 if res.failed_count == 0 else 1)


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list-suites":
        suites = {
            "service": "Standalone axck_service daemon suite (process lifecycle, pipeline creation, steady streaming, stop)",
            "media": "Media subsystem test suite (stream on/off, fps check, multi-res switch with proc gates, capture, mp4 record, audio mute)",
            "system": "System test suite (Storage SD, DTCF, Device)",
            "all": "Full automated test run across service, media, and system subsystems",
            "scenario-record-capture": "Format + continuous record + multi-res capture scenario"
        }
        print(json.dumps(suites, indent=2))
        sys.exit(0)

    elif args.command == "inspect-proc":
        host = args.host
        if not host:
            driver = BoardSerialDriver()
            driver.acquire_terminal()
            host = driver.get_board_ip("eth0") or os.environ.get("AXCK_BOARD_IP", "127.0.0.1")
        print(f"[axck-test] Inspecting hardware status on {host}...")
        inspector = TelnetInspector(host=host)
        if inspector.connect():
            ivps = inspector.get_ivps_info()
            venc = inspector.get_venc_info()
            pid_srv = inspector.get_process_pid("axck_service")
            pid_tst = inspector.get_process_pid("axck_test")
            print(json.dumps({
                "host": host,
                "processes": {"axck_service": pid_srv, "axck_test": pid_tst},
                "ivps": {str(k): v for k, v in ivps.items()},
                "venc": venc
            }, indent=2))
            inspector.close()
        else:
            print(f"[axck-test] ERROR: Could not connect to Telnet on {host}")
            sys.exit(1)

    elif args.command == "single-case":
        handle_single_case(args)

    elif args.command == "run-scenario":
        handle_run_scenario(args)

    elif args.command == "stress":
        handle_stress(args)

    elif args.command == "run-pipeline":
        from axck_ci_pipeline import run_pipeline
        code = run_pipeline(
            host=args.host,
            port=args.port,
            telnet_port=args.telnet_port,
            aov_soak_sec=args.aov_soak,
            export_dir=args.export_dir
        )
        sys.exit(code)

    elif args.command == "run-full":
        from run_full_test import run_all_tests
        rep = run_all_tests(host=args.host, port=args.port, export_dir=args.export_dir)
        summary = rep.get_summary()
        sys.exit(0 if summary["failed"] == 0 else 1)

    elif args.command == "run-venc":
        from run_venc_test import run_venc_test
        p, f = run_venc_test(host=args.host, port=args.port, export_dir=args.export_dir)
        sys.exit(0 if f == 0 else 1)

    elif args.command == "run":
        # Check driver mode: if http mode requested for scenarios
        if args.driver == "http":
            print(f"[axck-test] Running test suite '{args.suite}' via HTTP Driver...")
            # For HTTP driver, map 'scenario-record-capture' directly to HTTP scenario runner
            if args.suite in ["scenario-record-capture", "all"]:
                class MockArgs:
                    scenario = "continuous-record"
                    host = args.host or os.environ.get("AXCK_BOARD_IP", "127.0.0.1")
                    port = 80
                    report = args.report
                handle_run_scenario(MockArgs())
                return

        # Fallback to legacy UART menu driver
        driver = BoardSerialDriver(
            token=args.token,
            url=args.url,
            connection_ref=args.connection_ref,
            terminal_ref=args.terminal_ref
        )
        term_ref = driver.acquire_terminal()
        print(f"[axck-test] Connected to serial terminal: {term_ref}")

        board_ip = args.host
        if not board_ip:
            board_ip = driver.get_board_ip("eth0") or os.environ.get("AXCK_BOARD_IP", "127.0.0.1")
            print(f"[axck-test] Detected board IP: {board_ip}")

        inspector = None
        try:
            inspector = TelnetInspector(host=board_ip)
            inspector.connect()
            print(f"[axck-test] Out-of-band Telnet inspector connected on {board_ip}")
        except Exception as e:
            print(f"[axck-test] WARNING: Telnet inspector connection failed: {e}. Running without proc gate.")
            inspector = None

        collector = None
        if inspector and not args.no_archive:
            collector = EvidenceCollector(
                inspector=inspector,
                nfs_base_path=args.nfs_path,
                task_name=f"task_{args.suite}"
            )
            collector.prepare_task_environment()
            print(f"[axck-test] Evidence archive initialized: {collector.board_task_dir}")

        reporter = CaseReporter()

        # Execute Suites or Scenarios
        if args.suite == "scenario-record-capture":
            print("\n[axck-test] Preparing board environment for scenario test...")
            driver.ensure_in_main_menu()
            scenario_runner = ContinuousRecordCaptureScenario(driver, inspector, reporter, evidence_collector=collector)
            scenario_runner.run(min_photos_per_res=10)
        else:
            if args.suite in ["service", "all"]:
                service_runner = ServiceSuiteRunner(driver, inspector, reporter, evidence_collector=collector)
                service_runner.run_all()

            if args.suite in ["media", "all"]:
                print("\n[axck-test] Preparing board environment for axck_test...")
                driver.ensure_in_main_menu()
                media_runner = MediaSuiteRunner(driver, inspector, reporter, evidence_collector=collector)
                media_runner.run_all()

            if args.suite in ["system", "all"]:
                driver.ensure_in_main_menu()
                system_runner = SystemSuiteRunner(driver, inspector, reporter, evidence_collector=collector)
                system_runner.run_all()

            if args.suite == "all":
                print("\n[axck-test] Executing Continuous Record + Multi-Res Capture Scenario...")
                driver.ensure_in_main_menu()
                scenario_runner = ContinuousRecordCaptureScenario(driver, inspector, reporter, evidence_collector=collector)
                scenario_runner.run(min_photos_per_res=10)

        # Build full report payload
        summary = reporter.get_summary()
        report_payload = {
            "summary": summary,
            "cases": reporter.cases,
            "task_info": {
                "suite": args.suite,
                "host": board_ip,
                "terminal_ref": term_ref
            }
        }

        # Finalize Evidence Archive
        archive_info = {}
        if collector:
            archive_info = collector.finalize_task(report_payload, local_report_path=args.report)
            print(f"[axck-test] Evidence successfully archived to Board: {archive_info.get('evidence_dir_on_board')}")
            print(f"[axck-test] Corresponds to NAS Path: {archive_info.get('evidence_dir_on_nas')}")
        elif args.report:
            reporter.save_json(args.report)
            print(f"[axck-test] Structured report written locally to {args.report}")

        if inspector:
            inspector.close()

        total = summary["total"]
        passed = summary["passed"]
        failed = summary["failed"]
        print(f"\n===========================================================================")
        print(f"[axck-test] Full Execution Summary: {total} Cases | {passed} PASSED | {failed} FAILED")
        if archive_info.get("evidence_dir_on_board"):
            print(f"[axck-test] Evidence Directory : {archive_info.get('evidence_dir_on_board')}")
            print(f"[axck-test] NAS Archive Path    : {archive_info.get('evidence_dir_on_nas')}")
        print(f"===========================================================================")

        sys.exit(0 if failed == 0 else 2)


if __name__ == "__main__":
    main()
