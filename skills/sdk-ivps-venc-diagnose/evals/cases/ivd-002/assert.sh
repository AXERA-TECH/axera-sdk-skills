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

# 必答：结论为正常运行，且依据是两轮差值推进
required = [
    r'(正常|无卡死|未.{0,4}停滞|没有.{0,4}停滞|未发现.{0,4}(卡死|异常|停滞)|无异常|没有.{0,6}(卡死|异常|停滞))',
    r'(两轮|S1|S2|两次采样|差值)',
    r'1884',            # chn0 S1 计数基线
    r'2036',            # chn0 S2 推进值
    # 编码侧推进计数名：模型可能引用任一等价计数（FrmRecv/hskCnt 与 Send2EncCnt 同源推进）
    r'(Send2EncCnt|Send2Enc|FrmRecv|hskCnt)',
    r'EncSucCnt',
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 禁错：不得把正常在途/瞬时占用/未启用通道判为故障（宽泛词如"异常"交由盲测评分，
# assert 只拦行为结论，避免正常报告里"无异常"之类的表述误 FAIL）
forbidden = [
    '卡死', '停滞', '冻结',
    '需要调整', '建议调整', '需调整',
]
# 强否定词出现在短语前 24 字符内视为引用并否定该结论（如"无卡死""不是停滞"），不计为命中；
# 术语前紧邻"非"字（如"非停滞"）同样视为否定
negations = ('不得', '不应', '不要', '不能', '不可', '不建议', '避免', '禁止', '排除', '切勿', '而非', '而不是', '并非', '不是', '勿', '无', '没有', '未发现', '未检测到', '未见', '未落', '不判', '不算', '不把', '不构成', '构不成', '不视为', '不属于', '不直接判')
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
