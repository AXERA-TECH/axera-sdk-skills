#!/usr/bin/env python3
"""
axck-tool (Doctor/Diag): CLI for AX615 camera-kit boot/runtime log ingestion,
AXERA error code decoding, and first-root-cause fault isolation.
"""
import sys
import os
import argparse
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import doctor as doctor_mod

def cmd_doctor(args):
    log_content = ""
    if args.log_file:
        with open(args.log_file, "r", encoding="utf-8", errors="ignore") as f:
            log_content = f.read()
    elif not sys.stdin.isatty():
        log_content = sys.stdin.read()
    else:
        print("Error: No log file provided and stdin is empty. Use -f <logfile> or pipe logs via stdin.")
        sys.exit(1)

    diagnoser = doctor_mod.AxckLogDiagnoser(log_content)
    result = diagnoser.diagnose()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status_str = "ISSUES DETECTED" if result.get("detected_issues", 0) > 0 else "CLEAN"
        print(f"=== Camera-Kit Doctor Diagnostic Report: [{status_str}] ===")
        print(f"Total Lines Scanned : {result.get('total_lines', 0)}")
        print(f"Detected Issues     : {result.get('detected_issues', 0)}")

        if result.get("module_summary"):
            print("Issues by Module    :")
            for mod, cnt in result["module_summary"].items():
                print(f"  - {mod:12s}: {cnt}")

        if result.get("root_cause"):
            rc = result["root_cause"]
            print(f"\n>>> FIRST ROOT CAUSE IDENTIFIED (Line {rc.get('line_num')}) <<<")
            print(f"Module           : {rc.get('module')}")
            print(f"Category         : {rc.get('category')}")
            print(f"Severity         : {rc.get('severity')}")
            print(f"Raw Log Line     : {rc.get('raw_line')}")
            print(f"Root Cause       : {rc.get('explanation')}")
            print(f"Actionable Fix   : {rc.get('action')}")

        if result.get("recommendations"):
            print("\nActionable Recommendations:")
            for rec in result["recommendations"]:
                print(f"  - {rec}")

def main():
    parser = argparse.ArgumentParser(
        description="axck-tool (Doctor/Diag): Analyze boot/runtime logs and isolate first root cause",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to execute")

    # Doctor
    p_doctor = subparsers.add_parser("doctor", help="Analyze boot/runtime logs and locate first root cause")
    p_doctor.add_argument("-f", "--log-file", help="Path to log file (or pass via stdin)")
    p_doctor.add_argument("--json", action="store_true", help="Output raw JSON")
    p_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
