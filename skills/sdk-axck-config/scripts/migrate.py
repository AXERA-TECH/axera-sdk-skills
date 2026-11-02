#!/usr/bin/env python3
"""
axck_sensor_migrator.py - AXAP camera-kit Sensor Migration & Pipeline Topology Switcher

Capabilities:
1. Migrating single/dual camera sensor models (SC438HAI, SC431HAI, SC431AI, OS04D10, MIS20S1, XS9950, SC533HAI, SC235HAI, SC465SL, TP9963).
2. Hardware contract auto-resolution:
   - settingindex selection based on single/dual cam, resolution, fps, lanes, and MCLK.
   - MCLK rate ("24m" vs "27m") synchronization with chosen settingindex.
   - D-PHY lane mapping ("lane_4" vs "lane_2") preventing physical lane collisions.
   - dev_id enforcement (YUV AHD must use dev_id 1 or 2; RAW uses 0).
   - Board GPIOs (reset_gpio 69 for sensor 0, 66 for sensor 1, power_gpio 71 for AHD on Demo board; 99 for p105).
   - I2C bus (i2c_dev 1 for Demo, 5 for p105, 0 for Cust) and 7-bit slave address.
3. Synchronizing app_config.json camera and video streams to match sensor resolution & frame rate.
4. Unified Diff preview (--dry-run) and timestamped automatic backup (.backup_YYYYMMDD_HHMMSS).
5. Automatic post-migration validation hook calling axck_config_validator.py.
"""

import sys
import os
import json
import shutil
import argparse
import difflib
import subprocess
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

