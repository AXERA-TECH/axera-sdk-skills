#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

content = Path("answer.md").read_text(encoding="utf-8")
assert "-k" in content, "Missing -k parameter for kernel"
assert "-u" in content, "Missing -u parameter for uboot"
assert "-a" in content, "Missing -a parameter for atf"
assert "-o" in content, "Missing -o parameter for optee"
print("repair-m57-sdk-sources assertion passed")
PY
