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
assert result["platform"] == "linux", "Wrong platform"
assert result["status"] in ("diagnosed", "inconclusive"), "Expected attribution with any remaining root-cause uncertainty"
assert re.fullmatch(r"(?:AX_MAIN_BSP_)?ISP_PIPE(?:_[A-Z0-9]+)*", result["component"] or "", re.I), "Event 17 must be decoded with its module"
assert result["event"] == {"domain": 0, "module": 45, "event": 17}, "Wrong diagnostic tuple"
assert result["missing_services"] == [], "No service absence is established"
assert "ISP" in answer and re.search(r"帧|frame", answer, re.I), "Explain the ISP frame event"
assert re.search(r"ECM|FCU", "\n".join(result["next_steps"])), "Include the ECM/FCU reporting-path check"
PYASSERT
