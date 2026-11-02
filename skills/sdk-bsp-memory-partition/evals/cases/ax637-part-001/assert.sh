#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PYTHON'
import json
import re
import unicodedata
from pathlib import Path
oracle = json.loads('{"assertions": [{"contains_any": ["partitions", ".json"]}, {"contains_any": ["KB", "KiB"]}, {"contains_any": ["block alignment", "块对齐", "对齐"]}, {"contains_any": ["bad-block", "坏块"]}, {"contains_any": ["image", "filesystem", "文件系统"]}, {"contains": "SBL"}, {"contains_any": ["容量", "容纳", "超过", "不足"]}, {"contains_any": ["不能", "无法", "不可", "不足", "超过"]}], "files": {"SafetyIsland/rt-thread/bsp/m57/configs_ax637/.keep": "", "build/platforms/axera/demo_nor_nand/fixture.txt": "Synthetic board-directory marker only; not a selected PLAT.\\n", "build/platforms/axera/ax637_demo_only_nand/fixture.txt": "Synthetic board-directory marker only; not a selected PLAT.\\n", "build/platforms/axera/ax637_demo_only_nand/config.mk": "# Synthetic SDK fixture; no hardware, images or toolchain.\\nSYSTEM_MEMORY_SZ := 0x40000000\\nLINUX_MEMORY_SZ := 0x18000000\\n"}, "structured": {"flash_capacity_bytes": 536870912, "rootfs_per_slot_bytes": 1073741824, "rootfs_slots": 2, "rootfs_total_bytes": 2147483648, "fits": false}}')
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
