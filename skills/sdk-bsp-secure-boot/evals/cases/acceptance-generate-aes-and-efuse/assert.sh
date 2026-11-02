#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PYTHON'
import json
import re
import shlex
import unicodedata
from pathlib import Path
oracle = json.loads('{"assertions": [{"contains": "openssl rand -hex 32"}, {"contains": "aes-256.key"}, {"contains": "sample_efuse_key"}, {"contains": "sample_efuse"}, {"contains": "EFUSE_WRITE_ENABLE"}, {"contains": "rootkey random"}, {"contains": "pubkey"}, {"contains": "aeskey"}, {"contains": "bondoption"}, {"contains_any": ["ax_efuse_key aeskey", "改源码", "aeskey_static_array"]}], "config": "build/platforms/axera/demo_nor_nand/config.mk", "original": "# Synthetic SDK fixture; no hardware, signing keys or build toolchain.\\nSECURE_BOOT := FALSE\\nENABLE_CIPHER := FALSE\\nSIGN_USE_RSA3072 := FALSE\\nSIGN_USE_RSA_PSS := FALSE\\nROOTFS_DMVERITY := FALSE\\nROOTFS_FS_TYPE := UBI\\n"}')
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
