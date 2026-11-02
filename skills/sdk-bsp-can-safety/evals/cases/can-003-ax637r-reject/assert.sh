#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import re
from pathlib import Path

# Evaluator-only oracle: this script is not part of fixtures or installed-bundle.
# 原 answer/oracle.yaml（CAN-003）验收语义的确定性转写；
# evidence 签名由 tests/test_structure.py 静态校验，此处只断言模型输出。
result = Path("out/result.md").read_text(encoding="utf-8")
assert re.search(r"^结论[:：]\s*不支持", result, re.M), "结论必须是不支持；AX637R Safety 侧是 RTT RTOS CAN"
assert not re.search(r"^结论[:：]\s*支持", result, re.M), "结论不得为支持"
for concept in ("AX637R", "RTT"):
    assert concept in result, "result.md 缺少必需概念: " + concept
assert not re.search(r"因为.*Linux.*不支持", result), "禁止把主项目 OS 当作拒绝原因"
for forbidden in ("Bus-Off 处理建议", "Bus-Off 恢复建议", "CanAutoBusOffRecovery"):
    assert forbidden not in result, "禁止在不支持场景下给出 M57 MCAL Bus-Off 建议: " + forbidden
PY
