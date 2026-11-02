#!/usr/bin/env python3
"""Automated Golden Case benchmarks and evaluation runner for sdk-axck-diag."""

import json
import os
import subprocess
import sys
from pathlib import Path
import yaml

def evaluate_case(case_dir: Path, doctor_script: Path) -> dict:
    case_id = case_dir.name
    case_yaml = case_dir / "answer" / "case.yaml"
    oracle_yaml = case_dir / "answer" / "oracle.yaml"
    serial_log = case_dir / "input" / "serial.log"

    if not case_yaml.is_file() or not oracle_yaml.is_file() or not serial_log.is_file():
        return {"id": case_id, "status": "SKIP", "reason": "Missing case/oracle/log files"}

    with open(oracle_yaml, "r", encoding="utf-8") as f:
        oracle = yaml.safe_load(f)

    # Run doctor tool on serial.log
    cmd = [sys.executable, str(doctor_script), "-f", str(serial_log), "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode not in (0, 1):
        return {"id": case_id, "status": "FAIL", "reason": f"Doctor crashed (code {res.returncode}): {res.stderr}"}

    try:
        diag_output = json.loads(res.stdout)
    except json.JSONDecodeError:
        # Fallback to string search if not valid JSON
        diag_output = {"raw": res.stdout}

    output_str = json.dumps(diag_output, ensure_ascii=False) + "\n" + res.stdout

    # Check evidence signatures
    sig_checks = []
    signatures = oracle.get("evidence_signatures", {}).get("input/serial.log", [])
    for sig in signatures:
        found = sig.lower() in output_str.lower() or sig in serial_log.read_text(encoding="utf-8")
        sig_checks.append((sig, found))

    # Check required concepts in diagnosis
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
    doctor_script = skill_root / "scripts" / "doctor.py"

    cases = sorted([d for d in evals_dir.iterdir() if d.is_dir() and d.name.startswith("AXCK-")])
    print(f"=== Running AXCK Golden Benchmarks ({len(cases)} cases) ===")

    passed = 0
    total = len(cases)

    for case_dir in cases:
        res = evaluate_case(case_dir, doctor_script)
        if res["status"] == "PASS":
            print(f"[PASS] {res['id']}")
            passed += 1
        else:
            print(f"[{res['status']}] {res['id']} -> {res}")

    print(f"\nBenchmark Summary: {passed}/{total} passed (Pass Rate: {passed/total*100:.1f}%)")
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
