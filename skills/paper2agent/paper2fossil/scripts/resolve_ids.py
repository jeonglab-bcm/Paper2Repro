#!/usr/bin/env python3
"""Resolve the identifiers a user gave for one paper and check that they name the same paper.

Usage:
  resolve_ids.py ID [ID ...] [--title TITLE] [--json OUT]

Each ID may be a PMCID, DOI or PMID, bare or as a link (doi.org, PMC, Europe PMC, PubMed).
Every identifier is looked up on its own (NCBI ID Converter, then Europe PMC for the title and
access), then the results are compared.

Exit codes and status:
  0  ok             all identifiers name one paper, which is in PMC and open access
  2  mismatch       the identifiers name different papers (each one's paper is printed)
  2  title_mismatch the paper found does not look like the title given
  2  not_in_pmc     the paper has no PMCID or is not open access (fossil needs both)
  2  unresolved     an identifier could not be parsed or found
  3  lookup_failed  a service did not answer; nothing could be compared

Run this before anything else and stop on any non-zero exit: tell the user what was found.
"""

import argparse
import json
import sys

import common

TITLE_MIN = 0.6


def lookup(kind, value):
    """One identifier → one paper record. Kept as a function so tests can replace it."""
    conv = common.idconv(kind, value)
    rec = {"requested": value, "kind": kind}
    if "error" in conv and kind != "doi":
        # PMIDs and PMCIDs absent from PMC still resolve in Europe PMC; keep going for the title.
        rec["idconv_error"] = conv["error"]
    elif "error" not in conv:
        rec.update({k: v for k, v in conv.items() if v})
    epmc = common.europepmc_record(kind, value)
    if "error" in epmc:
        if "error" in conv:
            rec["error"] = f"{conv['error']}; {epmc['error']}"
        return rec
    for k, v in epmc.items():
        if v is not None and not rec.get(k):
            rec[k] = v
    if epmc.get("in_pmc") is not None:
        rec["in_pmc"] = bool(rec.get("pmcid")) and epmc["in_pmc"]
    return rec


def paper_key(rec):
    return rec.get("pmcid") or (f"doi:{rec['doi']}" if rec.get("doi") else None) or (f"pmid:{rec['pmid']}" if rec.get("pmid") else None)


def describe(rec):
    who = (rec.get("authors") or "").split(",")[0].strip()
    bits = [b for b in (who + (" et al." if "," in (rec.get("authors") or "") else ""), str(rec.get("year") or "")) if b]
    ids = ", ".join(x for x in (rec.get("pmcid"), f"doi:{rec['doi']}" if rec.get("doi") else None) if x)
    return f"{' '.join(bits)}: {rec.get('title') or '(no title)'} [{ids or 'no PMCID or DOI'}]"


def resolve(raw_ids, title=None, lookup_fn=None):
    lookup_fn = lookup_fn or lookup
    records, problems = [], []
    for raw in raw_ids:
        kind, value = common.classify_id(raw)
        if not kind:
            problems.append(f"{raw!r} is not a PMCID, DOI or PMID")
            records.append({"requested": raw, "error": "unrecognized"})
            continue
        records.append(lookup_fn(kind, value))

    failed = [r for r in records if r.get("error") and r.get("error") != "unrecognized"]
    if failed and all("answered 0" in r["error"] for r in failed):
        return {"status": "lookup_failed", "records": records,
                "messages": ["Could not reach NCBI or Europe PMC. Check the network and run again."]}
    for r in failed:
        problems.append(f"{r['requested']} was not found ({r['error']}). Is it mistyped?")
    if problems:
        return {"status": "unresolved", "records": records, "messages": problems}

    keys = {paper_key(r) for r in records}
    # Two records are the same paper if any shared identifier agrees.
    def same(a, b):
        return any(a.get(k) and a.get(k) == b.get(k) for k in ("pmcid", "doi", "pmid"))
    if len(keys) > 1 and not all(same(records[0], r) for r in records[1:]):
        lines = ["These identifiers point to different papers:"]
        lines += [f"  {r['requested']}  →  {describe(r)}" for r in records]
        lines.append("Which one did you mean?")
        return {"status": "mismatch", "records": records, "messages": lines}

    paper = {}
    for r in records:
        for k, v in r.items():
            if k not in ("requested", "kind", "idconv_error") and v is not None and k not in paper:
                paper[k] = v
    out = {"status": "ok", "records": records, "paper": paper, "messages": [f"All identifiers name {describe(paper)}"]}

    if title:
        score = common.title_similarity(title, paper.get("title"))
        out["title_similarity"] = round(score, 3)
        if score < TITLE_MIN:
            out["status"] = "title_mismatch"
            out["messages"] = [f"The title given does not match the paper found (similarity {score:.2f}):",
                               f"  given: {title}", f"  found: {describe(paper)}", "Which one did you mean?"]
            return out
    if not paper.get("pmcid") or not paper.get("in_pmc", True):
        out["status"] = "not_in_pmc"
        out["messages"] = [f"{describe(paper)} is not in PubMed Central. fossil works from the PMC full text, so it needs a paper with a PMCID."]
    elif paper.get("open_access") is False:
        out["status"] = "not_in_pmc"
        out["messages"] = [f"{describe(paper)} is in PMC but not in its Open Access subset. fossil needs an open-access paper."]
    out["pmcid"] = paper.get("pmcid")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--title")
    ap.add_argument("--json", help="write the result here (candidate.json takes it as `ids`)")
    a = ap.parse_args(argv)
    res = resolve(a.ids, a.title)
    print(f"status: {res['status']}")
    print("\n".join(res["messages"]))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=2)
    return {"ok": 0, "lookup_failed": 3}.get(res["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
