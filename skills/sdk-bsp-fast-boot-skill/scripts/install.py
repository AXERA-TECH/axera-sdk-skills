#!/usr/bin/env python3
"""Project runtime files into an AXAP installed-bundle, excluding eval answers."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = ("SKILL.md", "agents/openai.yaml", "references")


def install(bundle):
    bundle = Path(bundle)
    if bundle.exists() or bundle.is_symlink():
        raise ValueError("Bundle already exists: " + str(bundle))
    sources = []
    for item in RUNTIME_PATHS:
        path = ROOT / item
        if path.is_symlink() or not path.exists():
            raise ValueError("Missing or symlink runtime input: " + str(path))
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        if any(p.is_symlink() for p in candidates):
            raise ValueError("Runtime inputs must not contain symlinks")
        sources.extend(p for p in candidates if p.is_file())
    for path in sources:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or symlink runtime input: " + str(path))
    destination = bundle / ".axap/opencode/skills/marketplace/sdk-bsp-fast-boot-skill"
    manifest = []
    for path in sources:
        relative = path.relative_to(ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        manifest.append({"path": str(relative), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (bundle / "manifest.json").write_text(
        json.dumps({"skill": "sdk-bsp-fast-boot-skill", "files": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="installed-bundle")
    args = parser.parse_args()
    try:
        print(install(args.out))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
