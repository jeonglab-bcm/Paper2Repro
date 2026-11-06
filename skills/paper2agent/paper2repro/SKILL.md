---
name: paper2repro
description: Reproduce a published computational paper's figures, tables and reported numbers from its own data and code in one session, ending in one pull request that holds the pipeline, the renders, a normalized results.json with computed verdicts, a ledger of the session's turns and tokens, a pip-installable Python package of the method with an executed tutorial, and a tested cause for every result that is not an exact match. Use whenever the user asks to reproduce, rerun, replicate, re-derive, recover or check a paper's figures or tables (by PMC ID, DOI, PDF or URL), to add a paper to the fossil repository, or to work out why a reproduction does not match, even if they do not name this skill.
---

# Paper2Repro

One clean session, one pull request. A reproduction is finished when someone else can rerun it with one command and read, for every figure, table and number in the paper, whether it came back, how closely, and why not when it did not, and can install the method as a Python package and follow its tutorial on example data.

The first fossil papers each needed three to five pull requests because the first one stopped short: a scored figure with no render, a curve cut from a panel, the results page added a day later, CI fixed after merge and then timing out, verdicts typed by hand that the numbers did not support. Everything below exists to get all of that right the first time. Read [definition-of-done.md](references/definition-of-done.md) now and again before you open the pull request.

## Start clean

- Work in a fresh session whose first prompt is the kickoff in [session-ledger.md](references/session-ledger.md). The ledger measures what one reproduction costs; context carried over from another session makes that number meaningless and hides steps a rerun would need.
- Read the repository's own rules before writing anything: `README.md`, `design.md` (site voice and components) and one finished paper folder as a model. In fossil, [fossil-layout.md](references/fossil-layout.md) lists what a paper folder holds. Elsewhere, mirror the repository's existing layout.
- Create one branch (`<pmcid>-<short-name>`). Commit as you go; push and open the pull request once, at the end.

## Workflow

Each phase ends with a checkable state. Do not start the next until it holds, because each later phase assumes it.

| Phase | Work | Done when |
| --- | --- | --- |
| 1. Inventory | List every figure panel, table and quantitative statement in the text as an item in `results.json` (id, label, kind, source, attempted or not and why). | No result in the paper is missing from `results.json`. |
| 2. Sources | Fetch the paper, supplements, data and code into `<id>/sources/` (git-ignored); record each file's URL and SHA-256. If no paper skill exists, build one with [Paper2Skill](../paper2skill/SKILL.md) and read methods, captions and figures from it. Read the paper's copyright line and every data licence before you plan what to publish ([publishing.md](references/publishing.md)). Get the original-resolution figure files. | `fetch_inputs.sh` downloads everything from a clean folder and the checksums pass. |
| 3. Authors' code | Run it in its own language where a free runtime exists (R, Python, Octave for MATLAB). If you port it, check the port against the original on the paper's data. Record every shim and fix. | The original (or a port shown equal to it) runs end to end. |
| 4. Rebuild | Figures on the published pixel grid with negative controls ([figure-scoring.md](references/figure-scoring.md)), aligned and overlaid with `compare_figure.py` ([figure-matching.md](references/figure-matching.md)); tables and numbers as values at printed precision; claims in the text recomputed first from the paper's own tables ([text-claims.md](references/text-claims.md)). Render every attempted panel and its overlay. Put the method in `<id>/package/` and have the pipeline import it ([package-and-tutorial.md](references/package-and-tutorial.md)). | Every attempted item has scores, controls and outputs in `results.json`. |
| 5. Explain | Every item that is not `exact` gets a cause, with the hypotheses you tested ([mismatch-investigation.md](references/mismatch-investigation.md)). | `check_results.py` reports no missing or untested causes. |
| 6. Pipeline and CI | One Nextflow pipeline, pinned versions, a check step, a workflow inside its time budget ([pipeline-and-ci.md](references/pipeline-and-ci.md)). | The CI command, run from a clean checkout, passes locally and `compare_runs.py` finds the fresh run equal to the committed outputs. |
| 7. Package and tutorial | Finish the package from the [template](assets/package-template): example input with an independently sourced expected output, tests, and an executed tutorial that shows install, example input, API and command-line runs, and the comparison with the expected output ([package-and-tutorial.md](references/package-and-tutorial.md)). Skip only when the paper has no reusable method. | `check_package.py <id>/package` exits 0; the pipeline imports the package for the method; `results.json` has the `package` item. |
| 8. Pages and docs | The results page generated from `results.json`; the front-page row; README rows; the paper's README; a code-analysis page if the paper ships code that differs from its text. | Every verdict shown anywhere is read from `results.json`. |
| 9. Close | Validate, record the ledger, commit, push, open one pull request, drive CI to green, then push the final ledger. | The definition of done holds on the pull request's head. |

Work through items in the paper's order inside each phase, but do the core results first: if time runs short, a finished pipeline for Figs 2 to 6 with honest `not_attempted` entries beats half-finished everything.

