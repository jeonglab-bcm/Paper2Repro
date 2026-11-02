# Worked example: PMC4081639

Yu P, Shaw CA. An efficient algorithm for accurate computation of the Dirichlet-multinomial log-likelihood function. *Bioinformatics* 30(11):1547–1554 (2014). doi:10.1093/bioinformatics/btu079.

- Repository: <https://github.com/jeonglab-bcm/fossil> (folder `PMC4081639/figure-reproduction`)
- Comparison site: <https://jeonglab-bcm.github.io/fossil/PMC4081639/>

## Inputs

- Paper and supplement: PDF, plus a zip with the `lldmn` R package. The package contains only precompiled static libraries (GPL-2), no algorithm source.
- No code repository.
- Data: HMP 16S count matrices for four body sites, from the archived CRAN package HMP 2.0.1 (Apache-2.0).

## Results

| Item | Status | Evidence |
| --- | --- | --- |
| Fig. 2 | Identical data | ψ grid `seq(1e-11, 1e-10, length.out = 300)` found from the published curve. Eq. (6) with R's x86 arithmetic. 100% curve-pixel overlap. R on x86_64 equals the emulation at 300 of 300 points. |
| Fig. 4 | Identical data | Fig. 2 series plus mesh values from the authors' library. |
| Fig. 5 | Same setup | Same n grid; errors in whole ulps. VGAM: 26 of 50 marks identical with our implementation of Eq. (7). Mesh: 1–3 ulp errors under Rosetta where the paper shows 0. |
| Fig. 6 | Re-measured | One constant per method on the paper's axis. Mesh ratio 13.2–13.3× at every n (growth matches). VGAM ratio 4× to 77× (growth differs). |
| Table 1 | Identical at published precision | ψ = 0.003892, 0.006394, 0.008016, 0.010388; all round to the printed values. |
| Figs 1, 7, 8 | Not reproduced | Computable (beta-binomial PMFs, saliva heatmap, saliva runtime) but out of scope. Fig. 3 is a diagram. |

## Findings that changed the outcome

1. The published Fig. 2 axis started at 1e-11, not near 0. The axis calibration gave the data range, and the range identified the grid.
2. The same R code gave different noise on Apple Silicon. Emulating x86 arithmetic (no FMA, 80-bit `sum`) reproduced the published curve; a later CI run on x86_64 confirmed it.
3. Published errors were whole ulps. The reference had to be rounded to double before the subtraction.
4. The paper's ggplot2 0.9 theme, tikzDevice fonts, line unit and dash period had to be restated by hand. Current defaults move every element.
5. The JPEG panel greys were lighter than ggplot's grey90, and differently per figure.
6. Each figure needed its own raster scale (166 dpi for Fig. 2, 120–125 dpi for the others) and its own y-title size.
7. Table 1 fits converged in 0.1 s per site with analytic digamma gradients. Finite-difference attempts stalled or took about 20 minutes per site.
8. A Nextflow task overwrote committed parameter files through a symlinked input. `stageInMode = 'copy'` prevents this.

## Fitted, not measured

- Drawing size and raster resolution per figure.
- Axis-title gaps, title sizes and legend positions (one title gap is negative, which is not a real 0.9.3 setting).
- Fig. 6 scale constants.

A render with the original 2013 stack (R 3.0, ggplot2 0.9.3, tikzDevice 0.6) would replace most of these fitted values. That run was not done.
