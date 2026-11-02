"""Strict standalone/group layout shared by publication and trusted maintenance tools."""

import json
import re

from scripts.content import files, fingerprints

NAME = re.compile(r'[a-z0-9][a-z0-9._-]*')


def valid_skill_path(name, path):
    if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(path, str):
        return False
    parts = path.split('/')
    return path == f'skills/{name}' or (len(parts) == 4 and parts[0] == 'skills'
            and NAME.fullmatch(parts[1]) is not None and parts[2:] == ['skills', name])


def group_manifest(name, entry, source_commit, members):
    return {'schema_version': 1, 'name': name, 'entry': entry,
            'source_commit': source_commit,
            'members': [{key: row[key] for key in ('name', 'sha256', 'content_sha256')}
                        for row in members]}


def read_layout(root):
    base = root / 'skills'
    if base.is_symlink() or not base.is_dir():
        raise ValueError('skills/ 缺失或为软链接')
    paths, groups = {}, []
    for unit in sorted(base.iterdir()):
        if not NAME.fullmatch(unit.name) or unit.is_symlink() or not unit.is_dir():
            raise ValueError('skills/ 包含非法收录项')
        list(files(unit))  # Complete boundary preflight before reading any content.
        manifest = unit / 'group.json'
        if not manifest.exists():
            entries = [unit]
        else:
            if set(p.name for p in unit.iterdir()) != {'group.json', 'skills'}:
                raise ValueError('组合只能包含 group.json 和 skills/')
            data = json.loads(manifest.read_text())
            if (not isinstance(data, dict) or set(data) != {'schema_version', 'name', 'entry', 'source_commit', 'members'}
                    or data['schema_version'] != 1 or data['name'] != unit.name
                    or not isinstance(data['source_commit'], str)
                    or not re.fullmatch(r'[0-9a-f]{40}', data['source_commit'])):
                raise ValueError('组合清单格式错误')
            members = data['members']
            if (not isinstance(members, list) or len(members) < 2
                    or any(not isinstance(m, dict) or set(m) != {'name', 'sha256', 'content_sha256'}
                           or not isinstance(m['name'], str) or not NAME.fullmatch(m['name'])
                           for m in members)):
                raise ValueError('组合成员格式错误')
            names = [m['name'] for m in members]
            if len(set(names)) != len(names) or data['entry'] not in names:
                raise ValueError('组合入口缺失或成员重复')
            directory = unit / 'skills'
            if not directory.is_dir() or sorted(p.name for p in directory.iterdir()) != sorted(names):
                raise ValueError('组合成员缺失或存在未声明成员')
            entries = [directory / name for name in names]
            for member, entry in zip(members, entries):
                if fingerprints(entry) != {k: member[k] for k in ('sha256', 'content_sha256')}:
                    raise ValueError('组合成员内容指纹不一致')
            groups.append({**data, 'path': unit.relative_to(root).as_posix(), **fingerprints(unit)})
        for entry in entries:
            if entry.name in paths or not (entry / 'SKILL.md').is_file():
                raise ValueError('技能集合包含重复名称或缺少 SKILL.md')
            paths[entry.name] = entry.relative_to(root).as_posix()
    if not paths:
        raise ValueError('已收录技能集合为空')
    return dict(sorted(paths.items())), groups


def validate_layout(root, rows, recorded_groups=None):
    paths, groups = read_layout(root)
    records = {row['name']: row for row in rows}
    if len(records) != len(rows) or paths != {name: row.get('path') for name, row in records.items()}:
        raise ValueError('安装来源技能集合或路径与目录不一致')
    for group in groups:
        members = [records[m['name']] for m in group['members']]
        for expected, row in zip(group['members'], members):
            if (any(row.get(k) != expected[k] for k in ('sha256', 'content_sha256'))
                    or row.get('source_commit') != group['source_commit']
                    or row.get('chips') != members[0].get('chips')):
                raise ValueError('组合成员指纹、来源 commit 或芯片范围不一致')
    if recorded_groups is not None and groups != recorded_groups:
        raise ValueError('组合清单或整体指纹与验证记录不一致')
    return groups
