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

# 次生噪声：聚焦 chn1 的真错误，QVBR 的 '-' 占位不判异常
# 48/10 是低冲突数字（只在 QP 范围语境出现），裸匹配安全；
# "非法|颠倒|矛盾|大于" 保证模型真正点明 min>max，而非仅提到数字
required = [
    r'MinQp',
    r'(?<!\d)48(?!\d)',          # chn1 MinQp=48
    r'(?<!\d)10(?!\d)',          # chn1 MaxQp=10（Min>Max 颠倒）
    r'(非法|颠倒|矛盾|大于)',           # QP 范围颠倒必须点名
    r'QVBR',
    r'(未知|不适用|版本|确认)',         # QVBR 专属字段 '-' 按未知/需版本确认处理
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 不得把 chn0 判为错误/高风险（问题条目形态，双向顺序），不得把 chn2 的 '-' 当 0
forbidden = [
    r'(?i:(chn|ch|通道)\s*0)[^\n]{0,60}\[(错误|高风险)\]',
    r'\[(错误|高风险)\][^\n]{0,60}(?i:(chn|ch|通道)\s*0)',
    r'(chn\s*2|通道\s*2|通道2)(?:(?!通道|chn)[^。\n]){0,60}(?<![不未])(为|等于|是)\s*0(?!\d)',
]
hit = [p for p in forbidden if re.search(p, text)]
assert not hit, f"forbidden conclusion asserted: {hit}"
PY_ASSERT
