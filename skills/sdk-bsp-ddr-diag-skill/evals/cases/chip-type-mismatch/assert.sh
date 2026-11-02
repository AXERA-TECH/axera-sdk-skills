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
assert data["verdict_class"] == "config_issue", "log shows DDR3 2133Mbps, not a DDR2 timing problem"
assert data["claim_mismatch"] is True, "log facts contradict the claimed AX615DV100 DDR2 1333"
assert data["detected"]["dram_type"] == "DDR3", "log prints: dram type is DDR3"
assert data["detected"]["freq_mbps"] == 2133, "log prints: ddr freq=2133Mbps"
assert set(data["sus_hits"]) & {"SUS-001", "SUS-002", "SUS-003"}, "expected type-override/fallback evidence SUS-001/002/003"
assert "ddr2-timing-tuning" in data["refused_actions"], "must refuse DDR2 timing advice while the DDR3 fallback is active"
PY
