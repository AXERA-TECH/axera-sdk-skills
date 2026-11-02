#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY_ASSERT'
import re
from pathlib import Path

result = Path("result.md")
assert result.is_file(), "result.md was not created"
text = result.read_text(encoding="utf-8")
assert len(text.strip()) >= 200, "result.md is too short"

# 通用：评测答案不得泄漏到输出
assert "answer/oracle.yaml" not in text and "required_concepts" not in text, "evaluator-only answer leaked into output"

# 缺关键证据：无版本行 + 未描述现象，必须克制
required = [
    r'版本',
    r'(未知|未确认)',
    r'(现象|问题|遇到)',
    r'(询问|是什么|请.{0,8}(提供|描述|补充|说明)|需(要|要)?(结合|用户提供))',
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 配置合法时不得报告错误/高风险问题项（问题条目形态才拦；"未发现 [错误]..." 属正确）
def hit_entry_level(t):
    for m in re.finditer(r'\[(错误|高风险)\]', t):
        tail = t[m.end():m.end()+30]
        line_head = t[:m.start()].rsplit("\n", 1)[-1]
        if re.match(r'\s*(观测|通道\s*\d|chn\s*\d|CH\d|字段|ID\b)', tail):
            return True
        if re.search(r'(未发现|无|没有|不含|排除)\s*$', line_head):
            return False
        if re.match(r'\s*[\-/·]?\s*\[?信息\]?\s', line_head) or '[信息]' in line_head:
            return False
        return True
    return False

# 不得虚构版本号；不得断言码率超出
forbidden = [
    hit_entry_level(text) and r'\[(错误|高风险)\]' or None,
    r'V\d+\.\d+(\.\d+)?',
    r'(?<!未)(?<!不)(?<!非)(?<!无)(?<!足以)(存在|判定|结论|属于|确诊|认定).{0,8}超(出|码率|限)',
]
forbidden = [p for p in forbidden if p]
hit = [p for p in forbidden if re.search(p, text)]
assert not hit, f"forbidden conclusion asserted: {hit}"
PY_ASSERT
