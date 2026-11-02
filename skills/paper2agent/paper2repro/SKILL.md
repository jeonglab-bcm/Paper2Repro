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
5. List the software that the paper used. Mark each tool as current or outdated. See [current software](references/current-software.md).
6. Record the skill version: run `python3 ../scripts/skill_checksum.py` from this skill directory and save its output as `<project>/<paper-id>/reproduction/skill-version.json`.

## Workflow

| Stage | Read | Completion evidence |
| --- | --- | --- |
| 1. Inventory, licenses and software | [Publishing](references/publishing.md), [current software](references/current-software.md) | Item list with status; decision on what may be published; software list with latest versions and replacements |
| 2. Data | [Numerical fidelity](references/numerical-fidelity.md), [timing and estimation](references/timing-and-estimation.md) | Per item: parameters identified from the published figure; status with counts (identical, same setup, re-measured) |
| 3. Drawing and pixel comparison | [Figure matching](references/figure-matching.md) | Renders at the published pixel size; a `compare_figure.py` report per figure; overlays inspected |
| 4. Pipeline and delivery | [Publishing](references/publishing.md) | Workflow run passes; check report; CI on the paper's architecture; comparison site |
| 5. Self-review | [Publishing](references/publishing.md#self-review) | Review that lists gaps, fitted parameters, mistakes and open checks |

## Essential requirements

- Classify each result with evidence: **identical data** (for example, 300 of 300 points), **same setup** with numeric noise (k of n marks agree), or **re-measured** (timing on other hardware). Do not call a partial or re-measured result "reproduced" without the qualifier.
- Identify parameters from the published figure itself: calibrate axes from gridlines, then score candidate grids against the traced curve. A grid that only looks similar is not identified.
- When results sit at rounding level, reproduce the arithmetic with current tools: FMA contraction, x87 80-bit accumulation, operation order. Confirm on the original architecture in CI.
- Keep fitted presentation parameters (drawing size, title gaps, axis scale constants) apart from data and list them as fitted. Keep an unscaled version of any rescaled figure.
- Use published figures only for comparison. Do not commit the paper, its full text, page renders or supplements to a public repository unless their license allows it. Ask the user first.
- Compare at the published pixel size and inspect overlays. One mean-difference score is not evidence of a match.
- Use current software only. Do not run outdated tools (for example, Weka). Read them as the specification and implement the method in Python, R or Rust. For a maintained tool, run its latest release, not the paper's old version, and restate the old defaults. Report each replacement and its agreement count.
- Install the latest stable release of every runtime, package and CI action, then pin the resolved versions in a lockfile.

## Helpers

- [compare_figure.py](scripts/compare_figure.py) finds the plot panel in both images, aligns the reproduction to the published frame, and writes `aligned.png`, a red/cyan `overlay.png`, `diff.png` and `report.json`. The report gives the shift, the panel-size difference, mean grey difference, ink chamfer distances inside and outside the panel, and per-region offsets. It warns when a region offset reaches the search window or the panel sizes differ.
- [test_compare_figure.py](scripts/test_compare_figure.py) runs synthetic checks: `uv run scripts/test_compare_figure.py`.
- [skill_checksum.py](../scripts/skill_checksum.py) prints the skill checksum: the SHA-256 of every file path and content in the installed skill. Equal checksums mean the same skill version.

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
│       ├── skill-version.json # output of skill_checksum.py
│       ├── pipeline/          # scripts, committed inputs, params/, lockfiles
│       ├── published/         # only the figures used for comparison
│       └── output/            # renders: PDF, source, aligned PNG, fit summary
├── site/                      # static comparison pages
└── .github/workflows/         # reproduce.yml, pages.yml
```

Put the skill checksum in the paper README, the check report and every result file that you write. Lead the final response with a results table (item, status, evidence). Then give the pipeline and CI status, the site URL, items not reproduced and why, fitted parameters, replaced software with versions, licensing exclusions and the skill checksum.

For a complete case, read the [PMC4081639 worked example](references/example-pmc4081639.md).
