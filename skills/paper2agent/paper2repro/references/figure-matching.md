# Figure matching

Draw each figure with the tools the paper used, at the published pixel size, so the two images overlay directly.

## The published frame

A figure of ours is shown next to the published one and on top of it. That only compares something when both are on one frame: the same picture size, each panel's axes at the same place, the same axis limits. A plotting tool left to its defaults takes its limits, ticks and margins from the data and the device, so a small difference in the data, or another device size, moves the whole drawing. The overlay then shows two sets of axes, two legends and two titles, and nothing about the result. Reproductions have shipped overlays like that. The frame is a choice of the drawing, so it can always be the published one, and it comes before anything else is tuned.

There are two ways to be on the published frame:

- **Draw our series on a copy of the published picture** (figure-scoring.md, "Draw and compare"). The frame is the published one by construction.
- **Draw the figure anew**, as below.

For a new drawing:

1. **Measure the published picture.** Its size in pixels (W by H), each panel's axes box (x0, x1, y0, y1, with y down), and the data value at each edge of the box, from the fit of the tick positions to the printed tick labels (figure-scoring.md, "Map pixels to data from the axes alone").
2. **Draw ours at W by H pixels, with each axes at its published box and the limits set to the values at the box edges.** Turn off the padding the tool adds to an axis, and do not let it trim the picture.
   - matplotlib: `fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)`, then `ax = fig.add_axes([x0 / W, 1 - (y1 + 1) / H, (x1 - x0 + 1) / W, (y1 - y0 + 1) / H])`, `ax.set_xlim(...)`, `ax.set_ylim(...)`, and `fig.savefig(path, dpi=dpi)`. Never `bbox_inches="tight"` and never `tight_layout()`: both move the axes.
   - base R: `png(path, width = W, height = H, res = dpi)`, then for each panel `par(plt = c(x0 / W, (x1 + 1) / W, 1 - (y1 + 1) / H, 1 - y0 / H), xaxs = "i", yaxs = "i", new = <TRUE after the first panel>)` and `plot(..., xlim = ..., ylim = ...)`. Do not use `mfrow` or `layout()` for panels whose boxes you know.
   - ggplot2: the panel follows from the theme, so solve the drawing size until the panel has the published pixel size ("Size and resolution" below) and set the limits with `coord_cartesian(xlim = ..., ylim = ..., expand = FALSE)`.
3. **Take the axis from the paper, not from our data.** The limits, the tick values, the order of bars and groups, and a log or linear scale are the published ones even when our values differ. Count the points of ours that fall outside the published limits and report the count; do not clip them silently and do not widen the axis to hold them. Never change a value to make it fit.
4. **Then place what is around the data** where the paper has it: legend (position and size), title, axis titles, tick labels, text sizes ("Element alignment" below).
5. **Measure it.** `compare_figure.py --published <published> --render <ours> --out <dir> --require-frame` finds the panel in both pictures (by its fill, by its axis lines, or as the boxes you give with `--published-box` and `--render-box`), and fails when the panel of ours is more than 2 px off the published size or more than 1% of our ink falls outside the published picture. Correct the last pixels from its report: a tool draws its axis lines on the edge of the box, so a box measured at the outside of the lines is a pixel larger each way.
6. **Record it** as the item's `layout` in `results.json` (results-json.md, "Layout"): the two numbers of the report's `layout` block, and for each axis the published limits and the limits ours was drawn with, read back from the plotting code (`ax.get_xlim()`, `par("usr")`). `check_results.py` refuses a figure whose picture has no `layout`, a panel off the published size, or an axis that is not the published one.

The picture listed first in the item's `outputs`, and its overlay, are the ones on the published frame. A second picture on our own axis range can go in the README when points fall outside the published limits; it is never the one that is compared.

A drawing with no axes to share (a network laid out at random, a diagram) cannot be on the published frame. Record `layout.not_comparable` with the reason. A plot with axes never qualifies.

## Identify the toolchain

- Read the theme. ggplot2 0.9.x (2012–2014) defaults: grey90 panel, white major and grey95 minor gridlines, grey50 axis text at 0.8×, 0.15 cm ticks, 1.2-line legend keys with a grey95 fill and white border, grey80 strips. Current ggplot2 defaults differ. Restate the old values in a theme function; do not trust current defaults.
- Read the typography. Italic Greek letters, `μ` and superscripts set in math mode point to tikzDevice with pdfLaTeX. Computer Modern and Times are hard to separate below about 200 dpi: score both and report the result as uncertain if the scores are close.
- Measure line widths and dash periods from a legend key. tikzDevice 0.12 writes 0.4 pt per `lwd` (option `tikzLwdUnit`). Published 2014 figures measured about 1 pt; `tikzLwdUnit = 72.27/96` reproduced them. Set dash patterns from the measured period (for example, `"22"` for 2 pt on, 2 pt off).

## Colours

- Publisher JPEGs are often lighter than the source. Measured examples: grey90 (229) became 233 or 238; grey80 (204) became 212. Sample panel and strip fills per figure from the published image. Keep text colours at the theme values; antialiasing makes thin glyphs read lighter.
- State which colours are sampled and which are theme values.

## Size and resolution

- The published pixel size is fixed. The original drawing size and raster resolution are unknown.
- For a candidate resolution, solve the drawing width and height so the panel box has the published pixel size. Align on the panel's top-left corner and crop or pad to the published frame (`compare_figure.py` does this). The picture to show and to overlay is the aligned one (`aligned.png`), which has the published size.
- Choose the resolution by stroke alignment of text outside the panel (chamfer distance), not by mean grey difference. The mean is flat across resolutions because the panel dominates it.
- Figures in one paper can have different scales. Example: one figure fitted at 166 dpi, the others at 120–125 dpi.
- If text is shorter in one direction only, test separate x and y resolutions. Keep one resolution if the difference is inside the measurement noise.

## Element alignment

- Measure each element (axis titles, tick labels, legend, plot title, facet strips) with a local best shift, then change the matching theme parameter (title margin, `hjust`, legend spacing, title size).
- A shift at the edge of the search window is not a measurement. Increase the window or start closer. In the worked example, two automatic passes moved a title the wrong way for this reason.
- Different text sizes break the correlation. Measure the printed length of the text first and set its size (published y-titles measured 9.9–12.7 pt instead of a uniform 12 pt).
- Do not tune the theme on data-dependent elements. Tick labels of a different axis range move titles.
- `coord_cartesian(expand = FALSE)` also removes the padding of a discrete x axis. Set the y expansion on the scale instead.

## Axis ranges

- The paper's axis is the one ours is drawn with ("The published frame" above): set limits and breaks from the tick or gridline calibration. Count the points outside the limits and report them. Do not clip silently.
- If the data differ for a known reason (rounding noise, timing hardware) and points fall outside, a second version on our own range may go in the README.

## Comparison views

- Give each figure side-by-side, swipe, blink, overlay and difference views. Overlay: red channel = published, green and blue = reproduction, so cyan is ink only in the paper, red is ink only in the reproduction and black is both.
- Report per figure: pixel size, drawing size, resolution, panel fill, mean absolute grey difference, percentage of pixels within ±24, and the data status.
