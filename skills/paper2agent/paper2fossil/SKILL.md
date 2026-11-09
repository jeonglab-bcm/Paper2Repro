---
name: paper2fossil
description: Find a published computational paper whose software has been lost but whose data survive, check it, and propose it as a reproduction target by opening an issue in the fossil repository (jeonglab-bcm/fossil) with a full reproduction plan. Use whenever the user wants to nominate, propose, suggest or find a paper for fossil, names a paper (PMCID, DOI, PMID, link or title) whose code is gone, or describes the kind of old method they want revived without naming one, even if they do not name this skill.
---

# Paper2Fossil

Paper2Fossil feeds fossil. [Paper2Repro](../paper2repro/SKILL.md) brings a method back. This skill finds the paper to bring back and writes the issue that someone later claims and reproduces. One run ends in one issue in **jeonglab-bcm/fossil**, or in a clear reason why no issue was opened. Issues have no parent issue. Nobody opens a pull request until someone claims the issue.

A good fossil target has four things:

- an open-access paper in PubMed Central;
- software that is lost (gone, never released, or binary-only and dead), not merely moved;
- input data that can still be obtained;
- results that can be checked: figures, tables and numbers.

Everything below exists to prove those four with evidence, and to give the person who claims the issue an honest plan.

## Two ways in

- **The user names a paper** (PMCID, DOI, PMID, a link, or a title). Start at phase 1.
- **The user describes what they want** ("an old protein-structure method, well cited, code gone"). Run phase 0, show the shortlist, and let the user pick. Then continue from phase 1 with that paper.

## Workflow

Each phase ends with a checkable state. Stop at the first one that fails and tell the user why.

| Phase | Work | Done when |
| --- | --- | --- |
| 0. Search (description only) | Run `find_candidates.py --query ... [--years] [--min-rcr] --fossil <checkout>`. It searches the fossil audit catalog first, then Europe PMC (open access, title and abstract, methods papers). Show the user 3–5 candidates with code and data status, and say which are unchecked web hits. Let them choose; suggest better keywords if nothing fits. Read [selection-criteria.md](references/selection-criteria.md). | The user has picked one paper. |
| 1. Identify | Run `resolve_ids.py` on every identifier the user gave (and `--title` if they gave one). On any status other than `ok`, stop and show its message: different papers, wrong title, not in PMC, not open access, or mistyped. Never guess which one they meant. | `ids.json` has status `ok`. |
| 2. Not already in fossil | Run `check_duplicates.py PMCID --fossil <checkout>`. If fossil has the paper, report where (folder, plan, issue or PR) and stop. If GitHub did not answer, set `GITHUB_TOKEN` and retry; do not continue on a failed check. | `dups.json` has status `none_found`. |
| 3. Software is lost | Read the paper's availability section. Run `check_software.py` with its links, the tool's names and the authors' surnames. Then follow [software-search.md](references/software-search.md): open every possible home, and search by lab and successor tool, not only by name. If a live home is the same tool, the paper is not a target: report the home and stop. | `software.status` is `lost` or `partly_found`, with dated evidence for every place checked. |
| 4. Data survive | Find what input data the main results came from, and check that it can be obtained today ([data-check.md](references/data-check.md)). | `data_status` is `complete`, `partial` or `none_needed`, and every input has a working source. |
| 5. Plan | Read the full paper (build a paper skill with [Paper2Skill](../paper2skill/SKILL.md) for a PDF). List every figure, table and reported number. For each, record its inputs, whether it can be regenerated, the published values, the missing details and the risks. Write the plan and the issue fields into `candidate.json` ([issue-format.md](references/issue-format.md)). Copy every number from the paper; never estimate one. | `render_issue.py candidate.json --out issue.md` exits 0. |
| 6. Review and post | Show the user the draft: the title and the whole body. Post only when they say to: `render_issue.py candidate.json --post`. Give them the issue URL. | The issue is open in jeonglab-bcm/fossil, or the user chose not to post. |

Keep `ids.json`, `dups.json`, `software.json` and `candidate.json` in a scratch folder, not in either repository.

## Scripts

All are standard-library Python 3. Resolve paths relative to this skill's folder.

| Script | Use |
| --- | --- |
| `scripts/find_candidates.py --query Q [--years 2004-2015] [--min-rcr N] [--source both\|catalog\|web] [--fossil DIR] [--limit 5] [--json OUT]` | Shortlist from a description. Leaves out papers whose code moved and papers fossil already has. |
| `scripts/resolve_ids.py ID [ID ...] [--title T] [--json OUT]` | Check that every identifier names the same open-access PMC paper. Exit 2 on a mismatch, 3 if the services are down. |
| `scripts/check_duplicates.py PMCID [--fossil DIR] [--json OUT]` | Find folders, plans, issues and PRs in fossil that name the paper. Exit 2 if found, 3 if the check could not finish. |
| `scripts/check_software.py --pmcid P [--doi D] [--url U ...] [--name N ...] [--author A ...] [--json OUT]` | Collect evidence: are the links live, are there Wayback captures, registry entries (CRAN, Bioconductor, PyPI, bio.tools) and GitHub repositories. It collects only; you judge. |
| `scripts/render_issue.py candidate.json [--out FILE] [--post] [--repo OWNER/NAME]` | Validate and render the issue in fossil's fixed layout. It refuses unresolved IDs, duplicates, moved software, missing sections and over-long bodies. `--post` uses `gh`, or `GITHUB_TOKEN`. |
| `scripts/test_paper2fossil.py` | Offline self-test. Run it after changing any script. |

`--repo` defaults to `jeonglab-bcm/fossil`. Point it at a fork only to test.

## When to stop and ask

- The identifiers disagree, the title doesn't match, or the paper is not open access in PMC. Show what was found and ask.
- The software may have a live home, and you cannot tell whether it is the same tool.
- The core inputs are gone, or available only on request or behind a paywall.
- Before posting, always.

Everything else (a dead link, a supplement in a PDF, a missing parameter) is work to record in the plan, not a reason to stop.

## References

- [selection-criteria.md](references/selection-criteria.md): what makes a good target, the audit catalog's tiers and tags, and how to rank.
- [software-search.md](references/software-search.md): where to look, and when a hit counts as the same tool.
- [data-check.md](references/data-check.md): confirming inputs survive (supplements, accessions, public datasets).
- [issue-format.md](references/issue-format.md): every `candidate.json` field, the plan's structure, and the rendered issue.
- [example-candidate.json](assets/example-candidate.json): a filled candidate, rebuilt from fossil issue #22.
