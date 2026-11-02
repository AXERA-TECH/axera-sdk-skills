#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
assert "OCM" in content, "Missing OCM default load target"
assert "DDR" in content, "Missing DDR split target"
assert "ddr_bin_offset" in content, "Missing ddr_bin_offset header field"
print("m57-rtos-ocm-ddr assertion passed")
PY
