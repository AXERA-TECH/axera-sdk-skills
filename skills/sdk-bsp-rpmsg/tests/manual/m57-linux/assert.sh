#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import re
from pathlib import Path
import json
import sys


def _redact_line(line, focus=None):
    if re.search(r'password|passwd|token|secret|api[_ -]?key|authorization|bearer|密码|密钥|凭据', line, re.I):
        return '<REDACTED>'
    line = re.sub(
        r'(?:sk-|gh[po][_-])[A-Za-z0-9_-]+|[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|[A-Za-z0-9_-]{32,}',
        '<REDACTED>', line)
    match = re.search(focus, line) if focus else None
    if match:
        line = line[max(0, match.start() - 60):]
    return line[:240]


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
    focus = None
    if check.endswith('_DEVICE'):
        focus = r'/dev/rpzc' if 'RPZC_DEVICE' in check else r'/dev/rpmsg'
        evidence = [line for line in lines if re.search(focus, line)]
        if not evidence:
            focus = r'/dev/'
            evidence = [line for line in lines if re.search(focus, line)]
    evidence = evidence[:4]
    record = {
        'case': 'm57-linux',
        'phase': 'oracle',
        'kind': exception_type.__name__,
        'check': check,
        'answer_exists': answer_exists,
        'first_lines': [_redact_line(line) for line in lines[:2]],
        'evidence': [_redact_line(line, focus) for line in evidence],
    }
    print('RPMSG_DIAG:' + json.dumps(record, ensure_ascii=True), file=sys.stderr)
    if match:
        print('RPMSG_ASSERT:' + check, file=sys.stderr)


sys.excepthook = _diagnose

text = Path('out/answer.md').read_text(encoding='utf-8')
for term, code in (
    ('CONFIG_AXERA_MBOX', 'MBOX'), ('CONFIG_RPMSG_AXERA', 'RPMSG_DRIVER'),
    ('CONFIG_RPMSG_CHAR', 'RPMSG_CHAR'), ('CONFIG_RPMSG_CTRL', 'RPMSG_CTRL'),
    ('CONFIG_RPZC_SERVICE_RPMSG', 'RPZC_SERVICE'), ('CONFIG_RPZC_CONTROLLER', 'RPZC_CTRL'),
    ('memory-region', 'MEMORY_REGION'), ('mboxes', 'MAILBOX'),
):
    assert term in text, f'RPMSG_ASSERT:M57_LINUX_MISSING_{code}'
for device, placeholder, code in (('rpmsg_ctrl', 'X', 'RPMSG_DEVICE'), ('rpzc_ctrl', 'N', 'RPZC_DEVICE')):
    assert re.search(r'/dev/' + device + r'(?:[0-9]+|' + placeholder + r')(?![A-Za-z0-9_/-])', text), f'RPMSG_ASSERT:M57_LINUX_MISSING_{code}'
assert any(term in text for term in ('MCU', 'RTOS')), 'RPMSG_ASSERT:M57_LINUX_REMOTE_SIDE'
assert re.search(r'(不能|不可|不得|不应|不要|禁止|勿)[^。；\n]{0,24}(照搬|照抄|套用|直接使用)', text) or re.search(
    r'(仅|只是)[^。；\n]{0,6}(示例|参考)', text) or re.search(
    r'(核对|确认|读取|检查)[^。；\n]{0,24}(实际|当前|目标)[^。；\n]{0,12}(DTS|设备树|配置|地址)', text), 'RPMSG_ASSERT:M57_LINUX_BOARD_ADDRESS'
assert not re.search(r'(?<!不)(可以|允许|建议|应)\s*直接(照搬|照抄|套用)', text), 'RPMSG_ASSERT:M57_LINUX_UNSAFE_REUSE'
PY