SENSOR_CATALOG: Dict[str, Dict[str, Any]] = {
    "SC438HAI": {
        "sns_id": 19,
        "type": "raw",
        "pixel_fmt": "raw10bpppkd",
        "width": 2688,
        "height": 1520,
        "fps": 30.0,
        "raw_type": "raw10",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x30,
        "dev_id": 0,
        "lib": "libsns_sc438hai.so",
        "obj": "gSnssc438haiObj",
        "tuning_bin_sdr": "/opt/etc/sc438hai_sdr.bin",
        "tuning_bin_hdr": "/opt/etc/sc438hai_hdr_2x.bin",
        # Single cam uses 4-lane 27M; Dual cam uses 2-lane 24M or 27M
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "27m", "lane": "lane_4", "fps": 30.0, "w": 2688, "h": 1520},
        "dual_cam_preset":   {"settingindex": [-1, 3, -1], "mclk": "24m", "lane": "lane_2", "fps": 30.0, "w": 2688, "h": 1520}
    },
    "SC431HAI": {
        "sns_id": 14,
        "type": "raw",
        "pixel_fmt": "raw10bpppkd",
        "width": 2560,
        "height": 1440,
        "fps": 25.0,
        "raw_type": "raw10",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x30,
        "dev_id": 0,
        "lib": "libsns_sc431hai.so",
        "obj": "gSnssc431haiObj",
        "tuning_bin_sdr": "/opt/etc/sc431hai_sdr_t_aiisp_reduce_fps.bin",
        "tuning_bin_hdr": "/opt/etc/sc431hai_hdr_2x.bin",
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 2560, "h": 1440},
        "dual_cam_preset":   {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 2560, "h": 1440}
    },
    "SC431AI": {
        "sns_id": 17,
        "type": "raw",
        "pixel_fmt": "raw10bpppkd",
        "width": 2560,
        "height": 1440,
        "fps": 30.0,
        "raw_type": "raw10",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x30,
        "dev_id": 0,
        "lib": "libsns_sc431ai.so",
        "obj": "gSnssc431aiObj",
        "tuning_bin_sdr": "/opt/etc/sc431ai_sdr.bin",
        "tuning_bin_hdr": "/opt/etc/sc431ai_hdr_2x.bin",
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_4", "fps": 30.0, "w": 2688, "h": 1520},
        "dual_cam_preset":   {"settingindex": [-1, 33, -1], "mclk": "27m", "lane": "lane_2", "fps": 30.0, "w": 2560, "h": 1440}
    },
    "OS04D10": {
        "sns_id": 1,
        "type": "raw",
        "pixel_fmt": "raw10bpppkd",
        "width": 2560,
        "height": 1440,
        "fps": 30.0,
        "raw_type": "raw10",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x36,
        "dev_id": 0,
        "lib": "libsns_os04d10.so",
        "obj": "gSnsos04d10Obj",
        "tuning_bin_sdr": "/opt/etc/os04d10_sdr.bin",
        "tuning_bin_hdr": "/opt/etc/os04d10_hdr_2x.bin",
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 30.0, "w": 2560, "h": 1440},
        "dual_cam_preset":   {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 30.0, "w": 2560, "h": 1440}
    },
    "MIS20S1": {
        "sns_id": 8,
        "type": "raw",
        "pixel_fmt": "raw10bpppkd",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "raw_type": "raw10",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x30,
        "dev_id": 0,
        "lib": "libsns_mis20s1.so",
        "obj": "gSnsmis20s1Obj",
        "tuning_bin_sdr": "/opt/etc/mis20s1_sdr.bin",
        "tuning_bin_hdr": "/opt/etc/mis20s1_hdr_2x.bin",
        "single_cam_preset": {"settingindex": [-1, 2, -1], "mclk": "24m", "lane": "lane_2", "fps": 30.0, "w": 1920, "h": 1080},
        "dual_cam_preset":   {"settingindex": [-1, 2, -1], "mclk": "24m", "lane": "lane_2", "fps": 30.0, "w": 1920, "h": 1080}
    },
    "XS9950": {
        "sns_id": 6,
        "type": "yuv",
        "pixel_fmt": "yuv422",
        "width": 1920,
        "height": 1080,
        "fps": 25.0,
        "raw_type": "yuv422",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x30,
        "dev_id": 1, # CRITICAL AX615 RULE: MIPI YUV MUST USE DEV 1 OR 2
        "lib": "libsns_xs9950.so",
        "obj": "gSnsxs9950Obj",
        "tuning_bin_sdr": "",
        "tuning_bin_hdr": "",
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 1920, "h": 1080},
        "dual_cam_preset":   {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 1920, "h": 1080}
    },
    "TP9963": {
        "sns_id": 11,
        "type": "yuv",
        "pixel_fmt": "yuv422",
        "width": 1920,
        "height": 1080,
        "fps": 25.0,
        "raw_type": "yuv422",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x45,
        "dev_id": 1,
        "lib": "libsns_tp9963.so",
        "obj": "gSnstp9963Obj",
        "tuning_bin_sdr": "",
        "tuning_bin_hdr": "",
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 1920, "h": 1080},
        "dual_cam_preset":   {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 1920, "h": 1080}
    },
    "SC533HAI": {
        "sns_id": 21,
        "type": "raw",
        "pixel_fmt": "raw10bpppkd",
        "width": 2880,
        "height": 1620,
        "fps": 25.0,
        "raw_type": "raw10",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x30,
        "dev_id": 0,
        "lib": "libsns_sc533hai.so",
        "obj": "gSnssc533haiObj",
        "tuning_bin_sdr": "/opt/etc/sc533hai_sdr.bin",
        "tuning_bin_hdr": "/opt/etc/sc533hai_hdr_2x.bin",
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 2880, "h": 1620},
        "dual_cam_preset":   {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 2880, "h": 1620}
    },
    "SC235HAI": {
        "sns_id": 20,
        "type": "raw",
        "pixel_fmt": "raw10bpppkd",
        "width": 1920,
        "height": 1080,
        "fps": 25.0,
        "raw_type": "raw10",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x30,
        "dev_id": 0,
        "lib": "libsns_sc235hai.so",
        "obj": "gSnssc235haiObj",
        "tuning_bin_sdr": "/opt/etc/sc235hai_sdr.bin",
        "tuning_bin_hdr": "/opt/etc/sc235hai_hdr_2x.bin",
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 1920, "h": 1080},
        "dual_cam_preset":   {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 1920, "h": 1080}
    },
    "SC465SL": {
        "sns_id": 12,
        "type": "raw",
        "pixel_fmt": "raw10bpppkd",
        "width": 2560,
        "height": 1440,
        "fps": 25.0,
        "raw_type": "raw10",
        "bayer_pattern": "rggb",
        "default_i2c_addr": 0x30,
        "dev_id": 0,
        "lib": "libsns_sc465sl.so",
        "obj": "gSnssc465slObj",
        "tuning_bin_sdr": "/opt/etc/sc465sl_sdr.bin",
        "tuning_bin_hdr": "/opt/etc/sc465sl_hdr_2x.bin",
        "single_cam_preset": {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 2560, "h": 1440},
        "dual_cam_preset":   {"settingindex": [-1, 1, -1], "mclk": "24m", "lane": "lane_2", "fps": 25.0, "w": 2560, "h": 1440}
    }
}

