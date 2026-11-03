# Pipeline and CI

The pipeline is the reproduction; everything committed under `output/` must be what it writes. CI reruns it on every pull request, so it has to be fast, pinned and self-checking.

## Nextflow layout

One `main.nf` per paper, run from the repository root:

| Process | Does |
| --- | --- |
| `FETCH` | `pipeline/fetch_inputs.sh [DIR]`: download every input, check SHA-256, unpack. `--sources DIR` reuses local copies. |
| `RUN` / `PORT` | The authors' code or the port, on the paper's data. |
| `PORT_CHECK` (optional flag) | The port against the original runtime (`--octave` in PMC1847688). |
| `COMPARE`, `TABLES` | Renders, overlays, scores, controls, table values. |
| `RESULTS` | Merge the scores with the hand-written notes into `results.json`; run `check_results.py --write`. |
| `CHECK` | `check_results.py` must pass; `compare_runs.py` against the committed `output/` must find no difference; write `report.md`. |
| `BUILD_PAGE` | The results page from `results.json` and the published figures. |

Keep `process.errorStrategy = 'terminate'` and `stageInMode = 'copy'` (scripts write to their working folder and must not touch the repository through symlinks).

## Downloads

- Script every download and check its SHA-256. Record the URL and hash in `results.json` too.
- Use sources that accept scripted downloads, with a fallback: Springer/BMC `media.springernature.com/original/...` files; PMC's open-access copy on AWS (`https://pmc-oa-opendata.s3.amazonaws.com/<PMCID>.<version>/<file>`); Europe PMC (`https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/supplementaryFiles`, a zip of all supplements). PLOS refuses scripted downloads; Europe PMC has returned HTTP 500 to CI runners. Retry with `curl --retry 3`.
- If an archive is damaged (a failed CRC), say which file and line, and handle it in code, as PMC1847688 does for one line of `SOL_calib_08e.txt`.

## Pinning

Pin what the scores depend on: `requirements.txt` with `==` versions installed by the workflow; R packages by version or archive URL; the runtime versions (Python, R, Octave, Java, Nextflow) in the workflow and in `results.json`. The PNGs embedded in PMC1847688's committed results page already differ in bytes from a rerun's, though not in pixels; that is why `compare_runs.py` compares decoded pixels. Numeric libraries can move the scores themselves.

## The check step

`check_reproduction.py` (or equivalent) should fail the run when:

- a pass mark is breached (`check_results.py` exits 1);
- the fresh run differs from the committed outputs (`compare_runs.py <fresh> <id>/figure-reproduction/output`, with `--ignore` only for files that cannot be reproduced bit for bit, each named in the README);
- an expected output is missing.

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
    paths: ["<PMCID>/figure-reproduction/**", ".github/workflows/reproduce-<pmcid>.yml"]
  push:
    branches: [main]
    paths: ["<PMCID>/figure-reproduction/**", ".github/workflows/reproduce-<pmcid>.yml"]
permissions:
  contents: read
jobs:
  reproduce:
    runs-on: ubuntu-24.04
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -r <PMCID>/figure-reproduction/requirements.txt
      - uses: actions/setup-java@v4
        with: {distribution: temurin, java-version: "21"}
      - uses: nf-core/setup-nextflow@v2
        with: {version: "26.04.3"}
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
