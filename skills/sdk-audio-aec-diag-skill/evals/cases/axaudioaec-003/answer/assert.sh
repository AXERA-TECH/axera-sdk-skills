#!/usr/bin/env bash
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

def require(pattern, text, message):
    assert re.search(pattern, text, re.I), message

actions = json.dumps(d["actions"], ensure_ascii=False)
next_steps = actions + " " + " ".join(d["missing_evidence"])
regression = json.dumps(d["regression"], ensure_ascii=False)
codes = {item["code"] for item in m["findings"]}

assert d["classification"] in {"timing", "configuration"}, "Identify the delay configuration mismatch"
assert m["delay"]["status"] == "estimated", "Expected stable delay"
assert abs(m["delay"]["lag_ms"] - 2) <= 0.0625, "Expected MIC to lag REF by 2 ms"
valid = [w["candidate_lag_ms"] for w in m["delay"]["windows"] if w["accepted"]]
assert len(valid) >= 3 and max(valid) - min(valid) <= 0.0625, "Expected stable valid windows"
comp = m["delay"]["parameter_comparison"]
assert comp["status"] == "not_comparable", "Do not invent parameter semantics or tolerance"
assert m["delay"]["capture_stage"] == "unknown", "Capture compensation stage is not supplied"
assert not any(code.startswith("DELAY_PARAMETER_") for code in codes), "No documented parameter mapping"
require(r"语义|定义|映射|semantics|definition|mapping", next_steps, "Request the parameter definition")
require(r"采集|补偿|capture|compensation", next_steps, "Confirm the capture position")
observations("proc.txt")
observations("capture.txt")
observations("config.txt")
require(r"ref_delay_ms.{0,30}(?<![0-9])20(?![0-9])", observations("application.log"), "Use the 20 readback")
require(r"参考|REF|reference", next_steps, "Check the reference delay")
require(r"读回|readback|app_get", next_steps, "Verify the effective setting")
require(r"单变量|单项|一次.{0,6}一|逐项|one.{0,15}(time|variable)|single.variable", actions,
        "Propose a controlled comparison")
require(r"回声|echo", regression, "Verify echo after adjustment")
require(r"近端|保真|near.end|fidelity", regression, "Verify near-end preservation")
print("PASS: axaudioaec-003")
PY
