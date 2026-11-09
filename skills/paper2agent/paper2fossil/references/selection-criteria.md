# Selection criteria

fossil asks how much of 2004–2015 computational biology AI agents can bring back. A target is worth an issue when a reproduction would teach us something, and when someone can finish it.

## Must hold

| Criterion | Why | How to check |
| --- | --- | --- |
| Open access in PubMed Central | fossil works from the PMC full text and does not redistribute papers | `resolve_ids.py` status `ok` |
| Software lost: gone, never released, available only on request, or binary-only and no longer runnable | A paper whose code runs is a Paper2Agent case, not a fossil one | `check_software.py`, then [software-search.md](software-search.md) |
| Input data obtainable today | Without inputs, nothing can be compared | [data-check.md](data-check.md) |
| Computed results: figures, tables or numbers | They are the answer key | The inventory in the plan |
| Not already in fossil | One issue per paper | `check_duplicates.py` |

## Prefer

- **Well cited.** An iCite RCR of 1 or more means the method is used. The pilot of ten (fossil #14) used 1.9 or more. A lower RCR is fine when the user has a reason.
- **2004–2015.** In those years data were deposited but code mostly was not. Other years are fine when the user asks for them.
- **Small inputs.** Up to a few GB, with no 400 GB database to rebuild, unless the result is worth it.
- **Deterministic results.** Exact matches are more informative than distributions. Note the stochastic parts honestly; they don't disqualify a paper.
- **A method someone would reuse.** Paper2Repro also packages the method.

## The audit catalog

`availability-audit/paper_catalog.csv` in fossil covers 7,080 open-access methods papers from 2004–2015. It is the fastest source because links, archives, registries and data were already checked there (dated 28 October 2026). Re-check anything you rely on.

| Column or tag | Meaning |
| --- | --- |
| `tier` A–G | A: code in the supplement. B: live code-host link. C: live lab or web-service link. D: own links dead, Wayback copy. E: dead, no copy. F: can't tell. G: no own link and no code. Targets come from D, E and G. |
| `code:not-found-elsewhere` | A search of registries and the web found no new home (142 papers). The strongest signal. |
| `code:moved` | Found a live new home. Never a target. |
| `code:partly-found` | Some code or data found later. Still a target, but say what was found. |
| `lost_software_data` | complete-in-pmc, complete-public, no-external-data, partial, not-available |
| `reproduction_readiness` | high, medium or low, for the 143 lost-software papers |
| `icite_rcr` | Relative citation ratio |

`reproduction_plans/` holds the plans for the ten pilot papers. Read one before writing your own plan.

## Web candidates

Papers from Europe PMC are not checked. Before showing them, say that their code and data status is unknown. A highly cited database or review is rarely a target; prefer papers whose abstract presents a method, tool or algorithm. Run phases 1–4 on the user's choice before planning.

## Ranking a shortlist

Rank by, in order:

1. confirmed lost before possibly lost;
2. data complete before partial;
3. readiness;
4. how many results can be regenerated;
5. RCR.

Show the reason for each rank in one line.
