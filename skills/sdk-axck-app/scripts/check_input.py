#!/usr/bin/env python3
"""Validate camera-kit application source structure, build files, and packaging rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_FILES = (
    ("Makefile", "Top-level camera-kit build Makefile", True),
)

RECOMMENDED_DIRS = (
    ("service", "axck_service daemon implementation"),
    ("client", "libaxck_client shared library"),
    ("3rd", "Third-party dependencies"),
    ("com", "Common utilities and shared types"),
    ("apps", "Applications and test utilities"),
)


def check_directory(input_dir: Path) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for fname, desc, req in REQUIRED_FILES:
        target = input_dir / fname
        if not target.is_file():
            if req:
                errors.append(f"Missing required file: {fname} ({desc})")
            else:
                warnings.append(f"Missing optional file: {fname} ({desc})")
            continue
        if target.stat().st_size == 0:
            errors.append(f"File is empty: {fname}")

    for dname, desc in RECOMMENDED_DIRS:
        target = input_dir / dname
        if not target.is_dir():
            warnings.append(f"Missing sub-module directory: {dname}/ ({desc})")

    return len(errors) == 0, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="Path to camera-kit directory")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        print(f"ERROR: Directory does not exist: {input_dir}", file=sys.stderr)
        return 2

    passed, errors, warnings = check_directory(input_dir)

    if errors:
        print("[-] Build & Packaging Input Check Failed (Errors):")
        for err in errors:
            print(f"  * {err}")

    if warnings:
        print("[!] Warnings:")
        for w in warnings:
            print(f"  * {w}")

    if passed and (not warnings or not args.strict):
        print(f"[+] Build input verification passed: {input_dir}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
