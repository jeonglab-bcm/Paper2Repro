#!/usr/bin/env python3
"""Gather evidence on whether a paper's software is lost: its own links, archives, registries, GitHub.

Usage:
  check_software.py --pmcid PMCID [--url URL ...] [--name TOOL ...] [--author SURNAME ...] [--json OUT]

  --url     every software or data link the paper itself gives (abstract, availability section)
  --name    the tool's name and spellings of it (e.g. RPISeq, rpiseq)
  --author  surnames of the first and last authors, to look for their later repositories

For each --url: is it live today, and does the Wayback Machine have a capture? A dead link is not
proof the software is gone: the script also tries the other scheme (http <-> https), the parent paths
and the host's root page, and reports whether the host still answers.
For each --name: CRAN (current and archived), Bioconductor, PyPI, bio.tools (by exact name and ID, then
each entry's homepage, checked the same way as a paper link), and GitHub repositories with that name.
For the paper itself: GitHub repositories mentioning its DOI or PMCID, and for each --author, GitHub
users or repositories with the author's name and the tool's name.
Later papers (unless --no-later): open-access papers newer than this one that name the tool and share
an --author. Every link in their full text that names the tool is checked. A host in them that contains
an author's surname or a distinctive word of the paper's own host (lussierlab.org -> lussiergroup.org)
is taken as a possible new lab domain, and the paper's own paths are tried on it.

A live https copy of a paper link, a live homepage of a bio.tools entry with the tool's exact name, a
live link in a later paper, or a live copy of the paper's path on the lab's new domain is a *likely
moved* candidate. They are listed under `likely_moved` and the script exits 4. Open each one:
if it is the same tool, the paper is not a fossil target. If it is not, record why in candidate.json
`software.moved_candidates` ({where, why_not}); render_issue.py refuses a `lost` paper otherwise.

This script only collects evidence. A registry or GitHub hit is a *possible* home: it counts only if
it is the same tool (same authors, or it cites the paper). Read references/software-search.md, open
each hit, and record your judgement in candidate.json `software`.

Exit codes: 0 no live candidate found, 4 likely moved (see `likely_moved`), 2 bad arguments.
"""

import argparse
import datetime
import json
import re
import sys
import urllib.parse

import common


NO_ANSWER = {0, 502, 503, 504}  # timeouts and gateway errors: the server did not answer, it did not say "gone"


def is_live(status):
    return 200 <= status < 400


def norm(name):
    """Compare tool names without case, spaces or punctuation: E-Predict == epredict."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def url_variants(url):
    """The other scheme for the same path, then each parent path, then the host's root page."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return []
    other = "https" if parts.scheme == "http" else "http"
    out = [urllib.parse.urlunsplit((other, parts.netloc, parts.path, parts.query, ""))]
    segs = [x for x in parts.path.split("/") if x]
    for i in range(len(segs) - 1, -1, -1):
        path = "/" + "/".join(segs[:i]) + ("/" if i else "")
        for scheme in ("https", parts.scheme):
            u = urllib.parse.urlunsplit((scheme, parts.netloc, path, "", ""))
            if u not in out and u != url:
                out.append(u)
    return out


def probe(url):
    """Status of a URL and its variants. Returns (status, final, same_path_live_url, host_live)."""
    status, final = common.url_status(url)
    if is_live(status):
        return status, final, url, True
    variants = url_variants(url)
    same_path = None
    host_live = False
    for i, v in enumerate(variants):
        s, _ = common.url_status(v)
        if is_live(s):
            if i == 0:  # the other scheme, same path
                same_path = v
            host_live = True
            break
    return status, final, same_path, host_live


def describe_dead(status, final):
    if status in NO_ANSWER:
        return f"no answer ({final})"
    return f"dead ({final})"


def check_url(url, kind="paper link"):
    status, final, same_path, host_live = probe(url)
    live = is_live(status)
    _, wb = common.get_json("https://archive.org/wayback/available", {"url": url})
    snap = ((wb or {}).get("archived_snapshots") or {}).get("closest") or {}
    if live:
        finding = f"answers {status}"
    elif same_path:
        finding = f"{describe_dead(status, final)}, but {same_path} answers: open it, the software may live there"
    elif host_live:
        finding = (f"{describe_dead(status, final)}; the host still answers, so the page may have moved on the same "
                   "site: search the site's software or tools page")
    else:
        finding = describe_dead(status, final) + "; no other scheme or parent page on the host answers"
    finding += f"; Wayback capture {snap.get('timestamp', '')[:8]}" if snap.get("url") else "; no Wayback capture"
    return {"where": url, "kind": kind, "live": live, "http": status or final, "live_url": url if live else same_path,
            "host_live": host_live, "wayback": snap.get("url"), "wayback_timestamp": snap.get("timestamp"),
            "finding": finding}


