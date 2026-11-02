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

# 矛盾数据：DstFr=30 与 OutFps=15 偏差 50%，须先指出矛盾再给候选方向
required = [
    r'(OutFps|输出帧率).{0,8}15|15\.0',          # OutFps=15（减半）
    r'DstFr.{0,8}30|30.{0,8}DstFr',              # DstFr=30
    r'50%|偏差.{0,10}50',                          # 偏差约 50%
    r'RecvFps.{0,10}29\.8|29\.8',                 # 输入侧正常的关键对照
    r'(515|1031|一半|减半)',                       # BsFrmCnt 恰为 FrmRecv 一半的佐证
    r'(码流|ffprobe|日志)',                        # 下一步补证方向
]
missing = [p for p in required if not re.search(p, text)]
assert not missing, f"missing required evidence markers: {missing}"

# 不得在证据不足时断言唯一根因
# 只拦"断言式"结论（根因是输入/播放器/显示 或 播放器显示问题导致），
# 区分/列举语境（"区分编码丢帧与封装/播放显示问题"）不算断言
forbidden = [
    r'(根因|原因|首因).{0,15}(是|为).{0,30}(输入|VIN|供帧|上游).{0,10}(不足|问题|异常|未供帧)',
    r'(根因|原因|首因).{0,15}(是|为|在于).{0,20}(播放器|显示)',
    r'(播放器|显示).{0,12}(问题|异常|慢).{0,12}(导致|引起|造成)',
]
hit = [p for p in forbidden if re.search(p, text)]
assert not hit, f"forbidden conclusion asserted: {hit}"
PY_ASSERT
