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
