# Package and tutorial

A reproduction shows that the method came back. The package lets a reader use it on their own data. Each paper with a reusable method gets one pip-installable Python package that holds that method, its example data, tests and an executed tutorial. `scripts/check_package.py` checks all of it from a fresh install.

## When

- Make a package when the paper has a method a reader would apply to new data: an algorithm, an estimator, a model fit, a transform, a score.
- Skip it when the results are only data displays or descriptive statistics. Record the `package` item as `not_attempted` with cause `not_a_result` and say why.
- Start it when the method first runs (Phase 3 or 4), not at the end. Put the method in the package and have the pipeline import it. Keep one copy of the method: the reproduction is then the package's acceptance test, and the package cannot drift from what was checked against the paper.
- If the method is the authors' R, MATLAB or C code, the package is a Python port. The `port` check in `results.json` must show the port equal to the original on the paper's data.
- If the authors' code is Python and installable, the package depends on its release and adds the API, the example data and the tutorial. Do not copy the authors' code into the repository ([publishing.md](publishing.md)).

## Layout

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

## Name, licence and citation

- Name the distribution and the import package after the method (for example `peakfit`, import `peakfit`), not after the paper ID. Check that the name is not already a well-known PyPI package.
- Method implemented from the paper's text: use the repository's licence.
- Method ported from the authors' code: use that code's licence. A port of GPL-2 code is GPL-2.
- Authors' code without a licence: do not port it. Implement the method from the paper's text, or ask the user.
- Cite the paper in the package README, the `__init__` docstring and the tutorial's first cell.

## Code

- Public API: functions that take plain inputs (numbers, arrays, data frames, file paths) and return plain results. Read and write helpers for the file formats the tutorial uses.
- Command line: a console script in `[project.scripts]` that reads an input file and writes CSV or JSON, with `--help` and `--version`. `python -m <name>` runs the same entry point.
- `example_path(name)` returns a bundled data file through `importlib.resources`.
- Dependencies: compatible ranges with the tested versions as floors (`numpy>=2.1,<3`). Exact pins stay in the pipeline's `requirements.txt`. Use as few dependencies as the method allows.
- No hard-coded paths, no network access, no writes outside the paths the caller gives.

## Example data

- Small: 1 MB in total at most (`--max-data-kb` changes the limit). Enough to show the method, not to reproduce the paper.
- A subset of the paper's data only when its licence allows redistribution. Copy the licence and attribution into `data/README.md`. Otherwise generate synthetic data with a committed script and describe it.
- The expected output is evidence, not a snapshot. Take it from a source other than the package: the paper's printed values for that subset, the authors' original code, or the formula that generated synthetic data. Say which in `data/README.md`, with the tolerance to compare at. A package that writes its own expected output tests nothing.

## Tests

- Test the installed package with its bundled data only. `check_package.py` runs the tests from a copy outside the source tree; do not change `sys.path`.
- At least: the example input gives the expected output within the stated tolerance; the command line gives the same result as the API; one edge case (too little data, invalid input raises a clear error).

## Tutorial

`tutorial/tutorial.ipynb`, in this order:

1. What the method does, in two or three sentences, and the citation.
2. **Install**: the exact command as a markdown code block (not run):
   `pip install "git+https://github.com/<owner>/<repo>#subdirectory=<id>/package"`, and the `uv pip install` form. Then a code cell that imports the package and prints its version.
3. **Example input**: load the bundled file and show it (size, columns, first rows).
4. **Run the method** through the Python API and show the output as a table or a plot.
5. **Compare with the expected output**: print the agreement count ("4 of 4 wells match the expected output") and `assert` it.
6. **Command line**: the same run with `!<name> "{path}" ...`.
7. **Your own data**: the input format (columns, units), the options that matter, and what each output column means.
8. A link to the reproduction (results page and pipeline) for the paper's full data.

Rules:

- Never type outputs. Run `check_package.py <id>/package --write`: it executes the notebook in a fresh install, saves the outputs and generates `TUTORIAL.md`. Without `--write`, a mismatch between a fresh run and the saved outputs fails the check.
- Keep outputs reproducible: no absolute paths, timestamps, object addresses or unseeded random numbers. Numbers are compared with a relative tolerance of 1e-9. Tag a cell `nondeterministic` only when that cannot be avoided (a timing, for example) and say why in the cell.
- Plots render headless (`MPLBACKEND=Agg`) and go into `TUTORIAL_files/`. Images are compared by count, not by pixels.

## Check

```bash
python3 scripts/check_package.py <id>/package --write              # after any change to the method, data or tutorial
python3 scripts/check_package.py <id>/package --json package.json  # in the pipeline and CI
python3 scripts/check_package.py <id>/package --layout-only        # offline: layout, notebook, TUTORIAL.md
```

It checks the layout and metadata, builds a wheel from a copy of the folder, installs it into a fresh virtual environment whose path contains a space, imports the package from that environment, runs each console script with `--help`, runs the tests from a copy outside the source tree, executes the tutorial and compares its outputs with the saved ones, and checks that `TUTORIAL.md` is the notebook rendered. It uses uv when it is on `PATH`, otherwise venv and pip, and needs network access to install dependencies.

## In results.json

Add one item for the package. The pipeline's `RESULTS` step fills `check` from the report:

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

Use `source: "port"` for a port of the authors' code, `reconstructed` for a method implemented from the paper's text, and `authors_code` for a thin Python interface to the authors' Python code.
