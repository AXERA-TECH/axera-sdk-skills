#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
assert "load mtd" in content, "Missing load mtd command"
assert "booti" in content, "Missing booti command"
print("ax637-simple-bootcmd-nonab assertion passed")
PY
