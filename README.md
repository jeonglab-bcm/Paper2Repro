# Paper2Repro: Reproduce Published Figures and Tables

## 📖 Overview

`Paper2Repro` is a Claude Code skill that rebuilds a paper's computed figures and tables with the paper's own method, data and plotting tools. It then compares each result with the published version pixel by pixel.

- Works with or without a code repository.
- Reads the paper through an agent-readable paper skill, built by the bundled [Paper2Skill](skills/paper2agent/paper2skill/SKILL.md) component.
- Classifies every result with evidence: **identical data**, **same setup** (numeric noise) or **re-measured** (for example, timing on other hardware).
- Delivers a rerunnable Nextflow pipeline, a check report, CI on the paper's architecture and a static comparison site.
- Never changes data to make a figure match. Fitted presentation parameters are listed apart from data.

See the [Paper2Repro skill instructions](skills/paper2agent/paper2repro/SKILL.md) for the full workflow and requirements.

## 🚀 Quick Start

Ask Claude Code to install the skill, then give it the paper:

```text
Read https://github.com/jeonglab-bcm/Paper2Repro and install the paper2agent skill
from skills/paper2agent for Claude Code.

Use the paper2agent skill (its Paper2Repro component) to reproduce the computed
figures and tables of this paper. Compare each one with the published figure
pixel by pixel and deliver a rerunnable pipeline.

Paper and supplement: <PAPER_URL_OR_LOCAL_FILES>
Code repository (if available): <GITHUB_URL_OR_LOCAL_PATH>
Data (if not in the paper or repository): <DATA_URL_OR_LOCAL_PATH>
Output directory: <PROJECT_DIR>
```

