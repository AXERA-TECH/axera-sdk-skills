#!/usr/bin/env bash
# 克隆仓库和解压套件共用的安装入口，只依赖 Python 3 标准库。
set -euo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$REPO_ROOT/scripts/install_skills.py" "$@"
