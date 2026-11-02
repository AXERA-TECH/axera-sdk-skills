#!/usr/bin/env python3
"""Validate an AX615 VO oracle after the analyzer result is frozen."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_yaml(path: Path) -> dict:
    """使用本机 Bun YAML 解析器，避免依赖 PyYAML。"""
    parser = (
        "const path = process.argv[1]; "
        "console.log(JSON.stringify(Bun.YAML.parse(await Bun.file(path).text())));"
    )
    try:
        result = subprocess.run(
            ["bun", "-e", parser, str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        value = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取 {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是 mapping")
    return value


def require_string(data: dict, field: str) -> None:
    if not isinstance(data.get(field), str) or not data[field].strip():
        raise ValueError(f"{field} 必须是非空字符串")


def require_string_list(data: dict, field: str, allow_empty: bool = False) -> None:
    value = data.get(field)
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{field} 必须是{'可空' if allow_empty else '非空'}字符串列表")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} 只能包含非空字符串")


def resolve_inside(case_dir: Path, relative: object, field: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{field} 必须是非空相对路径")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError(f"{field} 必须是相对路径: {relative}")
    path = (case_dir / candidate).resolve()
    try:
        path.relative_to(case_dir)
    except ValueError as error:
        raise ValueError(f"{field} 越出 Case 目录: {relative}") from error
    return path


def validate_evidence_signatures(data: dict, case_dir: Path) -> None:
    signatures = data.get("evidence_signatures")
    if not isinstance(signatures, dict) or not signatures:
        raise ValueError("evidence_signatures 必须是非空 mapping")
    for source, values in signatures.items():
        if not isinstance(source, str) or not source.startswith("input/"):
            raise ValueError("evidence_signatures 的 key 必须是 input/ 相对路径")
        if not isinstance(values, list) or not values or not all(
            isinstance(item, str) and item.strip() for item in values
        ):
            raise ValueError(f"evidence_signatures[{source}] 必须是非空字符串列表")
        # 签名的归属文件必须真实存在且仍在 Case 目录内，避免 oracle 指向不存在的输入
        path = resolve_inside(case_dir, source, f"evidence_signatures[{source}]")
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"evidence_signatures 引用的输入文件不存在或为空: {source}")


def validate(path: Path, case_dir: Path | None = None) -> None:
    try:
        data = load_yaml(path)
    except ValueError as error:
        raise ValueError(str(error)) from error
    if not isinstance(data, dict):
        raise ValueError("oracle 顶层必须是 mapping")

    require_string(data, "root_cause")
    require_string_list(data, "required_concepts")
    require_string_list(data, "forbidden_conclusions", allow_empty=True)
    require_string_list(data, "evaluation_notes", allow_empty=True)
    validate_evidence_signatures(data, (case_dir or path.resolve().parent.parent).resolve())

    confidence = data.get("expected_confidence")
    if confidence not in {"high", "medium", "low"}:
        raise ValueError("expected_confidence 必须是 high、medium 或 low")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path, help="oracle.yaml 路径")
    parser.add_argument("case_dir", type=Path, nargs="?",
                        help="Case 根目录，用于核对 evidence_signatures 的输入文件；默认 oracle 的上级目录")
    args = parser.parse_args()
    oracle_path = args.oracle.resolve()
    case_dir = args.case_dir.resolve() if args.case_dir else oracle_path.parent.parent
    try:
        validate(oracle_path, case_dir)
    except ValueError as error:
        print(f"ERROR: {error}")
        return 2
    print(f"PASS: oracle 结构有效: {oracle_path}")
    print(f"case_dir: {case_dir}")
    print(f"evidence_signatures 输入核对通过: {case_dir / 'input'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