def biotools_entries(name):
    """bio.tools entries for this tool: (exact, partial). Free-text search splits "E-Predict" into two words
    and ranks thousands of tools first, so look up the ID and the exact name before searching. Exact means
    the name or ID equals the tool's name without case or punctuation; partial means it contains it."""
    want = norm(name)
    found, partial = {}, {}
    ids = {name.lower(), name.lower().replace(" ", "-"), name.lower().replace(" ", "_"), want}
    for i in sorted(ids):
        s, d = common.get_json(f"https://bio.tools/api/tool/{urllib.parse.quote(i)}/", {"format": "json"})
        if s == 200 and d and d.get("biotoolsID"):
            found[d["biotoolsID"]] = d
    for params in ({"name": name, "format": "json"}, {"q": name, "format": "json"}):
        s, d = common.get_json("https://bio.tools/api/tool/", params)
        for t in ((d or {}).get("list") or []) if s == 200 else []:
            if want and want in (norm(t.get("name")), norm(t.get("biotoolsID"))):
                found.setdefault(t.get("biotoolsID"), t)
            elif want and want in norm(t.get("name")) + " " + norm(t.get("biotoolsID")):
                partial.setdefault(t.get("biotoolsID"), t)
    return list(found.values()), [t for k, t in partial.items() if k not in found]


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
    exact, partial = biotools_entries(name)
    for t in partial:
        hits.append({"where": f"https://bio.tools/{t.get('biotoolsID')}", "kind": "bio.tools",
                     "homepage": t.get("homepage"),
                     "finding": f"bio.tools entry {t.get('name')} (name contains {name}); homepage {t.get('homepage')}"})
    for t in exact:
        home = t.get("homepage")
        e = {"where": f"https://bio.tools/{t.get('biotoolsID')}", "kind": "bio.tools", "homepage": home,
             "finding": f"bio.tools entry {t.get('name')}; homepage {home}"}
        if home:
            h = check_url(home, kind="bio.tools homepage")
            e["finding"] += f": {h['finding'].split('; Wayback')[0]}"
            e["live_url"] = h["live_url"]
        hits.append(e)
    return hits


def github_search(q, kind):
    s, d = common.get_json("https://api.github.com/search/repositories", {"q": q, "per_page": 5},
                           headers=common.github_headers())
    if s != 200 or not d:
        return [], f"GitHub search for {q!r} answered {s}"
    return [{"where": r["html_url"], "kind": kind,
             "finding": f"{r['full_name']}: {(r.get('description') or '')[:120]} (updated {r.get('pushed_at', '')[:10]})"}
            for r in d.get("items", [])], None


URL_RE = re.compile(r"""(?:https?|ftp)://[^\s<>"'\)\]]+""")


def later_papers(pmcid, names, authors, year, limit=10):
    """Open-access papers after `year` that name the tool and share an author. Returns (papers, note)."""
    if not names or not authors or not year:
        return [], None
    tool = " OR ".join(f'"{n}"' for n in names)
    who = " OR ".join(f'AUTH:"{a}"' for a in authors)
    q = f"({tool}) AND ({who}) AND OPEN_ACCESS:y AND IN_PMC:y AND PUB_YEAR:[{int(year) + 1} TO 3000]"
    s, d = common.get_json(common.EUROPEPMC, {"query": q, "format": "json", "resultType": "lite",
                                              "pageSize": limit, "sort": "P_PDATE_D desc"})
    if s != 200 or not d:
        return [], f"Europe PMC search for later papers answered {s}"
    recs = [r for r in d.get("resultList", {}).get("result", []) if r.get("pmcid") and r["pmcid"] != pmcid]
    return recs[:limit], None


def links_naming(text, names):
    keys = [norm(n) for n in names if len(norm(n)) >= 4]
    out = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".,;:")
        if any(k in norm(u) for k in keys) and u not in out:
            out.append(u)
    return out


GENERIC_HOST_WORDS = {"www", "http", "https", "html", "index", "home", "info", "people", "faculty", "research",
                      "software", "tools", "labs", "group", "groups", "department", "dept", "univ", "university",
                      "bioinf", "bioinformatics", "science", "sciences", "genome", "biology", "medicine", "server"}


def host_of(url):
    return urllib.parse.urlsplit(url).netloc.lower().split(":")[0].removeprefix("www.")


