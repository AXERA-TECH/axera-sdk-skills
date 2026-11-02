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

# 必答：指出矛盾 + INCONCLUSIVE/不一致结论 + 排查方向
required = [
    r'(不一致|矛盾|冲突|INCONCLUSIVE|无法.{0,4}(判定|定性|自洽))',
    r'(SW_Low_Mem|HSK|link_table)',
    r'(SessId|session|SESSION|syncagent)',
    r'(排查|核对|核实|确认|重采|检查)',
    # chn0 计数旁证（oracle：可作旁证不消除矛盾）：引用数值 1884 或等价"计数仍在推进"表述
    r'(1884|计数.{0,12}(推进|增长|正常)|业务计数)',
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 禁错：把矛盾现场强行归因为确定性根因
forbidden = ['卡死', '硬件故障', '固件异常', '停滞']
# 强否定词出现在短语前 24 字符内视为引用并否定该结论，不计为命中；
# 术语前紧邻"非"字（如"非卡死"）同样视为否定；
# '疑似/可能/假设/候选/若以' 保护受控假设表述（oracle 允许），不算命中
negations = ('不得', '不应', '不要', '不能', '不可', '不建议', '避免', '禁止', '排除', '切勿', '而非', '而不是', '并非', '不是', '勿', '无', '没有', '疑似', '可能', '假设', '候选', '若以', '不下', '不判', '不算', '不把', '不构成', '构不成', '不视为', '不属于', '不直接判')
def forbidden_hit():
    low = text.casefold()
    for item in forbidden:
        needle = item.casefold()
        start = 0
        while True:
            index = low.find(needle, start)
            if index < 0:
                break
            negated = any(neg in low[max(0, index - 24):index] for neg in negations) \
                or (index > 0 and low[index - 1] == '非')
            if not negated:
                return item
            start = index + 1
    return None
hit = forbidden_hit()
assert hit is None, f"forbidden conclusion found: {hit}"
PY_ASSERT
