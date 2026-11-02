# Current software

Build every reproduction with current, maintained software. Treat outdated software as a specification of the method. Do not run it.

## List the software

List every program, package, language runtime and workflow tool that the paper, its supplement and its code use. For each one, record:

- the version that the paper used, if it is stated;
- the latest stable release and its date, from the official registry or release page (PyPI, CRAN, Bioconductor, crates.io, GitHub releases). Check the registry; do not rely on memory;
- the status, **current** or **outdated**, and the reason.

## Outdated software

A tool is outdated when one or more of these conditions is true:

- Upstream marks it as archived, deprecated, discontinued or end-of-life, or its package index removed it (for example, an archived CRAN package).
- It has no stable release in the last three years.
- It runs only on an end-of-life runtime or platform: Python 2, an unsupported Python 3 release, R 3.x, Java 8 only, 32-bit only.
- It does not install or run on a current operating system or CI runner without patches.
- The user names it as outdated. Weka is an example.

A maintained tool that the paper used at an old version is not outdated. Install its latest release and restate the old defaults (see [Old versions of current tools](#old-versions-of-current-tools)).

Data inside an outdated package is still data. Extract it from the archive without installing the package.

## Replace outdated software

1. Do not install, run, containerize or emulate outdated software in the pipeline, the CI or the delivery.
2. Read its source code, manual and defaults as the specification. Take the algorithm, the parameters, the defaults, the random-number handling and the output format from them.
3. Implement the method in a current language: Python, R or Rust, or another maintained language that the user asks for.
   - Use a maintained library that implements the same algorithm, if one exists. Compare its defaults with the old tool and set each one that differs.
   - A similar name is not the same algorithm. Weka's J48 is C4.5; scikit-learn's decision tree is an optimized CART. Use a C4.5 implementation or write C4.5.
   - If no library implements the algorithm, write it. Use Rust for compute-heavy kernels and call it from Python or R.
   - Draw with the paper's plotting tool if it is current (ggplot2 in R, matplotlib in Python). If it is outdated, use a current tool and restate the old styles.
4. Test the implementation against the paper's numbers and an independent reference (exact or high precision). Report the agreement count (for example, k of n marks identical).
5. Record each replacement in the README and in the final response: the old tool and version, why it is outdated, the replacement and its version, and the agreement count.

If you cannot rebuild the method without running the old tool (a closed binary, or a method that the paper and the source do not describe), stop and ask the user. With approval, run it once in an isolated container, outside the pipeline, only to make a comparison reference. Commit its outputs and mark them as such. If nobody can answer, do not run it. Report the affected items as blocked by this rule.

## Keep software up to date

- Use the latest stable release of every runtime, package, workflow engine, container base image and CI action at the time of the run. Do not use pre-releases.
- Pin the resolved versions in a lockfile (`uv.lock`, `renv.lock`, `Cargo.lock`) or in a container image built from them. Record the versions in the README. The update at setup keeps the run current; the pin keeps it repeatable.
- If the latest release breaks a step, use the newest release that works. Record the version, the failure and any upstream issue.
- On a later rerun, update to the latest releases, rerun the check step and report any change in the results.

## Old versions of current tools

When the paper used an old version of a maintained tool (for example, ggplot2 0.9.3 in 2013):

1. Install the latest release.
2. Read the old version's source and documentation for each default that changes a number or the drawing: theme values, line units, default arguments, random-number generator, tolerances.
3. Restate those values in your code. List them as restated settings, apart from fitted values.
4. If the current version cannot express an old default, report the difference.

## Rounding-level arithmetic

Do not install an old library to get its rounding. Reproduce the arithmetic with current tools: turn off FMA contraction, accumulate with a 64-bit mantissa, or port the old function's operation order. See [numerical fidelity](numerical-fidelity.md). Confirm the result on the paper's architecture in CI.
