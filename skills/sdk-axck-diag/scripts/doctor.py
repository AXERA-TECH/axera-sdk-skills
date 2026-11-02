#!/usr/bin/env python3
"""
axck_log_diagnoser.py - AXAP camera-kit (AXCK) Log Diagnoser & Root-Cause Classifier

Features:
1. Filters & parses raw terminal / dmesg / board platform logs into modules:
   - SENSOR, VIN, ISP, IVPS, GDC, VENC, JENC, POOL, AUDIO, STORAGE, APP, MIPI, SIF
2. Timeline reconstruction: locates the FIRST root error, not the downstream cascading noise.
3. Decodes AXERA error codes (e.g. 0x80070216, 0x80080005, 0x80050004, etc.).
4. Hardware failure signature matching:
   - SIF FIFO overflow (HTS / line-time violation)
   - MIPI CRC / D-PHY lock-loss / ECC error
   - I2C NACK / timeout / address mismatch (8-bit vs 7-bit)
   - ITP rotation line-buffer exhaustion
   - Memory pool pipe0/pipe1 exhaustion
   - settingindex / MCLK mismatch indicators
5. Correlates errors with configuration and hardware constraints.
6. Generates actionable mitigation recommendations with config file attribution.
"""

import sys
import os
import re
import json
import argparse
from typing import Dict, List, Any, Optional

# AXERA Media Foundation Error Code Dictionary (expanded)
ERROR_CODE_MAP = {
    # VIN errors
    "0x80020005": {
        "module": "VIN",
        "name": "AX_ERR_VIN_ILLEGAL_PARAM",
        "cause": "Invalid parameter passed to VIN dev or pipe.",
        "solution": "检查 sns_info.json 的 dev_attr、mipi_intf_attr、mipi_lane 配置。"
    },
    "0x80020012": {
        "module": "VIN",
        "name": "AX_ERR_VIN_NOT_PERM",
        "cause": "VIN operation not permitted in current state.",
        "solution": "确认 VIN 初始化顺序：先创建 DEV 再创建 PIPE，避免重复创建。"
    },
    # ISP errors
    "0x80030005": {
        "module": "ISP",
        "name": "AX_ERR_ISP_ILLEGAL_PARAM",
        "cause": "ISP pipeline parameter invalid.",
        "solution": "检查 pipe_attr 的 width/height 是否与 sns_attr 一致。"
    },
    # POOL / CMM errors
    "0x80050004": {
        "module": "SYS/POOL",
        "name": "AX_ERR_POOL_NOBUF",
        "cause": "CMM 内存池耗尽 (AX_ERR_POOL_NOBUF)：无法分配帧 buffer 块，导致后续管线级联初始化失败。",
        "solution": "检查 app_config.json，调整 pool block_count 或 block_size，或降低分辨率/压缩级别。检查是否存在 buffer 泄漏。"
    },
    "0x80050003": {
        "module": "SYS/POOL",
        "name": "AX_ERR_POOL_ILLEGAL_PARAM",
        "cause": "Memory pool creation parameter error.",
        "solution": "检查 app_config.json 中的 pool block_size 和 block_count 是否合理（block_size 需 >= 帧大小）。"
    },
    # VENC errors
    "0x80070216": {
        "module": "VENC",
        "name": "AX_ERR_VENC_EXIST",
        "cause": "VENC 通道冲突 (AX_ERR_VENC_EXIST)：VENC/JENC 通道 ID 已存在或硬件表冲突，导致媒体管线构建终止。",
        "solution": "检查 ppl_config.json 中 cache.enc_chnl 和 thumb.enc_chnl，检查 enc_chnl 映射与 JENC 通道划分，确保 VENC(0~15) 和 JENC(0~15) 通道号互不冲突。"
    },
    "0x80070203": {
        "module": "VENC",
        "name": "AX_ERR_VENC_ILLEGAL_PARAM",
        "cause": "Invalid parameter passed to AX_VENC_CreateChn.",
        "solution": "检查 app_config 中 venc 的 width、height、framerate、bitrate 参数。"
    },
    "0x80070201": {
        "module": "VENC",
        "name": "AX_ERR_VENC_NULL_PTR",
        "cause": "Null pointer in VENC API call.",
        "solution": "检查编码通道创建参数，确保 stAttr 非空。"
    },
    # IVPS errors
    "0x80080005": {
        "module": "IVPS",
        "name": "AX_ERR_IVPS_ILLEGAL_PARAM",
        "cause": "IVPS group 或 filter 属性参数非法。",
        "solution": "确保 filter 的 width/height 偶数对齐且输入引擎支持请求的格式。"
    },
    "0x80080004": {
        "module": "IVPS",
        "name": "AX_ERR_IVPS_UNEXIST",
        "cause": "引用的 IVPS group 或 channel 不存在。",
        "solution": "检查 pipeline 启动顺序：确保 IVPS group 在 link 或 start 前已创建。"
    },
    # SYS errors
    "0x80010005": {
        "module": "SYS",
        "name": "AX_ERR_SYS_ILLEGAL_PARAM",
        "cause": "System-level illegal parameter.",
        "solution": "检查 AX_SYS_Init / AX_SYS_Link 参数。"
    },
}

