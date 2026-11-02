#!/usr/bin/env python3
"""Validate the IVD proc sampling bundle before stall diagnosis."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

INPUT_FILE = "hsk_proc.txt"

REQUIRED_MARKERS = (
    ("Link Table V2", "/proc/ax_proc/link_table"),
    ("SESSION", "/proc/ax_proc/syncagent"),
    ("IVPS VERSION", "/proc/ax_proc/ivps"),
)

VENC_ALTERNATIVES = (("VENC CHN ATTR", "VENC CHN STATUS"), "/proc/ax_proc/venc")

RECOMMENDED_MARKERS = (
    ("Link Table Kernel V2", "/proc/ax_proc/link_table_kernel（Engine 判定，JPEG 分支需要）"),
    ("JENC", "/proc/ax_proc/jenc（存在 JPEG 通道时）"),
)

SAMPLE_PATTERN = re.compile(r"^===== SAMPLE (\d+).*?=====\s*$", re.MULTILINE)

CAPTURE_SOP = """echo 'priv on' > /proc/ax_proc/syncagent
for n in 1 2; do
    echo "===== SAMPLE $n $(date) ====="
    cat /proc/ax_proc/link_table
    cat /proc/ax_proc/link_table_kernel
    cat /proc/ax_proc/syncagent
    cat /proc/ax_proc/venc
    cat /proc/ax_proc/jenc
    cat /proc/ax_proc/ivps
    [ "$n" = 1 ] && sleep 5
done > hsk_proc.txt"""


def validate(input_dir: Path) -> tuple[list[str], list[str], int]:
    issues: list[str] = []
    recapture: list[str] = []
    path = input_dir / INPUT_FILE
    if not path.is_file():
        return [f"缺少 {INPUT_FILE}：按 SKILL.md 第 1 节 SOP 采集的 proc 采样"], [INPUT_FILE], 0
    if path.stat().st_size == 0:
        return [f"{INPUT_FILE} 为空"], [INPUT_FILE], 0

    text = path.read_text(encoding="utf-8", errors="replace")
    samples = SAMPLE_PATTERN.findall(text)

    for marker, node in REQUIRED_MARKERS:
        if marker not in text:
            issues.append(f"{INPUT_FILE} 缺少内容标记：{marker}（对应 {node}）")
            recapture.append(INPUT_FILE)
    for alternatives, node in (VENC_ALTERNATIVES,):
        if not any(marker in text for marker in alternatives):
            issues.append(f"{INPUT_FILE} 缺少内容标记：{' / '.join(alternatives)}（对应 {node}）")
            recapture.append(INPUT_FILE)

    return issues, recapture, len(samples)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="包含 hsk_proc.txt 的输入目录")
    args = parser.parse_args()

    issues, _recapture, sample_count = validate(args.input_dir)
    if issues:
        print(f"INCOMPLETE: {args.input_dir} 未通过输入完整性门禁。")
        for issue in issues:
            print(f"- {issue}")
        print("\n补采指令（板端执行，两轮采样间隔 3~10 秒）：")
        print(CAPTURE_SOP)
        print("\n将 hsk_proc.txt 放回输入目录后重新运行本检查。")
        return 2

    notes: list[str] = []
    if sample_count == 0:
        notes.append("仅单次采样（无 SAMPLE 标记）：可做静态判读，但任何停滞只能表述为"
                     "疑似，需第二次采样确认。")
    elif sample_count == 1:
        notes.append("仅 1 个 SAMPLE 标记：采样残缺，需按 SOP 重采完整两轮。")
    for marker, node in RECOMMENDED_MARKERS:
        if marker not in text_note(args.input_dir):
            notes.append(f"未包含 {node}：对应判读只能标注待确认。")

    print(f"PASS: {args.input_dir}/{INPUT_FILE} 输入完整（{sample_count} 轮采样标记）。")
    for note in notes:
        print(f"NOTE: {note}")
    return 0


def text_note(input_dir: Path) -> str:
    return (input_dir / INPUT_FILE).read_text(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    sys.exit(main())
