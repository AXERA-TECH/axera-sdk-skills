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
assert result["platform"] == "qnx", "Wrong platform"
assert result["status"] in ("diagnosed", "inconclusive"), "Identify the service gap without requiring a final root cause"
# No event tuple was supplied, so leaving its module unspecified is valid.
assert result["component"] is None or result["component"].lower() in ("fcu", "fcu_drv", "ax_mcal_cdd_fcu_safety"), "Unsupported event module"
assert result["event"] is None, "No event tuple was supplied"
assert result["missing_services"] == ["fcu_drv"], "Use the complete process snapshot"
assert "fcu_drv" in answer and "/proc/ax_diag" in answer, "Explain the missing process and correct platform path"
steps = "\n".join(result["next_steps"])
assert "/dev/fcu" in answer + steps, "Identify the affected FCU device"
assert re.search(r"启动|恢复|退出|start|restore", steps, re.I), "Investigate or restore the service"
assert re.search(r"验证|确认|回查|核对|verify|check", steps, re.I), "Include recovery verification"
PYASSERT
