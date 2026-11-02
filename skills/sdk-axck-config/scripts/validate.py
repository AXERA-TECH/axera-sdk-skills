#!/usr/bin/env python3
"""
axck_config_validator.py - AXAP camera-kit (AXCK) Configuration Validator & Topology Analyzer

Deep static validator for AXERA camera-kit (AXCK) on AX615/AX615D and related platforms.
Verifies hardware pin contracts, I2C/GPIO configurations, MIPI PHY mappings, ISP dev_id constraints,
pipeline cascading, resolution/stride alignments, and VENC/JENC channel conflicts.
"""

import sys
import os
import json
import argparse
from typing import Dict, List, Any, Tuple, Optional, Set

def load_json(path: str) -> Tuple[Optional[Any], Optional[str]]:
    if not os.path.isfile(path):
        return None, f"File not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, f"JSON parse error in {path}: {str(e)}"

# ----------------------------------------------------------------------
# Hardware Matrix & Constraints for AX615D
# ----------------------------------------------------------------------
AX615_VALID_I2C_DEVS = {0, 1, 2, 5}
AX615_KNOWN_SENSOR_I2C_ADDRS = {
    "SC438HAI": [0x30, 0x0],
    "SC431HAI": [0x30, 0x0],
    "SC431AI":  [0x30, 0x0],
    "SC533HAI": [0x30, 0x0],
    "SC235HAI": [0x30, 0x0],
    "SC465SL":  [0x30, 0x0],
    "MIS20S1":  [0x30, 0x0],
    "OS04D10":  [0x36, 0x10, 0x0],
    "XS9950":   [0x30, 0x33, 0x0],
    "TP9963":   [0x45, 0x44, 0x0],
}

# Key GPIO pins on AX615D Demo board
AX615_VALID_GPIO_RANGES = range(0, 96) # 0 to 95
VIRTUAL_OR_SPECIAL_GPIOS = {99, -1} # 99: internal / dummy reset, -1: none

# SIF clock and pixel processing capability on AX615 (SDK 12 Doc, Section 5.9)
AX615_SIF_FREQ_MHZ = 367.0
AX615_SIF_PIXELS_PER_CYCLE = 2.0

