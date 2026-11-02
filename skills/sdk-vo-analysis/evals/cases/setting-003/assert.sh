#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY_ASSERT'
import re
from pathlib import Path

result = Path("result.md")
assert result.is_file(), "result.md was not created"
text = result.read_text(encoding="utf-8")
assert len(text.strip()) >= 200, "result.md is too short"
required = [r'588', r'338', r'148500', r'u8delaysel']
missing = [p for p in required if not re.search(p, text, re.IGNORECASE)]
assert not missing, f"missing required evidence markers: {missing}"
forbidden = ['一对一错']
# 强否定词出现在短语前 24 字符内视为引用并否定该结论（如“不得简化为 DDR=3”），不计为命中
negations = ('不得', '不应', '不要', '不能', '不可', '不建议', '避免', '禁止', '排除', '切勿', '而非', '而不是', '并非', '不是', '勿')
def forbidden_hit():
    low = text.casefold()
    for item in forbidden:
        needle = item.casefold()
        start = 0
        while True:
            index = low.find(needle, start)
            if index < 0:
                break
            if not any(neg in low[max(0, index - 24):index] for neg in negations):
                return item
            start = index + 1
    return None
hit = forbidden_hit()
assert hit is None, f"forbidden conclusion found: {hit}"
assert "answer/oracle.yaml" not in text and "required_concepts" not in text, "evaluator-only answer leaked into output"
PY_ASSERT
