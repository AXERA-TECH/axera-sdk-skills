#!/usr/bin/env bash
# Standalone evaluator assertion; generated from answer/assert.sh and scripts/validate_report.py.
# The generator is not included in this delivery.
set -euo pipefail
python3 - <<'PY'
import hashlib
import json
import re
from pathlib import Path

# Evaluator-only checks; inputs contain observations, not expected answers.
d = json.loads(Path("out/diagnosis.json").read_text(encoding="utf-8"))
m = json.loads(Path("out/measurements.json").read_text(encoding="utf-8"))
assert d["schema_version"] == 1
assert d["status"] in {"needs_evidence", "pending_verification"}
assert not d["resolution_evidence"], "No complete acceptance evidence is supplied"
assert d["summary"].strip() and d["missing_evidence"]
assert isinstance(d["hypotheses"], list)
assert m["verification"] == "not_run" and not m["input_errors"]
assert set(m["audio"]) == {"mic", "ref", "output"}
for role, point in (("mic", "vqeIn"), ("ref", "vqeRef"), ("output", "vqeOut")):
    raw = Path(f"AiCard0_Dev0_{point}.pcm").read_bytes()
    measured = m["audio"][role]
    assert measured["sha256"] == hashlib.sha256(raw).hexdigest()
    assert measured["samples"] == len(raw) // 2 and measured["sample_rate"] == 16000
assert {row["section"] for row in m["proc_tables"]} >= {
    "AI DEV ATTR", "AI DEV AEC ATTR", "AI DEV DUMP AND BYPASS", "AO DEV STATUS"}
assert m["energy_reduction_proxy_db"] is None
assert d["actions"] and all(all(str(a.get(k, "")).strip() for k in
    ("change", "reason", "rollback", "expected", "falsifier")) for a in d["actions"])
assert {r["scenario"] for r in d["regression"]} >= {
    "far_only", "near_only", "double_talk", "silence", "trigger"}
assert all(r["status"] == "not_run" and r["criterion"] and r["evidence"] for r in d["regression"])
assert Path("out/diagnosis.md").stat().st_size > 80

def observations(name):
    entries = [e["observation"] for e in d["evidence"] if
               re.search(r"(?:^|/)" + re.escape(name) + r"(?:[:#]|$)", e["source"])]
    assert entries, "Missing evidence from " + name
    return " ".join(entries)

def audio_observations():
    entries = [e["observation"] for e in d["evidence"] if
               re.search(r"(?:^|/)(?:measurements\.json|AiCard0_Dev0_vqe(?:In|Ref|Out)\.pcm)(?:[:#]|$)",
                         e["source"])]
    assert entries, "Missing evidence from measured audio"
    return " ".join(entries)

def require(pattern, text, message):
    assert re.search(pattern, text, re.I), message

actions = json.dumps(d["actions"], ensure_ascii=False)
next_steps = actions + " " + " ".join(d["missing_evidence"])
regression = json.dumps(d["regression"], ensure_ascii=False)
codes = {item["code"] for item in m["findings"]}

assert d["classification"] in {"processing", "inconclusive"}
assert not codes
observations("proc.txt")
facts = audio_observations()
require(r"MIC|输入|input", facts, "Use the pre-processing observation")
require(r"输出|output", facts, "Use the damaged speech observation")
require(r"NS|降噪", next_steps, "Check concurrent noise suppression")
require(r"AGC|增益", next_steps, "Check gain processing")
require(r"VAD|语音活动", next_steps, "Check voice activity processing")
require(r"单变量|单项|一次.{0,6}一|逐项|one.{0,15}(time|variable)|single.variable", actions,
        "Propose a controlled comparison")
require(r"首字|近端|可懂度|保真|intelligib|near.end", regression, "Verify near-end speech preservation")
require(r"回声|echo", regression, "Verify echo alongside near-end speech")
print("PASS: axaudioaec-005")
PY
python3 - --out out <<'AEC_REPORT_VALIDATOR'
#!/usr/bin/env python3
"""Validate report structure and evidence presence, not acoustic truth."""
import argparse
from pathlib import Path

import json

MAX_TEXT_BYTES = 2 * 1024 * 1024

def read_json(path):
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("JSON exceeds 2 MiB")
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)

def local_file(base, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("Evidence paths must be nonempty relative paths")
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise ValueError("Evidence missing or outside input directory: " + name)
    return path

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
AEC_REPORT_VALIDATOR
