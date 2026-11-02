#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUITE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SUITE_DIR/.." && pwd)"

# 在 axap-eval 容器中执行时，源码仓库挂载于工作空间，或 verify_eval_assertions.py 可通过 REPO_ROOT / 当前目录找到
if [ -f "$REPO_ROOT/scripts/verify_eval_assertions.py" ]; then
  PY_SCRIPT="$REPO_ROOT/scripts/verify_eval_assertions.py"
elif [ -f "/workspace/skills/sdk-bsp-sys-diag-skill/scripts/verify_eval_assertions.py" ]; then
  PY_SCRIPT="/workspace/skills/sdk-bsp-sys-diag-skill/scripts/verify_eval_assertions.py"
else
  # 兜底查找
  PY_SCRIPT="$(find / -name "verify_eval_assertions.py" 2>/dev/null | head -n 1)"
fi

python3 "$PY_SCRIPT" --eval-id 2 --file out/diagnosis.md
