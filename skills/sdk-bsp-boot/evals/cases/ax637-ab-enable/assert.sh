#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
assert "config.mk" in content, "Missing config.mk file mention"
assert "SUPPORT_AB" in content, "Missing SUPPORT_AB flag mention"
assert "TRUE" in content or "true" in content, "Missing TRUE flag value"
print("ax637-ab-enable assertion passed")
PY
