# The fossil repository

How a paper sits in `jeonglab-bcm/fossil`. Read `README.md` and `design.md` too; `design.md` is the rule for every page and wins over anything here.

## Paper folder

```text
<PMCID>/
├── README.md                      citation, licence, folder table, what is kept local
├── index.json                     the paper's row on the front page (below)
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
├── package/                       the method as a Python package (pyproject.toml, src/<name>/ with data/, tests/,
│                                  tutorial/) or an R package (DESCRIPTION, R/, inst/extdata/, tests/testthat/,
│                                  vignettes/tutorial.Rmd, tutorial/); see package-and-tutorial.md
└── <code>-implementation-analysis/   when the paper ships code: README and executable checks
```

Git-ignored and kept local: `<PMCID>/sources/` (paper, supplements, authors' code), `<PMCID>/<name>-paper/` (the Paper2Skill reading package), `<PMCID>/paper-review/`, `<PMCID>/staging/`, and any virtual environment. Add these lines to `.gitignore` in the same pull request.

Install a paper's package with `pip install "git+https://github.com/jeonglab-bcm/fossil#subdirectory=<PMCID>/package"` (Python) or `remotes::install_github("jeonglab-bcm/fossil/<PMCID>/package")` (R).

## Licences

Never commit the paper, its supplements or the authors' code. Commit the published figures for comparison only, with the licence and attribution in the paper README: CC BY papers say so (PMC1847688, PMC4247685, PMC4081021); for all-rights-reserved papers, say they are kept only for comparison and where to get the originals (PMC4081639).

## Site

- `site/<PMCID>/index.html`: the results page, written by `build_page.py` to `results/site/index.html` and copied into `site/<PMCID>/`. Each figure station shows published and ours (side by side, swipe, blink, overlay, difference), the scores, and a stamp from `results.json`.
- `site/<PMCID>/implementation.html`: the code-analysis page, when there is one.
- The front page lists every paper, but no pull request edits it: `site/index.html` is a template, and fossil's `tools/build_index.py` fills its paper rows, footer links and counts from each paper's `<PMCID>/index.json` when the site deploys. Never edit `site/index.html` or the top-level `README.md` for a paper; two open paper pull requests that touch the same shared file conflict, and CI does not run on a conflicted head.
- Stamps: `data-v` `agrees`, `partly`, `differs` or `running`; never red or amber. Map verdicts as in results-json.md.
- Voice: short, plain, dated sentences ("Fig. 5 came back the same."); no dashes, no middle-dot strings, no methods pitch.
- The Pages workflow builds the front page and deploys `site/` on push to `main`.

## The front-page row

Write `<PMCID>/index.json`; its fields are listed at the top of fossil's `tools/build_index.py`:

```json
{
  "pmcid": "PMC1234567",
  "published": "2010-03-22",
  "analyzed": "2026-11-24",
  "title": "The paper's title, plain text",
  "journal": "Surname et al., Journal",
  "doi": "10.1186/…",
  "links": [{"text": "Code analysis", "href": "PMC1234567/implementation.html"}],
  "lost": ["What did not survive, one item each"],
  "recovered": ["<a href=\"https://github.com/jeonglab-bcm/fossil/tree/main/PMC1234567/package\">The method as a Python package</a> (<a href=\"https://github.com/jeonglab-bcm/fossil/blob/main/PMC1234567/package/tutorial/TUTORIAL.md\">tutorial</a>)", "<a href=\"PMC1234567/\">Tables 1 to 3 and Fig. 2</a> against the paper"],
  "verdict": {"v": "partly", "note": "The main claim holds; one short line"},
  "footer": "Short name of what came back"
}
```

- The title links to the results page and Article (the DOI) and GitHub sit under it; the build writes those from `pmcid` and `doi`, so give only extra links (Code analysis) in `links`.
- `verdict.v` is the stamp, mapped from `results.json` as in results-json.md: have the pipeline's docs step write it (`set_fields` in `tools/build_index.py`), never type it. The note names no problems; those belong on the paper's own pages.
- The Paper2Repro column comes from the `skill` block in `results.json`; it is not in `index.json`.
- Check it with `python3 tools/build_index.py` and `python3 tools/check_index_links.py`; CI runs both.

The top-level `README.md` does not list papers. The workflow documents itself in the comments at the top of its file.

## Workflow

`.github/workflows/reproduce-<pmcid>.yml`, following pipeline-and-ci.md. The existing workflows use `ubuntu-24.04`, Java 21 (Temurin) and Nextflow 26.04.3.
