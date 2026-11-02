#!/usr/bin/env python3
"""Validate AXCK diagnostic log bundle before root-cause analysis."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LogRequirement:
    filename: str
    description: str
    required: bool
    marker_groups: tuple[tuple[str, ...], ...]


REQUIREMENTS = (
    LogRequirement(
        "serial.log",
        "应用启动至异常退出的串口控制台日志",
        True,
        (("[AXCK", "AXCK_", "[SDK", "[AX_", "AX_ERR", "main"),),
    ),
    LogRequirement(
        "dmesg.log",
        "Linux 内核 dmesg 故障现场日志",
        False,
        (("Kernel", "AX_", "ax_", "vin", "ivps", "venc", "sif", "cmm", "pool"),),
    ),
    LogRequirement(
        "app_config.json",
        "运行时 app_config.json 配置快照",
        False,
        (("camera", "ipc", "pool", "venc"),),
    ),
)


CAPTURE_GUIDELINES = {
    "serial.log": "通过串口终端工具（如 minicom, picocom, socat）捕获应用启动完整输出：\n  socat - TCP:<IP>:<PORT> | tee serial.log",
    "dmesg.log": "在板端或远程 shell 执行 dmesg 保存内核环形缓冲区：\n  dmesg > dmesg.log",
    "app_config.json": "拉取板端当前生效的配置文件：\n  cat /opt/etc/app_config.json > app_config.json",
}


def check_directory(input_dir: Path) -> tuple[bool, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []

    for req in REQUIREMENTS:
        target = input_dir / req.filename
        if not target.is_file():
            if req.required:
                errors.append(f"缺失必需输入日志: {req.filename} ({req.description})")
            else:
                warnings.append(f"未提供可选现场文件: {req.filename} ({req.description})")
            continue

        if target.stat().st_size == 0:
            errors.append(f"输入文件为空: {req.filename}")
            continue

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            errors.append(f"无法读取 {req.filename}: {e}")
            continue

        for group in req.marker_groups:
            matched = any(marker.lower() in content.lower() for marker in group)
            if not matched:
                warnings.append(
                    f"{req.filename} 未检测到预期特征标记 (例如: {', '.join(group[:3])})"
                )

    passed = len(errors) == 0
    return passed, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="待检测的现场输入目录 (包含 serial.log 等)")
    parser.add_argument("--strict", action="store_true", help="将警告也视作失败")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        print(f"ERROR: 目录不存在: {input_dir}", file=sys.stderr)
        return 2

    passed, errors, warnings = check_directory(input_dir)

    if errors:
        print("[-] 输入完整性检查失败 (Errors):")
        for err in errors:
            print(f"  * {err}")
        print("\n建议补采命令:")
        for name, cmd in CAPTURE_GUIDELINES.items():
            print(f"--- {name} ---\n{cmd}")

    if warnings:
        print("[!] 检查警告 (Warnings):")
        for w in warnings:
            print(f"  * {w}")

    if passed and (not warnings or not args.strict):
        print(f"[+] 输入完整性预检通过: {input_dir}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