If the skill does not appear after installation, restart Claude Code. For manual installation, see [Installation](#installation).

The skill is installed and invoked as `paper2agent` because Paper2Repro uses the other components in the same folder. See [Built on Paper2Agent](#built-on-paper2agent).

### Examples

Reproduce specific items:

```text
/paper2agent Reproduce Figures 2, 4, 5, 6 and Table 1 of <PAPER_URL> in <PROJECT_DIR>.
Compare each one with the published figure pixel by pixel and deliver a rerunnable pipeline.
```

Reproduce a paper that has no code repository:

```text
/paper2agent Reproduce Figure 3 of <PAPER_URL> in <PROJECT_DIR>.
There is no code repository. Rebuild the method from the paper and its supplement.
Data: <DATA_URL>
```

Run unattended (no questions, local only):

```text
/paper2agent Reproduce Table 1 of <PAPER_URL> in <PROJECT_DIR>.
This is an unattended run. Make reasonable decisions and record them in the project README.
Work locally only. Do not create repositories, push or deploy a site.
```

The skill reads the paper's copyright line and every data license before it plans the output. It commits only the published figures that the comparison needs and asks before it publishes any paper material.

<a id="installation"></a>

## ⚙️ Installation & Setup

### Prerequisites

- **Claude Code** with skill support, shell access and subagents. See the [Claude Code skills documentation](https://code.claude.com/docs/en/skills).
- **Python 3.11+ and [uv](https://docs.astral.sh/uv/)** for the helper scripts.
- **Git.**
- **The paper's own toolchain**, as each paper needs. The worked example and CI use:
  - R (for papers whose figures were drawn in R)
  - Java 21 and [Nextflow](https://www.nextflow.io/) for the pipeline
  - LaTeX and Poppler for tikzDevice figures: `texlive-latex-base`, `texlive-pictures`, `preview-latex-style`, `poppler-utils`

### Manual Installation

1. **Clone this repository**

   ```bash
   git clone https://github.com/jeonglab-bcm/Paper2Repro.git
   cd Paper2Repro
   ```

2. **Copy the entire skill folder to your personal Claude Code skills directory**

   Copy all subdirectories. Paper2Repro reads files from `paper2skill/` and the other components.

   ```bash
   mkdir -p "$HOME/.claude/skills/paper2agent"
   cp -R skills/paper2agent/. "$HOME/.claude/skills/paper2agent/"
   ```

3. **Start Claude Code in your analysis workspace**

   Open Claude Code in the directory where you want to work, then use the [Quick Start](#-quick-start) prompt. If the skill does not appear, restart Claude Code.

## 📦 Output

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

The final response starts with a results table (item, status, evidence). It then gives the pipeline and CI status, the site URL, items not reproduced and why, fitted parameters, and licensing exclusions.

## 🔬 Worked Example: PMC4081639

Yu P, Shaw CA. An efficient algorithm for accurate computation of the Dirichlet-multinomial log-likelihood function. *Bioinformatics* 30(11):1547–1554 (2014). [doi:10.1093/bioinformatics/btu079](https://doi.org/10.1093/bioinformatics/btu079)

- Reproduction: [jeonglab-bcm/fossil](https://github.com/jeonglab-bcm/fossil) (folder `PMC4081639/figure-reproduction`)
- Comparison site: <https://jeonglab-bcm.github.io/fossil/PMC4081639/>

| Item | Status | Evidence |
| --- | --- | --- |
| Fig. 2 | Identical data | ψ grid found from the published curve; 300 of 300 points equal on x86_64 |
| Fig. 4 | Identical data | Fig. 2 series plus mesh values from the authors' library |
| Fig. 5 | Same setup | Same n grid; errors in whole ulps; 26 of 50 VGAM marks identical |
| Fig. 6 | Re-measured | Timing on other hardware, one scale constant per method; mesh growth matches, VGAM growth differs |
| Table 1 | Identical at published precision | All four ψ values round to the printed values |
| Figs 1, 7, 8 | Not reproduced | Computable but out of scope. Fig. 3 is a diagram |

The paper had no code repository. The [full write-up](skills/paper2agent/paper2repro/references/example-pmc4081639.md) lists the findings that changed the outcome and the fitted parameters.

## 🖼️ Pixel Comparison Helper

[`compare_figure.py`](skills/paper2agent/paper2repro/scripts/compare_figure.py) finds the plot panel in both images, aligns the reproduction to the published frame, and measures the difference. You can run it on its own:

```bash
uv run skills/paper2agent/paper2repro/scripts/compare_figure.py \
  --published figure-4.jpg --render fig4.png \
  --out compare/fig4 --regions regions.json --window 10
```

It writes to `--out`:

- `aligned.png`: the reproduction shifted and cropped to the published frame
- `overlay.png`: red = reproduction only, cyan = published only, black = both
- `diff.png`: the grey-level difference
- `report.json`: shift, panel-size difference, mean grey difference, ink chamfer distances inside and outside the panel, and per-region offsets. It warns when a region offset reaches the search window or the panel sizes differ.

`--regions` is optional: a JSON list of `{"name": ..., "box": [x0, x1, y0, y1]}` in published pixels. Use `--published-grey` and `--render-grey` if automatic panel detection fails. Inspect the overlay; one mean-difference score is not evidence of a match.

## 🧪 Testing & CI

| Workflow | Runs | Checks |
| --- | --- | --- |
| [Skill tests](.github/workflows/skill-tests.yml) | Pull requests and pushes to `main` that change `skills/` or the harness | `compare_figure.py` synthetic tests, regression scorer and skill blinding, session log |
| [Skill regression](.github/workflows/skill-regression.yml) | Weekly, manual dispatch, or pull requests with the `skill-regression` label | An unattended Claude Code run reproduces Fig. 2 and Table 1 of PMC4081639 with the worked example withheld, then scores the result |

Run the fast tests locally:

```bash
uv run skills/paper2agent/paper2repro/scripts/test_compare_figure.py
```

```bash
python3 tests/skill-regression/test_score.py
```

```bash
python3 tests/skill-regression/test_session_log.py
```

The regression workflow needs the repository secret `ANTHROPIC_API_KEY` and costs API credits. Manual dispatch takes `model` and `max_budget_usd` inputs. The score, a session log (conversation, tool calls, tokens and cost) and the project go to the job summary and the run artifact. See [tests/skill-regression/README.md](tests/skill-regression/README.md) for how the skill is blinded, the pass conditions and how to add a case.

<a id="built-on-paper2agent"></a>

## 🧩 Built on Paper2Agent

Paper2Repro is built on [Paper2Agent](https://github.com/jmiao24/Paper2Agent), a multi-agent system that turns research papers into agent-readable paper skills and tested MCP servers. This repository keeps Paper2Agent's components in `skills/paper2agent/` because Paper2Repro uses them:

- [Paper2Skill](skills/paper2agent/paper2skill/SKILL.md) converts the paper and supplement into a paper skill. Paper2Repro reads methods, captions and figures from it.
- [Paper2MCP](skills/paper2agent/paper2mcp/SKILL.md) converts a code repository into tested MCP tools, if you also want those.

For Paper2Agent demos, hosted MCP servers and MCP connection instructions, see the [Paper2Agent repository](https://github.com/jmiao24/Paper2Agent). If you use Paper2Agent, cite:

```
@article{miao2026paper2agent,
  title={Reimagining research papers as interactive and reliable {AI} agents},
  author={Miao, Jiacheng and Davis, Joe R. and Zhang, Yaohui and Pritchard, Jonathan K. and Zou, James},
  journal={Nature},
  year={2026},
  doi={10.1038/s41586-026-11044-y},
  url={https://www.nature.com/articles/s41586-026-11044-y}
}
```

## 👥 Maintainers

Paper2Repro is maintained by the Jeong Lab at Baylor College of Medicine. Report problems in [GitHub issues](https://github.com/jeonglab-bcm/Paper2Repro/issues).

## 📄 License

MIT. See [LICENSE](LICENSE).
