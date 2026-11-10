#!/usr/bin/env python3
"""Paper2Repro versions: check that a change bumps them, and list the tags they should have.

  paper2repro_release.py check <base-ref>   fail if skills/paper2agent/paper2repro/ changed since
                                            <base-ref> without a new VERSION and a CHANGELOG row for it
  paper2repro_release.py tags <head-sha>    print "<tag> <commit>" for every CHANGELOG row; rows with
                                            commit "-" (the current release) get <head-sha>
"""
import re
import subprocess
import sys
from pathlib import Path

SKILL = "skills/paper2agent/paper2repro"
ROOT = Path(__file__).resolve().parent.parent
ROW = re.compile(r"^\|\s*(\d+\.\d+\.\d+)\s*\|\s*([\d-]+)\s*\|\s*([0-9a-f]{7,40}|-)\s*\|")


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def rows(text):
    return [(m[1], m[3]) for m in map(ROW.match, text.splitlines()) if m]


def key(v):
    return tuple(int(x) for x in v.split("."))


def check(base):
    changed = [p for p in git("diff", "--name-only", f"{base}...HEAD", "--", SKILL).split() if p]
    version = (ROOT / SKILL / "VERSION").read_text().strip()
    table = rows((ROOT / SKILL / "CHANGELOG.md").read_text())
    errors = []
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append(f"VERSION is {version!r}, not MAJOR.MINOR.PATCH")
    if not table or table[0][0] != version:
        errors.append(f"the first CHANGELOG row is not VERSION {version}")
    if [v for v, _ in table] != sorted((v for v, _ in table), key=key, reverse=True) or len({v for v, _ in table}) != len(table):
        errors.append("CHANGELOG rows are not unique and newest first")
    if changed:
        try:
            old = git("show", f"{base}:{SKILL}/VERSION").strip()
        except subprocess.CalledProcessError:
            old = "0.0.0"
        if not errors and key(version) <= key(old):
            errors.append(f"{len(changed)} file(s) in {SKILL}/ changed but VERSION is still {version} (was {old}): "
                          "bump it and add a CHANGELOG row with commit '-'")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if not errors:
        print(f"paper2repro {version}: ok" + (f" ({len(changed)} changed file(s))" if changed else ""))
    return 1 if errors else 0


def tags(head):
    for version, commit in rows((ROOT / SKILL / "CHANGELOG.md").read_text()):
        print(f"paper2repro-v{version} {head if commit == '-' else commit}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("check", "tags"):
        sys.exit(__doc__)
    sys.exit({"check": check, "tags": tags}[sys.argv[1]](sys.argv[2]))
