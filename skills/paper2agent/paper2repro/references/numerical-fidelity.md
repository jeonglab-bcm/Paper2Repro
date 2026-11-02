# Numerical fidelity

Reproduce the published numbers, not numbers that look similar. Rounding-level figures need the same parameters and the same arithmetic.

## Identify the exact parameters

1. Calibrate each axis from its major gridlines (linear fit from pixel to value) and the panel edges.
2. ggplot2 expands a continuous axis by 5% on each side. Remove the expansion to get the data minimum and maximum.
3. Trace the published curve per pixel column (darkest pixels inside the panel).
4. Generate candidate grids: `seq(a, b, length.out = n)`, `seq(a, b, by = s)`, integer multiples. Compute the series on each.
5. Accept a grid only when it reproduces the data extremes to the printed precision and the positions of the largest spikes. Example: `seq(1e-11, 1e-10, length.out = 300)` reproduced minimum −4.73e-4, maximum 3.82e-4 and the spike pixels of the published figure.

## Arithmetic environment

Results at rounding level depend on the platform:

- **FMA contraction.** Compilers on arm64 fuse `a*b + c` into one rounding. x86-64 builds from 2013 did not. On Apple Silicon, R's `lgammafn` (`(x - 0.5)*log(x) - x + ...`) changed 221 of 300 points of a published curve.
- **Extended accumulation.** R's `sum()` accumulates in `long double`: 80-bit on x86 Linux, 64-bit on Apple Silicon. Emulate it with a 64-bit-mantissa accumulator (for example, `mpmath` with `prec = 64`, rounding after each addition).
- **Emulators.** Rosetta 2 runs x86_64 binaries, but it may not reproduce x87 80-bit results. Do not treat Rosetta output as the original platform. Code that uses x87 can also run much slower there.
- **Math libraries.** `log` and `lgamma` can differ in the last bit between libraries. Check when a series still differs after the points above.

Validate an emulation on the original architecture. GitHub `ubuntu-24.04` runners are x86_64. In the worked example, R on x86_64 matched the emulation at 300 of 300 points.

## Error units

- If published errors are whole multiples of the unit in the last place, the reference was rounded to double before the subtraction. Compute `error = value − double(exact)`.
- Use an independent high-precision reference (for example, `mpmath` with 50 or more digits). Use exact decimal parameters only if the paper did.

## When the code is not available

- If the paper names a package for a comparison method ("the method in VGAM"), get the cited version's source from the archive. If you write your own version, say so and report the agreement count (for example, 26 of 50 marks).
- For binary-only supplements, call the compiled library through a small C driver. Difference-test it against a reimplementation and an exact reference. Keep decompiled code local; it falls under the library's license.
- Commit the outputs you computed with tools you cannot redistribute, and mark them as such.
