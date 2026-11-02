#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PYTHON'
import json
import re
import shlex
import unicodedata
from pathlib import Path
oracle = json.loads('{"assertions": [{"contains": "ax637_demo_only_nand"}, {"contains": "SECURE_BOOT"}, {"contains_any": ["TRUE", "开启"]}, {"contains": "SIGN_USE_RSA3072"}, {"contains": "FALSE"}, {"contains": "ENABLE_CIPHER"}, {"contains": "ROOTFS_DMVERITY"}, {"contains": "ROOTFS_FS_TYPE"}, {"contains": "UBI"}, {"contains_any": ["编译", "构建", "make -C build", "dry-run"]}, {"contains_any": ["未烧写", "不烧写", "不会烧写"]}], "config": "build/platforms/axera/ax637_demo_only_nand/config.mk", "original": "# Synthetic SDK fixture; no hardware, signing keys or build toolchain.\\nSECURE_BOOT := FALSE\\nENABLE_CIPHER := FALSE\\nSIGN_USE_RSA3072 := FALSE\\nSIGN_USE_RSA_PSS := FALSE\\nROOTFS_DMVERITY := FALSE\\nROOTFS_FS_TYPE := UBI\\n"}')
text = Path("out/response.md").read_text(encoding="utf-8")
def normalize(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"slot\s*[:：]?\s*(\d)", r"slot\1", value)
    return re.sub(r"[\s`*]+", "", value)

normalized = normalize(text)
for rule in oracle["assertions"]:
    for kind, expected in rule.items():
        if kind == "contains":
            assert normalize(expected) in normalized, f"Missing: {expected}"
        elif kind == "contains_any":
            assert any(normalize(value) in normalized for value in expected), f"Missing any of: {expected}"
        elif kind == "not_contains":
            assert normalize(expected) not in normalized, f"Unexpected: {expected}"
        elif kind == "command_tokens":
            commands = []
            for line in text.splitlines():
                try:
                    tokens = shlex.split(line.replace("`", " "))
                except ValueError:
                    continue
                commands.append(["-n" if t == "--dry-run" else t for t in tokens])
            assert any(set(expected) <= set(tokens) for tokens in commands), f"Missing command tokens: {expected}"
        else:
            raise AssertionError(f"Unknown assertion: {kind}")
assert Path(oracle["config"]).read_text() == oracle["original"], "Read-only SDK config changed"
PYTHON
