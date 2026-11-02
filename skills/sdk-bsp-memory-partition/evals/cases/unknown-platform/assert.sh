#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PYTHON'
import json
import re
import unicodedata
from pathlib import Path
oracle = json.loads('{"assertions": [{"contains_any": ["平台", "板型", "platform"]}, {"contains_any": ["确认", "指定", "提供", "告知", "请问"]}], "files": {"README.txt": "Synthetic workspace with no registered platform markers.\\n"}, "structured": {"platform": "unknown"}}')
text = Path("out/response.md").read_text(encoding="utf-8")
def normalize(value):
    value = unicodedata.normalize("NFKC", value).casefold().replace("u-boot", "uboot")
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
        else:
            raise AssertionError(f"Unknown assertion: {kind}")
for path, original in oracle["files"].items():
    assert Path(path).read_text() == original, f"Read-only fixture changed: {path}"
configs = {str(p) for p in Path(".").rglob("config.mk") if ".axap" not in p.parts}
assert configs == {p for p in oracle["files"] if p.endswith("config.mk")}, "Unexpected target config created"
if oracle["structured"] is not None:
    actual = json.loads(Path("out/analysis.json").read_text())
    assert actual == oracle["structured"], f"Calculation or routing mismatch: {actual}"
    for key, expected in oracle["structured"].items():
        assert type(actual[key]) is type(expected), f"Wrong field type: {key}"
PYTHON
