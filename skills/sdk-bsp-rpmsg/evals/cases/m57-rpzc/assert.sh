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
        answer_path = Path('out/result.json')
        answer_exists = answer_path.is_file() and not answer_path.is_symlink() and not answer_path.parent.is_symlink()
        if answer_exists:
            with answer_path.open('rb') as answer:
                lines = answer.read(32768).decode('utf-8', errors='replace').splitlines()
    except (OSError, UnicodeError):
        pass
    evidence = [line for line in lines if re.search(
        r'"(?:check_available_before_transmit|receive_steps|reply_ack_only_if_requested|reuse_sender_buffer_after_ack)"\s*:', line)]
    evidence = evidence[:4]
    record = {
        'case': 'm57-rpzc',
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

result = json.loads(Path('out/result.json').read_text(encoding='utf-8'))
assert isinstance(result, dict), 'RPMSG_ASSERT:M57_RPZC_OBJECT'
assert result.get('check_available_before_transmit') is True, 'RPMSG_ASSERT:M57_RPZC_CHECK_AVAILABLE'
assert result.get('receive_steps') == ['RECEIVE_BUF', 'CONSUME_PAYLOAD', 'REPLY_ACK'], 'RPMSG_ASSERT:M57_RPZC_STEP_ORDER'
assert result.get('reply_ack_only_if_requested') is True, 'RPMSG_ASSERT:M57_RPZC_ACK_CONDITION'
assert result.get('reuse_sender_buffer_after_ack') is True, 'RPMSG_ASSERT:M57_RPZC_BUFFER_REUSE'
PY
