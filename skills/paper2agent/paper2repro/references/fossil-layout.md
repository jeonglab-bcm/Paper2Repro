# The fossil repository

How a paper sits in `jeonglab-bcm/fossil`. Read `README.md` and `design.md` too; `design.md` is the rule for every page and wins over anything here.

## Paper folder

```text
<PMCID>/
├── README.md                      citation, licence, folder table, what is kept local
├── results.json                   the normalized record (results-json.md)
├── session/                       ledger.json, conversation.md
├── figure-reproduction/
│   ├── README.md                  Results, what the code does against the paper, Layout, Run, Pipeline steps, Limits
│   ├── main.nf, nextflow.config
│   ├── requirements.txt           pinned
│   ├── results_notes.json         labels, sources, assumptions, causes (written by hand)
│   ├── pipeline/                  fetch_inputs.sh, the port or driver, compare.py, make_tables.py,
│   │                              check_reproduction.py, build_page.py, page_template.html
│   ├── published/                 the paper's figures for comparison, with the licence note
│   └── output/                    fig*_ours.png, fig*_overlay.png, comparison.json, tables.json, report.md
└── <code>-implementation-analysis/   when the paper ships code: README and executable checks
```

Git-ignored and kept local: `<PMCID>/sources/` (paper, supplements, authors' code), `<PMCID>/<name>-paper/` (the Paper2Skill reading package), `<PMCID>/paper-review/`, `<PMCID>/staging/`, and any virtual environment. Add these lines to `.gitignore` in the same pull request.

## Licences

Never commit the paper, its supplements or the authors' code. Commit the published figures for comparison only, with the licence and attribution in the paper README: CC BY papers say so (PMC1847688, PMC4247685, PMC4081021); for all-rights-reserved papers, say they are kept only for comparison and where to get the originals (PMC4081639).

## Site

- `site/<PMCID>/index.html`: the results page, written by `build_page.py` to `results/site/index.html` and copied into `site/<PMCID>/`. Each figure station shows published and ours (side by side, swipe, blink, overlay, difference), the scores, and a stamp from `results.json`.
- `site/<PMCID>/implementation.html`: the code-analysis page, when there is one.
- `site/index.html`: one table row per paper with Published and Analyzed dates, the paper (PMC ID, linked title, authors and journal, links to Results, Code analysis and GitHub), "What we lost", "What we recovered" (links to reusable code), and the Verdict stamp with an optional short note. The front page names no problems found in a paper; those belong on its own pages.
- Stamps: `data-v` `agrees`, `partly`, `differs` or `running`; never red or amber. Map verdicts as in results-json.md.
- Voice: short, plain, dated sentences ("Fig. 5 came back the same."); no dashes, no middle-dot strings, no methods pitch.
- The Pages workflow deploys `site/` on push to `main`.

## README rows

Add the paper to the top-level `README.md` table (folder, citation with DOI, status) and its workflow to the sentence below the table. Generate the status from the `check_results.py` summary rather than writing it freehand.

## Workflow

`.github/workflows/reproduce-<pmcid>.yml`, following pipeline-and-ci.md. The existing workflows use `ubuntu-24.04`, Java 21 (Temurin) and Nextflow 26.04.3.
