#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
lower = content.lower()
assert "jump_reset_boot" in content, "Missing jump_reset_boot entry point"
assert "Jump Reset Back" in content, "Missing reset main return log"
assert "reset main boot" in lower, "Missing reset main boot mode"
print("m57-reset-main assertion passed")
PY