# Sensor SettingIndex Hardware Presets & Constraints Dictionary
# Mapping: Sensor -> Index -> {mode, width, height, fps, lanes, mclk, mipi_rate_mbps, desc}
SENSOR_SETTINGS_SPECS: Dict[str, Dict[int, Dict[str, Any]]] = {
    "SC438HAI": {
        1: {"mode": "SDR", "width": 2688, "height": 1520, "fps": 30.0, "lanes": 4, "mclk": 27, "rate": 900, "desc": "4L_27M_900M_30fps"},
        2: {"mode": "HDR", "width": 2688, "height": 1520, "fps": 30.0, "lanes": 4, "mclk": 27, "rate": 756, "desc": "4L_27M_756M_30fps_HDR"},
        3: {"mode": "SDR", "width": 2688, "height": 1520, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 900, "desc": "2L_24M_900M_30fps"},
        4: {"mode": "HDR", "width": 2688, "height": 1520, "fps": 25.0, "lanes": 2, "mclk": 24, "rate": 1188, "desc": "2L_24M_1188M_25fps_HDR"},
        5: {"mode": "SDR", "width": 2688, "height": 1520, "fps": 30.0, "lanes": 4, "mclk": 27, "rate": 720, "desc": "4L_27M_720M_30fps"},
        6: {"mode": "HDR", "width": 2688, "height": 1520, "fps": 30.0, "lanes": 4, "mclk": 27, "rate": 720, "desc": "4L_27M_720M_30fps_HDR"},
        7: {"mode": "SDR", "width": 2688, "height": 1520, "fps": 30.0, "lanes": 2, "mclk": 27, "rate": 900, "desc": "2L_27M_900M_30fps"},
        8: {"mode": "HDR", "width": 2688, "height": 1520, "fps": 25.0, "lanes": 2, "mclk": 27, "rate": 1188, "desc": "2L_27M_1188M_25fps_HDR"},
    },
    "SC431HAI": {
        1: {"mode": "SDR", "width": 2560, "height": 1440, "fps": 25.0, "lanes": 2, "mclk": 24, "rate": 630, "desc": "2L_24M_630M_25fps"},
        2: {"mode": "HDR", "width": 2560, "height": 1440, "fps": 25.0, "lanes": 2, "mclk": 24, "rate": 1080, "desc": "2L_24M_1080M_25fps_HDR"},
        3: {"mode": "SDR", "width": 2560, "height": 1440, "fps": 30.0, "lanes": 4, "mclk": 27, "rate": 315, "desc": "4L_27M_315M_30fps"},
        4: {"mode": "HDR", "width": 2560, "height": 1440, "fps": 30.0, "lanes": 4, "mclk": 27, "rate": 652, "desc": "4L_27M_652M_30fps_HDR"},
    },
    "SC431AI": {
        1: {"mode": "SDR", "width": 2688, "height": 1520, "fps": 30.0, "lanes": 4, "mclk": 24, "rate": 360, "desc": "4L_24M_360M_30fps"},
        2: {"mode": "HDR", "width": 2688, "height": 1520, "fps": 30.0, "lanes": 4, "mclk": 24, "rate": 720, "desc": "4L_24M_720M_30fps_HDR"},
        33: {"mode": "SDR", "width": 2560, "height": 1440, "fps": 30.0, "lanes": 2, "mclk": 27, "rate": 720, "desc": "2L_27M_720M_30fps_1440P"},
        34: {"mode": "SDR", "width": 2688, "height": 1520, "fps": 25.0, "lanes": 2, "mclk": 24, "rate": 720, "desc": "2L_24M_720M_25fps"},
        35: {"mode": "HDR", "width": 2688, "height": 1520, "fps": 25.0, "lanes": 2, "mclk": 24, "rate": 1120, "desc": "2L_24M_1120M_25fps_HDR"},
    },
    "OS04D10": {
        0: {"mode": "SDR", "width": 2560, "height": 1440, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 720, "desc": "2L_24M_720M_30fps_default"},
        1: {"mode": "SDR", "width": 2560, "height": 1440, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 720, "desc": "2L_24M_720M_30fps"},
    },
    "MIS20S1": {
        0: {"mode": "SDR", "width": 1920, "height": 1080, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 594, "desc": "2L_RAW12_30fps"},
        1: {"mode": "HDR", "width": 1920, "height": 1080, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 594, "desc": "2L_HDR_RAW12_30fps"},
        2: {"mode": "SDR", "width": 1920, "height": 1080, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 594, "desc": "2L_RAW10_30fps"},
        3: {"mode": "HDR", "width": 1920, "height": 1080, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 594, "desc": "2L_HDR_RAW10_30fps"},
        5: {"mode": "SDR", "width": 1920, "height": 1080, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 594, "desc": "2L_RAW12_30fps_VBLANK6MS"},
        6: {"mode": "HDR", "width": 1920, "height": 1080, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 594, "desc": "2L_HDR_RAW12_30fps_VBLANK6MS"},
    },
    "XS9950": {
        1: {"mode": "SDR", "width": 1920, "height": 1080, "fps": 25.0, "lanes": 2, "mclk": 24, "rate": 594, "desc": "AHD_1080P_25FPS_2LANE"},
        2: {"mode": "SDR", "width": 1920, "height": 1080, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 594, "desc": "AHD_1080P_30FPS_2LANE"},
        3: {"mode": "SDR", "width": 1280, "height": 720, "fps": 25.0, "lanes": 2, "mclk": 24, "rate": 297, "desc": "AHD_720P_25FPS_2LANE"},
        4: {"mode": "SDR", "width": 1280, "height": 720, "fps": 30.0, "lanes": 2, "mclk": 24, "rate": 297, "desc": "AHD_720P_30FPS_2LANE"},
        33: {"mode": "SDR", "width": 1920, "height": 1080, "fps": 25.0, "lanes": 0, "mclk": 24, "rate": 0, "desc": "AHD_1080P_25FPS_BT656"},
        34: {"mode": "SDR", "width": 1920, "height": 1080, "fps": 30.0, "lanes": 0, "mclk": 24, "rate": 0, "desc": "AHD_1080P_30FPS_BT656"},
    },
}

