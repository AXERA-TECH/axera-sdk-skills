#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PYTHON'
from pathlib import Path
text = Path("out/response.md").read_text()
assert any(x in text for x in ("平台", "板型", "platform")), "Must ask for platform"
assert any(x in text for x in ("确认", "指定", "提供", "请问", "告知")), "Must request clarification"
assert not list(Path(".").rglob("config.mk")), "Must not invent a target config"
PYTHON
