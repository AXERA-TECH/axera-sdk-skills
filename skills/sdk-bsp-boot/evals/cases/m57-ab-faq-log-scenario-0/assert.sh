#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
assert "出厂" in content, "Missing factory-state scenario (出厂态/出厂前)"
assert ("异常断电" in content or "软复位" in content), "Missing 异常断电/软复位 trigger"
print("m57-ab-faq-log-scenario-0 assertion passed")
PY
