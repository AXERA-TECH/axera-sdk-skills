#!/usr/bin/env python3
"""Validate report structure and evidence presence, not acoustic truth."""
import argparse
from pathlib import Path

from analyze import local_file, read_json

SCENARIOS = {"far_only", "near_only", "double_talk", "silence", "trigger"}
CLASSES = {"configuration", "signal_path", "timing", "processing", "sdk_suspected", "inconclusive"}
OUTPUTS = {"measurements.json", "measurements.md", "diagnosis.json", "diagnosis.md"}


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be nonempty text")


def records(data, field, keys):
    value = data.get(field)
    if not isinstance(value, list):
        raise ValueError(field + " must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(field + " entries must be objects")
        for key in keys:
            text(item.get(key), field + "[" + str(index) + "]." + key)
    return value


def strings(data, field):
    value = data.get(field)
    if not isinstance(value, list):
        raise ValueError(field + " must be a list")
    for item in value:
        text(item, field)
    return value


def evidence_file(base, reference):
    text(reference, "evidence path")
    path = local_file(base, reference.split("#", 1)[0])
    if path in {(base / name).resolve() for name in OUTPUTS}:
        raise ValueError("Generated reports cannot certify their own resolution")
    if path.stat().st_size == 0:
        raise ValueError("Evidence file is empty: " + reference)


def validate(data, base):
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("diagnosis schema_version must be 1")
    if data.get("status") not in ("needs_evidence", "pending_verification", "resolved"):
        raise ValueError("Invalid diagnosis status")
    if data.get("classification") not in CLASSES:
        raise ValueError("Invalid diagnosis classification")
    text(data.get("summary"), "summary")
    evidence = records(data, "evidence", ("source", "observation"))
    strings(data, "hypotheses")
    actions = records(data, "actions", ("change", "reason", "rollback", "expected", "falsifier"))
    if not actions:
        raise ValueError("At least one action or verification step is required")
    missing = strings(data, "missing_evidence")
    if data["status"] == "needs_evidence" and not missing:
        raise ValueError("needs_evidence requires an actionable evidence gap")
    if data["classification"] != "inconclusive" and not evidence:
        raise ValueError("A classified observation requires evidence")
    regression = records(data, "regression", ("scenario", "criterion", "status", "evidence"))
    if not SCENARIOS <= {r["scenario"] for r in regression}:
        raise ValueError("Regression must cover four speech scenarios and trigger")
    for item in regression:
        if item["status"] not in ("not_run", "pass", "fail"):
            raise ValueError("Invalid regression status")
        if item["status"] in ("pass", "fail"):
            evidence_file(base, item["evidence"])
    resolution = strings(data, "resolution_evidence")
    for item in resolution:
        evidence_file(base, item)
    if data["status"] == "resolved":
        if data["classification"] in ("inconclusive", "sdk_suspected") or not evidence or missing or not resolution:
            raise ValueError("resolved requires confirmed classification, evidence and no unresolved gaps")
        if any(r["status"] != "pass" for r in regression):
            raise ValueError("resolved requires every listed regression to pass")
    return data


def validate_output(base):
    base = Path(base).resolve()
    for name in OUTPUTS:
        path = local_file(base, name)
        if path.stat().st_size == 0:
            raise ValueError("Empty output: " + name)
    measurement = read_json(base / "measurements.json")
    if not isinstance(measurement, dict) or measurement.get("status") not in ("measured", "needs_evidence"):
        raise ValueError("Invalid measurement status")
    return validate(read_json(base / "diagnosis.json"), base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        data = validate_output(args.out)
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
    print("PASS: report structure and evidence presence; status=" + data["status"] + "; acoustic outcome requires independent verification")


if __name__ == "__main__":
    main()
