#!/usr/bin/env python3
"""Preflight an AX issue-analysis Golden Case without reading oracle contents."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_DIR = SKILL_ROOT / "evals"
DEFAULT_SKILLS_DIR = SKILL_ROOT.parent


def load_yaml(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"无法读取 {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是 mapping")
    return value


def resolve_inside(case_dir: Path, relative: object, field: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{field} 必须是非空相对路径")
    path = (case_dir / relative).resolve()
    try:
        path.relative_to(case_dir)
    except ValueError as error:
        raise ValueError(f"{field} 越出 Case 目录: {relative}") from error
    return path


def string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} 必须是非空字符串列表")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} 存在重复项")
    return value


def preflight(case_arg: Path, cases_dir_arg: Path, skills_dir_arg: Path) -> dict:
    case_dir = case_arg.resolve()
    if not case_dir.is_dir() and len(case_arg.parts) == 1:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", case_arg.name):
            raise ValueError(f"Case ID 格式非法: {case_arg.name}")
        case_dir = (cases_dir_arg / case_arg.name).resolve()
    if not case_dir.is_dir():
        raise ValueError(f"Case 目录不存在: {case_dir}")

    manifest_path = case_dir / "answer" / "case.yaml"
    if not manifest_path.is_file():
        raise ValueError(f"case.yaml 必须位于 answer/ 子目录: {manifest_path}")
    manifest = load_yaml(manifest_path)

    if manifest.get("schema_version") != 1:
        raise ValueError("case.yaml.schema_version 当前必须为 1")

    case_id = manifest.get("id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case.yaml.id 必须是非空字符串")

    analyzer = manifest.get("analyzer")
    if not isinstance(analyzer, dict):
        raise ValueError("case.yaml 缺少 analyzer mapping")
    analyzer_skill = analyzer.get("skill")
    if not isinstance(analyzer_skill, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", analyzer_skill):
        raise ValueError("case.yaml.analyzer.skill 必须使用小写字母、数字和连字符")

    separation = manifest.get("separation")
    if not isinstance(separation, dict):
        raise ValueError("case.yaml 缺少 separation mapping")
    visible = string_list(separation.get("analyzer_visible"), "separation.analyzer_visible")
    evaluator_only = string_list(separation.get("evaluator_only"), "separation.evaluator_only")

    overlap = sorted(set(visible) & set(evaluator_only))
    if overlap:
        raise ValueError(f"analyzer_visible 与 evaluator_only 重叠: {', '.join(overlap)}")
    if any(not item.startswith("input/") for item in visible):
        raise ValueError("analyzer_visible 只能包含 input/ 下的文件")
    if any(not item.startswith("answer/") for item in evaluator_only):
        raise ValueError("evaluator_only 只能包含 answer/ 下的文件")
    if "answer/case.yaml" not in evaluator_only:
        raise ValueError("answer/case.yaml 必须列入 evaluator_only")

    declared_input = manifest.get("input")
    if not isinstance(declared_input, dict):
        raise ValueError("case.yaml 缺少 input mapping")
    input_files = string_list(declared_input.get("files"), "input.files")
    if set(input_files) != set(visible):
        raise ValueError("input.files 与 separation.analyzer_visible 必须完全一致")

    visible_paths = []
    for relative in visible:
        path = resolve_inside(case_dir, relative, f"analyzer_visible[{relative}]")
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"分析输入不存在或为空: {relative}")
        visible_paths.append(path)

    oracle_relative = manifest.get("oracle")
    oracle_path = resolve_inside(case_dir, oracle_relative, "oracle")
    if oracle_relative not in evaluator_only:
        raise ValueError("oracle 必须列入 separation.evaluator_only")
    if not oracle_path.is_file() or oracle_path.stat().st_size == 0:
        raise ValueError(f"oracle 不存在或为空: {oracle_relative}")

    for relative in evaluator_only:
        path = resolve_inside(case_dir, relative, f"evaluator_only[{relative}]")
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"evaluator-only 文件不存在或为空: {relative}")

    skills_dir = skills_dir_arg.resolve()
    analyzer_path = skills_dir / analyzer_skill
    if not (analyzer_path / "SKILL.md").is_file():
        raise ValueError(f"对应问题分析 Skill 不存在: {analyzer_path}")

    return {
        "case_id": case_id,
        "case_dir": str(case_dir),
        "analyzer_skill": analyzer_skill,
        "analyzer_path": str(analyzer_path),
        "analyzer_visible": [str(path) for path in visible_paths],
        "oracle": str(oracle_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path, help="Golden Case ID 或包含 case.yaml 的目录")
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=DEFAULT_CASES_DIR,
        help=f"按 Case ID 查找时使用的目录，默认 {DEFAULT_CASES_DIR}",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=DEFAULT_SKILLS_DIR,
        help=f"问题分析 Skill 目录，默认 {DEFAULT_SKILLS_DIR}",
    )
    args = parser.parse_args()

    try:
        result = preflight(args.case_dir, args.cases_dir, args.skills_dir)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}")
        return 2

    print(f"PASS: Case {result['case_id']} 预检通过")
    print(f"case_dir: {result['case_dir']}")
    print(f"analyzer_skill: {result['analyzer_skill']}")
    print(f"analyzer_path: {result['analyzer_path']}")
    print("analyzer_visible (分析阶段只读以下文件，不要读取 answer/ 目录):")
    for path in result["analyzer_visible"]:
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
