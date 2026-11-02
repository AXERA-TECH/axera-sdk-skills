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

# 必答：单支（JENC chn1）冻结 + 其余链路正常 + 两轮差值
required = [
    r'(JENC|jenc)',
    r'(两轮|S1|S2|两次采样|差值)',
    r'63',             # jenc chn1 冻结基线计数
    # sess1 RegVal 冻结：引用数值 31232，或等价表述"寄存器停在 syncVal/RegVal 不变"
    r'(31232|寄存器.{0,30}(停|不变|冻结)|RegVal.{0,20}(不变|冻结|停))',
    r'(FrmRecv|SubmitCnt|SucCnt|hskCnt)',
    r'(正常|推进)',    # 必须陈述其余链路正常推进
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 禁错：判分支停滞时不得扩大为整组/整机停摆，不得误伤正常支路
forbidden = [
    '整个 IVPS 组', '整组卡死', '整机', '全部链路', '所有链路', '整体停摆',
    'venc chn0 停滞', 'VENC chn0 停滞', 'chn0 卡死', 'chn2 卡死', 'venc chn2 停滞',
]
# 强否定词出现在短语前 24 字符内视为引用并否定该结论，不计为命中
negations = ('不得', '不应', '不要', '不能', '不可', '不建议', '避免', '禁止', '排除', '切勿', '而非', '而不是', '并非', '不是', '勿', '无', '没有')
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
PY_ASSERT
