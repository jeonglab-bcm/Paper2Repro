# Definition of done

Check every line on the pull request's head commit. Each one is here because a past reproduction missed it and needed another pull request.

## Results

- [ ] `results.json` lists every figure panel, table and quantitative statement of the paper, attempted or not.
- [ ] `check_results.py <id>/results.json` exits 0: verdicts and summary computed, no missing causes, no untested open causes.
- [ ] Every attempted figure panel has a render (`fig*_ours.png`) and an overlay (`fig*_overlay.png`), listed in its `outputs`. Scoring a panel without drawing it is not enough.
- [ ] Every pixel-scored panel has at least one wrong-input control and, where amplitude or position matters, near-miss controls; the pass mark sits above all of them.
- [ ] Every constant read off a figure or found by search is an `assumption` with its sensitivity.
- [ ] Every `partly`, `inconclusive`, `differs` and `not_attempted` item has a cause; `open` causes list at least two tested hypotheses.
- [ ] If the authors' code was ported, the port is checked against the original runtime on the paper's data.

## Pipeline and CI

- [ ] One command reruns everything: `nextflow run <id>/figure-reproduction/main.nf --outdir results`.
- [ ] Inputs are downloaded by script, from a source that allows scripted downloads (with a fallback mirror), and their SHA-256 checked.
- [ ] Package versions are pinned (`requirements.txt` with `==`, R package versions or archive URLs, runtime versions recorded).
- [ ] The check step fails on a pass-mark breach and on any difference between the fresh run and the committed outputs (`compare_runs.py`).
- [ ] The pull-request workflow finishes inside its budget on a standard runner. Steps that do not (refits, long searches) run on `workflow_dispatch` or a schedule, and the README says so.
- [ ] The exact CI command was run from a clean checkout before pushing.

## Pages and docs

- [ ] The paper's results page is generated from `results.json` and the published figures; no verdict is typed into a template.
- [ ] The front page lists the paper, with its verdict taken from `results.json`.
- [ ] The top-level README table lists the paper and its workflow.
- [ ] `<id>/README.md` and `<id>/figure-reproduction/README.md` follow the existing papers: citation, licence, what is and is not in the repository, Results, what the code does against the paper, Layout, Run, Pipeline steps, Limits.
- [ ] If the paper ships code that differs from its text, a code-analysis folder with executable checks, and its page.
- [ ] Nothing the licence forbids is committed (paper PDFs, supplements, authors' code); large or restricted sources are git-ignored.

## Session and pull request

- [ ] `<id>/session/ledger.json` and `conversation.md` are committed.
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

### Run
`nextflow run <id>/figure-reproduction/main.nf --outdir results` (<minutes> min on <machine>). CI: <workflow name>, <minutes> min.

### Session
<Prompts>, <responses>, <tool calls>; tokens in / cache write / cache read / out: <...>; wall clock <...> (`<id>/session/ledger.json`).
```
