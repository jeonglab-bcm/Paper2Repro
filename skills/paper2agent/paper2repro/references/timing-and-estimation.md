# Timing figures and estimates

## Timing figures

- Absolute times depend on the hardware and the implementation. Re-measure with the paper's protocol, for example 100 evaluations per box with R's `microbenchmark`.
- Do not time x86_64 binaries under an emulator. In the worked example, Rosetta added about 80 µs to each call of the authors' library.
- To place your times on the paper's axis, divide each method by one constant. Fit it by least squares on log10 medians that you read from the published boxes. Keep the measured version and state the constants.
- Read the per-size ratios, not only the constant. A constant ratio means the growth with problem size matches the paper (mesh: 13.2–13.3× at every n). A changing ratio means it does not (VGAM: 4× to 77×). Report both.
- Run timing tasks alone. Workflow engines start independent tasks at the same time. Record the CPU model.

## Estimates in tables

- Use analytic gradients for maximum likelihood on large data. On a log-likelihood near −10⁶, finite differences are noisy. In the worked example, one finite-difference run stopped after 22 evaluations at its start value, and another took about 20 minutes per data set.
- Fit from several start values. Cross-check the optimum with a second formula of the likelihood, and scan the parameter around the optimum.
- Compare at the published precision (round to the printed digits). Report the full precision next to it.
