#!/usr/bin/env python3
"""Find fossil candidates from a description: papers whose software is lost and whose data may survive.

Usage:
  find_candidates.py --query "protein structure alignment" [--years 2004-2015] [--min-rcr 1]
                     [--source both|catalog|web] [--catalog PATH | --fossil DIR] [--limit 5] [--json OUT]

Two sources, in this order:
  catalog  fossil's availability audit (availability-audit/paper_catalog.csv): 7,080 papers whose
           links, archives, registries and data were already checked. Fast, and the code status is known.
  web      Europe PMC full search, open-access papers in PMC only, most cited first, with iCite RCR.
           These are unchecked: run check_software.py and the data check on each before nominating.

With --source both (default), the web is searched only when the catalog gives fewer than --limit.
Papers whose code moved to a live home (catalog tag code:moved) are never returned.
"""

import argparse
import csv
import json
import os
import re
import sys

import common

LOST_TAGS = {"code:not-found-elsewhere", "code:partly-found", "code:lost", "code:lost-archived", "code:no-link"}
READINESS = {"high": 3, "medium": 2, "low": 1}


def terms(query):
    return [t for t in re.findall(r"[a-z0-9][a-z0-9+\-]*", (query or "").lower()) if len(t) > 2 or t.isdigit()]


def tags_of(row):
    return {t.strip() for t in (row.get("tags") or "").split(";") if t.strip()}


def years_of(spec):
    m = re.fullmatch(r"\s*(\d{4})\s*(?:-|to|–)\s*(\d{4})\s*", spec or "")
    if not m:
        raise SystemExit(f"--years must look like 2004-2015, not {spec!r}")
    return int(m.group(1)), int(m.group(2))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def code_status(tags):
    if "code:partly-found" in tags:
        return "partly found"
    if "code:not-found-elsewhere" in tags:
        return "lost, not found elsewhere"
    if "code:lost-archived" in tags:
        return "own links dead, Wayback copy exists"
    if "code:lost" in tags:
        return "own links dead, no archive"
    if "code:no-link" in tags:
        return "no code link in the paper"
    return "unknown"


def search_catalog(rows, query, years, min_rcr):
    qt = terms(query)
    out = []
    for r in rows:
        tags = tags_of(r)
        if "code:moved" in tags or not tags & LOST_TAGS:
            continue
        y = int(num(r.get("year")) or 0)
        if not years[0] <= y <= years[1]:
            continue
        rcr = num(r.get("icite_rcr"))
        if min_rcr and (rcr is None or rcr < min_rcr):
            continue
        title = (r.get("title") or "").lower()
        other = " ".join(r.get(k) or "" for k in ("mesh_major", "oa_keywords", "oa_topic", "journal")).lower()
        hits = sum(3 * (t in title) + (t in other) for t in qt)
        if qt and not hits:
            continue
        # Confirmed-lost papers first, then readiness, then match strength and citations.
        confirmed = 2 if tags & {"code:not-found-elsewhere", "code:partly-found"} else (1 if tags & {"code:lost", "code:lost-archived"} else 0)
        score = (confirmed, READINESS.get(r.get("reproduction_readiness"), 0), hits, rcr or 0)
        out.append((score, {
            "source": "catalog", "pmcid": r["pmcid"], "pmid": r.get("pmid"), "doi": common.normalize_doi(r.get("doi") or ""),
            "year": y, "title": r.get("title"), "journal": r.get("journal"), "rcr": rcr, "tier": r.get("tier"),
            "code": code_status(tags), "data": r.get("lost_software_data") or "not checked",
            "readiness": r.get("reproduction_readiness") or "not rated", "new_home": r.get("new_home") or None,
        }))
    out.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in out]


METHOD_WORDS = ("software", "algorithm", "tool", "program", "package", '"web server"', "implementation", "method")


def web_query(query, years):
    # Keywords in the title or abstract; a bare full-text match drowns in papers that only mention them.
    topic = query if ":" in query else f"TITLE_ABS:({query})"
    method = " OR ".join(f"ABSTRACT:{w}" for w in METHOD_WORDS)
    return f"{topic} AND ({method}) AND OPEN_ACCESS:y AND IN_PMC:y AND PUB_YEAR:[{years[0]} TO {years[1]}]"