class AxckSensorMigrator:
    def __init__(self, config_dir: str, dual: bool = False, sync_video_streams: bool = True):
        self.config_dir = os.path.abspath(config_dir)
        self.dual = dual
        self.sync_video_streams = sync_video_streams

        # Parse platform and project
        parts = self.config_dir.strip(os.sep).split(os.sep)
        self.project = parts[-1] if len(parts) >= 1 else "demo"
        self.platform = parts[-2] if len(parts) >= 2 else "AX615D"

        suffix = "_dual.json" if dual else ".json"
        self.app_cfg_path = os.path.join(self.config_dir, f"app_config{suffix}")
        self.ppl_cfg_path = os.path.join(self.config_dir, f"ppl_config{suffix}")
        self.sns_cfg_path = os.path.join(self.config_dir, f"sns_info{suffix}")

    def _resolve_hardware_pins(self, cam_pos: int, s_meta: Dict[str, Any]) -> Tuple[int, int, Optional[int]]:
        """
        Returns (i2c_dev, reset_gpio, power_gpio) based on platform/project and cam position.
        """
        if self.project == "p105":
            i2c_dev = 5
            reset_gpio = 99 # virtual reset
            power_gpio = None
        elif self.project == "cust":
            i2c_dev = 0
            if cam_pos == 0:
                reset_gpio = 70
                power_gpio = None
            else:
                reset_gpio = 66
                power_gpio = 71
        else:
            # Default AX615D Demo board
            i2c_dev = 1
            if cam_pos == 0:
                reset_gpio = 69 # SENSOR0_RSTN
                power_gpio = None
            else:
                reset_gpio = 66 # SENSOR1 / AHD RSTN
                power_gpio = 71 # AHD power enable

        return i2c_dev, reset_gpio, power_gpio

    def migrate_sensor(self, target_sensor: str, cam_pos: int = 0, dry_run: bool = False,
                       force_lanes: Optional[int] = None, force_mclk: Optional[str] = None) -> Dict[str, Any]:
        target_sensor_key = target_sensor.upper()
        if target_sensor_key not in SENSOR_CATALOG:
            return {
                "success": False,
                "error": f"Unsupported sensor {target_sensor}. Available: {list(SENSOR_CATALOG.keys())}"
            }

        s_meta = SENSOR_CATALOG[target_sensor_key]
        preset = s_meta["dual_cam_preset"] if self.dual else s_meta["single_cam_preset"]

        # Override lanes or mclk if requested
        mipi_lane = f"lane_{force_lanes}" if force_lanes else preset["lane"]
        mclk_rate = force_mclk if force_mclk else preset["mclk"]
        settingindex = preset["settingindex"]
        target_fps = preset["fps"]
        target_w = preset["w"]
        target_h = preset["h"]

        if not os.path.isfile(self.app_cfg_path):
            return {"success": False, "error": f"app_config not found: {self.app_cfg_path}"}
        if not os.path.isfile(self.sns_cfg_path):
            return {"success": False, "error": f"sns_info not found: {self.sns_cfg_path}"}

        with open(self.app_cfg_path, "r", encoding="utf-8") as f:
            old_app_str = f.read()
            app_cfg = json.loads(old_app_str)

        with open(self.sns_cfg_path, "r", encoding="utf-8") as f:
            old_sns_str = f.read()
            sns_cfg = json.loads(old_sns_str)

        cameras = app_cfg.get("camera", [])
        if cam_pos >= len(cameras):
            return {
                "success": False,
                "error": f"Camera pos {cam_pos} not found in app_config (total cameras: {len(cameras)})"
            }

        target_cam = cameras[cam_pos]
        old_sns_name = target_cam.get("sns_name", "UNKNOWN")

        # 1. Update app_config.json camera settings
        target_cam["sns_name"] = target_sensor_key
        target_cam["sns_id"] = s_meta["sns_id"]
        target_cam["frame_rate"] = int(target_fps)
        target_cam["dev_id"] = s_meta["dev_id"] if s_meta["type"] == "yuv" else (0 if cam_pos == 0 else 1)

        # 2. Update video streams if enabled (synchronize primary video resolution to sensor native)
        if self.sync_video_streams:
            videos = app_cfg.get("video", [])
            # Find primary video for this camera
            for v in videos:
                if v.get("cam_id") == cam_pos and v.get("main_stream", 0) == 1:
                    v["width"] = target_w
                    v["height"] = target_h
                    v["frame_rate"] = int(target_fps)
                    break

        # 3. Resolve hardware pins
        i2c_dev, reset_gpio, power_gpio = self._resolve_hardware_pins(cam_pos, s_meta)

        # 4. Update or add sensor in sns_info.json
        sns_entry = None
        for s in sns_cfg:
            if s.get("sns_id") == s_meta["sns_id"] or s.get("sns_name", "").upper() == target_sensor_key:
                sns_entry = s
                break

        if sns_entry:
            sns_entry["sns_name"] = target_sensor_key
            sns_entry["sns_id"] = s_meta["sns_id"]
            sns_entry["sns_ahd"] = 1 if s_meta["type"] == "yuv" else 0
            sns_entry["i2c_dev"] = i2c_dev
            sns_entry["reset_gpio"] = reset_gpio
            if power_gpio is not None:
                sns_entry["power_gpio"] = power_gpio
            elif "power_gpio" in sns_entry and cam_pos == 0:
                del sns_entry["power_gpio"]

            sns_entry["sns_attr"]["width"] = target_w
            sns_entry["sns_attr"]["height"] = target_h
            sns_entry["sns_attr"]["frame_rate"] = target_fps
            sns_entry["sns_attr"]["settingindex"] = settingindex

            sns_entry["sns_clk"]["clk_rate"] = mclk_rate

            sns_entry["dev_attr"]["width"] = target_w
            sns_entry["dev_attr"]["height"] = target_h
            sns_entry["dev_attr"]["pixel_fmt"] = s_meta["pixel_fmt"]

            sns_entry["pipe_attr"]["width"] = target_w
            sns_entry["pipe_attr"]["height"] = target_h
            sns_entry["pipe_attr"]["ai_isp_enable"] = 1 if s_meta["type"] == "raw" else 0

            sns_entry["mipi_attr"]["lane"] = mipi_lane
        else:
            new_entry: Dict[str, Any] = {
                "sns_name": target_sensor_key,
                "sns_id": s_meta["sns_id"],
                "sns_ahd": 1 if s_meta["type"] == "yuv" else 0,
                "i2c_dev": i2c_dev,
                "i2c_addr": s_meta["default_i2c_addr"],
                "reset_gpio": reset_gpio,
                "sns_lib": {
                    "lib": s_meta["lib"],
                    "obj": s_meta["obj"]
                },
                "sns_attr": {
                    "sns_mode": 1,
                    "settingindex": settingindex,
                    "width": target_w,
                    "height": target_h,
                    "raw_type": s_meta["raw_type"],
                    "bayer_pattern": s_meta["bayer_pattern"],
                    "frame_rate": target_fps
                },
                "sns_clk": {
                    "clk_idx": 0,
                    "clk_rate": mclk_rate
                },
                "dev_attr": {
                    "dev_mode": "online",
                    "sns_type": "mipi",
                    "width": target_w,
                    "height": target_h,
                    "pixel_fmt": s_meta["pixel_fmt"]
                },
                "pipe_attr": {
                    "mode": "normal",
                    "width": target_w,
                    "height": target_h,
                    "ai_isp_enable": 1 if s_meta["type"] == "raw" else 0
                },
                "mipi_attr": {
                    "lane": mipi_lane
                }
            }
            if power_gpio is not None:
                new_entry["power_gpio"] = power_gpio

            sns_cfg.append(new_entry)

        new_app_str = json.dumps(app_cfg, indent=4, ensure_ascii=False) + "\n"
        new_sns_str = json.dumps(sns_cfg, indent=4, ensure_ascii=False) + "\n"

        app_diff = "".join(difflib.unified_diff(
            old_app_str.splitlines(keepends=True),
            new_app_str.splitlines(keepends=True),
            fromfile=self.app_cfg_path,
            tofile=self.app_cfg_path
        ))

        sns_diff = "".join(difflib.unified_diff(
            old_sns_str.splitlines(keepends=True),
            new_sns_str.splitlines(keepends=True),
            fromfile=self.sns_cfg_path,
            tofile=self.sns_cfg_path
        ))

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "old_sensor": old_sns_name,
                "new_sensor": target_sensor_key,
                "app_diff": app_diff,
                "sns_diff": sns_diff,
                "hardware_contract": {
                    "platform": self.platform,
                    "project": self.project,
                    "cam_pos": cam_pos,
                    "settingindex": settingindex,
                    "mclk": mclk_rate,
                    "lane": mipi_lane,
                    "i2c_dev": i2c_dev,
                    "reset_gpio": reset_gpio,
                    "power_gpio": power_gpio,
                    "dev_id": target_cam["dev_id"]
                }
            }

        # Create timestamped backup
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(self.config_dir, f".backup_{ts}")
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(self.app_cfg_path, os.path.join(backup_dir, os.path.basename(self.app_cfg_path)))
        shutil.copy2(self.sns_cfg_path, os.path.join(backup_dir, os.path.basename(self.sns_cfg_path)))

        with open(self.app_cfg_path, "w", encoding="utf-8") as f:
            f.write(new_app_str)
        with open(self.sns_cfg_path, "w", encoding="utf-8") as f:
            f.write(new_sns_str)

        return {
            "success": True,
            "dry_run": False,
            "backup_dir": backup_dir,
            "old_sensor": old_sns_name,
            "new_sensor": target_sensor_key,
            "app_diff": app_diff,
            "sns_diff": sns_diff,
            "hardware_contract": {
                "platform": self.platform,
                "project": self.project,
                "cam_pos": cam_pos,
                "settingindex": settingindex,
                "mclk": mclk_rate,
                "lane": mipi_lane,
                "i2c_dev": i2c_dev,
                "reset_gpio": reset_gpio,
                "power_gpio": power_gpio,
                "dev_id": target_cam["dev_id"]
            }
        }