class AxckValidator:
    def __init__(self, config_dir: str, dual: bool = False, sensor_suffix: Optional[str] = None):
        self.config_dir = os.path.abspath(config_dir)
        self.dual = dual
        self.sensor_suffix = sensor_suffix
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.topology: List[str] = []
        self.hardware_summary: List[str] = []

        # Determine platform and project from path if possible
        self.platform = "AX615D"
        self.project = "demo"
        parts = self.config_dir.strip(os.sep).split(os.sep)
        if len(parts) >= 2:
            self.project = parts[-1]
            self.platform = parts[-2]

        # Determine file names
        if self.sensor_suffix:
            s_suf = f"_{self.sensor_suffix}.json"
            self.app_cfg_path = os.path.join(self.config_dir, f"app_config{s_suf}")
            self.ppl_cfg_path = os.path.join(self.config_dir, f"ppl_config{s_suf}")
            self.sns_cfg_path = os.path.join(self.config_dir, f"sns_info{s_suf}")
        elif self.dual:
            self.app_cfg_path = os.path.join(self.config_dir, "app_config_dual.json")
            self.ppl_cfg_path = os.path.join(self.config_dir, "ppl_config_dual.json")
            self.sns_cfg_path = os.path.join(self.config_dir, "sns_info_dual.json")
        else:
            self.app_cfg_path = os.path.join(self.config_dir, "app_config.json")
            self.ppl_cfg_path = os.path.join(self.config_dir, "ppl_config.json")
            self.sns_cfg_path = os.path.join(self.config_dir, "sns_info.json")

    def run(self) -> Dict[str, Any]:
        self.info.append(f"Target Platform: {self.platform} | Project: {self.project}")
        self.info.append(f"Config Path: {self.config_dir}")

        app_cfg, err = load_json(self.app_cfg_path)
        if err:
            self.errors.append(err)
        ppl_cfg, err = load_json(self.ppl_cfg_path)
        if err:
            self.errors.append(err)
        sns_cfg, err = load_json(self.sns_cfg_path)
        if err:
            self.errors.append(err)

        if not app_cfg or not ppl_cfg or not sns_cfg:
            return self._build_report()

        # Execute check phases
        self._validate_sensors_and_hardware(app_cfg, sns_cfg)
        self._validate_pipeline(app_cfg, ppl_cfg, sns_cfg)
        self._validate_memory_pools_and_interpolation(app_cfg, ppl_cfg, sns_cfg)
        self._validate_venc_and_jenc(app_cfg, ppl_cfg)
        self._build_topology_summary(app_cfg, ppl_cfg, sns_cfg)

        return self._build_report()

    def _validate_sensors_and_hardware(self, app_cfg: Dict[str, Any], sns_cfg: List[Dict[str, Any]]):
        cameras = app_cfg.get("camera", [])
        if not cameras:
            self.errors.append("app_config.json has empty 'camera' array")
            return

        active_cameras = [c for c in cameras if c.get("sns_enable", 1) != 0]
        is_dual = self.dual or len(active_cameras) >= 2 or "dual" in os.path.basename(self.app_cfg_path)
        if self.dual and len(active_cameras) < 2:
            self.errors.append(f"Dual-cam requested but app_config only has {len(active_cameras)} active camera(s) (sns_enable!=0)")

        sns_map = {item.get("sns_id"): item for item in sns_cfg if isinstance(item, dict)}

        used_mipi_lanes: Set[int] = set()
        used_i2c_ports: Set[Tuple[int, int]] = set() # (i2c_dev, i2c_addr)

        for cam_idx, cam in enumerate(cameras):
            sns_enabled = cam.get("sns_enable", 1) != 0
            sns_id = cam.get("sns_id")
            sns_name = cam.get("sns_name", "UNKNOWN").upper()
            pos = cam.get("sns_pos", cam_idx)
            pos_label = "Front" if pos == 0 else "Rear"
            status_label = "ACTIVE" if sns_enabled else "DISABLED"
            self.info.append(f"Camera #{cam_idx} ({pos_label}) [{status_label}]: Sensor {sns_name} (sns_id={sns_id})")

            if not sns_enabled:
                if sns_id not in sns_map:
                    self.info.append(f"Camera #{cam_idx} is disabled (sns_enable=0); dormant sns_id {sns_id} omitted from sns_info.json")
                continue

            if sns_id not in sns_map:
                self.errors.append(f"Active Camera #{cam_idx} refers to sns_id {sns_id} which does not exist in sns_info.json")
                continue

            s_entry = sns_map[sns_id]
            s_attr = s_entry.get("sns_attr", {})
            s_width = s_attr.get("width", 0)
            s_height = s_attr.get("height", 0)
            s_fps = s_attr.get("frame_rate")
            cam_fps = cam.get("frame_rate")

            # 1. Check Resolution & Framerate Consistency
            if s_fps is not None and cam_fps is not None and abs(float(s_fps) - float(cam_fps)) > 0.01:
                self.warnings.append(
                    f"Camera #{cam_idx} frame_rate in app_config ({cam_fps}fps) does not match sns_attr in sns_info ({s_fps}fps)"
                )

            # 1.1 Deep SettingIndex & Hardware Timings Consistency Check
            settingindex = s_entry.get("settingindex", [])
            sns_mode = s_attr.get("sns_mode", 1) # 1: SDR/Linear, 2: HDR
            clean_sns_name = sns_name.replace("LIBSNS_", "").replace(".SO", "").strip()
            matched_sns_key = None
            for k in SENSOR_SETTINGS_SPECS:
                if k in clean_sns_name:
                    matched_sns_key = k
                    break

            if matched_sns_key and settingindex and isinstance(settingindex, list) and len(settingindex) >= 3:
                target_idx = settingindex[2] if sns_mode == 2 else settingindex[1]
                specs_map = SENSOR_SETTINGS_SPECS[matched_sns_key]

                if target_idx in specs_map:
                    spec = specs_map[target_idx]
                    spec_w = spec["width"]
                    spec_h = spec["height"]
                    spec_fps = spec["fps"]
                    spec_lanes = spec["lanes"]
                    spec_mclk = spec["mclk"]
                    spec_mode = spec["mode"]
                    spec_desc = spec["desc"]

                    # Check resolution match
                    if s_width > 0 and s_height > 0 and (s_width != spec_w or s_height != spec_h):
                        self.errors.append(
                            f"SettingIndex Conflict: Sensor {sns_name} settingindex[{sns_mode}]={target_idx} ({spec_desc}) "
                            f"hardcodes resolution {spec_w}x{spec_h}, but sns_attr.width/height is {s_width}x{s_height}! "
                            f"Driver will write register timings for {spec_w}x{spec_h} causing frame truncation/sync error."
                        )

                    # Check mode match (SDR vs HDR)
                    if (sns_mode == 1 and spec_mode != "SDR") or (sns_mode == 2 and spec_mode != "HDR"):
                        self.errors.append(
                            f"SettingIndex Mode Mismatch: Sensor {sns_name} sns_mode={sns_mode} ({'HDR' if sns_mode==2 else 'SDR'}) "
                            f"but settingindex target {target_idx} is configured for {spec_mode} ({spec_desc})!"
                        )

                    # Check MCLK clock rate match
                    sns_clk = s_entry.get("sns_clk", {})
                    clk_rate_str = str(sns_clk.get("clk_rate", "")).lower()
                    if clk_rate_str:
                        expected_clk_str = f"{spec_mclk}m"
                        if expected_clk_str not in clk_rate_str:
                            self.errors.append(
                                f"Sensor Clock Mismatch: Sensor {sns_name} settingindex target {target_idx} ({spec_desc}) "
                                f"requires {spec_mclk}MHz MCLK, but sns_clk.clk_rate is '{clk_rate_str}'! "
                                f"This will cause framerate and MIPI bitrate to shift by {(abs(spec_mclk - (24 if '24' in clk_rate_str else 27))/spec_mclk)*100:.1f}%."
                            )

                    # Check Lane Mode match
                    m_attr = s_entry.get("mipi_attr", {})
                    configured_lanes = 4 if m_attr.get("lane") == "lane_4" else (2 if m_attr.get("lane") == "lane_2" else 0)
                    if spec_lanes > 0 and configured_lanes > 0 and spec_lanes != configured_lanes:
                        self.errors.append(
                            f"MIPI Lane Count Mismatch: Sensor {sns_name} settingindex target {target_idx} ({spec_desc}) "
                            f"is hardcoded for {spec_lanes}-Lane MIPI, but mipi_attr.lane is '{m_attr.get('lane')}' ({configured_lanes} lanes)!"
                        )

                    self.info.append(
                        f"Sensor {sns_name} settingindex {target_idx} validated against driver preset: {spec_desc} "
                        f"({spec_w}x{spec_h}@{spec_fps}fps, {spec_lanes}L, {spec_mclk}MHz MCLK)"
                    )
                elif target_idx > 0:
                    self.warnings.append(
                        f"Sensor {sns_name}: settingindex[{sns_mode}]={target_idx} is not in standard verified dictionary for {matched_sns_key}. "
                        f"Verify that <sensor>_settings.h defines this index."
                    )

            # 1.2 AX615 SIF Hardware Processing Throughput & Minimum Line Time Check
            # Rule (SDK 12 Doc 5.9): min_line_time_us = width / AX615_SIF_FREQ_MHZ / AX615_SIF_PIXELS_PER_CYCLE
            if s_width > 0:
                min_line_time_us = s_width / AX615_SIF_FREQ_MHZ / AX615_SIF_PIXELS_PER_CYCLE
                self.info.append(
                    f"Sensor {sns_name}: Width={s_width} -> AX615 SIF Hardware min_line_time = {min_line_time_us:.3f} us (SIF: 367MHz, 2 pix/cycle)"
                )

            # 2. Check I2C Hardware Contract
            i2c_dev = s_entry.get("i2c_dev")
            i2c_addr = s_entry.get("i2c_addr")

            if i2c_dev is not None:
                if i2c_dev not in AX615_VALID_I2C_DEVS:
                    self.errors.append(
                        f"Sensor {sns_name} (sns_id={sns_id}): i2c_dev={i2c_dev} is invalid on AX615 (valid: {sorted(list(AX615_VALID_I2C_DEVS))})"
                    )

            if i2c_addr is not None:
                # 7-bit vs 8-bit check
                if i2c_addr > 0x7F:
                    self.errors.append(
                        f"Sensor {sns_name} (sns_id={sns_id}): i2c_addr=0x{i2c_addr:02X} ({i2c_addr}) exceeds 7-bit I2C address range! "
                        f"AX615 Linux driver requires 7-bit slave address (e.g. 0x30 instead of 8-bit 0x60)."
                    )
                else:
                    # Check against known sensor addresses
                    clean_name = sns_name.replace("LIBSNS_", "").replace(".SO", "").strip()
                    matched_sns = None
                    for k in AX615_KNOWN_SENSOR_I2C_ADDRS:
                        if k in clean_name:
                            matched_sns = k
                            break
                    if matched_sns:
                        valid_addrs = AX615_KNOWN_SENSOR_I2C_ADDRS[matched_sns]
                        if i2c_addr not in valid_addrs:
                            hex_valid = [f"0x{a:02X}" for a in valid_addrs]
                            self.warnings.append(
                                f"Sensor {sns_name} (sns_id={sns_id}): i2c_addr 0x{i2c_addr:02X} ({i2c_addr}) is unusual for {matched_sns} (expected {hex_valid})"
                            )

                # Check I2C address conflicts on same bus
                if i2c_dev is not None and i2c_addr > 0:
                    port_key = (i2c_dev, i2c_addr)
                    if port_key in used_i2c_ports:
                        self.errors.append(
                            f"Hardware I2C Conflict: Multiple sensors share I2C bus {i2c_dev} and slave address 0x{i2c_addr:02X}"
                        )
                    used_i2c_ports.add(port_key)

            # 3. Check GPIO Pin Contracts (Reset & Power)
            rst_gpio = s_entry.get("reset_gpio")
            pwr_gpio = s_entry.get("power_gpio")

            if rst_gpio is not None and rst_gpio not in VIRTUAL_OR_SPECIAL_GPIOS:
                if rst_gpio not in AX615_VALID_GPIO_RANGES:
                    self.warnings.append(
                        f"Sensor {sns_name} (sns_id={sns_id}): reset_gpio={rst_gpio} is outside standard AX615 GPIO range (0-95, 99=dummy)"
                    )
                # Check Demo board recommendations
                if self.platform == "AX615D" and self.project == "demo":
                    if pos == 0 and rst_gpio != 69 and rst_gpio != 99:
                        self.warnings.append(
                            f"AX615D Demo Board Check: Cam #0 (Front) typically uses SENSOR0_RSTN GPIO 69 (configured: {rst_gpio})"
                        )
                    elif pos == 1 and rst_gpio != 66 and rst_gpio != 99:
                        self.warnings.append(
                            f"AX615D Demo Board Check: Cam #1 (Rear/AHD) typically uses AHD_RESET GPIO 66 (configured: {rst_gpio})"
                        )

            if pwr_gpio is not None and pwr_gpio not in VIRTUAL_OR_SPECIAL_GPIOS:
                if pwr_gpio not in AX615_VALID_GPIO_RANGES:
                    self.warnings.append(
                        f"Sensor {sns_name} (sns_id={sns_id}): power_gpio={pwr_gpio} is outside standard AX615 GPIO range (0-95)"
                    )
                if self.platform == "AX615D" and self.project == "demo" and pos == 1:
                    if pwr_gpio != 71:
                        self.warnings.append(
                            f"AX615D Demo Board Check: AHD Rear Cam typically uses AHD_PWR_ON GPIO 71 (configured: {pwr_gpio})"
                        )

            # 4. Check MIPI Lane Mapping & PHY Constraints
            mipi_attr = s_entry.get("mipi_attr", {})
            lane_mode = mipi_attr.get("lane", "")
            lane_map = mipi_attr.get("lane_map", [])
            clk_lane = mipi_attr.get("clk_lane", [])
            rx_dev = cam.get("rx_dev", cam_idx)

            if lane_mode == "lane_4":
                if is_dual:
                    self.errors.append(
                        f"MIPI PHY Conflict: Sensor {sns_name} is configured for 'lane_4' in a Dual-camera system. "
                        f"AX615 MIPI RX PHY only has 4 data lanes + 2 clock lanes in total. "
                        f"Dual cameras must use 2Lane + 2Lane (or 2Lane MIPI + BT656/DVP)."
                    )
                expected_map = [0, 1, 3, 4]
                if lane_map and lane_map != expected_map:
                    self.warnings.append(
                        f"Sensor {sns_name}: 4-Lane mode lane_map is {lane_map}, expected standard physical mapping [0, 1, 3, 4]"
                    )
            elif lane_mode == "lane_2":
                # In AX615 DPHY architecture:
                # RX0 (Sensor 1): Data lanes RX_CD0, RX_CD1 (index 0, 1), Clk RX_CD2 (index 2)
                # RX1 (Sensor 2): Data lanes RX_CD3, RX_CD4 (index 3, 4), Clk RX_CD5 (index 5)
                # When rx_dev == 0, physical data lanes are 0, 1
                # When rx_dev == 1, physical data lanes are 3, 4
                if rx_dev == 0:
                    sensor_physical_lanes = [0, 1]
                elif rx_dev == 1:
                    sensor_physical_lanes = [3, 4]
                else:
                    sensor_physical_lanes = [l for l in lane_map if l >= 0][:2]

                for l in sensor_physical_lanes:
                    if l in used_mipi_lanes:
                        self.errors.append(f"MIPI PHY Lane Conflict: Physical Lane {l} is shared between multiple sensors!")
                    used_mipi_lanes.add(l)

            # 5. Check AX615 dev_id vs YUV / RAW
            dev_attr = s_entry.get("dev_attr", {})
            pixel_fmt = str(dev_attr.get("pixel_fmt", "")).lower()
            sns_type = str(dev_attr.get("sns_type", "")).lower()
            dev_id = cam.get("dev_id", 0)

            if ("yuv" in pixel_fmt or "yuv" in sns_type or s_entry.get("sns_ahd", 0) == 1) and dev_id == 0:
                self.errors.append(
                    f"AX615 Hardware Iron Rule Violation: Camera #{cam_idx} ({sns_name}) dev_id is 0, but pixel_fmt/type is YUV ({pixel_fmt}/{sns_type}). "
                    f"On AX615, dev_id 0 is hardware-dedicated to SIF RAW ISP pipeline. "
                    f"YUV/AHD sensors (e.g. XS9950) must set dev_id to 1 or 2!"
                )

            # 6. Check vin_ivps_mode vs Rotation & LDC
            vin_ivps_mode = cam.get("vin_ivps_mode", 0)
            rotate = cam.get("rotate", 0)
            if rotate in (1, 3) and vin_ivps_mode == 2:
                self.warnings.append(
                    f"Camera #{cam_idx}: 90/270 degree rotation requested with vin_ivps_mode=2 (AX_ITP_ONLINE_VPP). "
                    f"AX615 ITP line-buffer cannot sustain real-time 90/270 transpose in online mode. "
                    f"Recommend vin_ivps_mode=1 (AX_GDC_ONLINE_VPP) or mode 0 (OFFLINE)."
                )

            # Summary for hardware block
            rst_str = f"GPIO{rst_gpio}" if rst_gpio is not None else "None"
            pwr_str = f"GPIO{pwr_gpio}" if pwr_gpio is not None else "None"
            i2c_str = f"I2C{i2c_dev}@0x{i2c_addr:02X}" if (i2c_dev is not None and i2c_addr is not None) else "None"
            self.hardware_summary.append(
                f"Cam[{cam_idx}] {pos_label}: {sns_name} | {i2c_str} | Reset={rst_str}, Pwr={pwr_str} | Lane={lane_mode}"
            )

    def _validate_pipeline(self, app_cfg: Dict[str, Any], ppl_cfg: List[Dict[str, Any]], sns_cfg: List[Dict[str, Any]]):
        if not isinstance(ppl_cfg, list):
            self.errors.append("ppl_config top-level must be a list of pipelines")
            return

        cameras = app_cfg.get("camera", [])
        cam_count = len(cameras)

        for p_idx, p in enumerate(ppl_cfg):
            p_type = p.get("type", f"pipe_{p_idx}")
            enable = p.get("enable", 1)
            if not enable:
                self.info.append(f"Pipeline {p_type} is disabled.")
                continue

            ivps_list = p.get("ivps", [])
            for ivps in ivps_list:
                grp = ivps.get("group")
                filters = ivps.get("filter", [])
                outputs = ivps.get("output", [])

                # Check group input filter
                if filters:
                    first_f = filters[0]
                    f_w = first_f.get("width", 0)
                    f_h = first_f.get("height", 0)
                    if f_w % 2 != 0 or f_h % 2 != 0:
                        self.errors.append(f"Pipeline {p_type} IVPS Group {grp} input filter dimensions must be even (got {f_w}x{f_h})")

                # Check channels
                for out in outputs:
                    chn = out.get("chnl")
                    ch_filters = out.get("filter", [])
                    for cf in ch_filters:
                        cw = cf.get("width", 0)
                        ch = cf.get("height", 0)
                        if cw > 0 and cw % 2 != 0:
                            self.errors.append(f"Pipeline {p_type} IVPS Grp {grp} Chn {chn} width must be even (got {cw})")
                        if ch > 0 and ch % 2 != 0:
                            self.errors.append(f"Pipeline {p_type} IVPS Grp {grp} Chn {chn} height must be even (got {ch})")

                        # Stride / alignment check
                        if cw > 0 and cw % 16 != 0:
                            self.warnings.append(
                                f"Pipeline {p_type} IVPS Grp {grp} Chn {chn} width ({cw}) is not 16-aligned. "
                                f"May require software stride compensation in VENC/Display."
                            )

    def _validate_memory_pools_and_interpolation(self, app_cfg: Dict[str, Any], ppl_cfg: List[Dict[str, Any]], sns_cfg: List[Dict[str, Any]]):
        pool = app_cfg.get("pool", {})
        common_pools = pool.get("common", [])
        private_pools = pool.get("private", [])

        common_dims = [(cp.get("width", 0), cp.get("height", 0)) for cp in common_pools]
        private_dims = [(pp.get("width", 0), pp.get("height", 0)) for pp in private_pools]

        # 1. Check IVPS upscaling (interpolation)
        for p in ppl_cfg:
            if not p.get("enable", 1):
                continue
            p_type = p.get("type", "unknown")
            for ivps in p.get("ivps", []):
                grp = ivps.get("group", 0)
                in_w, in_h = 0, 0
                if ivps.get("filter"):
                    in_w = ivps["filter"][0].get("width", 0)
                    in_h = ivps["filter"][0].get("height", 0)

                for out in ivps.get("output", []):
                    chn = out.get("chnl", 0)
                    for f in out.get("filter", []):
                        out_w = f.get("width", 0)
                        out_h = f.get("height", 0)
                        engine = f.get("engine", "")
                        scl_type = f.get("scl_type", 0)

                        if in_w > 0 and in_h > 0 and (out_w > in_w or out_h > in_h):
                            scale_w = round(out_w / in_w, 2)
                            scale_h = round(out_h / in_h, 2)
                            self.info.append(
                                f"Interpolation (Scale Up) detected in Pipeline [{p_type}] IVPS Grp {grp} Chn {chn}: "
                                f"{in_w}x{in_h} -> {out_w}x{out_h} (Ratio {scale_w}x{scale_h}, engine '{engine}', scl_type {scl_type})"
                            )
                            if engine not in ["scl", "vpp"]:
                                self.errors.append(
                                    f"Pipeline [{p_type}] IVPS Grp {grp} Chn {chn} upscales {in_w}x{in_h} to {out_w}x{out_h} "
                                    f"using unsupported engine '{engine}'. AX615 upscaling requires 'scl' or 'vpp'."
                                )

        # 2. Check Cache vout against pool.common
        for p in ppl_cfg:
            if not p.get("enable", 1):
                continue
            p_type = p.get("type", "unknown")
            for c_idx, cache in enumerate(p.get("cache", [])):
                vout = cache.get("vout", {})
                vw = vout.get("width", 0)
                vh = vout.get("height", 0)
                if vw > 0 and vh > 0:
                    matched = any(pw == vw and ph == vh for pw, ph in common_dims)
                    if not matched:
                        self.errors.append(
                            f"Pool Mismatch: Pipeline [{p_type}] cache[{c_idx}] vout ({vw}x{vh}) has no matching "
                            f"pool.common entry in app_config.json! Available common pools: {common_dims}"
                        )
                    # Check SW_LOW_MEM circular buffer pool (height <= 256)
                    low_mem_pools = [cp for cp in common_pools if cp.get("height", 0) <= 256 and cp.get("width", 0) == vw]
                    if not low_mem_pools:
                        self.warnings.append(
                            f"Pipeline [{p_type}] cache[{c_idx}] stream width {vw} has no low-memory slice pool "
                            f"(e.g. {vw}x128) in pool.common. Low-memory ring-buffer encoding may fail."
                        )

    def _validate_venc_and_jenc(self, app_cfg: Dict[str, Any], ppl_cfg: List[Dict[str, Any]]):
        video_venc_channels: Dict[int, str] = {}
        jenc_channels: Dict[int, str] = {}

        for p_idx, p in enumerate(ppl_cfg):
            p_type = p.get("type", f"pipe_{p_idx}")
            for c_idx, cache in enumerate(p.get("cache", [])):
                v_chn = cache.get("enc_chnl")
                if v_chn is not None:
                    if v_chn in video_venc_channels:
                        self.errors.append(
                            f"VENC Channel Conflict: enc_chnl {v_chn} is allocated to multiple video caches "
                            f"({video_venc_channels[v_chn]} and {p_type}.cache[{c_idx}])"
                        )
                    video_venc_channels[v_chn] = f"{p_type}.cache[{c_idx}]"

                thumb = cache.get("thumb", {})
                if thumb.get("enable"):
                    t_chn = thumb.get("enc_chnl")
                    if t_chn is not None:
                        loc = f"{p_type}.cache[{c_idx}].thumb"
                        if t_chn in video_venc_channels:
                            self.errors.append(
                                f"AX615 VENC/JENC Hardware Collision: Thumbnail JENC enc_chnl {t_chn} in {loc} "
                                f"collides with Video Stream VENC {video_venc_channels[t_chn]}! "
                                f"AX615 shares 0-15 channel IDs between VENC and JENC."
                            )
                        if t_chn in jenc_channels:
                            self.warnings.append(
                                f"JENC Channel Reuse: Thumbnail enc_chnl {t_chn} is shared between {jenc_channels[t_chn]} and {loc}"
                            )
                        jenc_channels[t_chn] = loc

    def _build_topology_summary(self, app_cfg: Dict[str, Any], ppl_cfg: List[Dict[str, Any]], sns_cfg: List[Dict[str, Any]]):
        cameras = app_cfg.get("camera", [])
        self.topology.append("=== AXCK Pipeline & Hardware Topology ===")

        # Hardware summary
        self.topology.append("  [Hardware Layer]")
        for hw_line in self.hardware_summary:
            self.topology.append(f"    • {hw_line}")

        self.topology.append("  [Media Pipeline Layer]")
        for idx, cam in enumerate(cameras):
            pos = "FRONT" if cam.get("sns_pos", idx) == 0 else "REAR"
            sns_name = cam.get("sns_name", "UNKNOWN")
            fps = cam.get("frame_rate", 25)
            vin_mode = cam.get("vin_ivps_mode")
            dev_id = cam.get("dev_id", 0)
            pipe_id = cam.get("pipe_id", 0)
            self.topology.append(
                f"    ├── Cam[{idx}] ({pos}): {sns_name} @ {fps}fps | dev_id={dev_id}, pipe_id={pipe_id} | vin_ivps_mode={vin_mode}"
            )

        for p_idx, p in enumerate(ppl_cfg):
            p_type = p.get("type", f"pipe_{p_idx}")
            self.topology.append(f"    └── Pipeline [{p_type}]:")
            for ivps in p.get("ivps", []):
                grp = ivps.get("group")
                self.topology.append(f"          ├── IVPS Group {grp}:")
                for out in ivps.get("output", []):
                    chn = out.get("chnl")
                    f_info = []
                    for f in out.get("filter", []):
                        w = f.get("width")
                        h = f.get("height")
                        eng = f.get("engine", "")
                        f_info.append(f"{eng}:{w}x{h}")
                    self.topology.append(f"          │     └── Chn {chn}: {' -> '.join(f_info)}")

            caches = p.get("cache", [])
            if caches:
                self.topology.append(f"          └── Encoders (VENC/JENC):")
                for c in caches:
                    enc_c = c.get("enc_chnl")
                    thumb = c.get("thumb", {})
                    t_str = f" | Thumb JENC={thumb.get('enc_chnl')}" if thumb.get("enable") else ""
                    self.topology.append(f"                • Video VENC Chn {enc_c}{t_str}")

    def _build_report(self) -> Dict[str, Any]:
        return {
            "valid": len(self.errors) == 0,
            "platform": self.platform,
            "project": self.project,
            "config_dir": self.config_dir,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "topology": self.topology,
        }

