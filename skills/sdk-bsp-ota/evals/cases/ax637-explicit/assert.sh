#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PYASSERT'
"""External, deterministic decision checks; embedded in each isolated assert.sh."""
import json
import re
from pathlib import Path


def check_result(result, answer, oracle, skill_root):
    assert result.get('case_id', '').lower() == oracle['id'], 'case id mismatch'
    assert result.get('skill') == 'sdk-bsp-ota', 'skill identity mismatch'
    decisions = result.get('decisions')
    assert isinstance(decisions, dict), 'missing structured decisions'
    assert decisions.keys() == oracle['expected'].keys(), 'decision fields mismatch'
    for key, expected in oracle['expected'].items():
        actual = decisions[key]
        accepted = oracle.get('accepted_values', {}).get(key, [expected])
        assert type(actual) is type(expected) and actual in accepted, f'incorrect decision: {key}'
    assert result.get('execution_scope') == 'offline_analysis', 'wrong execution scope'
    assert result.get('device_operations_performed') == [], 'device operations claimed'
    evidence = result.get('evidence')
    assert isinstance(evidence, list) and evidence, 'missing evidence paths'
    citations = result.get('decision_evidence')
    assert isinstance(citations, dict) and citations.keys() == decisions.keys(), 'missing decision citations'
    for key, citation in citations.items():
        assert isinstance(citation, dict), f'invalid citation: {key}'
        path, quote = citation.get('path'), citation.get('quote')
        assert isinstance(path, str) and path in evidence, 'citation absent from evidence list'
        relative = Path(path)
        assert not relative.is_absolute() and '..' not in relative.parts, 'invalid evidence path'
        assert path in ('SKILL.md', 'routing.yaml') or relative.parts[0] in ('platforms', 'reference'), 'non-runtime evidence'
        source = (skill_root / relative).resolve()
        assert source.is_relative_to(skill_root.resolve()), 'evidence escapes skill'
        assert isinstance(quote, str) and len(quote.strip()) >= 8, 'citation too short'
        assert quote in source.read_text(), f'fabricated citation: {key}'
    # The judged decision is also visible in the human-readable answer, not a
    # private self-reported score. Free-form explanation is not the test oracle.
    marker = '## 自动验收决策'
    assert answer.count(marker) == 1, 'missing canonical decision section'
    canonical = answer.split(marker, 1)[1].strip()
    blocks = re.findall(r'```json[ \t]*\n(.*?)\n```', canonical, flags=re.S)
    assert len(blocks) == 1, 'expected one canonical JSON decision block'
    assert json.loads(blocks[0]) == decisions, 'answer/result decisions differ'

ORACLE = {'id': 'ax637-explicit', 'expected': {'explicit_platform': 'm57', 'detected_platform': 'ax637', 'target_conflict': True, 'configuration_change_allowed': False}, 'accepted_values': {}}
check_result(json.loads(Path('out/result.json').read_text()),
             Path('out/answer.md').read_text(), ORACLE,
             Path('.axap/opencode/skills/marketplace/sdk-bsp-ota'))
print('PASS: structured decisions, exact source citations and canonical answer agreement')
PYASSERT
