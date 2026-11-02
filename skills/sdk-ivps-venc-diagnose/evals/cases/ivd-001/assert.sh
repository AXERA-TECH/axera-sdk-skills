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

# 两轮采样与关键寄存器/计数锚点
required = [
    r'21120',            # VPP 侧 update 推进到的寄存器值
    # 编码侧 update 停在 initVal：引用数值 20992 或等价表述（initVal 字样）
    r'(20992|initVal)',
    r'HwUsed',
    r'(Send2EncCnt|Send2Enc)',
    r'EncSucCnt',
    r'(反压|传播|级联)',   # 上游冻结须解释为传播，不得判为独立首因
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 必须基于两轮差值确认停滞
assert re.search(r'(两轮|S1|S2|两次采样|差值)', text), "stall must be confirmed by two-sample delta"
PY_ASSERT
