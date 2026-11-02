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
assert data["verdict_class"] == "config_issue", "LPDDR3 board ran the DDR3 flow; fix the type, not the eye window"
assert data["claim_mismatch"] is True, "log contradicts the claimed LPDDR3 2133 setup"
assert data["detected"]["dram_type"] == "DDR3", "log prints: dram type is DDR3"
assert data["detected"]["freq_mbps"] == 2133, "log prints: ddr freq=2133Mbps"
assert any(("DDR3 training start" in e) or ("dram type is DDR3" in e) for e in data["evidence"]), "log shows the DDR3 training flow ran"
assert set(data["sus_hits"]) & {"SUS-001", "SUS-002"}, "expected hardcoded/overridden ddr_type evidence SUS-001/SUS-002"
assert "read-eye-tuning" in data["refused_actions"], "must not tune read eye on the wrong (DDR3) training flow"
PY
