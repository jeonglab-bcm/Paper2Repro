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
  "items": [ ... ],
  "summary": {"items": 9, "exact": 0, "agrees": 4, "...": 0, "open_causes": 2}
}
```

`summary` and each item's `verdict` are written by `check_results.py --write`. Do not edit them.

## Items

| Field | Content |
| --- | --- |
| `id` | Stable and unique: `fig2`, `fig3.b`, `fig5.monotone-minimum`, `table1`, `table2.row3`, `text.plasma_totals`, `port`. |
| `label` | As a reader would say it: "Fig. 3b", "Table 1, LIMPIC rows". |
| `kind` | `figure`, `table`, `value` (a number in the text) or `code_check`. |
| `source` | Where our version comes from: `authors_code`, `port` (checked against it), `papers_data`, `supplement_values` (replotted from a supplement table), `reconstructed` (rebuilt from public data or an unstated method), `public_data`, `none`. |
| `method` | `pixels`, `values`, `check` or `none` (not attempted). |
| `pixels` | `tolerance_px`, `dpi`, `published_near_ours`, `ours_near_published`, `threshold`, `controls` [{`name`, `kind`: `wrong_input` or `near_miss`, `score`}]. |
| `values` | `fields` [{`name`, `expected`, `observed`, optional `tolerance`}], `tolerance` ({`printed`: true} or {`abs`: x} or {`rel`: x}), optional `exceptions` [{`field`, `category`, `evidence`}]. |
| `check` | `passed`, `detail`: for executable checks such as a port against the original code. |
| `assumptions` | [{`what`, `source`: `paper`, `authors_code`, `our_choice`, `read_from_figure` or `found_by_search`, `sensitivity`}]. Anything not taken from the paper or the authors' code goes here. |
| `cause` | {`category`, `summary`, `evidence` [paths or URLs], `hypotheses` [{`hypothesis`, `test`, `result`: `supported`, `rejected` or `inconclusive`}], `status`: `explained` or `open`}. |
| `outputs` | Paths, relative to the paper folder, of the render and overlay of a scored figure. |

Give printed values as strings (`"0.69"`, `"277.37"`) so `{"printed": true}` knows their precision: half a unit in the last printed digit.

## Verdict rules

Pixels, with `s` the smaller of the two shares, `T` the threshold, and controls split by kind:

| Verdict | When |
| --- | --- |
| `differs` | `s` is no better than the best wrong-input control. |
| `inconclusive` | `s` is no better than the best near-miss control: the score cannot tell ours from a known-wrong variant. |
| `agrees` | `s ≥ T`. |
| `partly` | Between the controls and `T`. |

`T` must be above every control score, or the check fails: a pass mark that a wrong input reaches is not a test.

Values: `exact` if every field matches, `agrees` if every field matches but an assumption was read from a figure or found by search, `partly` if some match, `differs` if none. Fields listed in `exceptions` with category `paper_error` (the paper contradicts itself, for example a rank that disagrees with its own printed scores) are left out of the count but stay in the file. A value the paper does not print is not a field.

Checks: `agrees` if passed, `differs` if not. Method `none`: `not_attempted`.

A figure reaches `exact` only through `values`, when the plotted numbers themselves can be compared (source data, a vector figure, a table behind it). Pixels top out at `agrees`.

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
| `not_a_result` | A diagram or schematic. |
| `metric_resolution` | The comparison cannot resolve the difference (an `inconclusive` item). |
| `unknown` | Only with status `open`. |

`explained` needs evidence or a supported hypothesis. `open` needs at least two hypotheses tested and not supported, so the reader sees what was ruled out.

## Producing the file

Let the pipeline write the numbers. Keep what a person writes (labels, sources, assumptions, causes, controls' names) in a small notes file such as `figure-reproduction/results_notes.json`, and have a pipeline step merge it with the scores from the comparison outputs into `results.json`, then run `check_results.py --write`. That way a rerun updates every score and a stale cause shows up as a failed check, not as a wrong page.

On the site, map verdicts to the fossil stamps: `exact` and `agrees` to `data-v="agrees"`, `partly` and `inconclusive` to `partly`, `differs` to `differs`; `not_attempted` items are listed with their reason, without a stamp.
