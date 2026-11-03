# Scoring figures

The aim is to say how closely our figure matches the published one, in a way that would also catch a wrong one. Two parts: draw ours on the published figure's own pixel grid, and prove the score can tell right from wrong with negative controls.

## Get the best published copy

Use the authors' original figure files at full resolution: the publisher's "original" or "download high-res" files (TIFF or large PNG), the PMC open-access package, or the journal's figure page. A 600 dpi file lets a 2 px tolerance mean about 0.08 mm; a web thumbnail does not. Convert to PNG once, keep it in `published/` with the licence note, and never edit it.

## Map pixels to data from the axes alone

Find each panel's axes box and its tick marks; fit the pixel-to-data map to the tick positions and the printed tick labels, and record the fit residual. Nothing inside the box is fitted. If a constant cannot come from the paper or the code (a scale divisor, an unstated offset), read it from the figure, record it as an `assumption` with source `read_from_figure`, and say how the score changes when it moves (PMC1847688 Fig. 2: counts ÷ 5; at 0.19 or 0.21 times the counts the score falls from 99.99% to 98.97% and 98.26%).

## Draw and compare

- Draw our series at the published line width, in the published colour, on a copy of the published figure with the published trace removed (`fig*_ours.png`), and on the published figure in a contrasting colour (`fig*_overlay.png`). Render every panel you score; a score without a picture cannot be checked by a reader.
- Mask legends, labels and markers before scoring; score markers (peak crosses, points) separately by position and colour.
- Score both ways: the share of published trace pixels within the tolerance of ours, and of ours within the tolerance of the published. The smaller is the score. One way alone is blind: in PMC1847688 Fig. 3a a trace smoothed with the wrong window still covers 99.98% of the published pixels one way and 61% the other.
- Use one tolerance per repository (2 px at 600 dpi) unless the figure's resolution forces another, and record it.

## Negative controls

Score known-wrong versions of our series against the same panel, with the same code:

- `wrong_input`: a neighbouring sample, file, condition or subject (another spectrum, another patient, another dose).
- `near_miss`: the same input with a small, plausible error: amplitude ×1.05 and ×0.95, a shift of about 1% of the axis range, the neighbouring value of any parameter we chose (smoothing window, bin count, threshold).

Then set the pass mark between the best control and our score. If a near-miss scores as well as ours, the panel is `inconclusive`: the comparison cannot confirm that detail, and the honest options are a sharper comparison (per-column envelope in data units, peak heights, extracted values) or reporting the limit. PMC1847688 shows all three cases:

| Panel | Ours | Best wrong input | Best near-miss | Reading |
| --- | --- | --- | --- | --- |
| Fig. 2 | 99.96% | 62.2% (P_16) | 98.3% (×1.05) | Agrees with a 99% mark. |
| Fig. 7 | 99.57% | 12.9% (P_14) | 94.3% (×0.95) | Agrees with a 98% mark. |
| Fig. 3b | 99.13% | 68.5% (P_14) | 99.3% (×0.95) | Inconclusive on amplitude; spectrum and window confirmed. |

A pass mark tuned to sit just under the observed score, with no controls, would have called all three a match.

## When the numbers are available

If the figure's data can be recovered as numbers (a source-data file, a vector PDF, a table the figure draws), compare those as `values` as well. That is the only route to `exact` for a figure; the pixel score then checks the drawing.
