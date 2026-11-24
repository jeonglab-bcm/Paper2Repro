# results.json

One file per paper, `<id>/results.json`, schema `paper2repro/results/v1`. It is the normalized record every page, README row and pull-request table is generated from, so the papers in a repository can be compared and nothing is typed twice. `scripts/check_results.py` is the authority on the rules below; [example-results.json](../assets/example-results.json) shows each kind of item.

## Top level

```json
{
  "schema": "paper2repro/results/v1",
  "paper": {"id": "PMC1847688", "title": "...", "citation": "...", "doi": "...", "license": "CC BY 2.0"},
  "run": {"date": "2026-10-28", "pipeline": "<id>/figure-reproduction/main.nf", "command": "nextflow run ...",
          "inputs": [{"name": "S2.zip", "url": "...", "sha256": "..."}], "environment": {"python": "3.12.7", "numpy": "2.1.3"}},
  "session": {"ledger": "session/ledger.json"},
  "skill": {"name": "paper2repro", "version": "0.7.0", "tag": "paper2repro-v0.7.0", "commit": "<sha>", "modified": false},
  "items": [ ... ],
  "claims": [ ... ],
  "summary": {"items": 9, "exact": 0, "agrees": 4, "...": 0, "open_causes": 2}
}
```

`summary`, each item's `verdict` and its `basis` are written by `check_results.py --write`. Do not edit them. `summary` also counts `reviewed` (verdicts a reviewer set), `for_review` (items a person must decide) and `claims` by result, when there are any.

`skill` names the Paper2Repro release the session ran, so a reproduction can be traced to the exact instructions behind it. Write it with `scripts/skill_version.py`, run from the installed skill, never by hand:

- `version` and `tag` come from the skill's `VERSION` file. Each release is tagged `paper2repro-v<version>` in the Paper2Repro repository.
- `commit` is the skill checkout's git commit, or null when the skill is a copy without git (a cloud session, for example).
- `modified` is true when the skill folder had uncommitted changes, so the version alone does not describe what ran. It is null without git.

`check_results.py` fails when `skill` is missing.

## Items

| Field | Content |
| --- | --- |
| `id` | Stable and unique: `fig2`, `fig3.b`, `fig5.monotone-minimum`, `table1`, `table2.row3`, `text.plasma_totals`, `port`, `package`. |
| `label` | As a reader would say it: "Fig. 3b", "Table 1, LIMPIC rows". |
| `kind` | `figure`, `table`, `value` (a number in the text) or `code_check`. |
| `source` | Where our version comes from: `authors_code`, `port` (checked against it), `papers_data`, `supplement_values` (replotted from a supplement table), `reconstructed` (rebuilt from public data or an unstated method), `public_data`, `none`. |
| `method` | `pixels`, `values`, `check` or `none` (not attempted). |
| `pixels` | `tolerance_px`, `dpi`, `published_near_ours`, `ours_near_published`, `threshold`, `controls` [{`name`, `kind`: `wrong_input` or `near_miss`, `score`}]. |
| `values` | `fields` [{`name`, `expected`, `observed`, optional `tolerance`, optional `noise`}], `tolerance` ({`printed`: true} or {`abs`: x} or {`rel`: x}), optional `exceptions` [{`field`, `category`, `evidence`}]. See "Noise band". |
| `check` | `passed`, `detail`: for executable checks such as a port against the original code. |
| `assumptions` | [{`what`, `source`: `paper`, `authors_code`, `our_choice`, `read_from_figure` or `found_by_search`, `sensitivity`}]. Anything not taken from the paper or the authors' code goes here. |
| `cause` | {`category`, `summary`, `evidence` [paths or URLs], `hypotheses` [{`hypothesis`, `test`, `result`: `supported`, `rejected` or `inconclusive`}], `status`: `explained` or `open`, `checklist` {`wayback`, `references`, `leakage`, `convergence`}}. |
| `layout` | How a figure of ours sits on the published frame: `{"drawn_on_published": true}`, or `panel_size_difference_px`, `ink_outside_frame` and `axes` [{`axis`, optional `scale`: `log`, `published`, `ours`}] for a new drawing, or `{"not_comparable": "<why>"}`. See "Layout". |
| `outputs` | Paths, relative to the paper folder, of the render and overlay of a scored figure. |
| `review` | Set by a reviewer, never by the agent: {`verdict`, `computed`, `by`, `url`, `reason`: {`kind`, `text`}}. See "Reviews". |
| `basis` | Written by the checker when the printed digits alone do not give the verdict: "within noise: …" or "claim holds (…)". Pages show it as the line under the verdict. |

