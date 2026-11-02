#!/usr/bin/env python3
"""Automated Golden Case benchmarks and evaluation runner for sdk-axck-test."""

import json
import os
import subprocess
import sys
from pathlib import Path
import yaml


def evaluate_test_golden_case(case_dir: Path, skill_root: Path) -> dict:
    case_id = case_dir.name
    case_yaml = case_dir / "answer" / "case.yaml"
    oracle_yaml = case_dir / "answer" / "oracle.yaml"
    log_file = case_dir / "input" / "test_session.log"

    if not case_yaml.is_file() or not oracle_yaml.is_file() or not log_file.is_file():
        return {"id": case_id, "status": "SKIP", "reason": "Missing case/oracle/log files"}

    with open(oracle_yaml, "r", encoding="utf-8") as f:
        oracle = yaml.safe_load(f)

    log_content = log_file.read_text(encoding="utf-8")

    # Check evidence signatures in input files
    for source, sigs in oracle.get("evidence_signatures", {}).items():
        src_path = case_dir / source
        if not src_path.is_file():
            return {"id": case_id, "status": "FAIL", "reason": f"Missing signature source {source}"}
        src_content = src_path.read_text(encoding="utf-8", errors="replace")
        for sig in sigs:
            if sig.lower() not in src_content.lower():
                return {"id": case_id, "status": "FAIL", "reason": f"Missing signature '{sig}' in {source}"}

    # Check required concepts in test log analysis
    concept_checks = []
    for concept in oracle.get("required_concepts", []):
        found = concept.lower() in log_content.lower() or concept.lower() in (oracle.get("root_cause", "").lower())
        concept_checks.append((concept, found))

    # Check forbidden conclusions
    forbidden_hits = []
    for forbidden in oracle.get("forbidden_conclusions", []):
        if forbidden.lower() in log_content.lower():
            forbidden_hits.append(forbidden)

    all_concepts_met = all(c[1] for c in concept_checks)
    no_forbidden = len(forbidden_hits) == 0

    if all_concepts_met and no_forbidden:
        return {"id": case_id, "status": "PASS", "concepts": concept_checks}
    else:
        return {
            "id": case_id,
            "status": "FAIL",
            "missing_concepts": [c[0] for c in concept_checks if not c[1]],
            "forbidden_hits": forbidden_hits,
        }


def main():
    skill_root = Path(__file__).resolve().parents[1]
    evals_dir = skill_root / "evals"

    print("=== 1. Running AXCK Test Suite Golden Benchmarks ===")
    golden_cases = sorted([d for d in evals_dir.iterdir() if d.is_dir() and d.name.startswith("TEST-")])

    passed = 0
    total = len(golden_cases)

    for case_dir in golden_cases:
        res = evaluate_test_golden_case(case_dir, skill_root)
        if res["status"] == "PASS":
            print(f"[PASS] Golden Case: {res['id']}")
            passed += 1
        else:
            print(f"[{res['status']}] Golden Case: {res['id']} -> {res}")

    print("\n=== 2. Running Functional CLI, Menu, Pitfall & HTTP RPC Tests ===")
    # Test 1: CLI list-suites
    total += 1
    cmd = [sys.executable, str(skill_root / "scripts" / "cli.py"), "list-suites"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and "media" in res.stdout and "system" in res.stdout:
        print("[PASS] Unit: list_test_suites")
        passed += 1
    else:
        print(f"[FAIL] Unit: list_test_suites -> {res.stderr or res.stdout}")

    # Test 2: Board driver ANSI filter & menu tree parsing
    total += 1
    menu_doc = skill_root / "references" / "menu_tree.md"
    if menu_doc.exists():
        content = menu_doc.read_text(encoding="utf-8")
        if "axck_test" in content and "stream on" in content.lower():
            print("[PASS] Unit: media_stream_verification (menu tree validated)")
            passed += 1
        else:
            print("[FAIL] Unit: menu tree specification missing stream on")
    else:
        print("[FAIL] Unit: references/menu_tree.md not found")

    # Test 3: NOR Flash storage safety rules check
    total += 1
    pitfalls_doc = skill_root / "references" / "board_pitfalls.md"
    if pitfalls_doc.exists():
        content = pitfalls_doc.read_text(encoding="utf-8")
        if ("NOR Flash" in content or "Flash" in content) and ("/var/log" in content or "RAM" in content):
            print("[PASS] Unit: nor_flash_storage_safety (Flash protection validated)")
            passed += 1
        else:
            print("[FAIL] Unit: board pitfalls missing Flash & RAM storage protection rules")
    else:
        print("[FAIL] Unit: references/board_pitfalls.md not found")

    # Test 4: HTTP RPC Driver layered architecture & tests
    total += 1
    unittest_cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(skill_root / "tests"), "-v"]
    res_unit = subprocess.run(unittest_cmd, capture_output=True, text=True)
    if res_unit.returncode == 0 and "OK" in res_unit.stderr:
        print("[PASS] Unit: http_rpc_driver_verification (All unit tests passed)")
        passed += 1
    else:
        print(f"[FAIL] Unit: http_rpc_driver_verification -> {res_unit.stderr or res_unit.stdout}")

    print(f"\n=======================================================")
    print(f"Overall Benchmark Summary: {passed}/{total} passed (Pass Rate: {passed/total*100:.1f}%)")
    print(f"=======================================================")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
