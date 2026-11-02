#!/usr/bin/env python3
"""
axck-tool (App & Build): CLI for AX615 camera-kit application module compilation,
build environment inspection, and target orchestration.
"""
import sys
import os
import argparse
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import build as build_mod

def cmd_build(args):
    ck_root = build_mod.find_camera_kit_root(args.path or os.getcwd())
    if not ck_root:
        print(f"Error: Could not locate camera-kit root from: {args.path or os.getcwd()}")
        sys.exit(1)

    if args.inspect:
        info = build_mod.inspect_build_env(ck_root)
        if args.json:
            print(json.dumps(info, indent=2, ensure_ascii=False))
        else:
            print("=== Camera-Kit Build Environment ===")
            print(f"Camera-Kit Root : {info['camera_kit_root']}")
            print(f"SDK Root        : {info['sdk_root']}")
            print(f"Current Project : {info['current_project']}")
            print(f"Has Build Env   : {'✓' if info['has_build_env'] else '✗'}")
            print(f"Available Projs : {', '.join(info['available_projects'])}")
            print(f"Modules         : {', '.join(info['build_subdirs'])}")
        return

    res = build_mod.run_build(
        ck_root=ck_root,
        module=args.module,
        target=args.target,
        project=args.project,
        dry_run=args.dry_run
    )

    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        if args.dry_run:
            print("=== Camera-Kit Build Simulation (Dry Run) ===")
            print(f"Command : {res['command']}")
            print(f"Workdir : {res['workdir']}")
            print(f"Target  : {res['target']}")
            print(f"Module  : {res['module']}")
            print(f"Project : {res.get('project')}")
        else:
            status = "SUCCESS" if res.get("success", False) else "FAILED"
            print(f"=== Camera-Kit Build [{status}] ===")
            print(f"Command : {res.get('command')}")
            if res.get("stdout"):
                print("\n[STDOUT]")
                print(res["stdout"])
            if res.get("stderr"):
                print("\n[STDERR]")
                print(res["stderr"])
            if not res.get("success", False):
                sys.exit(res.get("returncode", 1))

def main():
    parser = argparse.ArgumentParser(
        description="axck-tool (App/Build): Compile and orchestrate AX615 camera-kit application modules",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to execute")

    # Build
    p_build = subparsers.add_parser("build", help="Inspect, dry-run, or execute camera-kit build targets")
    p_build.add_argument("-p", "--path", help="Path to camera-kit directory or parent")
    p_build.add_argument("-m", "--module", help="Sub-module to build (3rd, com, service, client, apps, apps/test, apps/dvcam)")
    p_build.add_argument("-t", "--target", default="all", choices=["all", "install", "clean"], help="Make target (default: all)")
    p_build.add_argument("--project", help="Target project (e.g. AX615_dashcam_nor)")
    p_build.add_argument("--inspect", action="store_true", help="Inspect build environment and project settings")
    p_build.add_argument("--dry-run", action="store_true", help="Print make command without executing")
    p_build.add_argument("--json", action="store_true", help="Output raw JSON")
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
