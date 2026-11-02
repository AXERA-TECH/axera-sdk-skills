#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

content = Path("answer.md").read_text(encoding="utf-8")
assert "config.mk" in content, "Missing config.mk file mention"
assert "SUPPORT_OPTEE" in content, "Missing SUPPORT_OPTEE flag mention"
assert "FALSE" in content or "false" in content, "Missing FALSE flag value"
assert "optee.img" in content, "Missing optee.img verification mention"
print("disable-optee-build-ax637 assertion passed")
PY
