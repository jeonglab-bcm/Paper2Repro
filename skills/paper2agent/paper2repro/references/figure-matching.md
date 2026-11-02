# Figure matching

Draw each figure with the tools the paper used, at the published pixel size, so the two images overlay directly.

## Identify the toolchain

- Read the theme. ggplot2 0.9.x (2012–2014) defaults: grey90 panel, white major and grey95 minor gridlines, grey50 axis text at 0.8×, 0.15 cm ticks, 1.2-line legend keys with a grey95 fill and white border, grey80 strips. Current ggplot2 defaults differ. Restate the old values in a theme function; do not trust current defaults.
- Read the typography. Italic Greek letters, `μ` and superscripts set in math mode point to tikzDevice with pdfLaTeX. Computer Modern and Times are hard to separate below about 200 dpi: score both and report the result as uncertain if the scores are close.
- Measure line widths and dash periods from a legend key. tikzDevice 0.12 writes 0.4 pt per `lwd` (option `tikzLwdUnit`). Published 2014 figures measured about 1 pt; `tikzLwdUnit = 72.27/96` reproduced them. Set dash patterns from the measured period (for example, `"22"` for 2 pt on, 2 pt off).

## Colours

- Publisher JPEGs are often lighter than the source. Measured examples: grey90 (229) became 233 or 238; grey80 (204) became 212. Sample panel and strip fills per figure from the published image. Keep text colours at the theme values; antialiasing makes thin glyphs read lighter.
- State which colours are sampled and which are theme values.

## Size and resolution

- The published pixel size is fixed. The original drawing size and raster resolution are unknown.
- For a candidate resolution, solve the drawing width and height so the panel box has the published pixel size. Align on the panel's top-left corner and crop or pad to the published frame (`compare_figure.py` does this).
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

- If the data differ for a known reason (rounding noise, timing hardware), offer the paper's axis as a second version: set limits and breaks from the gridline calibration. Count the points outside the limits and report them. Do not clip silently.

## Comparison views

- Give each figure side-by-side, swipe, blink, overlay and difference views. Overlay: red channel = published, green and blue = reproduction, so cyan is ink only in the paper, red is ink only in the reproduction and black is both.
- Report per figure: pixel size, drawing size, resolution, panel fill, mean absolute grey difference, percentage of pixels within ±24, and the data status.