Give printed values as strings (`"0.69"`, `"277.37"`) so `{"printed": true}` knows their precision: half a unit in the last printed digit.

The `package` item is a `code_check` whose `check` comes from the `check_package.py --json` report (Python: `passed` and its `detail` line) or the R steps (R). See [package-and-tutorial.md](package-and-tutorial.md).

## Verdict rules

Pixels, with `s` the smaller of the two shares, `T` the threshold, and controls split by kind:

| Verdict | When |
| --- | --- |
| `differs` | `s` is no better than the best wrong-input control. |
| `inconclusive` | `s` is no better than the best near-miss control: the score cannot tell ours from a known-wrong variant. |
| `agrees` | `s ≥ T`. |
| `partly` | Between the controls and `T`. |

`T` must be above every control score, or the check fails: a pass mark that a wrong input reaches is not a test.

Values: `exact` if every field matches, `agrees` if every field matches but an assumption was read from a figure or found by search, or if every field matches or falls inside its noise band, `partly` if some match, `differs` if none. Fields listed in `exceptions` with category `paper_error` (the paper contradicts itself, for example a rank that disagrees with its own printed scores) are left out of the count but stay in the file. A value the paper does not print is not a field.

Checks: `agrees` if passed, `differs` if not. Method `none`: `not_attempted`.

A figure reaches `exact` only through `values`, when the plotted numbers themselves can be compared (source data, a vector figure, a table behind it). Pixels top out at `agrees`.

## Noise band

The printed digits are not the only test. A method with random seeds, Monte Carlo replicates or folds the paper does not give cannot come back to the last digit, and fossil's reviewers raised 69 of 82 verdicts for that reason. Give a field the noise our own runs show, and a gap inside it counts:

```json
{"name": "AUC", "expected": "0.9110", "observed": 0.9111, "noise": {"runs": [0.9109, 0.9111, 0.9112]}}
```

| `noise` | Band |
| --- | --- |
| `{"runs": [...]}` | The range of our values over at least two seeds or reruns. |
| `{"spread": x}` | A spread measured another way; say how in the item's cause or assumptions. |
| `{"mc_se": se}` | 2 × the Monte Carlo standard error of our estimate. |
| `{"samples": k, "n": N, "scale": 100, "why": "..."}` | k of N samples behind an accuracy (scale 100 for percent). At most 3, and only when the paper gives no seeds, folds or settings: `why` says which. |

The band is the largest of those given, on top of the field's tolerance. Measure it: rerun with other seeds, or compute the standard error. A band is not a tolerance widened until the field matches; a field with no `noise` is held to its printed digits. An item whose every field matches or falls inside its band `agrees`, with `basis` "within noise".

## Claims

`claims` lists the paper's conclusions, the sentences a reader takes as its findings, each resting on the items that support it:

```json
{"id": "c1", "text": "Combining all three feature sets gives the highest AUC", "where": "Abstract; Results, Table 2",
 "items": ["table2.all", "fig3"], "test": "rank of the six feature sets by our AUC", "result": "holds"}
```

