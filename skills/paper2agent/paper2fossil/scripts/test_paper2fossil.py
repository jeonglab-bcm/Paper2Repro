#!/usr/bin/env python3
"""Self-test for the paper2fossil scripts. Offline: every network call is replaced by fixtures.

    python3 scripts/test_paper2fossil.py
"""

import copy
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_duplicates  # noqa: E402
import common  # noqa: E402
import find_candidates  # noqa: E402
import render_issue  # noqa: E402
import resolve_ids  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "assets", "example-candidate.json")
failures = []


def expect(cond, msg):
    if not cond:
        failures.append(msg)


def quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*a, **k)


# ----------------------------------------------------------- identifiers
def test_classify():
    cases = {
        "PMC4081639": ("pmcid", "PMC4081639"),
        "pmc4081639": ("pmcid", "PMC4081639"),
        "PMC4081639.1": ("pmcid", "PMC4081639"),
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC4081639/": ("pmcid", "PMC4081639"),
        "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4081639": ("pmcid", "PMC4081639"),
        "https://europepmc.org/article/PMC/PMC4081639": ("pmcid", "PMC4081639"),
        "10.1093/bioinformatics/btu079": ("doi", "10.1093/bioinformatics/btu079"),
        "doi:10.1093/Bioinformatics/BTU079": ("doi", "10.1093/bioinformatics/btu079"),
        "https://doi.org/10.1186/1752-0509-9-S1-S10": ("doi", "10.1186/1752-0509-9-s1-s10"),
        "https://dx.doi.org/10.1186/1471-2105-12-489.": ("doi", "10.1186/1471-2105-12-489"),
        "https://pubmed.ncbi.nlm.nih.gov/24519380/": ("pmid", "24519380"),
        "PMID: 24519380": ("pmid", "24519380"),
        "not an id": (None, "not an id"),
    }
    for raw, want in cases.items():
        got = common.classify_id(raw)
        expect(got == want, f"classify_id({raw!r}) = {got}, expected {want}")


# Two real papers, as the services return them.
PAPERS = {
    "yu": {"pmcid": "PMC4081639", "pmid": "24519380", "doi": "10.1093/bioinformatics/btu079", "year": 2014,
           "title": "An efficient algorithm for accurate computation of the Dirichlet-multinomial log-likelihood function.",
           "authors": "Yu P, Shaw CA.", "open_access": True, "in_pmc": True},
    "rpiseq": {"pmcid": "PMC3322362", "pmid": "22192482", "doi": "10.1186/1471-2105-12-489", "year": 2011,
               "title": "Predicting RNA-protein interactions using only sequence information.",
               "authors": "Muppirala UK, Honavar VG, Dobbs D.", "open_access": True, "in_pmc": True},
    "lecun": {"pmid": "26017442", "doi": "10.1038/nature14539", "year": 2015, "title": "Deep learning.",
              "authors": "LeCun Y, Bengio Y, Hinton G.", "open_access": False, "in_pmc": False},
    "closed": {"pmcid": "PMC1111111", "pmid": "1111111", "doi": "10.1000/closed", "year": 2010, "title": "A closed paper.",
               "authors": "Doe J.", "open_access": False, "in_pmc": True},
}


def fake_lookup(kind, value):
    for p in PAPERS.values():
        if p.get(kind) == value:
            return {"requested": value, "kind": kind, **p}
    return {"requested": value, "kind": kind, "error": "Identifier not found in PMC; not found in Europe PMC"}