# Deep hardware failure signature patterns (expanded)
KNOWN_PATTERNS = [
    # === SIF / VIN Hardware ===
    {
        "regex": r"sif.*fifo.*(overflow|full|overrun)",
        "module": "SIF/VIN",
        "severity": "CRITICAL",
        "category": "SIF_FIFO_OVERFLOW",
        "explanation": "SIF FIFO 溢出 (SIF FIFO OVERFLOW)：Sensor 输出行数据速率超过 SIF 硬件处理能力。AX615 SIF 主频 367MHz，2 pixel/cycle，最小行时间 = width / 367 / 2 us。下游 IVPS/VENC 超时为级联受害者。",
        "action": "检查 Sensor HTS (Horizontal Total Size) 是否满足 SIF 最小行时间约束，行时间违规 (Line time violation) 触发了 AX615 吞吐限制。调整 Sensor HTS / settingindex。"
    },
    {
        "regex": r"sif.*(error|err|abnormal|exception)",
        "module": "SIF/VIN",
        "severity": "ERROR",
        "category": "SIF_HARDWARE_ERROR",
        "explanation": "SIF 硬件异常，可能由 MIPI 信号质量或行长不足引起。下游 IVPS/VENC 超时为级联受害者。",
        "action": "检查 MIPI 连接、Lane 映射和 Sensor settingindex。调整 Sensor HTS / settingindex。"
    },
    # === MIPI D-PHY ===
    {
        "regex": r"mipi.*(crc|checksum).*(error|fail|mismatch)",
        "module": "MIPI",
        "severity": "CRITICAL",
        "category": "MIPI_CRC_ERROR",
        "explanation": "MIPI 数据包 CRC 校验失败：信号完整性问题或 PHY 配置错误。",
        "action": "检查 MIPI 走线质量、Lane 映射 (lane_map / clk_lane)、终端电阻。确认 settingindex 中 MIPI data rate 与实际匹配。"
    },
    {
        "regex": r"mipi.*(lock|pll).*(fail|lost|error|timeout)",
        "module": "MIPI",
        "severity": "CRITICAL",
        "category": "MIPI_PHY_LOCK_LOSS",
        "explanation": "MIPI D-PHY PLL 锁定失败或丢失：物理层无法同步时钟。",
        "action": "确认 MCLK 输出正常（24M/27M）、Sensor 供电稳定、Reset GPIO 正确拉高。检查 clk_lane 配置是否匹配物理连线。"
    },
    {
        "regex": r"mipi.*(ecc).*(error|fail)",
        "module": "MIPI",
        "severity": "ERROR",
        "category": "MIPI_ECC_ERROR",
        "explanation": "MIPI 包头 ECC 纠错失败。",
        "action": "检查 MIPI 信号质量和走线长度匹配。"
    },
    {
        "regex": r"mipi yuv dev_id 0 is invalid, should be 1 or 2",
        "module": "VIN/ISP",
        "severity": "CRITICAL",
        "category": "HARDWARE_CONSTRAINT_VIOLATION",
        "explanation": "AX615 SIF 硬件限定 dev_id 0 专用于 RAW Sensor。YUV 传感器（XS9950/TP9963）必须使用 dev_id 1 或 2。",
        "action": "修改 app_config.json 中对应 camera 的 dev_id 为 1。"
    },
    # === I2C Sensor Communication ===
    {
        "regex": r"i2c.*(nack|nak)",
        "module": "SENSOR/I2C",
        "severity": "CRITICAL",
        "category": "I2C_NACK",
        "explanation": "I2C 寻址 NACK：Sensor 未应答。常见原因：I2C 地址错误（误配 8-bit 地址而非 7-bit）、Sensor 未上电、复位 GPIO 未释放。",
        "action": "核对 sns_info.json 的 i2c_addr（必须为 7-bit，如 SC438HAI 应为 0x30 而非 0x60）、power_gpio 和 reset_gpio。执行 `i2cdetect -y <bus>` 确认设备在线。"
    },
    {
        "regex": r"i2c.*(transfer|timeout|error)",
        "module": "SENSOR/I2C",
        "severity": "CRITICAL",
        "category": "I2C_TRANSFER_ERROR",
        "explanation": "I2C 传输失败或超时。",
        "action": "检查 Sensor 供电、MCLK 输出、Reset GPIO 时序、I2C 总线上拉电阻。确认 i2c_dev 编号正确（Demo 板为 1，p105 为 5）。"
    },
    {
        "regex": r"sensor.*(probe|detect).*(fail|error|not found)",
        "module": "SENSOR",
        "severity": "CRITICAL",
        "category": "SENSOR_PROBE_FAILURE",
        "explanation": "Sensor 探测失败：驱动无法通过 I2C 读取 Chip ID。",
        "action": "确认：1) i2c_dev 编号正确 2) i2c_addr 为 7-bit 3) Reset GPIO 已释放（高电平） 4) MCLK 已输出 5) Sensor 供电正常。"
    },
    # === VENC / JENC Encoder ===
    {
        "regex": r"AX_VENC_CreateChn.*fail.*0x([0-9a-fA-F]+)",
        "module": "VENC/JENC",
        "severity": "CRITICAL",
        "category": "ENCODER_CHANNEL_CONFLICT",
        "explanation": "创建 VENC/JENC 通道失败。",
        "action": "检查 ppl_config.json 中 cache.enc_chnl 和 thumb.enc_chnl 通道号冲突（VENC 和 JENC 共享 0~15）。"
    },
    # === Memory Pool ===
    {
        "regex": r"AX_POOL_GetBlock.*fail|pool.*get.*block.*fail",
        "module": "POOL",
        "severity": "ERROR",
        "category": "MEMORY_EXHAUSTION",
        "explanation": "CMM 内存池 buffer 分配失败。",
        "action": "增加 pool block_count 或检查是否存在 buffer 泄漏。注意区分 pipe0/pipe1 池。"
    },
    {
        "regex": r"alloc.*cmm.*fail|cmm.*alloc.*fail|AX_SYS_MemAlloc.*fail",
        "module": "SYS/CMM",
        "severity": "CRITICAL",
        "category": "CMM_ALLOC_FAILURE",
        "explanation": "CMM 系统内存分配失败：可用物理内存不足。",
        "action": "检查 /proc/ax_proc/mem_cmm_info 确认 CMM 剩余空间。降低分辨率或减少通道数。"
    },
    # === ITP / GDC Rotation ===
    {
        "regex": r"itp.*(line.?buf|rotation).*(exhaust|overflow|fail|error)",
        "module": "ITP/GDC",
        "severity": "ERROR",
        "category": "ITP_LINEBUF_EXHAUSTION",
        "explanation": "ITP 旋转 Line Buffer 耗尽：分辨率过高导致旋转硬件资源不足。",
        "action": "降低旋转通道分辨率，或关闭不必要的旋转/转置。参考 pipeline_rules.md 中旋转约束。"
    },
    # === Record / Muxer ===
    {
        "regex": r"\[MUX_MP4\].*Need vps:.*need SPS:.*need PPS:.*needIDR:",
        "module": "RECORD/MUX",
        "severity": "WARNING",
        "category": "MP4_MUX_WAIT_KEY_VIOLATION",
        "explanation": "MP4 Muxer 切文件时收到非 IDR 关键帧：新录像文件初始化需首先写入 VPS/SPS/PPS/IDR，若录像模块在真正 IDR 到达前误放行了旧 GOP 残留 P 帧（例如缩略图帧提前解除等待关键帧状态），Muxer 将主动拦截并打印该报错。",
        "action": "检查 service/mod/axck_record/axck_record_api.c 的 ChkCanWrite()：确认切文件后处于 rwsWaitKey 时，缩略图帧(effIsThumb)不提前解除等待状态，仅真正视频关键帧(effIsKey)到达才切换为 rwsWaitNone。"
    },
    # === Watchdog / Heartbeat (downstream indicator) ===
    {
        "regex": r"heartbeat.*(timeout|fail)",
        "module": "SYS/WATCHDOG",
        "severity": "WARNING",
        "category": "HEARTBEAT_TIMEOUT",
        "explanation": "任务心跳超时：通常是上游硬件错误（如 SIF 溢出、MIPI 失锁）的下游连锁反应。",
        "action": "不要直接修复此项——向上追溯时间线，定位首个 CRITICAL 级根因。"
    },
    # === Segfault / Crash ===
    {
        "regex": r"segfault|signal 11|SIGSEGV|Segmentation fault",
        "module": "APP/CRASH",
        "severity": "CRITICAL",
        "category": "SEGFAULT",
        "explanation": "进程段错误崩溃。",
        "action": "收集 coredump 并使用 addr2line 定位崩溃点。检查是否由内存池耗尽或空指针引起。"
    },
    # === Kernel panic / oops ===
    {
        "regex": r"kernel.*panic|Oops|BUG:|Unable to handle kernel",
        "module": "KERNEL",
        "severity": "CRITICAL",
        "category": "KERNEL_PANIC",
        "explanation": "内核崩溃或 Oops。",
        "action": "检查驱动模块加载顺序和版本兼容性。收集完整 dmesg 日志。"
    },
    # === MCLK / Clock ===
    {
        "regex": r"mclk.*(error|fail|mismatch|not found)|clock.*(sensor|mclk).*(error|fail)",
        "module": "SENSOR/CLK",
        "severity": "ERROR",
        "category": "MCLK_ERROR",
        "explanation": "Sensor MCLK 时钟配置错误或输出失败。",
        "action": "确认 sns_clk.clk_rate 与 settingindex 绑定的 MCLK 一致（24M 或 27M）。检查时钟引脚硬件连接。"
    },
    # === Frame rate mismatch indicators ===
    {
        "regex": r"frame.?rate.*mismatch|fps.*drop|frame.*loss|frame.*drop",
        "module": "VIN/ISP",
        "severity": "WARNING",
        "category": "FRAMERATE_ANOMALY",
        "explanation": "帧率异常或丢帧。可能由 MCLK 不匹配（24M vs 27M 导致 11.1% 偏差）或 SIF 行时间不足引起。",
        "action": "确认 sns_clk.clk_rate 与 settingindex 匹配。检查 SIF 最小行时间约束。"
    },
]