`result` is `holds`, `partly` or `fails`, from a test our code computes on our run (a rank, a direction, a significance call at the paper's α). The agent writes the list in phase 1, before computing ours. The reviewer approves it.

An item whose numbers give `partly`, `inconclusive` or `differs` while every claim resting on it holds:

- **agrees** when its cause is `explained`, with `basis` "claim holds (c1); the numbers alone give partly";
- keeps its computed verdict and is listed **for a person** (`summary.for_review`, a `REVIEW` line) when its cause is `open`. An unexplained gap can be a setting of ours that is wrong while the claim still holds (fossil #35: PSI-BLAST settings), so a person decides.

## Reviews

A reviewer overrules a computed verdict with the item's `review` block:

```json
"review": {"verdict": "agrees", "computed": "partly", "by": "<GitHub login>", "url": "<the review>",
           "reason": {"kind": "noise", "text": "1 to 3 samples short; the paper gives no folds"}}
```

- `computed` is the verdict the reviewer saw. When the numbers later give another one, the check fails until the item is reviewed again.
- `reason.kind` is `noise`, `paper_error`, `follows` (with `reason.item`, the id of the accepted item it follows), `data_release` or `judgment`.
- `reason.text` says why. "Without comment", "per review comment …" and a bare "Partly → Agrees." are refused: a reason written once becomes a rule the checker can apply the next time. 51 of fossil's first 82 overrides had none.
- `check_results.py --base <the file on main>` lets reviews already on main warn instead of fail until their reason is filled in. A new or changed review always needs one. When that file is not there (a new paper), the check says so and treats every review as new.

## Layout

Every figure item that is attempted and lists a picture of ours in `outputs` has a `layout`, because the picture is shown next to the published one and on top of it. `check_results.py` accepts three records:

| Record | When | Rule |
| --- | --- | --- |
| `{"drawn_on_published": true}` | Our series is drawn on a copy of the published picture. | Nothing more: the frame is the published one. |
| `{"panel_size_difference_px": [0, 1], "ink_outside_frame": 0.0, "axes": [...]}` | The figure is drawn anew. | The panel of ours is within 2 px of the published size (or within the item's `pixels.tolerance_px` if that is larger), at most 1% of our ink falls outside the published picture, and every axis of ours is the published one. |
| `{"not_comparable": "<why>"}` | A drawing with no axes to share. | The reason is given. Never for a plot with axes. |

`panel_size_difference_px` and `ink_outside_frame` are the `layout` block of `compare_figure.py`'s `report.json`; let the pipeline copy them. `axes` has one entry for each axis of the panel:

```json
"axes": [
  {"axis": "x", "published": [0, 0.1], "ours": [0, 0.1]},
  {"axis": "y", "scale": "log", "published": [0.001, 1], "ours": [0.001, 1]},
  {"axis": "bars", "published": ["mean", "median", "ES"], "ours": ["mean", "median", "ES"]}
]
```

`published` holds the data values at the two ends of the axes box, from the tick calibration of the published picture; `ours` holds the limits our plotting code drew with, read back from it. Numeric limits agree when each end is within 0.5% of the published axis length (of its length in decades for `"scale": "log"`). An axis of names (bars, groups, the rows of a heat map) agrees when ours has the same names in the same order. Draw with the published axis even when our values differ; say in the item's cause how many points of ours fall outside it.

## Causes

Required for `partly`, `inconclusive`, `differs` and `not_attempted`; allowed on any item.

| Category | Meaning |
| --- | --- |
| `rendering_only` | The numbers agree; the residual is line width, anti-aliasing or overlap. |
| `paper_error` | A slip in the paper (rounding, rank, label, caption). |
| `undocumented_setting` | A value the paper and code do not give. |
| `code_differs_from_paper` | The published code computes something other than the text says. |
| `code_does_not_run` | The published code needed a fix to run. |
| `data_differs` | The shipped data are not the data behind the figure. |
| `data_unavailable` | The inputs are not public. |
| `proprietary_software` | The result needs software that is not available. |
| `nondeterminism` | Random seeds, run order, platform arithmetic. |
| `environment` | Library or runtime versions. |
| `not_a_result` | A diagram or schematic; for the `package` item, a paper with no reusable method. |
| `metric_resolution` | The comparison cannot resolve the difference (an `inconclusive` item). |
| `unknown` | Only with status `open`. |

`explained` needs evidence or a supported hypothesis. `open` needs at least two hypotheses tested and not supported, so the reader sees what was ruled out.

From release 0.8.0, an `open` cause, and the cause of a `not_attempted` item, also need `checklist`: the four searches of [mismatch-investigation.md](mismatch-investigation.md#before-you-stop), each a sentence on what was done and found, or `"n/a: <why>"`. A bare `"n/a"` is refused. Category `not_a_result` needs none. A results.json made with an earlier release is not asked for it, but a checklist it does give is checked.

```json
"checklist": {
  "wayback": "the lab page and FTP folder in the Availability section: a 2012 capture has the source archive (now in sources/, H3)",
  "references": "ref. 12's window and threshold, which the methods cite for this step, tried as H2: rejected",
  "leakage": "n/a: nothing is trained, tuned or selected",
  "convergence": "rerun at the paper's 1,000 iterations and at 10,000: values unchanged at printed precision"
}
```

## Producing the file

Let the pipeline write the numbers. Keep what a person writes (labels, sources, assumptions, causes, controls' names) in a small notes file such as `figure-reproduction/results_notes.json`, and have a pipeline step merge it with the scores from the comparison outputs into `results.json`, then run `check_results.py --write`. Stamp the notes file with `skill_version.py <notes file>` in phase 1, and have the merge step copy its `skill` block into `results.json` unchanged, like `session`. A copied `check_results.py` run in CI cannot tell which skill wrote the file, so the block has to travel with the notes. That way a rerun updates every score and a stale cause shows up as a failed check, not as a wrong page.

On the site, map verdicts to the fossil stamps: `exact` and `agrees` to `data-v="agrees"`, `partly` and `inconclusive` to `partly`, `differs` to `differs`; `not_attempted` items are listed with their reason, without a stamp.
