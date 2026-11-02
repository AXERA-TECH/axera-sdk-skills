#!/usr/bin/env python3
"""Install only runtime files, excluding evaluator inputs and answers."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ("SKILL.md", "agents/openai.yaml", "references/contract.md",
           "references/diagnosis.md",
           "references/collection.md",
           "references/delay.md", "references/signal-quality.md",
           "references/response-template.md",
           "scripts/validate_report.py", "scripts/render_report.py", "scripts/measure_segments.py",
           "scripts/requirements-delay.txt",
           "scripts/analyze.py", "scripts/proc_audio.py", "scripts/delay.py")


def install(bundle):
    bundle = Path(bundle)
    if bundle.exists() or bundle.is_symlink():
        raise ValueError("Bundle already exists")
    for name in RUNTIME:
        source = ROOT / name
        if not source.is_file() or source.is_symlink():
            raise ValueError("Missing or symlink runtime input: " + name)
        if not source.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("Runtime input escapes skill directory")
    destination = bundle / ".axap/opencode/skills/marketplace/sdk-audio-aec-diag-skill"
    destination.mkdir(parents=True, exist_ok=False)
    manifest = []
    for name in RUNTIME:
        source = ROOT / name
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest.append({"path": name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    (bundle / "manifest.json").write_text(json.dumps({"skill": "sdk-audio-aec-diag-skill", "files": manifest}, indent=2) + "\n", encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        print(install(args.out))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
