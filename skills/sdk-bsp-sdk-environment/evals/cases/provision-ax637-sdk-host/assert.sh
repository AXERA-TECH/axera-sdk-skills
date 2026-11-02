#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

content = Path("answer.md").read_text(encoding="utf-8")
assert any(tc in content for tc in ["5_4-2016q3", "arm-none-eabi", "5.4"]), "Missing RTOS toolchain 5.4"
assert any(f in content for f in ["rtconfig.py", "EXEC_PATH"]), "Missing RT-Thread EXEC_PATH alignment"
assert "scons" in content, "Missing scons mention"
print("provision-ax637-sdk-host assertion passed")
PY