def main():
    sdk_root = os.environ.get("AX615_SDK_ROOT") or os.environ.get("SDK_ROOT")
    default_dir = os.path.join(sdk_root, "camera-kit", "service", "res", "config", "AX615D", "demo") if sdk_root else os.getcwd()
    parser = argparse.ArgumentParser(description="AXAP AX615 camera-kit Sensor Migration Tool")
    parser.add_argument("--config-dir", "-d", default=default_dir, help=f"Path to config dir (default: {default_dir})")
    parser.add_argument("--sensor", "-s", required=True, help="Target sensor name (SC438HAI, SC431HAI, SC431AI, OS04D10, MIS20S1, XS9950, etc.)")
    parser.add_argument("--cam-pos", "-p", type=int, default=0, help="Camera index to replace (0: Front, 1: Rear)")
    parser.add_argument("--dual", action="store_true", help="Operate on dual cam config (_dual.json)")
    parser.add_argument("--lanes", type=int, choices=[2, 4], help="Explicitly force MIPI lane count")
    parser.add_argument("--mclk", choices=["24m", "27m"], help="Explicitly force MCLK frequency")
    parser.add_argument("--dry-run", action="store_true", help="Preview diff without modifying files")
    parser.add_argument("--validate", action="store_true", help="Run axck_config_validator after migration")
    args = parser.parse_args()

    migrator = AxckSensorMigrator(args.config_dir, dual=args.dual)
    res = migrator.migrate_sensor(
        args.sensor,
        cam_pos=args.cam_pos,
        dry_run=args.dry_run,
        force_lanes=args.lanes,
        force_mclk=args.mclk
    )

    if not res["success"]:
        print(f"[ERROR] Migration failed: {res['error']}", file=sys.stderr)
        return 1

    print("========================================================")
    print(f" AXAP camera-kit Sensor Migration ({'PREVIEW / DRY RUN' if args.dry_run else 'COMMITTED'})")
    print(f" Target Sensor: {res['new_sensor']} (Replaced: {res['old_sensor']})")
    print(f" Target Config: {args.config_dir} (Platform: {res['hardware_contract']['platform']}, Project: {res['hardware_contract']['project']})")
    print(f" Hardware Contracts Applied:")
    hc = res['hardware_contract']
    print(f"   - MIPI Lane: {hc['lane']} | MCLK: {hc['mclk']} | settingindex: {hc['settingindex']}")
    print(f"   - dev_id: {hc['dev_id']} | I2C Dev: {hc['i2c_dev']} | Reset GPIO: {hc['reset_gpio']} | Power GPIO: {hc['power_gpio']}")
    if not args.dry_run:
        print(f" Rollback Backup Created: {res['backup_dir']}")
    print("========================================================")

    if res["app_diff"]:
        print("\n--- app_config.json Unified Diff ---")
        print(res["app_diff"])
    if res["sns_diff"]:
        print("\n--- sns_info.json Unified Diff ---")
        print(res["sns_diff"])

    # Optional validation run
    if args.validate or not args.dry_run:
        print("\n🔎 Running post-migration validation...")
        # Search for validator script
        validator_script = os.path.join(os.path.dirname(__file__), "validate.py")
        if not os.path.isfile(validator_script):
            validator_script = os.path.join(os.path.dirname(__file__), "..", "..", "sdk-axck-check-config", "scripts", "axck_config_validator.py")

        if os.path.isfile(validator_script):
            cmd = [sys.executable, validator_script, "-d", args.config_dir]
            if args.dual:
                cmd.append("--dual")
            p = subprocess.run(cmd)
            if p.returncode != 0:
                print("⚠️  Warning: Post-migration validation reported warnings or errors. Check report above.")
            else:
                print("✅ Post-migration validation passed cleanly.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
