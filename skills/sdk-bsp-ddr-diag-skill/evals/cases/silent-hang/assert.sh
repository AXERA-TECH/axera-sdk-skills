#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path

# Evaluator-only oracle: this script is not part of fixtures or installed-bundle.
data = json.loads(Path("out/result.json").read_text(encoding="utf-8"))
assert data["schema_version"] == 1
assert data["status"] == "ok"
assert data["verdict_class"] in {"design_expected", "config_issue", "known_fix", "suspected_defect", "inconclusive"}
assert data["confidence"] in {"low", "mid", "high"}
assert len(data["evidence"]) >= 1
assert data["verdict_class"] == "inconclusive", "FAQ-001 verdict is 待验证, a silent hang proves nothing about the DRAM"
assert "FAQ-001" in data["faq_hits"], "expected FAQ-001 hit"
assert "dram-damage-verdict" in data["refused_actions"], "must not conclude DRAM damage from a single log line"
steps = " ".join(data["next_steps"])
assert ("日志开关" in steps) or ("DEBUG" in steps.upper()), "must ask to enable the BL1 debug log switch"
assert any(k in steps for k in ("重新编译", "重新采集", "完整日志")), "must rebuild/recapture with full logging before further triage"
PY
