#!/usr/bin/env python3
"""Check that fossil does not already have a paper before an issue is drafted for it.

Usage:
  check_duplicates.py PMCID [--fossil DIR] [--repo OWNER/NAME] [--json OUT]

Looks for, in the fossil repository:
  - a paper folder PMCID/ (local checkout if --fossil is given, and on GitHub's default branch);
  - a reproduction plan availability-audit/reproduction_plans/PMCID.md;
  - any issue or pull request, open or closed, whose title or body names the PMCID.

Exit codes and status:
  0  none_found     nothing names this paper
  2  found          fossil already has it (where is printed); do not open another issue
  3  check_failed   GitHub could not be reached; the check is incomplete, so do not draft yet

Set GITHUB_TOKEN (or GH_TOKEN) to avoid GitHub's anonymous rate limit.
"""

import argparse
import json
import sys

import common


def remote_folder(repo, pmcid):
    status, _ = common.get_json(f"https://api.github.com/repos/{repo}/contents/{pmcid}", headers=common.github_headers())
    return status  # 200: exists, 404: absent, other: unknown


def check(pmcid, fossil_dir=None, repo=common.FOSSIL_REPO, issues=None, folder_status=None):
    pmcid = common.normalize_pmcid(pmcid)
    if not pmcid:
        raise SystemExit("not a PMCID")
    known, issues_ok = common.fossil_known(fossil_dir, repo, issues=issues)
    found = list(known.get(pmcid, []))
    status_code = folder_status if folder_status is not None else remote_folder(repo, pmcid)
    if status_code == 200:
        found.append(f"folder {pmcid}/ on {repo}'s default branch")
    remote_ok = issues_ok and status_code in (200, 404)
    if found:
        status = "found"
    elif not remote_ok:
        status = "check_failed"
    else:
        status = "none_found"
    return {"status": status, "pmcid": pmcid, "repo": repo, "found": found, "remote_checked": remote_ok}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pmcid")
    ap.add_argument("--fossil", help="local fossil checkout")
    ap.add_argument("--repo", default=common.FOSSIL_REPO)
    ap.add_argument("--json", help="write the result here (candidate.json takes it as `duplicates`)")
    a = ap.parse_args(argv)
    res = check(a.pmcid, a.fossil, a.repo)
    print(f"status: {res['status']}")
    if res["found"]:
        print(f"fossil already has {res['pmcid']}:")
        print("\n".join(f"  - {w}" for w in res["found"]))
    elif res["status"] == "check_failed":
        print(f"Could not reach {res['repo']} on GitHub (rate limit or network). Set GITHUB_TOKEN and run again.")
    else:
        print(f"No folder, plan, issue or pull request in {res['repo']} names {res['pmcid']}.")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=2)
    return {"none_found": 0, "found": 2}.get(res["status"], 3)


if __name__ == "__main__":
    sys.exit(main())
