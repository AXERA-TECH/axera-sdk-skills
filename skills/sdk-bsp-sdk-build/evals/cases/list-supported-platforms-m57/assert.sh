#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

content = Path("answer.md").read_text(encoding="utf-8")
assert "make plist" in content, "Missing make plist command"
assert "BOARDNAME_FLASHTYPE" in content, "Missing BOARDNAME_FLASHTYPE naming rule"
print("list-supported-platforms-m57 assertion passed")
PY
