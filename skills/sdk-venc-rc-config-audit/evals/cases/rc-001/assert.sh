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

# 呼吸效应归因锚点：CBR + I 帧质量配置（MaxIQp/Iprop）+ GOP=30 周期 1 秒
required = [
    r'CBR',
    r'MaxIQp',
    r'MaxIQp.{0,8}30|30.{0,8}MaxIQp',   # MaxIQp=30（chn0 I 帧 QP 上限）
    r'Iprop(?:Max)?|I\s*帧',
    r'GOP.{0,8}30|Gop.{0,8}30',          # GOP=30 @30fps -> 周期 1 秒
    r'呼吸',
    r'1\s*秒|一秒|1\s*s\b',
    r'(副作用|牺牲|清晰度|画质)',          # 修改建议必须交代 I 帧清晰度代价
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 码率 4118 相对目标 4096 偏差约 0.5%，未超 10%，不得断言码率超出。
# 只拦"断言式"结论（实际码率 + 超出/超过 + 目标/上限 + 建议/处理），
# 否定/假设/列举语境（"若后续出现码率持续超出""码率持续超限"作现象举例）不拦
forbidden = [
    r'(实际码率|BitRate).{0,15}(超出|超过).{0,10}(目标|上限).{0,15}(需|应|建议|处理|解决)',
    r'更换编码(格式|器|芯片)',
]
hit = [p for p in forbidden if re.search(p, text)]
assert not hit, f"forbidden conclusion asserted: {hit}"
PY_ASSERT
