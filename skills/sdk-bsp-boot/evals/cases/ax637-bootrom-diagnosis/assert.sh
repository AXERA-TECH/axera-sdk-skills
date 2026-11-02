#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
assert "CF" in content, "Missing BOOTROM char CF"
assert "checksum" in content.lower(), "Missing CF=checksum failure meaning"
print("ax637-bootrom-diagnosis assertion passed")
PY
