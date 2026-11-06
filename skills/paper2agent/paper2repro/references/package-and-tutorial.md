# Package and tutorial

A reproduction shows that the method came back. The package lets a reader use it on their own data. Each paper with a reusable method gets one installable package, in Python or R, that holds that method, its example data, tests and an executed tutorial. `scripts/check_package.py` checks a Python package from a fresh install; an R package follows the [R steps](#check-an-r-package) until the R checker exists.

## When

- Make a package when the paper has a method a reader would apply to new data: an algorithm, an estimator, a model fit, a transform, a score.
- Skip it when the results are only data displays or descriptive statistics. Record the `package` item as `not_attempted` with cause `not_a_result` and say why.
- Start it when the method first runs (Phase 3 or 4), not at the end. Put the method in the package and have the pipeline call it. Keep one copy of the method: the reproduction is then the package's acceptance test, and the package cannot drift from what was checked against the paper.

## Language

The package is in Python or R. The person can choose in the kickoff prompt (`Package language: python` or `r`). One shot means not asking later: if the kickoff does not say, apply the default rule and record the choice and the reason in the package README and the pull request.

**Default:** R when the method relies on R or Bioconductor packages (DESeq2, limma, edgeR) or the authors' code is R. Python otherwise. A Python port of a method built on R libraries means re-implementing them or swapping in look-alikes that do not give the same numbers, and the method's users work in R.

The package never ships the authors' source: depend on their released package, or port. Never commit the authors' code ([publishing.md](publishing.md)).

| Authors' code | Package | How | Port checked against |
| --- | --- | --- | --- |
| Python, installable | Python | Depend on the authors' release; the package adds the API, example data and tutorial. | Not needed (`source: authors_code`). |
| Python, not installable | Python | Port. | The authors' code. |
| R, including CRAN or Bioconductor packages | R | Depend on the CRAN or Bioconductor packages the method uses; rewrite the authors' own scripts as package functions. | The authors' scripts. |
| R with Rcpp, C, C++, Fortran | By the default rule | Port the compiled part. An R package may use its own Rcpp code and a Python package NumPy or Numba for speed, written from the method, not copied. | The authors' build (free compilers). |
| Julia, Java, other free languages | Python, unless the person chose R | Port. | The original, on its free runtime (Julia, OpenJDK). |
| MATLAB | By the default rule | Port. | The original under Octave when it runs there; otherwise as for proprietary code. |
| SAS, Stata, other proprietary languages | By the default rule | Port. | The paper only. |
| None (method from the paper's text) | By the default rule | Implement from the text (`source: reconstructed`). | The paper. |

**When the original cannot be run** (proprietary software, no Octave-compatible code): check the port against the paper's printed values and figures only. Record the `port` item as `not_attempted` with cause `proprietary_software`, and say in the package README that the port was checked against the paper, not against the original code. That is still a package; it is not a reason to stop and ask.

## Layout

### Python

Start from [assets/package-template](../assets/package-template). Copy it to `<id>/package/`, rename `example_method` and `example-method` everywhere, then replace the method, the data, the tests and the tutorial text.

```text
<id>/package/
├── pyproject.toml                 name, version, licence, requires-python, dependencies, console script
├── README.md                      install command, quick start, citation, licence, link to the reproduction
├── LICENSE
├── scripts/make_example_data.py   when the example data are synthetic
├── src/<name>/
│   ├── __init__.py                public API, __version__, citation, example_path()
│   ├── core.py                    the method
│   ├── cli.py, __main__.py        the command line (`<name>` and `python -m <name>`)
│   └── data/
│       ├── README.md              what each file is, where it comes from, its licence
│       ├── <example input>
│       └── <expected output>
├── tests/test_<name>.py
└── tutorial/
    ├── tutorial.ipynb             executed, outputs saved by check_package.py --write
    ├── TUTORIAL.md                generated from the notebook; do not edit
    └── TUTORIAL_files/            images from the notebook, when it has plots
```

Install: `pip install "git+https://github.com/<owner>/<repo>#subdirectory=<id>/package"`.

### R

There is no R template yet. Follow the layout of a standard R package:

```text
<id>/package/
├── DESCRIPTION                    Package, Title, Version, License, Imports with tested minimum versions;
│                                  biocViews: when it depends on Bioconductor packages
├── NAMESPACE
├── README.md                      install command, quick start, citation, licence, link to the reproduction
├── LICENSE or LICENSE.md
├── R/                             the method, example_path()
├── src/                           your own Rcpp code, only when the port needs it
├── inst/extdata/                  example input, expected output, README.md (provenance, licence)
├── tests/testthat/
├── vignettes/tutorial.Rmd         the tutorial; R CMD build runs it
└── tutorial/                      TUTORIAL.md and its figures, rendered from the vignette; do not edit
```

Install: `remotes::install_github("<owner>/<repo>/<id>/package")` or `pak::pak("<owner>/<repo>/<id>/package")`. Both take the `owner/repo/subdir` form. With a `biocViews:` field in DESCRIPTION, remotes treats the package as a Bioconductor package and installs its Bioconductor dependencies.

## Name, licence and citation

- Name the package after the method (for example `peakfit`), not after the paper ID. Check that the name is not already a well-known PyPI, CRAN or Bioconductor package. R package names use only letters, numbers and dots.
- Method implemented from the paper's text: use the repository's licence.
- Method ported from the authors' code: use that code's licence. A port of GPL-2 code is GPL-2.
- Authors' code without a licence: do not port it. Implement the method from the paper's text, or ask the user.
- Cite the paper in the package README, the package documentation (`__init__` docstring, or the package help page in R) and the tutorial's first section.

## Code

- Public API: functions that take plain inputs (numbers, arrays, data frames, file paths) and return plain results. Read and write helpers for the file formats the tutorial uses.
- Python: a console script in `[project.scripts]` that reads an input file and writes CSV or JSON, with `--help` and `--version`; `python -m <name>` runs the same entry point. R: exported functions are enough; a command line is optional (`Rscript -e`).
- `example_path(name)` returns a bundled data file (`importlib.resources` in Python, `system.file("extdata", name, package = ...)` in R).
- Dependencies: compatible ranges with the tested versions as floors (`numpy>=2.1,<3`; `limma (>= 3.60)` in DESCRIPTION). Exact pins stay in the pipeline (`requirements.txt`, R package versions). Use as few dependencies as the method allows.
- No hard-coded paths, no network access, no writes outside the paths the caller gives.

## Example data

- Small: 1 MB in total at most (`--max-data-kb` changes the limit for Python). Enough to show the method, not to reproduce the paper.
- A subset of the paper's data only when its licence allows redistribution. Copy the licence and attribution into the data README. Otherwise generate synthetic data with a committed script and describe it.
- The expected output is evidence, not a snapshot. Take it from a source other than the package: the paper's printed values for that subset, the authors' original code, or the formula that generated synthetic data. Say which in the data README, with the tolerance to compare at. A package that writes its own expected output tests nothing.

## Tests

- Test the installed package with its bundled data only. Python tests run from a copy outside the source tree; do not change `sys.path`. R tests use `testthat` and `example_path()`.
- At least: the example input gives the expected output within the stated tolerance; the command line (Python) gives the same result as the API; one edge case (too little data, invalid input raises a clear error).

## Tutorial

Python: `tutorial/tutorial.ipynb`. R: `vignettes/tutorial.Rmd`. In this order:

1. What the method does, in two or three sentences, and the citation.
2. **Install**: the exact command, shown and not run (a markdown block in the notebook, an `eval = FALSE` chunk in the vignette), then load the package and print its version.
3. **Example input**: load the bundled file and show it (size, columns, first rows).
4. **Run the method** through the API and show the output as a table or a plot.
5. **Compare with the expected output**: print the agreement count ("4 of 4 wells match the expected output") and fail if it is short (`assert` in Python, `stopifnot()` in R).
6. **Command line** (Python): the same run with `!<name> "{path}" ...`.
7. **Your own data**: the input format (columns, units), the options that matter, and what each output column means.
8. A link to the reproduction (results page and pipeline) for the paper's full data.

Rules:

- Never type outputs. Python: run `check_package.py <id>/package --write`, which executes the notebook in a fresh install, saves the outputs and generates `TUTORIAL.md`. Without `--write`, a mismatch between a fresh run and the saved outputs fails the check. R: `R CMD build` runs the vignette, and `TUTORIAL.md` is rendered from it (see below).
- Keep outputs reproducible: no absolute paths, timestamps, object addresses or unseeded random numbers. Python numbers are compared with a relative tolerance of 1e-9. Tag a notebook cell `nondeterministic` only when that cannot be avoided (a timing, for example) and say why in the cell.
- Plots render headless and go into the tutorial's figure folder. Python images are compared by count, not by pixels.

## Check a Python package

```bash
python3 scripts/check_package.py <id>/package --write              # after any change to the method, data or tutorial
python3 scripts/check_package.py <id>/package --json package.json  # in the pipeline and CI
python3 scripts/check_package.py <id>/package --layout-only        # offline: layout, notebook, TUTORIAL.md
```

It checks the layout and metadata, builds a wheel from a copy of the folder, installs it into a fresh virtual environment whose path contains a space, imports the package from that environment, runs each console script with `--help`, runs the tests from a copy outside the source tree, executes the tutorial and compares its outputs with the saved ones, and checks that `TUTORIAL.md` is the notebook rendered. It uses uv when it is on `PATH`, otherwise venv and pip, and needs network access to install dependencies. On an R package it stops with exit code 2 and points here.

## Check an R package

Until the R checker exists, the pipeline's `PACKAGE` step runs these from the repository root, in a fresh library (`R_LIBS_USER` set to an empty folder):

1. `R CMD build <id>/package`: builds the tarball and runs the vignette.
2. `R CMD check --no-manual <name>_<version>.tar.gz`: installs it, runs the tests and rebuilds the vignette. Any ERROR or WARNING fails the step.
3. `Rscript -e 'rmarkdown::render("<id>/package/vignettes/tutorial.Rmd", output_format = rmarkdown::github_document(html_preview = FALSE), output_file = "TUTORIAL.md", output_dir = "<id>/package/tutorial")'`, then `git diff --exit-code <id>/package/tutorial` (a changed tutorial fails the step: commit the new rendering).

Write the outcome as the `package` item: `check.passed` from the three steps, `check.detail` with the test count and the `R CMD check` status line.

## In results.json

Add one item for the package. The pipeline's `RESULTS` step fills `check` from the Python report or the R steps:

```json
{
  "id": "package",
  "label": "Python package <name> and its tutorial",
  "kind": "code_check",
  "source": "port",
  "method": "check",
  "check": {"passed": true, "detail": "<the report's detail line>"},
  "outputs": ["package/tutorial/TUTORIAL.md"]
}
```

Use `source: "port"` for a port of the authors' code, `reconstructed` for a method implemented from the paper's text, and `authors_code` for a package that depends on the authors' released Python or R package.
