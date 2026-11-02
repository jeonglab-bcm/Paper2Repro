#!/usr/bin/env python3
"""Print the checksum that identifies this copy of the paper2agent skill.

The checksum is the SHA-256 of a manifest with one line per file, sorted by path:
"<sha256 of the file>  <path relative to the skill root>". It depends only on file
paths and contents, not on timestamps, permissions or the install location, so an
installed copy and a git checkout of the same skill give the same value.
Python caches (__pycache__, *.pyc), .git and .DS_Store are skipped.

Usage: python3 skill_checksum.py [--root <skill dir>] [--manifest]
Prints JSON: {"skill": ..., "checksum": "sha256:...", "files": n}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".git"}
SKIP_FILES = {".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def manifest(root: Path) -> list[str]:
    lines = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if name in SKIP_FILES or path.suffix in SKIP_SUFFIXES or not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.relative_to(root).as_posix()}\n")
    return sorted(lines, key=lambda line: line[66:].encode())


def checksum(root: Path) -> dict:
    lines = manifest(root)
    if not lines:
        raise SystemExit(f"No files under {root}")
    name = root.resolve().name
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        for line in skill_md.read_text().splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
                break
    return {"skill": name, "checksum": "sha256:" + hashlib.sha256("".join(lines).encode()).hexdigest(),
            "files": len(lines)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                    help="skill directory (default: the skill that contains this script)")
    ap.add_argument("--manifest", action="store_true", help="print the per-file manifest instead")
    a = ap.parse_args(argv)
    if not a.root.is_dir():
        print(f"Not a directory: {a.root}", file=sys.stderr)
        return 1
    if a.manifest:
        sys.stdout.write("".join(manifest(a.root)))
    else:
        print(json.dumps(checksum(a.root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
