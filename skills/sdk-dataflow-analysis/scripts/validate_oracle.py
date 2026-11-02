#!/usr/bin/env python3
"""Validate an AX issue-analysis oracle after the analyzer result is frozen."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def require_string(data: dict, field: str) -> None:
    if not isinstance(data.get(field), str) or not data[field].strip():
        raise ValueError(f"{field} 必须是非空字符串")


def require_string_list(data: dict, field: str, allow_empty: bool = False) -> None:
    value = data.get(field)
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{field} 必须是{'可空' if allow_empty else '非空'}字符串列表")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} 只能包含非空字符串")


def validate(path: Path) -> None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"无法读取 {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("oracle 顶层必须是 mapping")

    require_string(data, "root_cause")
    require_string_list(data, "required_concepts")
    require_string_list(data, "forbidden_conclusions", allow_empty=True)
    require_string_list(data, "evaluation_notes", allow_empty=True)

    signatures = data.get("evidence_signatures")
    if not isinstance(signatures, dict) or not signatures:
        raise ValueError("evidence_signatures 必须是非空 mapping")
    for source, values in signatures.items():
        if not isinstance(source, str) or not source.startswith("input/"):
            raise ValueError("evidence_signatures 的 key 必须是 input/ 相对路径")
        if not isinstance(values, list) or not values or not all(
            isinstance(item, str) and item for item in values
        ):
            raise ValueError(f"evidence_signatures[{source}] 必须是非空字符串列表")

    confidence = data.get("expected_confidence")
    if confidence not in {"high", "medium", "low"}:
        raise ValueError("expected_confidence 必须是 high、medium 或 low")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path, help="oracle.yaml 路径")
    args = parser.parse_args()
    try:
        validate(args.oracle.resolve())
    except ValueError as error:
        print(f"ERROR: {error}")
        return 2
    print(f"PASS: oracle 结构有效: {args.oracle.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