def test_resolve():
    r = resolve_ids.resolve(["PMC4081639", "https://doi.org/10.1093/bioinformatics/btu079", "24519380"], lookup_fn=fake_lookup)
    expect(r["status"] == "ok" and r["pmcid"] == "PMC4081639", f"same paper, three forms: {r['status']}")

    r = resolve_ids.resolve(["PMC4081639", "10.1186/1471-2105-12-489"], lookup_fn=fake_lookup)
    expect(r["status"] == "mismatch", f"PMCID of one paper with DOI of another must be a mismatch: {r['status']}")
    text = "\n".join(r["messages"])
    expect("Yu P" in text and "Muppirala UK" in text, f"mismatch message must name both papers: {text}")

    r = resolve_ids.resolve(["PMC3322362"], title="Predicting RNA protein interactions using only sequence information",
                            lookup_fn=fake_lookup)
    expect(r["status"] == "ok", f"close title must pass: {r['status']}")
    r = resolve_ids.resolve(["PMC3322362"], title="Deep learning for images", lookup_fn=fake_lookup)
    expect(r["status"] == "title_mismatch", f"wrong title must be flagged: {r['status']}")

    r = resolve_ids.resolve(["10.1038/nature14539"], lookup_fn=fake_lookup)
    expect(r["status"] == "not_in_pmc", f"DOI without a PMCID: {r['status']}")
    r = resolve_ids.resolve(["PMC1111111"], lookup_fn=fake_lookup)
    expect(r["status"] == "not_in_pmc", f"PMC paper outside the open-access subset: {r['status']}")

    r = resolve_ids.resolve(["PMC99999999"], lookup_fn=fake_lookup)
    expect(r["status"] == "unresolved" and "mistyped" in r["messages"][0], f"unknown PMCID: {r}")
    r = resolve_ids.resolve(["hello"], lookup_fn=fake_lookup)
    expect(r["status"] == "unresolved", f"garbage id: {r['status']}")
    r = resolve_ids.resolve(["PMC4081639"], lookup_fn=lambda k, v: {"requested": v, "error": "ID converter answered 0; Europe PMC answered 0"})
    expect(r["status"] == "lookup_failed", f"network down: {r['status']}")


# ---------------------------------------------------------------- catalog
CATALOG = [
    # pmcid, year, title, tags, readiness, rcr, mesh
    ("PMC1", 2008, "Protein structure alignment by contact maps", "code:lost-archived; code:not-found-elsewhere", "high", 2.0, "Proteins"),
    ("PMC2", 2010, "Protein structure alignment server", "code:lost-archived; code:moved", "", 9.0, "Proteins"),
    ("PMC3", 2012, "Protein folding kinetics", "code:no-link", "", 5.0, "Protein Folding"),
    ("PMC4", 2001, "Protein structure alignment, early", "code:not-found-elsewhere", "high", 3.0, ""),
    ("PMC5", 2014, "RNA secondary structure", "code:not-found-elsewhere", "low", 0.4, "RNA"),
    ("PMC6", 2009, "A protein structure tool on GitHub", "code:repository-live", "", 4.0, "Proteins"),
    ("PMC7", 2011, "Alignment of protein structures, revisited", "code:lost", "medium", 1.5, "Proteins"),
]


def test_catalog():
    rows = [{"pmcid": p, "year": str(y), "title": t, "tags": tg, "reproduction_readiness": rd, "icite_rcr": str(rc),
             "mesh_major": m, "journal": "J", "doi": f"10.1/{p}"} for p, y, t, tg, rd, rc, m in CATALOG]
    got = [c["pmcid"] for c in find_candidates.search_catalog(rows, "protein structure alignment", (2004, 2015), 1.0)]
    expect("PMC2" not in got, "a paper whose code moved must never be a candidate")
    expect("PMC6" not in got, "a paper whose code is live must never be a candidate")
    expect("PMC4" not in got, "years outside the range must be left out")
    expect("PMC5" not in got, "RCR below the minimum must be left out")
    expect(got[:2] == ["PMC1", "PMC7"], f"best topic match first, then confirmed-lost: {got}")
    expect(got.index("PMC3") > got.index("PMC7"), f"a weaker topic match ranks lower even when cited more: {got}")
    expect("PMC3" in got, f"keyword match in the title should keep PMC3 (protein): {got}")
    expect(find_candidates.search_catalog(rows, "zebrafish", (2004, 2015), 0) == [], "no keyword match, no candidates")
    q = find_candidates.web_query("flux balance", (2004, 2015))
    expect("TITLE_ABS:(flux balance)" in q and "OPEN_ACCESS:y" in q and "IN_PMC:y" in q and "[2004 TO 2015]" in q,
           f"web query: {q}")


# -------------------------------------------------------------- duplicates
def test_duplicates():
    issues = [{"number": 22, "state": "open", "title": "Reproduce PMC4331676: DNA-binding proteins", "body": ""},
              {"number": 13, "state": "open", "title": "Reproduce RPISeq", "body": "Closes #24 (PMC3322362)", "pull_request": {}}]
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "PMC4081639"))
        os.makedirs(os.path.join(d, "availability-audit", "reproduction_plans"))
        open(os.path.join(d, "availability-audit", "reproduction_plans", "PMC2735674.md"), "w").close()
        cases = {"PMC4081639": "found", "PMC2735674": "found", "PMC4331676": "found", "PMC3322362": "found", "PMC2262056": "none_found"}
        for pmcid, want in cases.items():
            r = check_duplicates.check(pmcid, d, issues=issues, folder_status=404)
            expect(r["status"] == want, f"{pmcid}: {r['status']}, expected {want} ({r['found']})")
        r = check_duplicates.check("PMC2262056", d, issues=issues, folder_status=200)
        expect(r["status"] == "found", "a folder on GitHub's default branch counts")
        r = check_duplicates.check("PMC2262056", d, issues=issues, folder_status=403)
        expect(r["status"] == "check_failed", f"an unanswered GitHub check must not pass: {r['status']}")


