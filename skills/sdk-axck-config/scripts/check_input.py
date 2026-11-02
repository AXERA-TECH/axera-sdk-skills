#!/usr/bin/env python3
"""Validate AXCK pipeline and hardware configuration directory before verification."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REQUIREMENTS = (
    {
        "filename": "app_config.json",
        "description": "应用与系统资源主配置文件",
        "required": True,
        "top_keys": ("camera", "pool"),
    },
    {
        "filename": "ppl_config.json",
        "description": "多媒体管线拓扑与引擎配置文件",
        "required": True,
        "top_keys": (),
    },
    {
        "filename": "sns_info.json",
        "description": "Sensor 硬件属性与引脚契约配置",
        "required": True,
        "top_keys": (),
    },
)


def check_directory(input_dir: Path) -> tuple[bool, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []

    for req in REQUIREMENTS:
        target = input_dir / req["filename"]
        if not target.is_file():
            if req["required"]:
                errors.append(f"缺失必需配置文件: {req['filename']} ({req['description']})")
            else:
                warnings.append(f"未提供可选配置文件: {req['filename']} ({req['description']})")
            continue

        if target.stat().st_size == 0:
            errors.append(f"配置文件为空: {req['filename']}")
            continue

        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            errors.append(f"JSON 解析失败 {req['filename']}: {e}")
            continue

        if isinstance(data, dict):
            for k in req["top_keys"]:
                if k not in data:
                    warnings.append(f"{req['filename']} 缺少推荐顶级配置键: '{k}'")

    passed = len(errors) == 0
    return passed, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="待检测的配置目录 (包含 app_config.json 等)")
    parser.add_argument("--strict", action="store_true", help="将警告视作失败")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        print(f"ERROR: 目录不存在: {input_dir}", file=sys.stderr)
        return 2

    passed, errors, warnings = check_directory(input_dir)

    if errors:
        print("[-] 配置完整性检查失败 (Errors):")
        for err in errors:
            print(f"  * {err}")

    if warnings:
        print("[!] 检查警告 (Warnings):")
        for w in warnings:
            print(f"  * {w}")

    if passed and (not warnings or not args.strict):
        print(f"[+] 配置输入完整性预检通过: {input_dir}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