def lab_hosts(old_urls, later_urls, authors):
    """Hosts in later papers that look like the lab's new address: they contain an author's surname, or a
    distinctive word of the host the paper used (lussierlab.org -> lussiergroup.org)."""
    old_hosts = {host_of(u) for u in old_urls}
    words = {w for h in old_hosts for w in re.findall(r"[a-z]{4,}", h.rsplit(".", 1)[0]) if w not in GENERIC_HOST_WORDS}
    words |= {norm(a) for a in authors if len(norm(a)) >= 4}
    out = []
    for u in later_urls:
        h = host_of(u)
        if h and h not in old_hosts and h not in out and any(w in norm(h) for w in words):
            out.append(h)
    return out


def moved_paths(old_urls, hosts):
    """The paper's own paths on each new host of the lab."""
    out = []
    for u in old_urls:
        parts = urllib.parse.urlsplit(u)
        if not parts.path.strip("/"):
            continue
        for h in hosts:
            v = urllib.parse.urlunsplit(("https", h, parts.path, parts.query, ""))
            if v not in out:
                out.append(v)
    return out


def check_later(pmcid, names, authors, year, old_urls=()):
    evidence, notes = [], []
    recs, note = later_papers(pmcid, names, authors, year)
    if note:
        notes.append(note)
    if not recs:
        if not note and names and authors and year:
            evidence.append({"where": "Europe PMC: later open-access papers by the same authors", "kind": "later papers",
                             "finding": f"none name {' / '.join(names)}"})
        return evidence, notes
    all_links = []
    for r in recs:
        text = common.europepmc_fulltext(r["pmcid"])
        all_links += [(u.rstrip(".,;:"), r) for u in URL_RE.findall(text or "")]
        links = links_naming(text, names)
        if not links:
            evidence.append({"where": f"{r['pmcid']} ({r.get('pubYear')})", "kind": "later papers",
                             "finding": f"{(r.get('title') or '')[:80]}: names the tool, gives no link to it"})
        for u in links:
            e = check_url(u, kind="later paper link")
            e["finding"] = f"given in {r['pmcid']} ({r.get('pubYear')}): {e['finding']}"
            evidence.append(e)
    hosts = lab_hosts(old_urls, [u for u, _ in all_links], authors)
    for h in hosts:
        r = next(r for u, r in all_links if host_of(u) == h)
        evidence.append({"where": h, "kind": "lab host in later paper",
                         "finding": f"{r['pmcid']} ({r.get('pubYear')}) links this host; it may be the lab's new address"})
    for v in moved_paths(old_urls, hosts):
        evidence.append(check_url(v, kind="paper path on lab's new host"))
    return evidence, notes


def gather(pmcid, urls=(), names=(), authors=(), doi=None, year=None, later=True):
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
    if later and names and authors:
        if year is None:
            year = common.europepmc_record("pmcid", pmcid).get("year")
        ev, nt = check_later(pmcid, list(names), list(authors), year, old_urls=list(urls))
        evidence += ev
        notes += nt
    for e in evidence:
        e["checked"] = today
    likely_moved = [{"where": e["live_url"], "via": f"{e['kind']}: {e['where']}"}
                    for e in evidence if e.get("live_url")]
    possible = [e for e in evidence if e["kind"] not in ("paper link", "registries", "later papers", "later paper link",
                                                          "lab host in later paper", "paper path on lab's new host")]
    live_links = [e for e in evidence if e["kind"] == "paper link" and e["live"]]
    summary = (f"{len(live_links)} of {len(urls)} paper links live; {len(possible)} possible homes to inspect"
               + ("; some searches failed, see notes" if notes else ""))
    if likely_moved:
        summary = (f"LIKELY MOVED: {len(likely_moved)} live candidate(s) found; open each before calling the "
                   "software lost. " + summary)
    return {"pmcid": pmcid, "checked": today, "evidence": evidence, "notes": notes,
            "possible_homes": len(possible), "live_paper_links": len(live_links),
            "likely_moved": likely_moved, "summary": summary}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pmcid", required=True)
    ap.add_argument("--doi")
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--name", action="append", default=[])
    ap.add_argument("--author", action="append", default=[])
    ap.add_argument("--year", type=int, help="publication year (looked up in Europe PMC when omitted)")
    ap.add_argument("--no-later", action="store_true", help="skip the search of later papers by the same authors")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    pmcid = common.normalize_pmcid(a.pmcid)
    if not pmcid:
        ap.error("--pmcid is not a PMCID")
    res = gather(pmcid, a.url, a.name, a.author, common.normalize_doi(a.doi) if a.doi else None,
                 year=a.year, later=not a.no_later)
    print(res["summary"])
    for e in res["evidence"]:
        print(f"  [{e['kind']}] {e['where']}: {e['finding']}")
    for n in res["notes"]:
        print(f"  note: {n}")
    for m in res["likely_moved"]:
        print(f"  LIKELY MOVED: {m['where']} (from {m['via']})")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=2)
    return 4 if res["likely_moved"] else 0


if __name__ == "__main__":
    sys.exit(main())
