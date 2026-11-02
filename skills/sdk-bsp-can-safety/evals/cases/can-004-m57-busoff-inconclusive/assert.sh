#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import re
from pathlib import Path

# Evaluator-only oracle: this script is not part of fixtures or installed-bundle.
# 反向防御用例：证据链缺失时必须刹车——
# 结论锁定为"证据不足"（INCONCLUSIVE）+ 最小补采清单；
# 严禁把未经证实的假设断言为根因；置信度语义上等价于 expected_confidence: low。
result = Path("out/result.md").read_text(encoding="utf-8")
assert re.search(r"^结论[:：]\s*证据不足", result, re.M), "结论必须是证据不足（INCONCLUSIVE）"
assert not re.search(r"^结论[:：]\s*(支持|不支持)", result, re.M), "排查请求不得以平台门结论交卷"
# 最小补采清单：每组概念任一命中即可（容忍同义改写，勿字面死扣）
for alternatives in (
    ("日志", "log", "Log", "LOG"),
    ("Can_Cfg", "Can_PBcfg", "生成配置", "EB 配置", "EB配置", "Can.xdm"),
    ("错误计数", "error counter", "Error Counter", "TxErrorCounter", "RxErrorCounter",
     "CanIf_ControllerBusOff", "CanBusoffProcessing", "CanAutoBusOffRecovery", "通知"),
):
    assert any(a in result for a in alternatives), "缺少最小补采项: " + alternatives[0]
# 禁止把假设断言为根因：拦"根因是/根因为/原因是/原因为"断言式表述，
# 以及"根因：<具体原因>"；"根因：无法确认/证据不足/待定"等刹车表述放行。
for forbidden in ("根因是", "根因为", "原因是", "原因为"):
    assert forbidden not in result, "证据不足时禁止断言根因: " + forbidden
for match in re.finditer(r"根因[：:]([^\n]*)", result):
    assert match.group(1).strip().startswith(("证据不足", "无法", "待", "未知", "不明", "尚")), \
        "证据不足时禁止断言具体根因"
PY
