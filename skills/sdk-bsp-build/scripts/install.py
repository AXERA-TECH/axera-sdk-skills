#!/usr/bin/env python3
"""Project runtime files into an AXAP installed-bundle, excluding eval answers."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = ("SKILL.md", "agents/openai.yaml", "scripts/find-latest-axp.sh")


def install(bundle):
    bundle = Path(bundle)
    if bundle.exists() or bundle.is_symlink():
        raise ValueError("Bundle already exists: " + str(bundle))
    sources = [ROOT / item for item in RUNTIME_PATHS]
    for path in sources:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or symlink runtime input: " + str(path))
    destination = bundle / ".axap/opencode/skills/marketplace/sdk-bsp-build"
    manifest = []
    for path in sources:
        relative = path.relative_to(ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        manifest.append({"path": str(relative), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (bundle / "manifest.json").write_text(
        json.dumps({"skill": "sdk-bsp-build", "files": manifest}, indent=2) + "\n",
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
