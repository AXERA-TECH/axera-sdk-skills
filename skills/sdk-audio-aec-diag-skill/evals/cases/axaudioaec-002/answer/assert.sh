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

assert d["classification"] in {"signal_path", "inconclusive"}
assert "REFERENCE_ZERO" in codes
assert m["audio"]["ref"]["zero_fraction"] == 1
assert m["audio"]["mic"]["power"] > 0
facts = observations("capture.txt") + " " + audio_observations()
require(r"VQE_REF", facts, "Use the actual reference capture point")
require(r"全零|非零.{0,8}0|zero|参考.{0,8}缺失", facts, "Identify the reference observation")
require(r"播放|扬声器|playback|speaker", facts, "Relate reference absence to active playback")
require(r"来源|路由|接线|源选择|source|routing|wiring", actions, "Trace the reference path")
require(r"采集|录音|dump|capture|record", next_steps, "Plan a fresh capture after checking the reference route")
require(r"参考|REF|reference", regression, "Verify reference content after correction")
print("PASS: axaudioaec-002")
PY
