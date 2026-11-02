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
    if 'IMAGE_' in check:
        focus = r'镜像|固件|编译|编入|sample_ipc_test|sample_ipczc_test|命令'
        evidence = [line for line in lines if re.search(focus, line)]
    evidence = evidence[:4]
    record = {
        'case': 'm57-mcal',
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
checks = (
    ('SafetyIsland/mcal/mcal_drv/Ipc/', 'MCAL_IPC_PATH'),
    ('SafetyIsland/rt-thread/bsp/m57/drivers/ipc/', 'RTOS_IPC_PATH'),
    ('IpcEptLinkStatusCheck', 'EPT_LINK_STATUS'),
    ('IpcZcLinkStatusCheck', 'ZC_LINK_STATUS'),
    ('sample_ipc_test', 'IPC_SAMPLE'),
    ('sample_ipczc_test', 'ZC_SAMPLE'),
    ('reference/ax_ipc_FAQ.md', 'FAQ_SOURCE'),
)
for term, code in checks:
    if term.endswith('/'):
        matched = re.search(re.escape(term.rstrip('/')) + r'(?:/|(?=$|[\s`*，。；：,;:]))', text)
    else:
        matched = term in text
    assert matched, f'RPMSG_ASSERT:M57_MCAL_MISSING_{code}'
availability = any(term in text for term in ('编入镜像', '编入当前镜像', '是否可用')) or re.search(
    r'(?:(?:编译|构建|集成|启用)(?:到|进|入)|编入)[^。；\n]{0,12}(镜像|固件)|'
    r'(镜像|固件)[^。；\n]{0,20}(已编译|包含|编入|集成|启用)[^。；\n]{0,24}(IPC|测试|应用|命令|示例|sample_)', text)
assert availability, 'RPMSG_ASSERT:M57_MCAL_IMAGE_AVAILABILITY'
assert not re.search(
    r'(无需|不必|不用|不需要)\s*(?:先\s*)?(编入|集成到|编译进|编译到)[^。；\n]{0,12}(镜像|固件)|'
    r'(无需|不必|不用|不需要)\s*(?:先\s*)?(确认|检查|核对)[^。；\n]{0,20}(镜像|固件|命令(?:是否)?可用)', text), 'RPMSG_ASSERT:M57_MCAL_UNSAFE_IMAGE_ASSUMPTION'
assert any(term in text for term in ('两端', '对端', '不能只改一端')), 'RPMSG_ASSERT:M57_MCAL_CROSS_DOMAIN'
assert 'ACK' in text, 'RPMSG_ASSERT:M57_MCAL_ACK'
PY
