#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import json
import re
import sys


def _redact_line(line):
    if re.search(r'password|passwd|token|secret|api[_ -]?key|authorization|bearer|密码|密钥|凭据', line, re.I):
        return '<REDACTED>'
    return re.sub(
        r'(?:sk-|gh[po][_-])[A-Za-z0-9_-]+|[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|[A-Za-z0-9_-]{32,}',
        '<REDACTED>', line)[:240]


def _diagnose(exception_type, exception, traceback):
    match = re.search(r'RPMSG_ASSERT:([A-Z0-9_]{1,160})(?![A-Z0-9_])', str(exception))
    check = match.group(1) if match else 'EXCEPTION'
    answer_exists = False
    lines = []
    try:
        answer_path = Path('out/answer.md')
        answer_exists = answer_path.is_file() and not answer_path.is_symlink() and not answer_path.parent.is_symlink()
        if answer_exists:
            with answer_path.open('rb') as answer:
                lines = answer.read(32768).decode('utf-8', errors='replace').splitlines()
    except (OSError, UnicodeError):
        pass
    evidence = [line for line in lines if re.search(
        r'QNX|主域判定|同步判定|地址|配置|共享|实际|板|示例|照搬|照抄|DTS|SafetyIsland|Ipc', line)]
    if any(term in check for term in ('BOARD', 'ADDRESS', 'REUSE')):
        evidence.sort(key=lambda line: not re.search(r'地址|配置|共享|实际|板|示例|照搬|照抄|DTS', line))
    evidence = evidence[:4]
    record = {
        'case': 'm57-qnx',
        'phase': 'oracle',
        'kind': exception_type.__name__,
        'check': check,
        'answer_exists': answer_exists,
        'first_lines': [_redact_line(line) for line in lines[:2]],
        'evidence': [_redact_line(line) for line in evidence],
    }
    print('RPMSG_DIAG:' + json.dumps(record, ensure_ascii=True), file=sys.stderr)
    if match:
        print('RPMSG_ASSERT:' + check, file=sys.stderr)


sys.excepthook = _diagnose

text = Path('out/answer.md').read_text(encoding='utf-8')
for term, code in (
    ('M57', 'M57'), ('QNX', 'QNX'), ('kernel/osdrv/open_drv/ax_ipc/', 'DRIVER_PATH'),
    ('Ipc_cfg', 'IPC_CFG'), ('Ipc_zc_cfg', 'ZC_CFG'), ('LocalAddr', 'LOCAL_ADDR'),
    ('RemoteAddr', 'REMOTE_ADDR'), ('RL_ADDR_ANY', 'ADDR_ANY'), ('NEED_NS', 'NAME_SERVICE'),
    ('IPC_ZC_BUFFER_BY_DDR', 'BUFFER_MEMORY'), ('IPC_GPIO_TRIGGER_IRQ_EN', 'IRQ_MODE'),
    ('IRAM', 'IRAM'), ('DDR', 'DDR'), ('sample_ipc_rpmsg', 'SAMPLE'),
    ('pidin syspage=asinfo', 'RESERVED_MEMORY'),
):
    assert term in text, f'RPMSG_ASSERT:M57_QNX_MISSING_{code}'
assert any(term in text for term in ('MCU', 'RTOS')), 'RPMSG_ASSERT:M57_QNX_REMOTE_SIDE'
assert any(term in text for term in ('同步', '两端')), 'RPMSG_ASSERT:M57_QNX_CROSS_DOMAIN'
PY