def main():
    sdk_root = os.environ.get("AX615_SDK_ROOT") or os.environ.get("SDK_ROOT")
    default_dir = os.path.join(sdk_root, "camera-kit", "service", "res", "config", "AX615D", "demo") if sdk_root else os.getcwd()
    parser = argparse.ArgumentParser(description="AXAP AX615 camera-kit Config Validator & Topology Analyzer")
    parser.add_argument("--config-dir", "-d", default=default_dir, help=f"Path to config dir (default: {default_dir})")
    parser.add_argument("--dual", action="store_true", help="Validate dual camera config (_dual.json)")
    parser.add_argument("--sensor", "-s", default=None, help="Optional sensor variant suffix (e.g. 'os04d10', 'os04d10_xs9950')")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")
    args = parser.parse_args()

    validator = AxckValidator(args.config_dir, dual=args.dual, sensor_suffix=args.sensor)
    report = validator.run()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\n================================================================================")
        print(f" AXAP camera-kit Configuration Validation Report")
        print(f" Platform: {report['platform']} | Project: {report['project']}")
        print(f" Directory: {report['config_dir']}")
        print(f" Mode: {'DUAL' if args.dual or (args.sensor and 'xs9950' in args.sensor) else 'SINGLE'}")
        print(f"================================================================================")
        status_str = "✅ PASS (VALID CONFIGURATION)" if report["valid"] else "❌ FAIL (INVALID CONFIGURATION)"
        print(f"Result: {status_str}")
        print(f"Errors: {report['error_count']} | Warnings: {report['warning_count']}\n")

        if report["topology"]:
            for line in report["topology"]:
                print(line)
            print("")

        if report["errors"]:
            print("❌ ERRORS (Must fix before build/run):")
            for err in report["errors"]:
                print(f"  - [ERROR] {err}")
            print("")

        if report["warnings"]:
            print("⚠️ WARNINGS (Review for performance/stability):")
            for w in report["warnings"]:
                print(f"  - [WARN] {w}")
            print("")

        if report["info"]:
            print("ℹ️ DETAILS:")
            for item in report["info"]:
                print(f"  - {item}")
            print("")

    return 0 if report["valid"] else 1

if __name__ == "__main__":
    sys.exit(main())
