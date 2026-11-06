# Example data

| File | What it is |
| --- | --- |
| `growth_curves.csv` | Example input: OD600 every 0.5 h from 0 to 10 h for wells A1, A2, A3 and a blank well B1. Columns `well`, `time_h`, `od600`. |
| `growth_curves_expected.csv` | Expected output for that input with the default window 0.05 to 0.5. Columns `well`, `n_points`, `growth_rate_per_h`, `doubling_time_h`, `r_squared`; empty cells mean no estimate. |

## Where it comes from

- Input: synthetic, written by `scripts/make_example_data.py`. OD = 0.01 × 2^(t / d), capped at 0.9, with doubling times d of 1.0, 1.5 and 2.0 h. B1 stays at 0.02, below the window.
- Expected output: from the same formula, not from this package. The growth rate is ln(2) / d, the doubling time is d and R² is 1. `n_points` counts the time points whose OD lies inside the window.
- Licence: synthetic data, released with the package under its licence.

Compare with a relative tolerance of 1e-9: the fit takes logarithms of rounded values.