class AxckLogDiagnoser:
    def __init__(self, log_content: str):
        self.raw_lines = log_content.splitlines()
        self.parsed_events: List[Dict[str, Any]] = []
        self.root_cause: Optional[Dict[str, Any]] = None
        self.recommendations: List[str] = []
        self.module_summary: Dict[str, int] = {}

    def diagnose(self) -> Dict[str, Any]:
        seen_lines = set()

        for idx, line in enumerate(self.raw_lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            matched = False

            # Check known regex patterns (priority order)
            for pat in KNOWN_PATTERNS:
                m = re.search(pat["regex"], line, re.IGNORECASE)
                if m:
                    event = {
                        "line_num": idx + 1,
                        "raw_line": line_stripped[:200],
                        "module": pat["module"],
                        "severity": pat["severity"],
                        "category": pat["category"],
                        "explanation": pat["explanation"],
                        "action": pat["action"]
                    }
                    # Extract hex error code if present
                    hex_match = re.search(r"0x(800[0-9a-fA-F]{5})", line)
                    if hex_match:
                        code = hex_match.group(0).lower()
                        if code in ERROR_CODE_MAP:
                            event["decoded_code"] = ERROR_CODE_MAP[code]

                    self.parsed_events.append(event)
                    self.module_summary[pat["module"]] = self.module_summary.get(pat["module"], 0) + 1
                    matched = True
                    break

            # Fallback: standalone AXERA error code detection
            if not matched:
                hex_match = re.search(r"0x(800[0-9a-fA-F]{5})", line)
                if hex_match:
                    code = hex_match.group(0).lower()
                    info = ERROR_CODE_MAP.get(code, {
                        "module": "UNKNOWN",
                        "name": f"CODE_{code}",
                        "cause": f"AXERA SDK 错误码 {code}",
                        "solution": "检查该时间点前后的模块日志。"
                    })
                    self.parsed_events.append({
                        "line_num": idx + 1,
                        "raw_line": line_stripped[:200],
                        "module": info["module"],
                        "severity": "ERROR",
                        "category": "AX_ERR_RETURN",
                        "decoded_code": info,
                        "explanation": info["cause"],
                        "action": info["solution"]
                    })
                    mod = info["module"]
                    self.module_summary[mod] = self.module_summary.get(mod, 0) + 1

        # Root cause identification: earliest CRITICAL, then earliest ERROR
        if self.parsed_events:
            # First pass: find earliest CRITICAL
            self.root_cause = None
            for ev in self.parsed_events:
                if ev["severity"] == "CRITICAL":
                    # Skip heartbeat timeout as root cause (it's downstream)
                    if ev["category"] == "HEARTBEAT_TIMEOUT":
                        continue
                    self.root_cause = ev
                    break

            # If no CRITICAL found (excluding heartbeat), fall back to first ERROR
            if not self.root_cause:
                for ev in self.parsed_events:
                    if ev["severity"] in ("CRITICAL", "ERROR"):
                        self.root_cause = ev
                        break

            # Final fallback: first event
            if not self.root_cause:
                self.root_cause = self.parsed_events[0]

            self.recommendations.append(
                f"[根因 Line {self.root_cause['line_num']}] {self.root_cause['action']}"
            )

            # Add secondary recommendations for other unique categories
            seen_cats = {self.root_cause["category"]}
            for ev in self.parsed_events:
                if ev["category"] not in seen_cats and ev["severity"] in ("CRITICAL", "ERROR"):
                    seen_cats.add(ev["category"])
                    self.recommendations.append(f"[关联 Line {ev['line_num']}] {ev['action']}")
                    if len(self.recommendations) >= 5:
                        break

        return {
            "total_lines": len(self.raw_lines),
            "detected_issues": len(self.parsed_events),
            "root_cause": self.root_cause,
            "events": self.parsed_events,
            "recommendations": self.recommendations,
            "module_summary": self.module_summary
        }

def main():
    parser = argparse.ArgumentParser(description="AXAP AX615 camera-kit Log Diagnoser")
    parser.add_argument("--file", "-f", help="Path to log file")
    parser.add_argument("--text", "-t", help="Raw log string text")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--max-events", type=int, default=50, help="Maximum events to report (default: 50)")
    args = parser.parse_args()

    content = ""
    if args.file:
        if not os.path.isfile(args.file):
            print(f"Error: file not found {args.file}", file=sys.stderr)
            return 1
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    elif args.text:
        content = args.text
    else:
        content = sys.stdin.read()

    diagnoser = AxckLogDiagnoser(content)
    result = diagnoser.diagnose()

    # Limit events for output
    if len(result["events"]) > args.max_events:
        result["events"] = result["events"][:args.max_events]
        result["events_truncated"] = True

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("========================================================")
        print(" AXAP camera-kit 日志诊断与时间线根因分析")
        print("========================================================")
        print(f"日志总行数: {result['total_lines']}")
        print(f"检测到异常: {result['detected_issues']}\n")

        # Module summary
        if result["module_summary"]:
            print("📊 [模块分布]")
            for mod, cnt in sorted(result["module_summary"].items(), key=lambda x: -x[1]):
                print(f"  - {mod}: {cnt} 条")
            print("")

        rc = result["root_cause"]
        if rc:
            print(f"🎯 [根因定位]")
            print(f"  - Line #{rc['line_num']}: {rc['raw_line']}")
            print(f"  - 模块: {rc['module']} | 分类: {rc['category']}")
            print(f"  - 解析: {rc['explanation']}")
            print(f"  - 措施: {rc['action']}")
            if "decoded_code" in rc:
                dc = rc["decoded_code"]
                print(f"  - 错误码: {dc.get('name', 'N/A')} - {dc.get('cause', '')}")
            print("")
        else:
            print("✅ 未检测到 camera-kit 相关异常。\n")

        if len(result["events"]) > 1:
            print("📋 [事件时间线]")
            for ev in result["events"][:15]:
                sev_icon = "🔴" if ev["severity"] == "CRITICAL" else ("🟡" if ev["severity"] == "ERROR" else "⚪")
                print(f"  {sev_icon} Line #{ev['line_num']} [{ev['module']}] {ev['raw_line'][:120]}")
            if len(result["events"]) > 15:
                print(f"  ... 还有 {len(result['events']) - 15} 条事件")
            print("")

        if result["recommendations"]:
            print("💡 [建议措施]")
            for rec in result["recommendations"]:
                print(f"  👉 {rec}")
            print("")

    return 0 if not result["root_cause"] else 1

if __name__ == "__main__":
    sys.exit(main())
