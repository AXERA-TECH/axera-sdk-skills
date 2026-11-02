#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY_ASSERT'
import re, sys
from pathlib import Path

report = Path("out/report.md")
assert report.is_file(), "out/report.md was not generated"
text = report.read_text(encoding="utf-8")
assert len(text.strip()) >= 40, f"out/report.md too short: {len(text.strip())} chars"

# Answer leakage check
assert "answer/oracle.yaml" not in text, "Evaluator oracle leaked into output"
assert "evaluator_only" not in text, "Evaluator metadata leaked into output"

# Required concepts
required = ['MP4_MUX_WAIT_KEY_VIOLATION', 'rwsWaitKey', 'effIsThumb', 'ChkCanWrite']
missing = [c for c in required if not re.search(re.escape(c), text, re.IGNORECASE)]
assert not missing, f"Missing required concepts: {missing}"

# Forbidden conclusions
forbidden = ['CMM 内存池耗尽', 'Sensor I2C', 'VENC 编码器崩溃']
forbidden_hits = [f for f in forbidden if re.search(re.escape(f), text, re.IGNORECASE)]
assert not forbidden_hits, f"Forbidden conclusion found: {forbidden_hits}"

print("PASS: Case assertion verified")
PY_ASSERT
