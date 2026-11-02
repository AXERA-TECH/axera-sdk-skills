#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
assert "sdk-bsp-secure-boot" in content, "Missing route to sdk-bsp-secure-boot"
assert "efuse" in content.lower(), "Missing eFuse rationale"
print("m57-scope-boundary assertion passed")
PY
