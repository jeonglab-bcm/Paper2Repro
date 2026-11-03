# Finding out why

Every item that is not `exact` ends with a cause in `results.json`. "Close enough" and "probably a different version" are not causes. The goal is the smallest change that closes the gap, shown by rerunning with it, or a recorded list of what was ruled out.

## Steps

1. **Locate the gap.** Where does it start, how big is it, is it everywhere or in one region, one panel, one row? Overlays and per-field differences usually say more than the overall score. ("One block near 7.25 kDa dips to 1.5; the rest overlays" points at one interval, not at the method.)
2. **List hypotheses before testing any**, in this order, because earlier ones are both likelier and cheaper:
   1. Our error: wrong input file or sample, units or scale, axis read wrong, an off-by-one, a step of the authors' script skipped.
   2. A setting the paper does not state: bin count, seed, window, threshold, normalization, the version of a library default.
   3. The code differs from the text: compare each step of the authors' code with the methods section.
   4. The data differ from what the figure used: supplement versions, row order, filtered subsets. Check counts first.
   5. The paper is wrong: a rounding slip, a rank that contradicts its own scores, a caption that names the wrong panel.
   6. Nondeterminism or platform: seeds, parallel order, optimizer stopping rules, compiled arithmetic.
3. **Test each with a command whose result is recorded**: what you ran, what it gave. Keep scripts that bear on the result in `pipeline/` so the pipeline reruns them; one-off searches go in a JSON record under `output/` with a README line saying they are not part of the pipeline.
4. **Stop** when one hypothesis closes the gap quantitatively (removing the cause makes the item match): status `explained`. Otherwise, when the plausible hypotheses are tested, status `open` with at least two of them recorded as rejected or inconclusive.
5. **Write it once**: the cause in `results.json`, the explanation in the paper's README (Details or Limits), the one-liner in the pull request.

## Searching for an unstated setting

A search over settings that keeps the best match is fitting, so report it as fitting: give the grid searched, the setting found, and how fast the score falls for its neighbours. Record the setting as an `assumption` with source `found_by_search`. In PMC1847688 Fig. 5 a wavelet-denoised running minimum reproduced the comparison curve (99.99% and 98.45% within 2 px) with one combination out of a search over wavelet, levels, threshold and thresholding rule; neighbouring settings fell to 72% or below. That specificity is what makes it a finding rather than a fit.

## Examples

| Item | Gap | Cause | Status |
| --- | --- | --- | --- |
| PMC1847688, all figures | The published MATLAB code stops with an index error. | `code_does_not_run`: `kurtosis(block, 0) < 1` can never hold for MATLAB's kurtosis; with excess kurtosis the 16 published peaks of Figs 7 and 8 come back. | explained |
| PMC1847688, Fig. 9b | Bars 1 and 6 are off by 10 and 7 classes. | Bin-edge ties rejected (no class count sits on an edge); misreading rejected (tick fit within 0.55). | open |
| PMC1847688, plasma totals | 9,071 peaks against 4,382 in the text. | Kurtosis definitions, 150 Da blocks, block-mean baselines and subject order all rejected; Additional File 4 itself has 7,893. | open |
| PMC4081021, Table 1 | 4 of 120 fields differ. | `paper_error`: a rounding slip and three ranks that contradict the table's own BICs. | explained |
| PMC4081021, Figs 3B and 4B | The figure is not what the text describes. | `code_differs_from_paper`: the plotting script draws the dose response at 60 min; the data, the fit and the text are at 30 min. We draw it as the script does. | explained |
| PMC4081021, Fig. 6 | Mixture weights 68.1/31.9% against 68.0/32.0%. | `environment`: MATLAB's EM stops at a relative change of 10⁻⁶; emulating that rule gives the published weights. | explained |

Leave no hypothesis untested that a reader would raise first. In PMC1847688 the in-vitro tables (667 peaks per spectrum against 16) were left with no tested hypothesis, although the in-vitro spectra ran with the plasma settings; a reader's first question would be about those settings.
