#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AX615 AOV Skill Eval 验证与检查脚本
用于验证 evals.json 的格式完整性与字段合规性。
兼容 assertions 与 criteria 两种评分/断言体系。
"""

import json
import os
import sys

# 基础必须字段
REQUIRED_FIELDS = [
    "id",
    "name",
    "prompt",
    "expected_output",
]


def validate_evals(file_path: str) -> bool:
    if not os.path.exists(file_path):
        print(f"Error: Eval file not found: {file_path}")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON format: {e}")
            return False

    if not isinstance(data, dict):
        print("Error: Top-level structure must be an object (dict)")
        return False

    evals = data.get("evals")
    if not isinstance(evals, list) or len(evals) == 0:
        print("Error: 'evals' list is missing or empty")
        return False

    print(f"Loaded {len(evals)} evaluation cases for skill: {data.get('skill_name', 'unknown')}\n")

    valid = True
    for idx, case in enumerate(evals, 1):
        case_id = case.get("id", f"case_{idx}")
        missing = [f for f in REQUIRED_FIELDS if f not in case]
        if missing:
            print(f"[{case_id}] FAILED: Missing fields: {missing}")
            valid = False
            continue

        # 检查 assertions 或 criteria 至少有一个非空列表
        assertions = case.get("assertions")
        criteria = case.get("criteria")
        has_assertions = isinstance(assertions, list) and len(assertions) > 0
        has_criteria = isinstance(criteria, list) and len(criteria) > 0

        if not (has_assertions or has_criteria):
            print(f"[{case_id}] FAILED: Either 'assertions' or 'criteria' must be a non-empty list")
            valid = False
            continue

        items_count = len(assertions) if has_assertions else len(criteria)
        rule_type = "assertions" if has_assertions else "criteria"
        print(f"[{case_id}] OK - {case['name']} ({items_count} {rule_type})")

    return valid


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    evals_file = os.path.join(current_dir, "evals.json")
    success = validate_evals(evals_file)
    if not success:
        sys.exit(1)
    print("\nAll evaluation cases passed structure validation successfully!")
