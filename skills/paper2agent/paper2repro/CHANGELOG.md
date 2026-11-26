# Paper2Repro changelog

The version in [`VERSION`](VERSION) covers everything in this folder. Each release is tagged
`paper2repro-v<version>` at the merge on `main` that brought it in, so a reproduction can name the exact
skill it ran with.

Bump the version in any pull request that changes this folder, and add a row below. Leave the commit
as `-`. The release workflow tags the merge commit when the pull request lands. Before 1.0, a minor
bump is for a new phase, rule or output a reproduction must follow, and a patch is for wording, fixes
and examples that change nothing a reproduction produces.

| Version | Date | Commit on `main` | Pull request | What changed |
| --- | --- | --- | --- | --- |
| 0.9.0 | 2026-11-26 | - | #22 | Paper2Revise (`../paper2revise/`) reviews and revises a reproduction pull request after it opens: each round reruns the pipeline from a clean checkout and `check_results.py`, two blind reviewers check every overlay and every sentence against its number (claims against the top-level `claims` of 0.7.0), and a fixer answers each blocking finding or marks it `needs_human` with two tested hypotheses. It stops at a clean round, at `needs_human` only, after 5 rounds or at $50, and labels the pull request `paper2revise-clean` or `needs-human`. |
| 0.8.0 | 2026-11-24 | - | - | Rules from the 23 Nov fossil update (fossil #128). The workflow runs in fossil's CI image pinned by digest, and a fix to the environment goes into the image, not one paper. Before a cause stays `open` or an item is `not_attempted`, the Wayback Machine, the cited references' settings, leakage and convergence are searched and recorded in `cause.checklist`, which `check_results.py` requires from this release. `session_ledger.py` masks emails, home folders, the git identity and `--redact` names as it writes, and `--check` finds any left. The front-page row is the paper's own `index.json`; a pull request no longer edits `site/index.html` or the README. |
| 0.7.0 | 2026-11-23 | - | - | One checker for the skill and fossil, with verdicts closer to the reviewers': `review` blocks from fossil, now with a required `reason` {kind, text} (`--base` lets reviews already on main warn until filled in); a measured noise band per field (`noise`: our runs' range, 2 Monte Carlo SE, or up to 3 samples when the paper gives no seeds or folds); a top-level `claims` list, where an item whose claims all hold agrees when its gap is explained and goes to a person when it is open; a `basis` line for verdicts the printed digits alone do not give. |
| 0.6.0 | 2026-11-17 | - | #20 | Figures of ours are on the published frame: the published picture size, axes box and axis limits. Each figure item with a picture records its `layout`, and `check_results.py` refuses a missing one, a panel off the published size or an axis that is not the published one. `compare_figure.py` also finds a panel with no fill by its axis lines, takes the boxes as arguments, reports `same_frame` and fails on `--require-frame`. |
| 0.5.0 | 2026-11-10 | d6a7558 | #9 | The skill records its release: `scripts/skill_version.py` writes the top-level `skill` block (version, tag, commit, uncommitted changes) into `results.json`, and `check_results.py` requires it. |
| 0.4.0 | 2026-11-07 | 727d35e | #5 | Package the paper's method as a Python or R package with an executed tutorial; rules for other languages; R install through pak. |
| 0.3.0 | 2026-11-05 | 0e010bc | #6 | Claims in the paper's text are scored like figures and tables; gaps with several differing inputs. |
| 0.2.0 | 2026-11-03 | 77e217f | #4 | The fossil version: normalized `results.json` with computed verdicts, its checker, run comparison and the session ledger. |
| 0.1.0 | 2026-11-01 | 2d4cd82 | #1 | First release: reproduce a paper's figures and tables, Nextflow pipeline, figure comparison. |
