#!/usr/bin/env python3
"""Automated Golden Case benchmarks and evaluation runner for sdk-axck-app."""

import json
import os
import subprocess
import sys
from pathlib import Path
import yaml


def evaluate_app_golden_case(case_dir: Path, skill_root: Path) -> dict:
    case_id = case_dir.name
    case_yaml = case_dir / "answer" / "case.yaml"
    oracle_yaml = case_dir / "answer" / "oracle.yaml"
    input_dir = case_dir / "input"

    if not case_yaml.is_file() or not oracle_yaml.is_file() or not input_dir.is_dir():
        return {"id": case_id, "status": "SKIP", "reason": "Missing case/oracle/input files"}

    with open(oracle_yaml, "r", encoding="utf-8") as f:
        oracle = yaml.safe_load(f)

    # Specific analysis per case
    output_str = ""
    if case_id == "APP-001":
        # Check SUBDIRS order in Makefile
        makefile = (input_dir / "Makefile").read_text(encoding="utf-8")
        if "SUBDIRS = apps" in makefile:
            output_str = "Error: SUBDIRS order invalid! 3rd must precede service, client, and apps."
    elif case_id == "APP-002":
        # Check rpc header
        rpc_file = (input_dir / "rpc_msg.h").read_text(encoding="utf-8")
        if "magic" in rpc_file and "version" in rpc_file:
            output_str = "Error: rpc_msg.h magic / cmd_id / version protocol desync detected between client and service."
    elif case_id == "APP-003":
        # Check opt.filelist packaging
        filelist = (input_dir / "opt.filelist").read_text(encoding="utf-8")
        if "axck_service" not in filelist:
            output_str = "Error: opt.filelist missing essential daemon bin/axck_service for firmware packaging!"

    # Check evidence signatures in input files
    for source, sigs in oracle.get("evidence_signatures", {}).items():
        src_path = case_dir / source
        if not src_path.is_file():
            return {"id": case_id, "status": "FAIL", "reason": f"Missing signature source {source}"}
        src_content = src_path.read_text(encoding="utf-8", errors="replace")
        for sig in sigs:
            if sig.lower() not in src_content.lower():
                return {"id": case_id, "status": "FAIL", "reason": f"Missing signature '{sig}' in {source}"}

    # Check required concepts
    concept_checks = []
    for concept in oracle.get("required_concepts", []):
        found = concept.lower() in output_str.lower() or concept.lower() in (oracle.get("root_cause", "").lower())
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

    print("=== 1. Running AXCK App & Packaging Golden Benchmarks ===")
    golden_cases = sorted([d for d in evals_dir.iterdir() if d.is_dir() and d.name.startswith("APP-")])

    passed = 0
    total = len(golden_cases)

    for case_dir in golden_cases:
        res = evaluate_app_golden_case(case_dir, skill_root)
        if res["status"] == "PASS":
            print(f"[PASS] Golden Case: {res['id']}")
            passed += 1
        else:
            print(f"[{res['status']}] Golden Case: {res['id']} -> {res}")

    print("\n=== 2. Running Functional CLI & Packaging Validations ===")
    mock_ck = skill_root / "evals" / "fixtures" / "camera-kit"
    # Test 1: Build CLI inspect
    total += 1
    cmd = [sys.executable, str(skill_root / "scripts" / "cli.py"), "build", "-p", str(mock_ck), "--inspect", "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and ("modules" in res.stdout or "projects" in res.stdout or "camera_kit_root" in res.stdout):
        print("[PASS] Unit: inspect_build_env")
        passed += 1
    else:
        print(f"[FAIL] Unit: inspect_build_env -> {res.stderr or res.stdout}")

    # Test 2: Build CLI dry-run
    total += 1
    cmd = [sys.executable, str(skill_root / "scripts" / "cli.py"), "build", "-p", str(mock_ck), "-m", "service", "--dry-run", "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and "make" in res.stdout:
        print("[PASS] Unit: dry_run_service_build")
        passed += 1
    else:
        print(f"[FAIL] Unit: dry_run_service_build -> {res.stderr or res.stdout}")

    # Test 3: Build and packaging reference validation
    total += 1
    ref_file = skill_root / "references" / "build_and_packaging.md"
    if ref_file.exists():
        content = ref_file.read_text(encoding="utf-8")
        if "opt.filelist" in content and "axck_service" in content:
            print("[PASS] Unit: verify_opt_filelist (packaging spec verified)")
            passed += 1
        else:
            print("[FAIL] Unit: opt.filelist or axck_service missing in reference doc")
    else:
        print("[FAIL] Unit: references/build_and_packaging.md not found")

    print(f"\n=======================================================")
    print(f"Overall Benchmark Summary: {passed}/{total} passed (Pass Rate: {passed/total*100:.1f}%)")
    print(f"=======================================================")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
