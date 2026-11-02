#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import re
from pathlib import Path
import json
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
        'case': 'ax637-rpzc',
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
for term in ('AX637', 'CHECK_AVAIL', 'IpcZcLinkStatusCheck', 'ACK'):
    assert term in text, f'RPMSG_ASSERT:AX637_RPZC_MISSING_{term.upper()}'
for code, choices in (('BUFFER_NAME', ('BufferName', 'buffer name', 'buffer 名')),
                      ('SHARED_MEMORY', ('reserved-memory', '共享内存')),
                      ('ENDPOINT', ('endpoint', 'name service')),
                      ('RESET', ('reset', 'reinit', '重启'))):
    assert any(term in text for term in choices), f'RPMSG_ASSERT:AX637_RPZC_MISSING_{code}'
assert re.search(r'(不|勿|不可|不能).{0,15}(直接)?照搬.{0,20}(M57|示例|地址)', text), 'RPMSG_ASSERT:AX637_RPZC_BOARD_ADDRESS'
assert not re.search(r'(?<!不)(可以|可|应|建议)\s*直接照搬\s*M57', text), 'RPMSG_ASSERT:AX637_RPZC_UNSAFE_REUSE'
PY