## results.json

The single record of what came back. Each paper folder has one, the pipeline writes its numbers, and `scripts/check_results.py` computes every verdict from them:

- `exact`: every value equals the paper at printed precision, with nothing read off a figure or found by search.
- `agrees`: the figure matches beyond what its negative controls reach, or values match with an assumption taken from the figure.
- `partly`: better than any control or some values match, but short of the pass mark.
- `inconclusive`: a near-miss control scores as well as ours, so the comparison cannot tell; sharpen the comparison.
- `differs`: no better than a wrong input, or no value matches.
- `not_attempted`: with the reason.

Read [results-json.md](references/results-json.md) for the fields and rules; [example-results.json](assets/example-results.json) is a worked example from PMC1847688. Never type a verdict: run `check_results.py --write`, and generate every page, README row and pull-request table from its output, so the record cannot drift from the numbers.

## Scripts

| Script | Use |
| --- | --- |
| `scripts/check_results.py results.json [--write] [--markdown] [--root DIR]` | Validate, compute verdicts and the summary; `--markdown` prints the table for the README and the pull request. Exit 1 on any rule broken or verdict stale. |
| `scripts/compare_runs.py FRESH COMMITTED [--ignore GLOB]` | Fresh run against committed outputs: numbers within tolerance, images by decoded pixels, HTML with embedded images compared as pixels. Use it in the pipeline's check step. |
| `scripts/session_ledger.py --out <id>/session` | Prompts, responses, tool calls and tokens of this session (and its subagents) into `ledger.json` and `conversation.md`. |
| `scripts/compare_figure.py --published PUB --render OURS --out DIR [--regions JSON] [--window N]` | Find the plot panel in both images, align ours to the published frame, and write `aligned.png`, `overlay.png`, `diff.png` and `report.json` (shift, panel-size difference, ink distances, per-region offsets). |
| `scripts/check_package.py PKG [--write] [--json FILE] [--layout-only]` | Build the paper's Python package, install it into a fresh environment, run its tests, execute the tutorial and compare the outputs with the saved ones, and check `TUTORIAL.md`. `--write` saves fresh tutorial outputs and regenerates `TUTORIAL.md`. |
| `scripts/test_paper2repro.py` | Self-test after changing any script. |
| `scripts/test_compare_figure.py` | Synthetic checks for `compare_figure.py`: `uv run scripts/test_compare_figure.py`. |

Resolve script paths relative to this skill's folder. They need Python 3; `compare_runs.py` also needs Pillow for images; run `compare_figure.py` with `uv run`, which installs its dependencies. `check_package.py` needs Python 3.11 or later and network access to install the package's dependencies.

## When to stop and ask

One shot means not pausing for confirmation. Stop only for decisions that belong to the user: the licence forbids even comparison copies of the figures, the core results need paid or proprietary software, the core pipeline cannot fit any CI budget, or the only source for the method is authors' code with no licence and the paper's text is not enough to implement it. Everything else (a missing setting, a broken script, a figure that will not match) is work to do and record.

## Effort on mismatches

Investigation can grow without end. An item's investigation stops when a hypothesis closes the gap quantitatively (status `explained`), or when the plausible hypotheses are tested and none does (status `open`, at least two recorded). An open cause is an honest result; an untested one is not. Spend the most on the paper's central claims.

## References

- [definition-of-done.md](references/definition-of-done.md): the checklist and the pull-request template. Read first and last.
- [results-json.md](references/results-json.md): fields, verdict rules, cause categories.
- [figure-scoring.md](references/figure-scoring.md): pixel grids, two-way scores, negative controls, pass marks.
- [mismatch-investigation.md](references/mismatch-investigation.md): how to find out why, with examples; when several inputs differ.
- [text-claims.md](references/text-claims.md): claims in the text; the arithmetic check, our run and sensitivity variants kept apart.
- [pipeline-and-ci.md](references/pipeline-and-ci.md): downloads, pinning, the check step, CI time budgets.
- [session-ledger.md](references/session-ledger.md): the kickoff prompt and how the session is recorded.
- [fossil-layout.md](references/fossil-layout.md): folder, site and README conventions of the fossil repository.
- [figure-matching.md](references/figure-matching.md): aligning a render to the published frame with `compare_figure.py`, and reading its report.
- [numerical-fidelity.md](references/numerical-fidelity.md): rounding-level results, FMA, x87 80-bit sums, library versions; identifying parameters from the figure.
- [timing-and-estimation.md](references/timing-and-estimation.md): runtime figures re-measured on other hardware.
- [package-and-tutorial.md](references/package-and-tutorial.md): the paper's method as a Python package, its example data, tests and tutorial.
- [publishing.md](references/publishing.md): licences, what may be committed, and the self-review.
- [example-pmc4081639.md](references/example-pmc4081639.md): a complete worked case (Yu and Shaw 2014).
