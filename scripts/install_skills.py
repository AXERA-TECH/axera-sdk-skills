#!/usr/bin/env python3
"""克隆与解压安装共用的 Python 标准库入口；保护未管理内容与本地修改。"""

import argparse
import fcntl
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.content import fingerprints
from scripts.skill_layout import valid_skill_path, validate_layout


def default_target():
    local = Path.cwd() / '.opencode/skills'
    if local.is_dir():
        return local
    for relative in ['.config/opencode/skills', '.agents/skills']:
        candidate = Path.home() / relative
        if candidate.is_dir():
            return candidate
    return Path.home() / '.agents/skills'


def install(root, target, chip=None, mode='copy', channel='external', group=None):
    root = root.resolve()
    target = target.expanduser().absolute()
    if target.is_symlink():
        raise ValueError('目标目录不能为软链接')
    target = target.resolve()
    if target == root or root in target.parents or target in root.parents:
        raise ValueError('安装目标与交付内容不能重叠')
    catalog = verify_source(root)
    rows = catalog['skills']
    groups = validate_layout(root, rows, catalog.get('groups', []))
    family = None
    if chip:
        for name, definition in catalog['chip_definitions'].items():
            if chip.lower() in [str(alias).lower() for alias in [name] + definition.get('aliases', [])]:
                family = name
                break
        if not family:
            raise ValueError(f'未知芯片: {chip}')
    selected = [row for row in rows if not chip or '*' in row['chips'] or family in row['chips']]
    if group:
        match = next((g for g in groups if g['name'] == group), None)
        if match is None:
            raise ValueError(f'未知技能组合: {group}')
        member_names = {m['name'] for m in match['members']}
        selected = [row for row in selected if row['name'] in member_names]
    for unit in groups:
        members = {m['name'] for m in unit['members']}
        chosen = members & {row['name'] for row in selected}
        if chosen and chosen != members:
            raise ValueError('芯片筛选不能拆分技能组合')
    if not selected:
        raise ValueError('没有匹配芯片的技能')
    target.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(target / '.axap-install.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _install_locked(root, target, selected, mode)


def _install_locked(root, target, rows, mode):
    state_path = target / '.axap_installed.json'
    if state_path.is_symlink():
        raise ValueError('安装台账不能为软链接')
    state = json.loads(state_path.read_text()) if state_path.exists() else {'schema_version': 1, 'skills': {}}
    if state.get('schema_version') != 1 or not isinstance(state.get('skills'), dict):
        raise ValueError('安装台账格式不兼容')
    changes = []
    for row in rows:
        destination = target / row['name']
        previous = state['skills'].get(row['name'])
        if destination.exists() or destination.is_symlink():
            if not previous:
                raise ValueError(f'{row["name"]}: 目标存在未管理内容')
            if destination.is_symlink():
                if previous.get('mode') != 'link' or os.readlink(destination) != previous.get('source'):
                    raise ValueError(f'{row["name"]}: 链接被修改，保留现有内容')
                current = fingerprints(destination.resolve())
            else:
                current = fingerprints(destination)
            linked_update = (destination.is_symlink() and mode == 'link' and
                             destination.resolve() == root / row['path'] and
                             current['content_sha256'] == row['content_sha256'])
            if current['content_sha256'] != previous['content_sha256'] and not linked_update:
                raise ValueError(f'{row["name"]}: 目标存在本地修改，保留现有内容')
            if (current['content_sha256'] == row['content_sha256'] and previous.get('mode') == mode
                    and previous['content_sha256'] == row['content_sha256']
                    and (mode != 'link' or linked_update)):
                continue
        changes.append(row)
    if not changes:
        return {'status': 'NOOP', 'installed': 0, 'selected': len(rows)}
    transaction = Path(tempfile.mkdtemp(prefix='.axap-install-', dir=target.parent))
    operations = []
    completed = False
    state_attempted = False
    prepared_state = transaction / 'state.json'
    try:
        for row in changes:
            prepared = transaction / 'new' / row['name']
            prepared.parent.mkdir(parents=True, exist_ok=True)
            if mode == 'link':
                prepared.symlink_to(root / row['path'], target_is_directory=True)
            else:
                shutil.copytree(root / row['path'], prepared, ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache', '*.pyc'))
            if fingerprints(prepared.resolve())['content_sha256'] != row['content_sha256']:
                raise ValueError('暂存安装内容指纹不一致')
        next_state = {**state, 'skills': dict(state['skills'])}
        for row in changes:
            next_state['skills'][row['name']] = {'sha256': row['sha256'], 'content_sha256': row['content_sha256'],
                                                'version': row['version'], 'mode': mode, 'source': str(root / row['path'])}
        prepared_state.write_text(json.dumps(next_state, indent=2, ensure_ascii=False) + '\n')
        if state_path.exists():
            shutil.copy2(state_path, transaction / 'old-state.json')
        for row in changes:
            destination = target / row['name']
            backup = transaction / 'old' / row['name']
            backup.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                previous = state['skills'].get(row['name'])
                if not previous:
                    raise ValueError('安装期间目标出现未管理内容')
                if destination.is_symlink() and (previous.get('mode') != 'link' or os.readlink(destination) != previous.get('source')):
                    raise ValueError('安装期间目标链接被修改')
                expected = row['content_sha256'] if destination.is_symlink() and mode == 'link' and destination.resolve() == root / row['path'] else previous['content_sha256']
                if fingerprints(destination.resolve())['content_sha256'] != expected:
                    raise ValueError('安装期间目标被修改')
                operations.append((destination, backup))
                destination.replace(backup)
                if fingerprints(backup.resolve())['content_sha256'] != expected:
                    raise ValueError('安装期间目标被修改')
            else:
                operations.append((destination, backup))
            (transaction / 'new' / row['name']).replace(destination)
        state_attempted = True
        prepared_state.replace(state_path)
        completed = True
    except BaseException as error:
        recovery_failed = False
        for destination, backup in reversed(operations):
            try:
                prepared = transaction / 'new' / destination.name
                installed = not prepared.exists() and not prepared.is_symlink()
                if installed and (destination.exists() or destination.is_symlink()):
                    # 撤回到事务目录；保留失败期间产生的内容。
                    withdrawn = transaction / 'withdrawn' / destination.name
                    withdrawn.parent.mkdir(parents=True, exist_ok=True)
                    destination.replace(withdrawn)
                if backup.exists() or backup.is_symlink():
                    backup.replace(destination)
            except OSError:
                recovery_failed = True
        if recovery_failed:
            raise RuntimeError(f'安装恢复失败，备份保留在 {transaction}')
        if state_attempted and not prepared_state.exists():
            old_state = transaction / 'old-state.json'
            if old_state.exists():
                old_state.replace(state_path)
            else:
                state_path.unlink(missing_ok=True)
        raise RuntimeError(f'安装已撤回，恢复材料保留在 {transaction}') from error
    finally:
        if completed:
            shutil.rmtree(transaction)
    return {'status': 'UPDATED', 'installed': len(changes), 'selected': len(rows)}


def verify_source(root):
    """Verify the public installation manifest without writing to the filesystem."""
    allowed = {'.git', '.gitignore', '.gitattributes', '.github', 'docs', 'configs', 'scripts', 'skills',
               'README.md', 'README.en.md', 'INSTALLATION.md', 'CONTRIBUTING.md', 'CHANGELOG.md',
               'LICENSE', 'NOTICE', 'install.sh', 'router.yaml'}
    ignored = {'__pycache__', '.pytest_cache'}
    if any(path.name not in allowed | ignored for path in root.iterdir()):
        raise ValueError('公开仓包含未批准的顶层文件')
    if {p.name for p in (root / 'configs').iterdir()} != {'validation.json'}:
        raise ValueError('公开仓包含内部配置')
    expected_scripts = {'__init__.py', 'install_skills.py', 'content.py', 'skill_layout.py', 'publish_release.py'}
    if {p.name for p in (root / 'scripts').iterdir()} - ignored != expected_scripts:
        raise ValueError('公开安装脚本集合不一致')
    if (root / 'docs').is_dir() and {p.name for p in (root / 'docs').iterdir()} != {'assets'}:
        raise ValueError('公开仓包含未批准文档')
    from scripts.content import files
    list(files(root))  # Reject symlinks and credential paths before reading the manifest.
    if {path.relative_to(root / '.github').as_posix() for path in files(root / '.github')} != {'workflows/release.yaml'}:
        raise ValueError('公开工作流集合不一致')
    manifest = root / 'configs/validation.json'
    if manifest.is_symlink():
        raise ValueError('清单不能为软链接')
    catalog = json.loads(manifest.read_text())
    if (not isinstance(catalog, dict) or set(catalog) != {'schema_version', 'chip_definitions', 'skills'}
            or type(catalog['schema_version']) is not int or catalog['schema_version'] != 3):
        raise ValueError('公开安装清单格式不兼容')
    definitions = catalog['chip_definitions']
    if not isinstance(definitions, dict) or not definitions:
        raise ValueError('缺少芯片定义')
    for name, definition in definitions.items():
        if (not isinstance(definition, dict) or not isinstance(definition.get('aliases', []), list)
                or any(not isinstance(alias, str) or not alias for alias in definition.get('aliases', []))):
            raise ValueError('芯片别名格式错误')
    rows = catalog['skills']
    if not isinstance(rows, list) or not rows:
        raise ValueError('技能集合为空')
    fields = {'name', 'description', 'version', 'chips', 'path', 'sha256', 'content_sha256'}
    for row in rows:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError('技能清单字段不兼容')
        if (not valid_skill_path(row['name'], row['path'])
                or not isinstance(row['description'], str) or not row['description'].strip()
                or not isinstance(row['version'], str) or not row['version'].strip()
                or not isinstance(row['chips'], list) or not row['chips']
                or len(set(row['chips'])) != len(row['chips'])
                or any(chip not in definitions and chip != '*' for chip in row['chips'])):
            raise ValueError('技能元数据或芯片范围无效')
        if fingerprints(root / row['path']) != {key: row[key] for key in ('sha256', 'content_sha256')}:
            raise ValueError('安装来源与目录指纹不一致')
    validate_layout(root, rows, [])
    license_path = root / 'LICENSE'
    if license_path.is_symlink() or not license_path.is_file() or not license_path.read_text().strip():
        raise ValueError('缺少 LICENSE')
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument('--target', default='auto', help='Agent skills 目录或 auto')
    parser.add_argument('--group', help='安装交付目录中已登记的完整技能组合')
    parser.add_argument('--chip', help='只安装适配指定芯片的技能；省略时安装全部')
    parser.add_argument('--mode', choices=['copy', 'link'], default='copy')
    parser.add_argument('--channel', choices=['external'], default='external')
    parser.add_argument('--verify', action='store_true', help='只校验清单、布局及指纹，不执行安装')
    args = parser.parse_args()
    try:
        if args.verify:
            catalog = verify_source(args.root.resolve())
            print(json.dumps({'status': 'VERIFIED', 'skills_count': len(catalog['skills'])}))
            return 0
        target = default_target() if args.target == 'auto' else Path(args.target)
        print(json.dumps(install(args.root.resolve(), target, args.chip, args.mode, args.channel, args.group), ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, AttributeError) as error:
        print(f'FAILED: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
