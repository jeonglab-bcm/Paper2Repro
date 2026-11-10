#!/usr/bin/env python3
"""Record which Paper2Repro release this session runs, in a reproduction's results.json.

Usage:
  skill_version.py                  print the skill block as JSON
  skill_version.py results.json     write it into results.json as the top-level "skill"

The block is read from the skill folder this script lives in, never typed by hand:

  "skill": {"name": "paper2repro", "version": "0.5.0", "tag": "paper2repro-v0.5.0",
            "commit": "<sha of the skill checkout>" or null, "modified": false, true or null}

`version` comes from the VERSION file. `commit` and `modified` come from git when the skill folder
is a checkout of the Paper2Repro repository (an installed worktree, for example). They are null for
a copy without git, such as a cloud session's. `modified` is true when the folder has uncommitted
changes, so the version alone does not describe it.

Run it from the installed skill, not from a copy inside the paper folder, once results.json exists
(phase 1). Standard library only.
"""

import json
import os
import re
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
NAME = "paper2repro"


def git(*args):
    p = subprocess.run(["git", "-C", SKILL_DIR, *args], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def block():
    with open(os.path.join(SKILL_DIR, "VERSION"), encoding="utf-8") as f:
        version = f.read().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit(f"{SKILL_DIR}/VERSION is {version!r}, not MAJOR.MINOR.PATCH")
    commit = modified = None
    # Only trust git when VERSION is tracked by the repository the folder sits in: a copy dropped
    # into another repository (and ignored there) would otherwise report that repository's commit.
    if git("ls-files", "--error-unmatch", "VERSION") is not None:
        commit = git("rev-parse", "HEAD")
        status = git("status", "--porcelain", "--", ".")
        modified = None if status is None else bool(status)
    return {"name": NAME, "version": version, "tag": f"{NAME}-v{version}", "commit": commit, "modified": modified}


def main():
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help")):
        sys.exit(__doc__)
    skill = block()
    if len(sys.argv) == 1:
        print(json.dumps(skill, indent=2))
        return
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Keep "skill" next to "session" so the top level reads in the documented order.
    out = {}
    for k, v in data.items():
        if k != "skill":
            out[k] = v
        if k == "session":
            out["skill"] = skill
    out.setdefault("skill", skill)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    flag = " (with uncommitted changes)" if skill["modified"] else ""
    print(f"{path}: {skill['tag']} at {(skill['commit'] or 'no git checkout')[:12]}{flag}", file=sys.stderr)


if __name__ == "__main__":
    main()
