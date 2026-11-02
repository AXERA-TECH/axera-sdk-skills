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

# 必须声明单次采样限制并要求第二次采样
required = [
    r"(单次|一次|只有一)(采样|轮)",
    r"(疑似|待确认|未确认|尚不能确认|持续性)",
    r"(第二次|第二回|再(次|采一轮|采)|2 轮|两轮|S2|补采|重采|追加.{0,6}采样)",
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 禁止确定性卡死断言（"疑似卡死/疑似停滞"不算命中）
forbidden = [r"(已确认|确认)(的)?(卡死|停滞)", r"持续(卡死|停滞)"]
for pat in forbidden:
    m = re.search(pat, text)
    assert m is None, f"forbidden conclusion found: {m.group(0)}"
PY_ASSERT
