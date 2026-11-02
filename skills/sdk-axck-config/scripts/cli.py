#!/usr/bin/env python3
"""
axck-tool (Config & Pipeline): CLI for AX615 camera-kit configuration inspection,
pipeline validation, interpolation scaling, and sensor migration.
"""
import sys
import os
import argparse
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import inspect as inspect_mod
import validate as validate_mod
import migrate as migrate_mod

def cmd_inspect(args):
    config_dir = args.config_dir or os.getcwd()
    result = inspect_mod.inspect_config(config_dir, args.project)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"=== Camera-Kit Configuration Inspection ===")
        print(f"Config Directory: {result['config_dir']}")
        print(f"Files Found:")
        for k, v in result['files_found'].items():
            status = "✓" if v else "✗ MISSING"
            print(f"  - {k:16s}: {status}")
        
        if result['variants']:
            print(f"\nVariant Files ({result['variant_files_count']}):")
            for v in result['variants']:
                print(f"  - {v}")

        if result['sensors']:
            print(f"\nConfigured Sensors ({len(result['sensors'])}):")
            for s in result['sensors']:
                pos_str = "Front (0)" if s['cam_pos'] == 0 else f"Rear ({s['cam_pos']})"
                print(f"  [{s['index']}] {s['sensor_name']} ({pos_str})")
                print(f"      Resolution : {s['resolution']}")
                print(f"      Hardware   : I2C Dev {s['i2c_dev']} @ {s['i2c_addr']}, MCLK {s['mclk_id']}, Lanes {s['lanes']}")
                print(f"      Pipeline   : DevID {s['dev_id']}, PipeID {s['pipe_id']}, SettingIndex {s['settingindex']}")

        if result.get("pipeline_summary", {}).get("pipelines"):
            print(f"\nConfigured Pipelines ({len(result['pipeline_summary']['pipelines'])}):")
            for pl in result['pipeline_summary']['pipelines']:
                status = "ENABLED" if pl['enable'] else "DISABLED"
                print(f"  - Pipeline [{pl['type']}] ({status}): {len(pl['ivps'])} IVPS groups")

def cmd_validate(args):
    config_dir = args.config_dir or os.getcwd()
    validator = validate_mod.AxckValidator(
        config_dir=config_dir,
        dual=args.dual,
        sensor_suffix=args.sensor_suffix
    )
    report = validator.run()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        status_str = "PASSED" if report.get("valid", False) else "FAILED"
        print(f"=== Camera-Kit Configuration Validation: [{status_str}] ===")
        print(f"Platform    : {report.get('platform', 'Unknown')}")
        print(f"Project     : {report.get('project', 'Unknown')}")
        print(f"Config Path : {report.get('config_dir')}")
        print(f"Errors      : {report.get('error_count', 0)}")
        print(f"Warnings    : {report.get('warning_count', 0)}")

        if report.get("errors"):
            print("\nErrors:")
            for err in report["errors"]:
                print(f"  [ERROR] {err}")

        if report.get("warnings"):
            print("\nWarnings:")
            for warn in report["warnings"]:
                print(f"  [WARN]  {warn}")

        if report.get("topology"):
            print("\nTopology:")
            for line in report["topology"]:
                print(f"  {line}")

        if not report.get("valid", False):
            sys.exit(1)

def cmd_migrate(args):
    config_dir = args.config_dir or os.getcwd()
    migrator = migrate_mod.AxckSensorMigrator(
        config_dir=config_dir,
        dual=args.dual,
        sync_video_streams=not args.no_sync_video
    )
    if args.rollback:
        success = migrator.rollback(args.rollback)
        if not success:
            sys.exit(1)
        return

    if not args.sensor:
        print("Error: Target sensor (-s / --sensor) is required for migration.")
        sys.exit(1)

    result = migrator.migrate_sensor(
        target_sensor=args.sensor,
        cam_pos=args.cam_pos,
        dry_run=args.dry_run,
        force_lanes=args.lanes,
        force_mclk=args.mclk
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status_str = "SUCCESS" if result.get("success", False) else "FAILED"
        print(f"=== Camera-Kit Sensor Migration: [{status_str}] ===")
        print(f"Target Sensor : {result.get('new_sensor', args.sensor)}")
        print(f"Previous      : {result.get('old_sensor')}")
        print(f"Camera Pos    : {args.cam_pos} ({'Front' if args.cam_pos == 0 else 'Rear'})")
        print(f"Dry Run       : {result.get('dry_run')}")

        if result.get("app_diff"):
            print(f"\n--- app_config.json Diff ---")
            print(result["app_diff"])

        if result.get("sns_diff"):
            print(f"\n--- sns_info.json Diff ---")
            print(result["sns_diff"])

        if result.get("backup_dir"):
            print(f"\nBackup created at: {result['backup_dir']}")

        if result.get("errors"):
            print("\nErrors:")
            for err in result["errors"]:
                print(f"  [ERROR] {err}")

        if not result.get("success", False):
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="axck-tool (Config & Pipeline): Inspect, validate, scale, and migrate AX615 camera-kit configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to execute")

    # Inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect and summarize camera-kit JSON configurations")
    p_inspect.add_argument("-c", "--config-dir", help="Path to config directory (default: current dir)")
    p_inspect.add_argument("-p", "--project", help="Project name (e.g. demo, cust, p105)")
    p_inspect.add_argument("--json", action="store_true", help="Output raw JSON")
    p_inspect.set_defaults(func=cmd_inspect)

    # Validate
    p_validate = subparsers.add_parser("validate", help="Validate static hardware, IVPS, and VENC/JENC constraints")
    p_validate.add_argument("-c", "--config-dir", help="Path to config directory (default: current dir)")
    p_validate.add_argument("--dual", action="store_true", help="Enforce dual-camera validation")
    p_validate.add_argument("--sensor-suffix", help="Suffix of sensor variant to test (e.g. sc431hai, xs9950)")
    p_validate.add_argument("--json", action="store_true", help="Output raw JSON")
    p_validate.set_defaults(func=cmd_validate)

    # Migrate
    p_migrate = subparsers.add_parser("migrate", help="Migrate sensor model and update pipeline configuration")
    p_migrate.add_argument("-c", "--config-dir", help="Path to config directory (default: current dir)")
    p_migrate.add_argument("-s", "--sensor", help="Target sensor name (SC431HAI, SC465SL, OS04D10, XS9950, MIS20S1)")
    p_migrate.add_argument("--cam-pos", type=int, default=0, help="Camera position (0=front, 1=rear)")
    p_migrate.add_argument("--dual", action="store_true", help="Dual camera configuration")
    p_migrate.add_argument("--dry-run", action="store_true", help="Simulate changes without writing files")
    p_migrate.add_argument("--lanes", type=int, help="Override MIPI lanes count")
    p_migrate.add_argument("--mclk", help="Override MCLK rate (e.g. 24m, 27m)")
    p_migrate.add_argument("--no-sync-video", action="store_true", help="Do not sync video stream resolutions in app_config.json")
    p_migrate.add_argument("--rollback", help="Timestamp of backup to rollback to (e.g. 20260916_163000)")
    p_migrate.add_argument("--json", action="store_true", help="Output raw JSON")
    p_migrate.set_defaults(func=cmd_migrate)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
