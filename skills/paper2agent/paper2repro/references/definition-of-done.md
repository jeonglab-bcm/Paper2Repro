# Definition of done

Check every line on the pull request's head commit. Each one is here because a past reproduction missed it and needed another pull request.

## Results

- [ ] `results.json` lists every figure panel, table and quantitative statement of the paper, attempted or not.
- [ ] `check_results.py <id>/results.json` exits 0: verdicts and summary computed, no missing causes, no untested open causes.
- [ ] `results.json` has the `skill` block written by `skill_version.py` from the installed skill, and the pipeline's merge step keeps it on a rerun.
- [ ] Every attempted figure panel has a render (`fig*_ours.png`) and an overlay (`fig*_overlay.png`), listed in its `outputs`. Scoring a panel without drawing it is not enough.
- [ ] Every one of those renders is on the published frame: the published picture size, each panel's axes at the published box, the published axis limits, tick values and order of bars, and its `layout` in `results.json` says so ([figure-matching.md](figure-matching.md), "The published frame"). Open each overlay and look: one set of axes, one legend, one title.
- [ ] Every pixel-scored panel has at least one wrong-input control and, where amplitude or position matters, near-miss controls; the pass mark sits above all of them.
- [ ] Every constant read off a figure or found by search is an `assumption` with its sensitivity.
- [ ] Every `partly`, `inconclusive`, `differs` and `not_attempted` item has a cause; `open` causes list at least two tested hypotheses.
- [ ] Every `open` cause and every `not_attempted` item (but a `not_a_result` one) has its `checklist`: the Wayback Machine, the cited references' settings, leakage and convergence, each searched or `n/a` with the reason ([mismatch-investigation.md](mismatch-investigation.md#before-you-stop)).
- [ ] If the authors' code was ported, the port is checked against the original runtime on the paper's data.
- [ ] Every claim in the text is recomputed from the paper's own tables (`text.arithmetic`) before it is compared with our run ([text-claims.md](text-claims.md)).
- [ ] No number from a sensitivity variant (one of the paper's values put into our run) is cited as agreement anywhere.
- [ ] A rebuilt tool's agreement count uses only inputs identical to the paper's.

## Pipeline and CI

- [ ] One command reruns everything: `nextflow run <id>/figure-reproduction/main.nf --outdir results`.
- [ ] Inputs are downloaded by script, from a source that allows scripted downloads (with a fallback mirror), and their SHA-256 checked.
- [ ] Package versions are pinned (`requirements.txt` with `==`, R package versions or archive URLs, runtime versions recorded).
- [ ] The workflow runs in the repository's CI image, named by digest, and the README's Run section gives the digest. Any fix the run needed in the environment (a BLAS kernel, a font, the locale, a system library, a CRAN package) is a pull request on the image, not a setting in this paper's workflow or `nextflow.config` ([pipeline-and-ci.md](pipeline-and-ci.md#the-ci-image)).
- [ ] The check step fails on a pass-mark breach and on any difference between the fresh run and the committed outputs (`compare_runs.py`).
- [ ] The pull-request workflow finishes inside its budget on a standard runner. Steps that do not (refits, long searches) run on `workflow_dispatch` or a schedule, and the README says so.
- [ ] The exact CI command was run from a clean checkout before pushing.

## Package and tutorial

- [ ] The paper's method is a Python or R package in `<id>/package/`, in the language the kickoff named or by the default rule, with the choice and its reason in the package README; or the `package` item is `not_attempted` because the paper has no reusable method.
- [ ] The pipeline calls the package for the method; there is no second copy of the method's code.
- [ ] The install command is in the package README and the tutorial: `pip install "git+https://github.com/<owner>/<repo>#subdirectory=<id>/package"` (Python) or `remotes::install_github("<owner>/<repo>/<id>/package")` (R).
- [ ] A port is checked against the authors' code on its free runtime; where only proprietary software runs it, against the paper, with the `port` item `not_attempted` (`proprietary_software`) and the README saying so. No authors' source is in the package.
- [ ] The example data are 1 MB or less, licensed for redistribution, and the data README says where the input and the expected output come from. The expected output does not come from the package itself.
- [ ] The tutorial shows install, the example input, a run through the API (and the command line in Python), and the comparison with the expected output. Its outputs were produced by running it (`check_package.py --write`, or `R CMD build` for the vignette), and `TUTORIAL.md` was generated from it.
- [ ] `check_package.py <id>/package` (Python) or the R steps (R) pass in CI, and the result is the `package` item in `results.json`.

## Pages and docs

- [ ] The paper's results page is generated from `results.json` and the published figures; no verdict is typed into a template.
- [ ] The front page lists the paper: `<id>/index.json` is written, its verdict taken from `results.json`, and `tools/build_index.py` and `tools/check_index_links.py` pass ([fossil-layout.md](fossil-layout.md#the-front-page-row)).
- [ ] The pull request touches only `<id>/`, `site/<id>/` and its own workflow (and a `.gitignore` line); not `site/index.html`, the top-level README or another paper's files.
- [ ] `<id>/README.md` and `<id>/figure-reproduction/README.md` follow the existing papers: citation, licence, what is and is not in the repository, Results, what the code does against the paper, Layout, Run, Pipeline steps, Limits.
- [ ] The claims section of the README and the results page ends with one line: the verdict on the main claim and the causes of the claims that do not match.
- [ ] The self-review checked each sentence against the numbers it cites ([publishing.md](publishing.md#self-review)).
- [ ] If the paper ships code that differs from its text, a code-analysis folder with executable checks, and its page.
- [ ] Nothing the licence forbids is committed (paper PDFs, supplements, authors' code); large or restricted sources are git-ignored.

## Session and pull request

- [ ] `<id>/session/ledger.json` and `conversation.md` are committed, written with the names of everyone in the session passed to `--redact`, and `session_ledger.py --check` passes on them before they were first committed.
- [ ] One pull request, using the template below.
- [ ] CI is green on the head commit; the final ledger is pushed after it.

## Pull-request template

```markdown
## <Paper short title> (<PMCID>)

<Citation with DOI.>

### What came back
<Output of: check_results.py <id>/results.json --markdown>

### Not exact, and why
<One line per non-exact item: the cause and whether it is explained or open, with what was ruled out.>

### Package
<Python or R, and why.> `<install command>`; tutorial: `<id>/package/tutorial/TUTORIAL.md`. <Or: no reusable method, and why.>

### Run
`nextflow run <id>/figure-reproduction/main.nf --outdir results` (<minutes> min on <machine>). CI: <workflow name>, <minutes> min.

### Session
<Prompts>, <responses>, <tool calls>; tokens in / cache write / cache read / out: <...>; wall clock <...> (`<id>/session/ledger.json`).
```
