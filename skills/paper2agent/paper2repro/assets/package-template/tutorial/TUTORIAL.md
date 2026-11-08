<!-- Generated from tutorial.ipynb by check_package.py --write. Do not edit by hand. -->

# example-method tutorial

`example-method` estimates the doubling time of each well from OD600 growth curves. It keeps the readings inside an OD window (the exponential phase), fits log(OD) against time, and reports the growth rate, the doubling time and the R² of the fit.

This is the Paper2Repro package template. In a real package, cite the paper here:

> <Authors>. <Title>. *<Journal>* <volume>:<pages> (<year>). doi:<doi>

## 1. Install

Install the package from its folder in the repository:

```bash
pip install "git+https://github.com/<owner>/<repo>#subdirectory=<paper-id>/package"
```

Or with uv:

```bash
uv pip install "git+https://github.com/<owner>/<repo>#subdirectory=<paper-id>/package"
```

It needs Python 3.10 or later. This notebook was run in a fresh environment with the package installed from its wheel. Check the version:

```python
import example_method as em

print("example-method", em.__version__)
```

```text
example-method 0.1.0
```

## 2. The example input

The package ships a small example: OD600 every 0.5 h from 0 to 10 h for three growing wells (A1, A2, A3) and a blank well (B1). `em.example_path()` returns its location. The data are synthetic; `data/README.md` says how they were made.

```python
path = em.example_path("growth_curves.csv")
lines = path.read_text().splitlines()
print(len(lines) - 1, "readings; columns:", lines[0])
print("\n".join(lines[1:6]))
```

```text
84 readings; columns: well,time_h,od600
A1,0.0,0.01
A1,0.5,0.014142135623730952
A1,1.0,0.02
A1,1.5,0.028284271247461905
A1,2.0,0.04
```

## 3. Run the method

`read_curves` reads the CSV into one series per well. `doubling_times` fits each well. The window sets which readings count as exponential growth.

```python
curves = em.read_curves(path)
results = em.doubling_times(curves, window=(0.05, 0.5))


def show(value, spec):
    return "n/a" if value is None else format(value, spec)


print(f"{'well':<5}{'points':>7}{'rate (1/h)':>12}{'doubling (h)':>14}{'R2':>10}")
for r in results:
    print(
        f"{r['well']:<5}{r['n_points']:>7}{show(r['growth_rate_per_h'], '.4f'):>12}"
        f"{show(r['doubling_time_h'], '.4f'):>14}{show(r['r_squared'], '.6f'):>10}"
    )
```

```text
well  points  rate (1/h)  doubling (h)        R2
A1         7      0.6931        1.0000  1.000000
A2        10      0.4621        1.5000  1.000000
A3        11      0.3466        2.0000  1.000000
B1         0         n/a           n/a       n/a
```

B1 has no estimate: none of its readings lie inside the window.

## 4. Compare with the expected output

The expected output ships with the package. It comes from the formula that generated the input, not from this package, so a match is a real check.

```python
import math

expected = em.read_results(em.example_path("growth_curves_expected.csv"))


def same(a, b):
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


keys = ("growth_rate_per_h", "doubling_time_h", "r_squared")
matches = sum(
    o["well"] == e["well"] and o["n_points"] == e["n_points"] and all(same(o[k], e[k]) for k in keys)
    for o, e in zip(results, expected)
)
print(f"{matches} of {len(expected)} wells match the expected output")
assert matches == len(expected)
```

```text
4 of 4 wells match the expected output
```

## 5. From the command line

The same method runs as `example-method`. Without `-o` it writes the CSV to standard output.

```python
!example-method "{path}" --window 0.05 0.5
```

```text
well,n_points,growth_rate_per_h,doubling_time_h,r_squared
A1,7,0.6931471805599453,1.0,0.9999999999999999
A2,10,0.46209812037329684,1.5,0.9999999999999997
A3,11,0.34657359027997264,2.0,1.0
B1,0,,,
```

## 6. Your own data

- **Input:** a CSV with columns `well`, `time_h` and `od600`, one row per reading. Other columns are ignored.
- **Window:** `window=(low, high)` in Python or `--window LOW HIGH` on the command line. Choose the OD range where your curves grow exponentially.
- **Output:** one row per well with `n_points` (readings inside the window), `growth_rate_per_h`, `doubling_time_h` and `r_squared`. Empty values mean no estimate: fewer than three readings in the window, or no growth.

```bash
example-method my_plate.csv --window 0.05 0.5 -o doubling_times.csv
```

To see the method on the paper's own data, with the comparison against the published figures, open the reproduction: `<link to the paper folder>`.
