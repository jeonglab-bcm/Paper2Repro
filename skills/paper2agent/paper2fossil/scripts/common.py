"""Shared helpers for the paper2fossil scripts: identifier parsing and small HTTP calls.

Standard library only, so every script runs with plain `python3`.
"""

import difflib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "paper2fossil (+https://github.com/jeonglab-bcm/Paper2Repro)"
FOSSIL_REPO = "jeonglab-bcm/fossil"
IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ICITE = "https://icite.od.nih.gov/api/pubs"


# ---------------------------------------------------------------- identifiers

def normalize_pmcid(s):
    m = re.fullmatch(r"\s*(?:PMC)?(\d{3,9})(?:\.\d+)?\s*", str(s), re.I)
    return f"PMC{m.group(1)}" if m else None


def normalize_doi(s):
    s = urllib.parse.unquote(str(s).strip())
    s = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I)
    s = s.rstrip(" .;,")
    return s.lower() if re.match(r"^10\.\d{4,9}/\S+$", s) else None


def classify_id(raw):
    """Return (kind, value) for a PMCID, DOI or PMID given bare or as a link; (None, raw) if unknown."""
    s = str(raw).strip()
    m = re.search(r"(?:pmc/articles/|articles/|article/PMC/)(PMC\d+)", s, re.I)
    if m:
        return "pmcid", normalize_pmcid(m.group(1))
    m = re.search(r"pubmed(?:\.ncbi\.nlm\.nih\.gov)?/(\d+)", s, re.I) or re.search(r"article/MED/(\d+)", s, re.I)
    if m:
        return "pmid", m.group(1)
    if re.fullmatch(r"PMC\d+(?:\.\d+)?", s, re.I):
        return "pmcid", normalize_pmcid(s)
    doi = normalize_doi(s)
    if doi:
        return "doi", doi
    m = re.fullmatch(r"(?:PMID:?\s*)?(\d{1,9})", s, re.I)
    if m:
        return "pmid", m.group(1)
    return None, s


def title_similarity(a, b):
    words = lambda t: " ".join(re.findall(r"[a-z0-9]+", (t or "").lower()))  # noqa: E731
    return difflib.SequenceMatcher(None, words(a), words(b)).ratio()


# ---------------------------------------------------------------------- HTTP

def _request(url, method="GET", data=None, headers=None, timeout=30):
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url, params=None, headers=None, timeout=30):
    """GET a JSON document. Returns (http_status, data or None). Network errors give status 0."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        with _request(url, headers=headers, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, None
    except Exception:
        return 0, None


def url_status(url, timeout=20):
    """Live check of a link. Returns (status_code_or_0, final_url_or_error)."""
    for method in ("HEAD", "GET"):
        try:
            with _request(url, method=method, headers={"Accept": "*/*"}, timeout=timeout) as r:
                return r.status, r.geturl()
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue
            return e.code, f"HTTP {e.code}"
        except Exception as e:
            if method == "HEAD":
                continue
            return 0, type(e).__name__ + (f": {e.reason}" if hasattr(e, "reason") else "")
    return 0, "no answer"


def github_headers():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fossil_issues(repo=FOSSIL_REPO, max_pages=10):
    """All issues and pull requests of the fossil repository (any state). Returns (ok, items)."""
    items = []
    for page in range(1, max_pages + 1):
        status, data = get_json(f"https://api.github.com/repos/{repo}/issues",
                                {"state": "all", "per_page": 100, "page": page}, headers=github_headers())
        if status != 200 or not isinstance(data, list):
            return False, items
        items += data
        if len(data) < 100:
            break
    return True, items


def pmcids_in(text):
    return {normalize_pmcid(m) for m in re.findall(r"PMC\d{4,9}", text or "", re.I)}


def fossil_known(fossil_dir=None, repo=FOSSIL_REPO, issues=None):
    """PMCIDs fossil already has: paper folders, reproduction plans, and any issue or PR that names one.

    Returns (known: {pmcid: [where, ...]}, remote_checked: bool).
    """
    known = {}
    if fossil_dir and os.path.isdir(fossil_dir):
        for name in os.listdir(fossil_dir):
            if re.fullmatch(r"PMC\d+", name) and os.path.isdir(os.path.join(fossil_dir, name)):
                known.setdefault(name, []).append(f"folder {name}/ in the local fossil checkout")
        plans = os.path.join(fossil_dir, "availability-audit", "reproduction_plans")
        if os.path.isdir(plans):
            for name in os.listdir(plans):
                m = re.fullmatch(r"(PMC\d+)\.md", name)
                if m:
                    known.setdefault(m.group(1), []).append(f"plan availability-audit/reproduction_plans/{name}")
    ok = True
    if issues is None:
        ok, issues = fossil_issues(repo)
    for it in issues:
        kind = "PR" if "pull_request" in it else "issue"
        for p in pmcids_in(f"{it.get('title', '')}\n{it.get('body') or ''}"):
            known.setdefault(p, []).append(f"{kind} #{it['number']} ({it.get('state')}): {it.get('title')}")
    return known, ok


# ------------------------------------------------------------ paper lookups

def idconv(kind, value):
    """NCBI ID Converter. It takes one identifier type per request, so call it once per identifier."""
    status, data = get_json(IDCONV, {"ids": value, "idtype": kind, "format": "json", "tool": "paper2fossil"})
    if status != 200 or not data or data.get("status") != "ok":
        return {"error": f"ID converter answered {status}"}
    rec = (data.get("records") or [{}])[0]
    if rec.get("status") == "error":
        return {"error": rec.get("errmsg", "not found")}
    return {"pmcid": rec.get("pmcid"), "pmid": str(rec["pmid"]) if rec.get("pmid") else None,
            "doi": normalize_doi(rec["doi"]) if rec.get("doi") else None}


def europepmc_record(kind, value):
    q = {"pmcid": f"PMCID:{value}", "doi": f'DOI:"{value}"', "pmid": f"EXT_ID:{value} AND SRC:MED"}[kind]
    status, data = get_json(EUROPEPMC, {"query": q, "format": "json", "resultType": "lite", "pageSize": 1})
    if status != 200 or not data:
        return {"error": f"Europe PMC answered {status}"}
    hits = data.get("resultList", {}).get("result", [])
    if not hits:
        return {"error": "not found in Europe PMC"}
    return europepmc_fields(hits[0])


def europepmc_fields(r):
    return {
        "pmcid": r.get("pmcid"), "pmid": r.get("pmid"),
        "doi": normalize_doi(r["doi"]) if r.get("doi") else None,
        "title": r.get("title"), "authors": r.get("authorString"), "journal": r.get("journalTitle"),
        "year": int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None,
        "open_access": r.get("isOpenAccess") == "Y", "in_pmc": r.get("inPMC") == "Y",
        "cited_by": r.get("citedByCount"),
    }


def icite_rcr(pmids):
    """Relative citation ratios from iCite, keyed by PMID string."""
    pmids = [str(p) for p in pmids if p]
    out = {}
    for i in range(0, len(pmids), 200):
        status, data = get_json(ICITE, {"pmids": ",".join(pmids[i:i + 200]), "fl": "pmid,relative_citation_ratio"})
        if status == 200 and data:
            for d in data.get("data", []):
                out[str(d["pmid"])] = d.get("relative_citation_ratio")
    return out
