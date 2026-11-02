#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY_ASSERT'
import json
import re
from pathlib import Path

RULES = {'status': 'failure', 'root_patterns': ['(旋转|Rotation)', '(失败|不支持|不匹配|fail|mismatch)', '(运行|切换|已.*建链|runtime)'], 'evidence_patterns': ['0x80110114', '1080', '1920'], 'sources': ['input/ivps.proc', 'input/link.proc', 'input/logctl.proc', 'input/serial.log', 'input/syslog.log', 'input/venc.proc', 'input/vin.proc']}
report = Path("result.md").read_text(encoding="utf-8")
assert len(report.encode()) >= 200, "result.md is too short"
data = json.loads(Path("result.json").read_text(encoding="utf-8"))
assert data["status"] == RULES["status"], "incorrect diagnostic status"
assert data["confidence"] in {"high", "medium", "low"}, "invalid confidence"
root_cause = data["root_cause"]
assert isinstance(root_cause, str) and root_cause.strip(), "missing root cause"
for pattern in RULES["root_patterns"]:
    assert re.search(pattern, root_cause, re.I), "missing conclusion concept: " + pattern
assert not any(marker in report + json.dumps(data, ensure_ascii=False)
               for marker in ("answer/oracle.yaml", "required_concepts", "reproducer.patch")), "evaluator-only material leaked"
missing = data["missing_information"]
assert isinstance(missing, list) and all(isinstance(x, str) for x in missing), "invalid missing_information"
evidence = data["evidence"]
assert isinstance(evidence, list), "invalid evidence"
for item in evidence:
    assert item["source"] in RULES["sources"], "undeclared evidence source"
    assert isinstance(item["quote"], str) and len(item["quote"].strip()) >= 5, "empty evidence quote"
if RULES["status"] == "incomplete":
    assert data["confidence"] == "low", "incomplete evidence cannot support high confidence"
    for name in ("serial", "syslog", "logctl", "vin", "venc", "link", "ivps"):
        assert name in " ".join(missing).lower(), "missing recapture requirement: " + name
    assert "INCONCLUSIVE" in report or "INCOMPLETE" in report, "missing input-gate result"
else:
    assert len(evidence) >= 2, "at least two evidence quotes required"
    quotes = "\n".join(item["quote"] for item in evidence)
    for pattern in RULES["evidence_patterns"]:
        assert re.search(pattern, quotes, re.I), "missing evidence marker: " + pattern
print("PASS: deterministic diagnostic assertions")
PY_ASSERT
