#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = ("SKILL.md", "routing.yaml", "platforms", "reference")


def install(bundle):
    bundle = Path(bundle)
    if bundle.exists() or bundle.is_symlink():
        raise ValueError("Bundle already exists: " + str(bundle))
    sources = []
    for item in RUNTIME_PATHS:
        path = ROOT / item
        if not path.exists() or path.is_symlink():
            raise ValueError("Missing or linked runtime input: " + str(path))
        sources.extend(sorted(path.rglob("*")) if path.is_dir() else [path])
    if any(path.is_symlink() for path in sources):
        raise ValueError("Runtime inputs must not contain symlinks")
    destination = bundle / ".axap/opencode/skills/marketplace/sdk-bsp-rpmsg"
    manifest = []
    for path in sources:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        manifest.append({"path": str(relative), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (bundle / "manifest.json").write_text(
        json.dumps({"skill": "sdk-bsp-rpmsg", "files": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install runtime files without evaluator inputs")
    parser.add_argument("--out", default="installed-bundle")
    args = parser.parse_args()
    try:
        print(install(args.out))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
