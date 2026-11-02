---
name: paper2repro
description: Reproduce a paper's computed figures and tables with the paper's own method, data and plotting tools, compare them with the published versions pixel by pixel, and deliver a rerunnable pipeline with a check report and comparison site. Use when the user asks to reproduce, verify or redraw published results, with or without a code repository.
---

# Paper2Repro

Rebuild what a paper computes, draw it with the paper's own tools, and measure how close it is to the published version. The evidence comes from the paper's method, data and arithmetic. Never change data to make a figure match.

## Start here

1. Obtain the paper and supplement, any code repository or package, the data, the target figures and tables, and the output project. Ask only for missing required inputs.
2. If no paper skill exists, build one with [Paper2Skill](../paper2skill/SKILL.md). Read methods, captions and figures from it.
3. Read the paper's copyright line and every data license before you plan the output. See [publishing](references/publishing.md).
4. List every figure and table. Mark each one as computable, diagram or data display, and record the inputs it needs. Report the ones you do not reproduce.

## Workflow

| Stage | Read | Completion evidence |
| --- | --- | --- |
| 1. Inventory and licenses | [Publishing](references/publishing.md) | Item list with status; decision on what may be published |
| 2. Data | [Numerical fidelity](references/numerical-fidelity.md), [timing and estimation](references/timing-and-estimation.md) | Per item: parameters identified from the published figure; status with counts (identical, same setup, re-measured) |
| 3. Drawing and pixel comparison | [Figure matching](references/figure-matching.md) | Renders at the published pixel size; a `compare_figure.py` report per figure; overlays inspected |
| 4. Pipeline and delivery | [Publishing](references/publishing.md) | Workflow run passes; check report; CI on the paper's architecture; comparison site |
| 5. Self-review | [Publishing](references/publishing.md#self-review) | Review that lists gaps, fitted parameters, mistakes and open checks |

## Essential requirements

- Classify each result with evidence: **identical data** (for example, 300 of 300 points), **same setup** with numeric noise (k of n marks agree), or **re-measured** (timing on other hardware). Do not call a partial or re-measured result "reproduced" without the qualifier.
- Identify parameters from the published figure itself: calibrate axes from gridlines, then score candidate grids against the traced curve. A grid that only looks similar is not identified.
- When results sit at rounding level, reproduce the arithmetic: FMA contraction, x87 80-bit accumulation, library versions. Confirm on the original architecture in CI.
- Keep fitted presentation parameters (drawing size, title gaps, axis scale constants) apart from data and list them as fitted. Keep an unscaled version of any rescaled figure.
- Use published figures only for comparison. Do not commit the paper, its full text, page renders or supplements to a public repository unless their license allows it. Ask the user first.
- Compare at the published pixel size and inspect overlays. One mean-difference score is not evidence of a match.
- If the paper cites a package version for a method, use that version's source. If you substitute your own implementation, say so and report the agreement count.

## Helpers

- [compare_figure.py](scripts/compare_figure.py) finds the plot panel in both images, aligns the reproduction to the published frame, and writes `aligned.png`, a red/cyan `overlay.png`, `diff.png` and `report.json`. The report gives the shift, the panel-size difference, mean grey difference, ink chamfer distances inside and outside the panel, and per-region offsets. It warns when a region offset reaches the search window or the panel sizes differ.
- [test_compare_figure.py](scripts/test_compare_figure.py) runs synthetic checks: `uv run scripts/test_compare_figure.py`.

```bash
uv run /path/to/scripts/compare_figure.py --published figure-4.jpg --render fig4.png \
  --out compare/fig4 --regions regions.json --window 10
```

## Output

```text
<project>/
├── README.md
├── <paper-id>/
│   ├── README.md              # citation, copyright note, results table
│   └── reproduction/
│       ├── main.nf
│       ├── nextflow.config
│       ├── pipeline/          # scripts, committed inputs, params/
│       ├── published/         # only the figures used for comparison
│       └── output/            # renders: PDF, source, aligned PNG, fit summary
├── site/                      # static comparison pages
└── .github/workflows/         # reproduce.yml, pages.yml
```

Lead the final response with a results table (item, status, evidence). Then give the pipeline and CI status, the site URL, items not reproduced and why, fitted parameters, and licensing exclusions.

For a complete case, read the [PMC4081639 worked example](references/example-pmc4081639.md).
