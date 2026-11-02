#!/usr/bin/env python3
"""Automated Golden Case benchmarks and evaluation runner for sdk-axck-config."""

import json
import os
import subprocess
import sys
from pathlib import Path
import yaml


def evaluate_golden_case(case_dir: Path, validator_script: Path) -> dict:
    case_id = case_dir.name
    case_yaml = case_dir / "answer" / "case.yaml"
    oracle_yaml = case_dir / "answer" / "oracle.yaml"
    input_dir = case_dir / "input"

    if not case_yaml.is_file() or not oracle_yaml.is_file() or not input_dir.is_dir():
        return {"id": case_id, "status": "SKIP", "reason": "Missing case/oracle/input files"}

    with open(oracle_yaml, "r", encoding="utf-8") as f:
        oracle = yaml.safe_load(f)

    # Run validator tool on input directory
    cmd = [sys.executable, str(validator_script), "-d", str(input_dir), "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True)

    try:
        diag_output = json.loads(res.stdout)
    except json.JSONDecodeError:
        diag_output = {"raw": res.stdout, "stderr": res.stderr}

    output_str = json.dumps(diag_output, ensure_ascii=False) + "\n" + res.stdout + "\n" + res.stderr

    # Check evidence signatures in input files
    for source, sigs in oracle.get("evidence_signatures", {}).items():
        src_path = case_dir / source
        if not src_path.is_file():
            return {"id": case_id, "status": "FAIL", "reason": f"Missing signature source {source}"}
        src_content = src_path.read_text(encoding="utf-8", errors="replace")
        for sig in sigs:
            if sig.lower() not in src_content.lower():
                return {"id": case_id, "status": "FAIL", "reason": f"Missing signature '{sig}' in {source}"}

    # Check required concepts in diagnosis / validation output
    concept_checks = []
    for concept in oracle.get("required_concepts", []):
        found = concept.lower() in output_str.lower()
        concept_checks.append((concept, found))

    # Check forbidden conclusions
    forbidden_hits = []
    for forbidden in oracle.get("forbidden_conclusions", []):
        if forbidden.lower() in output_str.lower():
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
    validator_script = skill_root / "scripts" / "validate.py"

    print("=== 1. Running AXCK Configuration Golden Benchmarks ===")
    golden_cases = sorted([d for d in evals_dir.iterdir() if d.is_dir() and d.name.startswith("CFG-")])

    passed = 0
    total = len(golden_cases)

    for case_dir in golden_cases:
        res = evaluate_golden_case(case_dir, validator_script)
        if res["status"] == "PASS":
            print(f"[PASS] Golden Case: {res['id']}")
            passed += 1
        else:
            print(f"[{res['status']}] Golden Case: {res['id']} -> {res}")

    print("\n=== 2. Running Functional CLI & Unit Validations ===")
    # Test 1: CLI inspect
    total += 1
    config_dir = skill_root / "evals" / "fixtures" / "demo"
    cmd = [sys.executable, str(skill_root / "scripts" / "cli.py"), "inspect", "-c", str(config_dir), "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and "SC438HAI" in res.stdout:
        print("[PASS] Unit: inspect_pipeline_topology")
        passed += 1
    else:
        print(f"[FAIL] Unit: inspect_pipeline_topology -> {res.stderr}")

    # Test 2: Interpolation unit tests
    total += 1
    interp_script = skill_root / "scripts" / "test_interpolation.py"
    if interp_script.exists():
        res = subprocess.run([sys.executable, str(interp_script)], capture_output=True, text=True)
        if res.returncode == 0 and ("OK" in res.stderr or "OK" in res.stdout):
            print("[PASS] Unit: validate_interpolation_constraints")
            passed += 1
        else:
            print(f"[FAIL] Unit: validate_interpolation_constraints -> {res.stderr}")
    else:
        print("[FAIL] Unit: test_interpolation.py not found")

    print(f"\n=======================================================")
    print(f"Overall Benchmark Summary: {passed}/{total} passed (Pass Rate: {passed/total*100:.1f}%)")
    print(f"=======================================================")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