def search_web(query, years, min_rcr, limit, exclude=()):
    q = web_query(query, years)
    status, data = common.get_json(common.EUROPEPMC, {"query": q, "format": "json", "resultType": "lite",
                                                      "pageSize": max(25, limit * 5), "sort": "CITED desc"})
    if status != 200 or not data:
        print(f"warning: Europe PMC answered {status}; no web results", file=sys.stderr)
        return []
    recs = [common.europepmc_fields(r) for r in data.get("resultList", {}).get("result", [])]
    recs = [r for r in recs if r.get("pmcid") and r["pmcid"] not in exclude]
    rcr = common.icite_rcr([r["pmid"] for r in recs])
    out = []
    for r in recs:
        r_rcr = rcr.get(str(r["pmid"]))
        if min_rcr and (r_rcr is None or r_rcr < min_rcr):
            continue
        out.append({"source": "web", "pmcid": r["pmcid"], "pmid": r["pmid"], "doi": r["doi"], "year": r["year"],
                    "title": r["title"], "journal": r["journal"], "rcr": r_rcr, "tier": None,
                    "code": "not checked: run check_software.py", "data": "not checked", "readiness": "not rated",
                    "new_home": None})
    return out[:limit * 2]


def default_catalog(fossil):
    for base in [fossil, os.environ.get("FOSSIL_DIR"), "../fossil", "../../fossil", os.path.expanduser("~/fossil")]:
        if base:
            p = os.path.join(base, "availability-audit", "paper_catalog.csv")
            if os.path.isfile(p):
                return p
    return None


def table(cands):
    lines = ["| # | PMCID | Year | RCR | Title | Code | Data | Readiness | Source |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i, c in enumerate(cands, 1):
        t = (c["title"] or "")[:80] + ("…" if len(c["title"] or "") > 80 else "")
        rcr = f"{c['rcr']:.1f}" if c["rcr"] is not None else "–"
        lines.append(f"| {i} | {c['pmcid']} | {c['year']} | {rcr} | {t} | {c['code']} | {c['data']} | {c['readiness']} | {c['source']} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--query", default="", help="keywords describing the paper wanted")
    ap.add_argument("--years", default="2004-2015")
    ap.add_argument("--min-rcr", type=float, default=0.0)
    ap.add_argument("--source", choices=["both", "catalog", "web"], default="both")
    ap.add_argument("--catalog", help="path to paper_catalog.csv")
    ap.add_argument("--fossil", help="local fossil checkout (to find the catalog)")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--repo", default=common.FOSSIL_REPO, help="fossil repository on GitHub (default %(default)s)")
    ap.add_argument("--include-known", action="store_true",
                    help="keep papers fossil already has (a folder, a plan, or an issue or PR naming them)")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    years = years_of(a.years)
    if a.source != "catalog" and not a.query.strip():
        ap.error("a web search needs --query")

    known = {}
    if not a.include_known:
        known, remote_ok = common.fossil_known(a.fossil or os.environ.get("FOSSIL_DIR"), a.repo)
        if not remote_ok:
            print(f"warning: could not list {a.repo} issues; papers already proposed there may appear. "
                  "check_duplicates.py runs again before any issue is drafted.", file=sys.stderr)

    cands, catalog_ids = [], set()
    if a.source in ("both", "catalog"):
        path = a.catalog or default_catalog(a.fossil)
        if not path:
            msg = "paper_catalog.csv not found; pass --catalog or --fossil (a fossil checkout)"
            if a.source == "catalog":
                ap.error(msg)
            print(f"warning: {msg}; searching the web only", file=sys.stderr)
        else:
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            catalog_ids = {r["pmcid"] for r in rows}
            cands = [c for c in search_catalog(rows, a.query, years, a.min_rcr) if c["pmcid"] not in known][:a.limit]
    if a.source == "web" or (a.source == "both" and len(cands) < a.limit):
        cands += search_web(a.query, years, a.min_rcr, a.limit - len(cands), exclude=catalog_ids | set(known))[:a.limit - len(cands)]

    if known and not a.include_known:
        print(f"({len(known)} papers fossil already has were left out; --include-known keeps them)")
    if not cands:
        print("No candidates match. Widen the years, lower --min-rcr or change the keywords.")
    else:
        print(table(cands))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(cands, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
