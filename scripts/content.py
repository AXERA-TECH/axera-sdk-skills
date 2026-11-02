"""仓内快照与安装内容的稳定指纹，不读取凭据文件或跟随软链接。"""

import hashlib
import os
from pathlib import Path

IGNORED_DIRS = {'.git', '__pycache__', '.pytest_cache'}


def check_name(path: Path):
    name = path.name
    if name in {'.env', 'id_rsa', 'id_ed25519', 'id_ecdsa'} or (name.startswith('.env.') and name != '.env.example') or path.suffix in {'.pem', '.key', '.p12', '.pfx'}:
        raise ValueError('包含私有配置或凭据文件，不读取也不交付')


def files(root: Path):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('技能目录缺失或为软链接')
    for current, directories, names in sorted(os.walk(root)):
        directories[:] = sorted(d for d in directories if d not in IGNORED_DIRS)
        for name in directories + sorted(names):
            path = Path(current) / name
            if path.is_symlink():
                raise ValueError('技能包含软链接')
            check_name(path)
        for name in sorted(names):
            path = Path(current) / name
            if path.suffix != '.pyc':
                if not path.is_file():
                    raise ValueError('技能包含非普通文件')
                yield path


def fingerprints(root: Path):
    """sha256 兼容现有 SkillClient；content_sha256 另涵盖可执行位。"""
    client, content = hashlib.sha256(), hashlib.sha256()
    for path in files(root):
        relative = path.relative_to(root).as_posix().encode('utf-8')
        data = path.read_bytes()
        client.update(relative)
        client.update(data)
        content.update(relative + b'\0')
        content.update(b'x' if path.stat().st_mode & 0o111 else b'-')
        content.update(hashlib.sha256(data).digest())
    return {'sha256': client.hexdigest(), 'content_sha256': content.hexdigest()}
