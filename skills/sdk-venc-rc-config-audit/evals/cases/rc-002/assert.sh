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

# 防误报：必须给出正常结论，并用配置/实测数字支撑
required = [
    r'(正常|无异常)',
    r'(?<!\d)48(?!\d)',              # QP 范围 10..48
    r'29\.8|30\.7',                  # RecvFps/OutFps
    r'(4118|4096|404|400)',          # 实际/目标码率
    r'(10%|以内|未超|范围内|偏差)',   # 偏差在阈值内的明确表述
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 正常现场不得报告错误/高风险问题项，不得虚构码率超出
# [错误]/[高风险] 只在"问题条目"语境才算误报；"未发现 [错误]..." 属正确表述
def hit_entry_level(t):
    for m in re.finditer(r'\[(错误|高风险)\]', t):
        tail = t[m.end():m.end()+30]
        line_head = t[:m.start()].rsplit("\n", 1)[-1]
        if re.match(r'\s*(观测|通道\s*\d|chn\s*\d|CH\d|字段|ID\b)', tail):
            return True
        if re.search(r'(未发现|无|没有|不含|排除)\s*$', line_head):
            return False
        if re.match(r'\s*[\-/·]?\s*\[?信息\]?\s', line_head) or '[信息]' in line_head:
            return False
        return True
    return False
# 码率超出只拦"断言式"结论（实际码率 + 超出 + 目标/上限 + 建议/处理），
# 否定/假设/列举语境（"若后续出现码率持续超出""码率持续超限"作现象举例）不拦
forbidden = [
    hit_entry_level(text) and r'\[(错误|高风险)\]' or None,
    r'(实际码率|BitRate).{0,15}(超出|超过).{0,10}(目标|上限).{0,15}(需|应|建议|处理|解决)',
]
forbidden = [p for p in forbidden if p]
hit = [p for p in forbidden if re.search(p, text)]
assert not hit, f"forbidden conclusion asserted: {hit}"
PY_ASSERT
