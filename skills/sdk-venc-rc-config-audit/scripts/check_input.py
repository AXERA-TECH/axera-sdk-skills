#!/usr/bin/env python3
"""Validate the VENC RC proc snapshot before config audit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

INPUT_FILE = "venc_proc.txt"

REQUIRED_MARKERS = (
    ("VENC CHN ATTR 1", "通道属性表"),
    ("VENC CHN RC ATTR 1", "码控属性表"),
    ("VENC CHN STATUS 2", "运行状态表"),
)

RECOMMENDED_MARKERS = (
    ("VENC CHN GOP ATTR", "GOP 配置（GOP/IP 比例审查需要）"),
    ("SDK version", "SDK 版本行（版本相关差异确认需要）"),
)

CAPTURE_SOP = """cat /proc/ax_proc/venc > venc_proc.txt
cat /proc/ax_proc/version   # 如 proc 头部无 [SDK version] 行，另存版本信息"""


def validate(input_dir: Path) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    notes: list[str] = []
    path = input_dir / INPUT_FILE
    if not path.is_file():
        return [f"缺少 {INPUT_FILE}：按 SKILL.md 第 1 节采集的 /proc/ax_proc/venc 快照"], []
    if path.stat().st_size == 0:
        return [f"{INPUT_FILE} 为空"], []

    text = path.read_text(encoding="utf-8", errors="replace")
    for marker, label in REQUIRED_MARKERS:
        if marker not in text:
            issues.append(f"{INPUT_FILE} 缺少内容标记：{marker}（{label}）")
    for marker, label in RECOMMENDED_MARKERS:
        if marker not in text:
            notes.append(f"未包含 {marker}：{label}，对应结论需标注待确认。")
    if issues:
        notes = []
    return issues, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="包含 venc_proc.txt 的输入目录")
    args = parser.parse_args()

    issues, notes = validate(args.input_dir)
    if issues:
        print(f"INCOMPLETE: {args.input_dir} 未通过输入完整性门禁。")
        for issue in issues:
            print(f"- {issue}")
        print("\n补采指令（板端执行）：")
        print(CAPTURE_SOP)
        print("\n将 venc_proc.txt 放回输入目录后重新运行本检查。")
        return 2

    print(f"PASS: {args.input_dir}/{INPUT_FILE} 输入完整。")
    for note in notes:
        print(f"NOTE: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
