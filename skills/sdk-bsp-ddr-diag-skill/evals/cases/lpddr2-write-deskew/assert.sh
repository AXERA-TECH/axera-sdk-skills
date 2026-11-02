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
assert data["verdict_class"] == "inconclusive", "FAQ-DDR-007 verdict is 待验证, not a confirmed root cause"
assert data["detected"]["dram_type"] == "LPDDR2", "log prints: dram type is LPDDR2"
assert data["detected"]["freq_mbps"] == 800, "log prints: ddr freq=800Mbps"
assert any("write deskew training fail" in e for e in data["evidence"]), "first failure is write deskew training"
assert set(data["faq_hits"]) & {"FAQ-002", "FAQ-DDR-006", "FAQ-DDR-007"}, "expected a training-fail FAQ hit (FAQ-002/FAQ-DDR-006/FAQ-DDR-007)"
assert set(data["refused_actions"]) & {"write-eye-tuning", "freq-tuning"}, "must not suggest timing/freq tuning before common preconditions"
ask = " ".join(data["missing_info"] + data["next_steps"]).upper()
assert ("ELPIDA" in ask) or ("JSC" in ask), "must ask which DV110 LPDDR2 vendor branch (ELPIDA/JSC)"
PY
