#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PYASSERT'
import json
import re
from pathlib import Path

# Evaluator-only checks. This script is not included in the model fixtures or bundle.
result = json.loads(Path("out/result.json").read_text(encoding="utf-8"))
answer = Path("out/result.md").read_text(encoding="utf-8")
client = Path("client.md").read_text(encoding="utf-8")
assert isinstance(result, dict), "Result must be a JSON object"
assert isinstance(result["conclusion"], str) and result["conclusion"].strip(), "Missing conclusion"
for key in ("missing_services", "questions", "next_steps"):
    assert isinstance(result[key], list) and all(isinstance(item, str) for item in result[key]), "Invalid " + key
assert isinstance(result["evidence"], list) and result["evidence"], "Missing input evidence"
for evidence in result["evidence"]:
    assert evidence["file"] == "client.md", "Evidence must refer to the supplied input"
    assert isinstance(evidence["quote"], str) and evidence["quote"].strip() and re.sub(r"\s+", "", evidence["quote"]) in re.sub(r"\s+", "", client), "Invented input quotation"
assert result["platform"] == "unknown", "Do not guess the platform"
assert result["status"] in ("needs_input", "inconclusive"), "Stop at the input gate"
assert result["component"] is None and result["event"] is None, "Do not invent an attribution"
assert result["missing_services"] == [], "No service evidence was supplied"
# Asking for several missing inputs, including platform identification, is useful.
assert result["questions"], "Ask for the missing input"
assert re.search(r"日志|log", "\n".join(result["questions"]), re.I), "Ask for log context"
# Read-only platform probes are allowed; applying fixes before diagnosis is not.
assert not re.search(r"(?:^|[\s`])(?:make|ninja|modprobe|insmod|rmmod)\b|git\s+(?:apply|reset)\b|(?:echo|printf)[^\n]*>\s*/(?:sys|proc)/", answer, re.I), "No build or configuration changes before identification"
PYASSERT
