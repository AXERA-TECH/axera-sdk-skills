#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

content = Path("answer.md").read_text(encoding="utf-8")
assert "kernel/linux" in content or "kernel" in content, "Missing kernel directory"
assert "ax637_demo_only_nand" in content, "Missing AX637 target PLAT"
assert "ax637-tiny_defconfig" in content, "Missing defconfig"
assert "kernel.img" in content, "Missing kernel.img artifact"
print("standalone-kernel-build-ax637 assertion passed")
PY
