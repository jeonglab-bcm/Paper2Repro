#!/usr/bin/env python3
"""Copy the paper2agent skill with the answers to a held-out case removed.

The skill's worked example and some reference notes contain the answers for the
regression case. A test that hands the agent the answers proves nothing, so this
script replaces the worked-example file with a stub and removes every sentence that
contains a marker from expected.json. It exits 1 if any marker survives.

Usage: python3 blind_skill.py <skill dir> <dest dir> <expected.json>
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

WITHHELD = "(Example withheld for the regression test.)"
STUB = "# Worked example\n\nThis example is withheld while the skill regression test runs.\n"
TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".yml", ".yaml", ".sh", ".R", ".r"}
# A sentence ends at ., ! or ? followed by whitespace and a capital, quote, bracket or emphasis.
# Periods inside numbers, file names and versions (3.82e-4, ubuntu-24.04) do not split.
BOUNDARY = re.compile(r"(?<=[.!?])(\s+)(?=[A-Z*`(\[])")


def redact_line(line: str, markers: list[str]) -> str:
    if not any(m in line for m in markers):
        return line
    indent = line[: len(line) - len(line.lstrip())]
    text = line.strip()
    m = re.match(r"(?:[-*]|\d+\.)\s+", text)  # keep list markers
    prefix = m.group(0) if m else ""
    sentences = BOUNDARY.split(text[len(prefix):])[0::2]
    kept = [s for s in sentences if not any(mk in s for mk in markers)]
    return indent + prefix + " ".join(kept + [WITHHELD])


def blind(src: Path, dest: Path, markers: list[str], stub_glob: str) -> list[str]:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    for p in dest.rglob(stub_glob):
        p.write_text(STUB)
    leaks = []
    for p in sorted(dest.rglob("*")):
        if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        text = p.read_text()
        new = "\n".join(redact_line(line, markers) for line in text.split("\n"))
        if new != text:
            p.write_text(new)
        for m in markers:
            if m in new:
                leaks.append(f"{p.relative_to(dest)}: {m}")
    return leaks


def main() -> int:
    src, dest, expected = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    cfg = json.loads(expected.read_text())
    leaks = blind(src, dest, cfg["skill_redact_markers"], f"example-{cfg['case']}*.md")
    if leaks:
        print("Markers survived the redaction:\n  " + "\n  ".join(leaks), file=sys.stderr)
        return 1
    print(f"Blinded skill written to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
