#!/usr/bin/env python3
"""Turn a checked candidate.json into a fossil issue, and post it only when asked.

Usage:
  render_issue.py candidate.json [--out issue.md]          validate and write the draft (title + body)
  render_issue.py candidate.json --post [--repo OWNER/NAME] post it (default repo: jeonglab-bcm/fossil)

The issue layout is fixed here, not written by hand, so every nomination reads the same way.
The fields of candidate.json are in references/issue-format.md; assets/example-candidate.json is a
filled example. Rendering refuses (exit 1) when a guard fails:
  - the identifiers were not resolved to one paper (resolve_ids.py status must be ok);
  - fossil already has the paper, or the duplicate check did not finish (check_duplicates.py);
  - the software is not lost (status must be lost or partly_found; moved papers are not fossils);
  - a required section is empty, or the body is longer than GitHub allows.

Post only after the user has read the draft and said to post it. Posting uses `gh` when it is
installed and logged in, otherwise the GitHub API with GITHUB_TOKEN (or GH_TOKEN).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import common

SCHEMA = "paper2fossil/candidate/v1"
SOFTWARE_OK = {"lost": "lost", "partly_found": "partly found"}
MAX_BODY = 65000  # GitHub rejects issue bodies over 65,536 characters
SKILL_URL = "https://github.com/jeonglab-bcm/Paper2Repro/blob/main/skills/paper2agent"


def errors_of(c):
    errs = []
    if c.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA}")
    p = c.get("paper") or {}
    pmcid = common.normalize_pmcid(p.get("pmcid") or "")
    if not pmcid:
        errs.append("paper.pmcid is missing")
    for k in ("title", "citation", "doi", "short", "authors_short", "year"):
        if not p.get(k):
            errs.append(f"paper.{k} is missing")

    ids = c.get("ids") or {}
    if ids.get("status") != "ok":
        errs.append(f"identifiers not resolved to one open-access PMC paper (resolve_ids.py status: {ids.get('status', 'not run')})")
    elif common.normalize_pmcid(ids.get("pmcid") or "") != pmcid:
        errs.append(f"resolve_ids.py found {ids.get('pmcid')}, but paper.pmcid is {p.get('pmcid')}")
    elif ids.get("paper", {}).get("doi") and common.normalize_doi(p.get("doi") or "") != ids["paper"]["doi"]:
        errs.append(f"paper.doi {p.get('doi')} is not the DOI resolve_ids.py found ({ids['paper']['doi']})")

    dup = c.get("duplicates") or {}
    if dup.get("status") == "found":
        errs.append("fossil already has this paper: " + "; ".join(dup.get("found", [])))
    elif dup.get("status") != "none_found":
        errs.append(f"duplicate check not complete (check_duplicates.py status: {dup.get('status', 'not run')})")
    elif common.normalize_pmcid(dup.get("pmcid") or "") != pmcid:
        errs.append(f"the duplicate check was run for {dup.get('pmcid')}, not {pmcid}")

    sw = c.get("software") or {}
    if sw.get("status") == "moved":
        errs.append("the software moved to a live home; a paper whose code still runs is not a fossil target")
    elif sw.get("status") not in SOFTWARE_OK:
        errs.append("software.status must be lost or partly_found")
    if not sw.get("summary"):
        errs.append("software.summary is missing")
    if not sw.get("evidence"):
        errs.append("software.evidence is empty: list where you looked (check_software.py output, judged)")
    for e in sw.get("evidence", []):
        if not all(e.get(k) for k in ("where", "finding", "checked")):
            errs.append(f"software.evidence entry needs where, finding and checked: {e}")

    v = c.get("validate") or []
    if not v:
        errs.append("validate is empty: list the figures, tables and numbers to compare against")
    for row in v:
        if not row.get("item") or not row.get("published"):
            errs.append(f"validate row needs item and published: {row}")
    for k in ("inputs", "effort", "plan"):
        if not c.get(k):
            errs.append(f"{k} is missing")
    if c.get("data_status") not in ("complete", "partial", "none_needed"):
        errs.append("data_status must be complete, partial or none_needed (papers whose data are gone are not nominated)")
    return errs


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def bullets(xs):
    return "\n".join(f"- {x}" for x in xs)


def render(c):
    p, sw = c["paper"], c["software"]
    pmcid = common.normalize_pmcid(p["pmcid"])
    doi = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/|^doi:\s*", "", p["doi"].strip(), flags=re.I)
    title = f"Reproduce {pmcid}: {p['short']} ({p['authors_short']} {p['year']})"
    rcr = f" iCite RCR {p['rcr']:.1f}." if isinstance(p.get("rcr"), (int, float)) else ""
    source = " and the fossil availability audit" if c.get("from_catalog") else ""

    out = [
        "> [!WARNING]",
        f"> **AI-generated task spec.** Claude Code wrote this with the [Paper2Fossil skill]({SKILL_URL}/paper2fossil/SKILL.md) "
        f"from the paper's full text{source}. Nothing was run. Before you start, read the paper and confirm the target is right: "
        "the PMCID, the title, the figures and tables, and the numbers below.",
        "",
        "**Assign yourself when you start working on it,** so that two people don't take the same paper. Unassign yourself if you stop.",
        "",
        "## Paper",
        "",
        f"**[{pmcid}](https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/)**. {p['citation']} [doi:{doi}](https://doi.org/{doi}).{rcr}",
        "",
        f"**Software:** {SOFTWARE_OK[sw['status']]}. {sw['summary']}",
        "",
        "## What to validate",
        "",
        "| Item | Published result |",
        "| --- | --- |",
        *[f"| {cell(r['item'])} | {cell(r['published'])} |" for r in c["validate"]],
        "",
    ]
    if c.get("validate_notes"):
        out += [c["validate_notes"], ""]
    out += ["## Inputs", "", bullets(c["inputs"]), ""]
    if c.get("gaps"):
        out += ["## Known gaps", "", bullets(c["gaps"]), ""]
    out += [f"**Estimated effort:** {c['effort']}", ""]
    out += [
        "## Reproduction plan",
        "",
        "<details><summary>Inventory, method details, steps, reported numbers and risks</summary>",
        "",
        c["plan"].strip(),
        "",
        "</details>",
        "",
        "## Where we looked for the software",
        "",
        "| Checked | Where | Finding |",
        "| --- | --- | --- |",
        *[f"| {cell(e['checked'])} | {cell(e['where'])} | {cell(e['finding'])} |" for e in sw["evidence"]],
        "",
        "## How to take this paper",
        "",
        "1. Read the paper on PMC and check this spec against it. The spec can be wrong; say so in a comment.",
        f"2. Use the [Paper2Repro skill]({SKILL_URL}/paper2repro/SKILL.md) and follow its workflow and definition of done.",
        f"3. Open one pull request with the work in a folder named `{pmcid}/`, laid out like the existing papers, "
        "and put `Closes #<this issue>` in its body.",
        "4. Don't commit the paper, its supplements or downloaded datasets. Commit only the published figures you "
        "compare against, and only if the licence allows it.",
    ]
    return title, "\n".join(out) + "\n"


def post(title, body, repo):
    if shutil.which("gh"):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(body)
        try:
            p = subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", f.name],
                               capture_output=True, text=True)
        finally:
            os.unlink(f.name)
        if p.returncode == 0:
            return p.stdout.strip()
        print(f"gh failed: {p.stderr.strip()}", file=sys.stderr)
    headers = common.github_headers()
    if "Authorization" not in headers:
        raise SystemExit("Cannot post: install and log in to `gh`, or set GITHUB_TOKEN with permission to open issues on " + repo)
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues", method="POST",
                                 data=json.dumps({"title": title, "body": body}).encode(),
                                 headers={**headers, "User-Agent": common.USER_AGENT, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["html_url"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidate")
    ap.add_argument("--out", help="write the draft (title on the first line) here")
    ap.add_argument("--post", action="store_true", help="open the issue; only after the user approved the draft")
    ap.add_argument("--repo", default=common.FOSSIL_REPO)
    a = ap.parse_args(argv)
    with open(a.candidate) as f:
        c = json.load(f)
    errs = errors_of(c)
    if errs:
        print("Not rendered:", file=sys.stderr)
        print("\n".join(f"  - {e}" for e in errs), file=sys.stderr)
        return 1
    title, body = render(c)
    if len(body) > MAX_BODY:
        print(f"Body is {len(body)} characters; GitHub allows {MAX_BODY}. Shorten the plan.", file=sys.stderr)
        return 1
    draft = f"# {title}\n\n{body}"
    if a.out:
        with open(a.out, "w") as f:
            f.write(draft)
        print(f"draft written to {a.out} ({len(body)} characters)")
    if a.post:
        print(f"opened: {post(title, body, a.repo)}")
    elif not a.out:
        print(draft)
    return 0


if __name__ == "__main__":
    sys.exit(main())
