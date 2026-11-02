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

assert d["classification"] in {"signal_path", "processing", "configuration", "inconclusive"}
assert "FULL_SCALE_MIC" in codes and "FULL_SCALE_REF" not in codes
assert m["audio"]["mic"]["rail_fraction"] > 0.001
assert m["audio"]["ref"]["rail_fraction"] == 0
facts = audio_observations() + " " + observations("capture.txt")
require(r"MIC", facts, "Identify the clipped MIC branch")
require(r"REF", facts, "Contrast the reference branch")
require(r"削顶|满幅|平台|clipp|full.scale", facts, "Recognize the observed clipping")
require(r"32767|32768|满幅.{0,12}(比例|样本)|rail_fraction", facts, "Cite the clipping measurement")
require(r"MIC|麦克风|采集|capture", actions, "Target the affected input branch")
require(r"增益|gain", actions, "Locate the gain stage introducing distortion")
require(r"ALC|自动电平", next_steps, "Check gain control before changing manual gain")
require(r"相邻|前级|上游|模拟|upstream|analog|adjacent", next_steps, "Bound the first distortion point")
require(r"目标|产品|target|product", regression, "Retain the product playback requirement")
require(r"弱.{0,8}(语音|近端)|近端.{0,8}(弱|拾音)|weak|pickup", regression, "Verify near-end pickup")
print("PASS: axaudioaec-004")
PY
