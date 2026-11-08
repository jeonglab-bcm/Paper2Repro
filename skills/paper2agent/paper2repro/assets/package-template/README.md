# example-method

Doubling time of each well from OD600 growth curves. This is the Paper2Repro package template: replace the method, the data, the tests and the tutorial, and keep the structure.

The method comes from:

> <Authors>. <Title>. *<Journal>* <volume>:<pages> (<year>). doi:<doi>

Its reproduction (pipeline, results and comparison with the published figures) is at `<link to the paper folder>`.

## Install

```bash
pip install "git+https://github.com/<owner>/<repo>#subdirectory=<paper-id>/package"
```

Or with uv:

```bash
uv pip install "git+https://github.com/<owner>/<repo>#subdirectory=<paper-id>/package"
```

Python 3.10 or later. No other dependencies.

## Use

```python
import example_method as em

curves = em.read_curves(em.example_path("growth_curves.csv"))  # the bundled example input
for row in em.doubling_times(curves, window=(0.05, 0.5)):
    print(row["well"], row["doubling_time_h"])
```

From the command line:

```bash
example-method "$(example-method --example-path)" -o doubling_times.csv
```

The [tutorial](tutorial/TUTORIAL.md) installs the package, runs it on the bundled example input, compares the result with the expected output, and explains the input and output formats.

## Input and output

- Input: CSV with columns `well`, `time_h` and `od600`, one row per reading.
- Output: CSV with columns `well`, `n_points` (readings inside the window), `growth_rate_per_h`, `doubling_time_h` and `r_squared`. Empty cells mean no estimate: fewer than three readings in the window, or no growth.

## Licence

MIT. See [LICENSE](LICENSE). The example data are described in [data/README.md](src/example_method/data/README.md).
