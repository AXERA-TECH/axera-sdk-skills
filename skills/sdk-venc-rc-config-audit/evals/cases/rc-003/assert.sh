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

# 相似症状不同根因：两路码率超出，必须分通道给出不同根因
required = [
    r'5000',                          # chn0 实际码率
    r'490',                           # chn1 实际码率
    r'(MaxQp|MaxIQp|QP 上限)',
    r'(MaxQp|MaxIQp|QP).{0,8}30|30.{0,8}(MaxQp|MaxIQp)',   # chn0 QP 上限 30
    r'(?<!\d)48(?!\d)',               # chn1 QP 已到满量程 48
    r'(通道\s*0|chn\s*0|通道0)',
    r'(通道\s*1|chn\s*1|通道1)',
    r'(目标码率|TargetBitRate).{0,20}(偏低|不足|过小|过低|低于|提高|提升|上调)|(偏低|不足|过低|低于).{0,12}(目标码率|目标|码率)|(提高|提升|上调).{0,6}(目标码率|目标|码率|TargetBitRate)',
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 禁止把两路归为同一根因
forbidden = [
    r'两(个|路)?(通道|路).{0,25}(同一|相同|同样|同一个).{0,12}(根因|原因|问题)',
    r'根因相同',
]
hit = [p for p in forbidden if re.search(p, text)]
assert not hit, f"forbidden conclusion asserted: {hit}"
PY_ASSERT
