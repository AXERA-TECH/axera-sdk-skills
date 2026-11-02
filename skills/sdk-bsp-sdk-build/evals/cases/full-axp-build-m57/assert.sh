#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

content = Path("answer.md").read_text(encoding="utf-8")
assert "demo_nor_nand" in content, "Missing target PLAT demo_nor_nand"
assert any(cmd in content for cmd in ["clean all install axp", "make PLAT=demo_nor_nand clean all install axp"]), "Missing full build command"
assert any(path in content for path in ["build/out", ".axp"]), "Missing output artifact check"
print("full-axp-build-m57 assertion passed")
PY