# ----------------------------------------------------------------- render
def render_case(mutate):
    c = json.load(open(EXAMPLE))
    mutate(c)
    return render_issue.errors_of(c), c


def test_render():
    errs, c = render_case(lambda c: None)
    expect(errs == [], f"example must render: {errs}")
    title, body = render_issue.render(c)
    expect(title == "Reproduce PMC4331676: DNA-binding proteins by SVM and PSSM distance transformation (Xu et al. 2015)", title)
    for section in ("> [!WARNING]", "## Paper", "## What to validate", "## Inputs", "## Known gaps", "**Estimated effort:**",
                    "## Reproduction plan", "<details>", "## Where we looked for the software", "## How to take this paper",
                    "https://pmc.ncbi.nlm.nih.gov/articles/PMC4331676/", "doi:10.1186/1752-0509-9-S1-S10", "Closes #<this issue>"):
        expect(section in body, f"rendered body lacks {section!r}")
    expect("Part of #" not in body, "issues have no parent")
    expect("/blob/main/skills/paper2agent/paper2fossil/SKILL.md" in body, "skill links default to main")
    _, body_ref = render_issue.render(c, "paper2fossil")
    expect("/blob/paper2fossil/skills/paper2agent/paper2repro/SKILL.md" in body_ref, "--skill-ref changes the links")
    expect("| Table 1 | Jackknife on the benchmark" in body, "validate rows render as a table")

    broken = {
        "ids mismatch": (lambda c: c["ids"].update(status="mismatch"), "identifiers not resolved"),
        "ids for another paper": (lambda c: c["ids"].update(pmcid="PMC3322362"), "resolve_ids.py found PMC3322362"),
        "doi typed differently": (lambda c: c["paper"].update(doi="10.1186/1471-2105-12-489"), "is not the DOI"),
        "already in fossil": (lambda c: c.update(duplicates={"status": "found", "pmcid": "PMC4331676", "found": ["issue #22"]}), "already has"),
        "duplicate check not run": (lambda c: c.pop("duplicates"), "duplicate check not complete"),
        "duplicate check failed": (lambda c: c["duplicates"].update(status="check_failed"), "duplicate check not complete"),
        "duplicate check for another paper": (lambda c: c["duplicates"].update(pmcid="PMC1"), "was run for"),
        "software moved": (lambda c: c["software"].update(status="moved"), "not a fossil target"),
        "no evidence": (lambda c: c["software"].update(evidence=[]), "evidence is empty"),
        "evidence without a date": (lambda c: c["software"]["evidence"][0].pop("checked"), "needs where, finding and checked"),
        "nothing to validate": (lambda c: c.update(validate=[]), "validate is empty"),
        "data gone": (lambda c: c.update(data_status="unavailable"), "data_status"),
        "no plan": (lambda c: c.update(plan=""), "plan is missing"),
    }
    for name, (mutate, needle) in broken.items():
        errs, _ = render_case(mutate)
        expect(any(needle in e for e in errs), f"{name}: expected an error containing {needle!r}, got {errs}")

    with tempfile.TemporaryDirectory() as d:
        big = copy.deepcopy(json.load(open(EXAMPLE)))
        big["plan"] = "x" * 70000
        p = os.path.join(d, "big.json")
        json.dump(big, open(p, "w"))
        expect(quiet(render_issue.main, [p]) == 1, "a body over GitHub's limit must be refused")
        out = os.path.join(d, "issue.md")
        expect(quiet(render_issue.main, [EXAMPLE, "--out", out]) == 0, "example must write a draft")
        expect(open(out).read().startswith("# Reproduce PMC4331676:"), "draft starts with the title")


def main():
    for t in (test_classify, test_resolve, test_catalog, test_duplicates, test_render):
        t()
    if failures:
        print(f"{len(failures)} failure(s):")
        print("\n".join(f"  - {f}" for f in failures))
        return 1
    print("paper2fossil self-test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
