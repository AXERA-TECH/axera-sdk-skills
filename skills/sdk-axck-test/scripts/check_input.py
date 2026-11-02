#!/usr/bin/env python3
"""Validate test session logs, console streams, or RPC execution dumps before evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_FILES = (
    ("test_session.log", "Interactive test run console or automation output log", True),
)


def check_directory(input_dir: Path) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for fname, desc, req in REQUIRED_FILES:
        target = input_dir / fname
        if not target.is_file():
            if req:
                errors.append(f"Missing required test log: {fname} ({desc})")
            else:
                warnings.append(f"Missing optional log: {fname} ({desc})")
            continue
        if target.stat().st_size == 0:
            errors.append(f"Test log is empty: {fname}")

    return len(errors) == 0, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="Path to test evidence directory")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        print(f"ERROR: Directory does not exist: {input_dir}", file=sys.stderr)
        return 2

    passed, errors, warnings = check_directory(input_dir)

    if errors:
        print("[-] Test Session Input Check Failed (Errors):")
        for err in errors:
            print(f"  * {err}")

    if warnings:
        print("[!] Warnings:")
        for w in warnings:
            print(f"  * {w}")

    if passed and (not warnings or not args.strict):
        print(f"[+] Test session input verification passed: {input_dir}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
