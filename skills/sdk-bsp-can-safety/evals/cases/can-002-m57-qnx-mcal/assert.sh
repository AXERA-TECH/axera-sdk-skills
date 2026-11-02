#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import re
from pathlib import Path

# Evaluator-only oracle: this script is not part of fixtures or installed-bundle.
# 原 answer/oracle.yaml（CAN-002）验收语义的确定性转写；
# evidence 签名由 tests/test_structure.py 静态校验，此处只断言模型输出。
result = Path("out/result.md").read_text(encoding="utf-8")
assert re.search(r"^结论[:：]\s*支持", result, re.M), "结论必须是支持；主项目 QNX 不影响 Safety 侧 MCAL CAN 适用性"
assert not re.search(r"^结论[:：]\s*不支持", result, re.M), "结论不得为不支持"
for concept in ("M57", "AUTOSAR MCAL", "Safety"):
    assert concept in result, "result.md 缺少必需概念: " + concept
assert not re.search(r"因为.*QNX.*不支持", result), \
    "禁止把主项目 QNX 当作拒绝原因"
PY
