# Pipeline and CI

The pipeline is the reproduction; everything committed under `output/` must be what it writes. CI reruns it on every pull request, so it has to be fast, pinned and self-checking.

## Nextflow layout

One `main.nf` per paper, run from the repository root:

| Process | Does |
| --- | --- |
| `FETCH` | `pipeline/fetch_inputs.sh [DIR]`: download every input, check SHA-256, unpack. `--sources DIR` reuses local copies. |
| `RUN` / `PORT` | The authors' code or the port, on the paper's data. The method comes from the installed Python or R package `<id>/package` ([package-and-tutorial.md](package-and-tutorial.md)). |
| `PORT_CHECK` (optional flag) | The port against the original runtime (`--octave` in PMC1847688). |
| `COMPARE`, `TABLES` | Renders, overlays, scores, controls, table values. |
| `PACKAGE` | Python: `check_package.py <id>/package --json package.json` (wheel, fresh install, tests, tutorial rerun). R: `R CMD build`, `R CMD check --no-manual`, tutorial render ([R steps](package-and-tutorial.md#check-an-r-package)). |
| `RESULTS` | Merge the scores, the package report and the hand-written notes into `results.json`; run `check_results.py --write`. |
| `CHECK` | `check_results.py` must pass; `compare_runs.py` against the committed `output/` must find no difference; write `report.md`. |
| `BUILD_PAGE` | The results page from `results.json` and the published figures. |

Keep `process.errorStrategy = 'terminate'` and `stageInMode = 'copy'` (scripts write to their working folder and must not touch the repository through symlinks).

## Downloads

- Script every download and check its SHA-256. Record the URL and hash in `results.json` too.
- Use sources that accept scripted downloads, with a fallback: Springer/BMC `media.springernature.com/original/...` files; PMC's open-access copy on AWS (`https://pmc-oa-opendata.s3.amazonaws.com/<PMCID>.<version>/<file>`); Europe PMC (`https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/supplementaryFiles`, a zip of all supplements). PLOS refuses scripted downloads; Europe PMC has returned HTTP 500 to CI runners. Retry with `curl --retry 3`.
- If an archive is damaged (a failed CRC), say which file and line, and handle it in code, as PMC1847688 does for one line of `SOL_calib_08e.txt`.

## The CI image

In fossil, a reproduction runs, and is checked, in the repository's pinned CI image: built from fossil's `Dockerfile`, published to GHCR and named in the workflow **by digest** (`<image>@sha256:<digest>`), never by a tag that can move. The image holds what changes numbers from one runner to the next and that no `requirements.txt` pins: the OpenBLAS build and its CPU kernel, fonts, the locale, R with a dated CRAN snapshot, Java and Nextflow 26. Copy the `container:` line, digest included, from the newest `reproduce-*.yml` on fossil's `main`.

- **A fix to the environment goes into the image, not into the paper.** When a run needs a kernel setting, a font, a locale, a system library or a CRAN package, open a pull request on fossil's `Dockerfile`, and use the new digest once it is built. Do not set it only in the paper's workflow or `nextflow.config`. In fossil #37 (PMC2850872) the reproduce job passed on some runners and failed on others, because OpenBLAS picks its kernel by CPU; the fix, `OPENBLAS_CORETYPE=Haswell`, went into that paper's `nextflow.config`. It has since been copied by hand into the configs of PMC2711306 (#38), PMC522806 and PMC4079617, and a paper that misses it passes or fails by runner.
- Python packages are still installed from the paper's `requirements.txt`, pinned with `==`; the image holds the runtimes and system libraries beneath them.
- Record the image digest in the README's Run section, next to the runtime versions.
- Until fossil's image exists (fossil #133), use the setup actions in the template below, pin each runtime version, and switch to the image when it lands.

## Pinning

Pin what the scores depend on: `requirements.txt` with `==` versions installed by the workflow; R packages by version or archive URL; the runtime versions (Python, R, Octave, Java, Nextflow) in the workflow and in `results.json`. The PNGs embedded in PMC1847688's committed results page already differ in bytes from a rerun's, though not in pixels; that is why `compare_runs.py` compares decoded pixels. Numeric libraries can move the scores themselves.

## The check step

`check_reproduction.py` (or equivalent) should fail the run when:

- a pass mark is breached (`check_results.py` exits 1);
- a figure of ours is not on the published frame, or its `layout` is missing (`check_results.py` exits 1; `compare_figure.py --require-frame` says so where the figure is drawn);
- the fresh run differs from the committed outputs (`compare_runs.py <fresh> <id>/figure-reproduction/output`, with `--ignore` only for files that cannot be reproduced bit for bit, each named in the README);
- an expected output is missing;
- the package check fails (`check_package.py` exits 1, or an R step fails).

Print `report.md` with the `check_results.py --markdown` table and the `compare_runs.py` table, and send it to the job summary.

## CI time budget

- The pull-request workflow should finish in about 30 minutes on a standard GitHub runner. Measure the pipeline on a known machine, scale by cores, and keep the slow parts out of the pull-request run.
- Put expensive steps (refits from thousands of starts, genetic-algorithm reruns, long parameter searches) behind a `workflow_dispatch` input or a schedule, as PMC4247685's `rerun_ga` input does. PMC4081021's pull-request workflow ran `--refit` (2,000 starts for each of 24 models) and was cancelled twice at its 120-minute limit.
- Set `timeout-minutes` to about twice the measured time, so a hang fails fast.
- Before pushing, run the workflow's exact command from a clean checkout (or a fresh clone in a scratch folder). Anything that only works with files left over from development will fail in CI.

## Workflow template

```yaml
name: Reproduce <PMCID>
on:
  workflow_dispatch:
    inputs:
      full:
        description: "Also run the slow steps"
        type: boolean
        default: false
  pull_request:
    paths: ["<PMCID>/figure-reproduction/**", "<PMCID>/package/**", ".github/workflows/reproduce-<pmcid>.yml"]
  push:
    branches: [main]
    paths: ["<PMCID>/figure-reproduction/**", "<PMCID>/package/**", ".github/workflows/reproduce-<pmcid>.yml"]
permissions:
  contents: read
jobs:
  reproduce:
    runs-on: ubuntu-24.04
    container: <fossil CI image>@sha256:<digest>  # copied from the newest reproduce-*.yml on main
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r <PMCID>/figure-reproduction/requirements.txt ./<PMCID>/package
      # R package instead: drop ./<PMCID>/package above and install it with pak in the image's R.
      # Before the image exists (fossil #133): no container line; add actions/setup-python@v5 (3.12),
      # astral-sh/setup-uv@v6, actions/setup-java@v4 (temurin 21), nf-core/setup-nextflow@v2 (26.04.3),
      # and for R r-lib/actions/setup-r@v2 and setup-r-dependencies@v2 (extra-packages: any::rcmdcheck).
      - run: nextflow run <PMCID>/figure-reproduction/main.nf --outdir results -ansi-log false ${{ inputs.full && '--full' || '' }}
      - if: always()
        run: cat results/report.md >> "$GITHUB_STEP_SUMMARY" || echo "No report." >> "$GITHUB_STEP_SUMMARY"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: <pmcid>-reproduction
          path: |
            results
            .nextflow.log
          include-hidden-files: true
```
