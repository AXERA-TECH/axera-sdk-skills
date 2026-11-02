#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path("answer.md")
assert path.is_file(), "Missing answer.md: the agent did not produce the required deliverable"
content = path.read_text(encoding="utf-8")
assert "SUPPORT_TEST_CASE_DEMO_BOOTCNT" in content, "Missing BootCnt build switch"
assert "boot_diag_info" in content, "Missing boot_diag_info structure"
assert any(token in content for token in ["hexdump", "dd ", "metadata"]), "Missing metadata dump method"
print("m57-bootcnt assertion passed")
PY
