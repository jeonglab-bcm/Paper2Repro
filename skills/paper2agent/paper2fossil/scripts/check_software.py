#!/usr/bin/env python3
"""Gather evidence on whether a paper's software is lost: its own links, archives, registries, GitHub.

Usage:
  check_software.py --pmcid PMCID [--url URL ...] [--name TOOL ...] [--author SURNAME ...] [--json OUT]

  --url     every software or data link the paper itself gives (abstract, availability section)
  --name    the tool's name and spellings of it (e.g. RPISeq, rpiseq)
  --author  surnames of the first and last authors, to look for their later repositories

For each --url: is it live today, and does the Wayback Machine have a capture?
For each --name: CRAN (current and archived), Bioconductor, PyPI, bio.tools, and GitHub repositories
with that name. For the paper itself: GitHub repositories mentioning its DOI or PMCID, and for each
--author, GitHub users or repositories with the author's name and the tool's name.

This script only collects evidence. A registry or GitHub hit is a *possible* home: it counts only if
it is the same tool (same authors, or it cites the paper). Read references/software-search.md, open
each hit, and record your judgement in candidate.json `software`. Exit 0 unless --pmcid is invalid.
"""

import argparse
import datetime
import json
import sys
import urllib.parse

import common


def check_url(url):
    status, final = common.url_status(url)
    live = 200 <= status < 400
    _, wb = common.get_json("https://archive.org/wayback/available", {"url": url})
    snap = ((wb or {}).get("archived_snapshots") or {}).get("closest") or {}
    return {"where": url, "kind": "paper link", "live": live, "http": status or final,
            "wayback": snap.get("url"), "wayback_timestamp": snap.get("timestamp"),
            "finding": ("answers " + str(status) if live else f"dead ({final})")
                       + (f"; Wayback capture {snap.get('timestamp', '')[:8]}" if snap.get("url") else "; no Wayback capture")}


def check_registries(name):
    hits = []
    s, d = common.get_json(f"https://crandb.r-pkg.org/{urllib.parse.quote(name)}")
    if s == 200 and d and "error" not in d:
        hits.append({"where": f"https://cran.r-project.org/package={name}", "kind": "CRAN",
                     "finding": f"CRAN package {name} ({'archived' if d.get('archived') else 'current'}): {d.get('Title', '')}",
                     "authors": d.get("Author") or d.get("Maintainer")})
    # bioconductor.org/packages/<name>/ answers 200 for any name, so ask the release index pages instead.
    for repo in ("bioc", "data/experiment"):
        url = f"https://bioconductor.org/packages/release/{repo}/html/{urllib.parse.quote(name)}.html"
        s, _ = common.url_status(url)
        if s == 200:
            hits.append({"where": url, "kind": "Bioconductor", "finding": f"Bioconductor release package {name}"})
            break
    s, d = common.get_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
    if s == 200 and d:
        info = d.get("info", {})
        hits.append({"where": f"https://pypi.org/project/{name}/", "kind": "PyPI",
                     "finding": f"PyPI project {name}: {info.get('summary') or ''}", "authors": info.get("author")})
    s, d = common.get_json("https://bio.tools/api/tool/", {"q": name, "format": "json"})
    for t in ((d or {}).get("list") or [])[:3] if s == 200 else []:
        if name.lower() in (t.get("name") or "").lower() or name.lower() == (t.get("biotoolsID") or "").lower():
            hits.append({"where": f"https://bio.tools/{t.get('biotoolsID')}", "kind": "bio.tools",
                         "finding": f"bio.tools entry {t.get('name')}; homepage {t.get('homepage')}",
                         "homepage": t.get("homepage")})
    return hits


def github_search(q, kind):
    s, d = common.get_json("https://api.github.com/search/repositories", {"q": q, "per_page": 5},
                           headers=common.github_headers())
    if s != 200 or not d:
        return [], f"GitHub search for {q!r} answered {s}"
    return [{"where": r["html_url"], "kind": kind,
             "finding": f"{r['full_name']}: {(r.get('description') or '')[:120]} (updated {r.get('pushed_at', '')[:10]})"}
            for r in d.get("items", [])], None


def gather(pmcid, urls=(), names=(), authors=(), doi=None):
    today = datetime.date.today().isoformat()
    evidence, notes = [], []
    for u in urls:
        evidence.append(check_url(u))
    for n in names:
        found = check_registries(n)
        evidence += found
        if not found:
            evidence.append({"where": "CRAN, Bioconductor, PyPI, bio.tools", "kind": "registries",
                             "finding": f"no entry named {n}"})
        hits, err = github_search(f"{n} in:name", "GitHub (tool name)")
        evidence += hits
        notes += [err] if err else []
        for a in authors:
            hits, err = github_search(f"{n} {a}", "GitHub (tool + author)")
            evidence += hits
            notes += [err] if err else []
    for ident in [i for i in (doi, pmcid) if i]:
        hits, err = github_search(f'"{ident}" in:readme,description', "GitHub (cites the paper)")
        evidence += hits
        notes += [err] if err else []
    for e in evidence:
        e["checked"] = today
    possible = [e for e in evidence if e["kind"] not in ("paper link", "registries")]
    live_links = [e for e in evidence if e["kind"] == "paper link" and e["live"]]
    return {"pmcid": pmcid, "checked": today, "evidence": evidence, "notes": notes,
            "possible_homes": len(possible), "live_paper_links": len(live_links),
            "summary": (f"{len(live_links)} of {len(urls)} paper links live; {len(possible)} possible homes to inspect"
                        + ("; some searches failed, see notes" if notes else ""))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pmcid", required=True)
    ap.add_argument("--doi")
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--name", action="append", default=[])
    ap.add_argument("--author", action="append", default=[])
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    pmcid = common.normalize_pmcid(a.pmcid)
    if not pmcid:
        ap.error("--pmcid is not a PMCID")
    res = gather(pmcid, a.url, a.name, a.author, common.normalize_doi(a.doi) if a.doi else None)
    print(res["summary"])
    for e in res["evidence"]:
        print(f"  [{e['kind']}] {e['where']}: {e['finding']}")
    for n in res["notes"]:
        print(f"  note: {n}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
