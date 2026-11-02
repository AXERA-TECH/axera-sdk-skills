#!/usr/bin/env python3
"""Project only OTA runtime knowledge into the AXAP analyzer bundle."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = ('SKILL.md', 'routing.yaml', 'platforms', 'reference')

def install(output):
    bundle = Path(output)
    if bundle.exists() or bundle.is_symlink():
        raise ValueError(f'Bundle already exists: {bundle}')
    destination = bundle / '.axap/opencode/skills/marketplace/sdk-bsp-ota'
    manifest = []
    for item in RUNTIME_PATHS:
        source = ROOT / item
        paths = sorted(source.rglob('*')) if source.is_dir() else [source]
        for path in paths:
            if path.is_symlink():
                raise ValueError(f'Symlink is not allowed: {path}')
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            manifest.append({'path': str(relative), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (bundle / 'manifest.json').write_text(json.dumps({'skill': 'sdk-bsp-ota', 'files': manifest}, indent=2) + '\n')
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(install(args.out))
