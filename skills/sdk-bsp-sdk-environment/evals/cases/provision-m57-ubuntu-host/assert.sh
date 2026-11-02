#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

content = Path("answer.md").read_text(encoding="utf-8")
assert any(tc in content for tc in ["9.2", "gcc-arm-9.2", "aarch64-none-linux-gnu"]), "Missing ARM64 9.2 toolchain"
assert any(tc in content for tc in ["7.5", "arm-linux-gnueabi", "gcc-linaro-7.5"]), "Missing Linaro 7.5 toolchain"
assert "sdk_unpack.sh" in content, "Missing sdk_unpack.sh mention"
print("provision-m57-ubuntu-host assertion passed")
PY
