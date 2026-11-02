#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
assert "distro_bootcmd" in content, "Missing default bootcmd"
assert "extlinux" in content, "Missing extlinux.conf config file"
assert "sysboot" in content, "Missing sysboot core command"
print("ax637-distro-boot assertion passed")
PY
