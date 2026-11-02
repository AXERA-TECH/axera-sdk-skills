#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8").lower()
for token in ["bootrom", "sbl", "spl", "bl31", "u-boot", "kernel"]:
    assert token in content, f"Missing boot stage: {token}"
assert "op-tee" in content or "optee" in content, "Missing OP-TEE boot stage"
print("m57-boot-chain assertion passed")
PY
