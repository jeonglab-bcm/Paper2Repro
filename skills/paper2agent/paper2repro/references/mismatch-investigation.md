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

## When several inputs differ

A recovered reproduction often has more than one input that is not the paper's: data recovered in a later version, a tool rebuilt because it was never released. A gap can come from any of them.

- Change one input at a time and rerun. The input whose change moves the number is a cause. Record each run as a hypothesis with its result.
- For a statistic that one input sets (a minimum, a maximum, a rank), find which input sets it before you name a cause. In PMC2349296 the smallest cut in F error (−2.3% against the paper's 21%) was blamed on BioInfer, whose only surviving copy is a later conversion. With the paper's BioInfer row put back, IEPA set the minimum (4.1%). IEPA's corpus is the paper's, so the rebuilt RelEx was a second cause.
- Measure a rebuilt tool's agreement only on inputs that are identical to the paper's, and report the count. In PMC2349296 the rebuilt RelEx matched 0 of 9 Table 2 cells on HPRD50, IEPA and LLL; co-occurrence, which needs no rebuild, matched 9 of 9.
- A run with one of the paper's values put in place of ours is a hypothesis test. It can show that an input matters. It moves toward the paper by construction, so it never shows that we agree.

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
| PMC2349296, smallest cut in F error | −2.3% against 21%. | `data_differs` (later BioInfer conversion) and the rebuilt RelEx (low by 7 F points on IEPA, whose corpus is the paper's), each found by changing one input. | explained |
| PMC4081021, Fig. 6 | Mixture weights 68.1/31.9% against 68.0/32.0%. | `environment`: MATLAB's EM stops at a relative change of 10⁻⁶; emulating that rule gives the published weights. | explained |

Leave no hypothesis untested that a reader would raise first. In PMC1847688 the in-vitro tables (667 peaks per spectrum against 16) were left with no tested hypothesis, although the in-vitro spectra ran with the plasma settings; a reader's first question would be about those settings.
