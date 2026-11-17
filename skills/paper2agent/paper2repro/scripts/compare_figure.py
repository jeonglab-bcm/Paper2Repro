#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.4", "pillow==12.2.0", "scipy==1.18.1"]
# ///
"""Align a reproduced figure to the published figure and measure the pixel difference.

The plot panel is found in both images: by its fill grey, by its axis lines where the panel has
no fill, or as the box given with --published-box and --render-box. The reproduction is shifted
so the panel corners coincide, then cropped or padded to the published frame. Outputs:
aligned.png, overlay.png (red = reproduction only, cyan = published only, black = both),
diff.png and report.json. Optional regions give per-element offsets.

report.json says whether the reproduction is on the published frame (same_frame): its panel has
the published size within --frame-tolerance, and its ink stays inside the published picture.
An overlay of two figures on different frames compares nothing, so fix the frame first.
--require-frame makes a different frame an error (exit 1).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

INK = 170  # grey level below which a pixel counts as ink (text, lines, marks)
LINE_SHARE = 0.3  # an axis line is a run of ink at least this share of the picture's width or height


def load(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L"), dtype=float)


def panel_grey(img: np.ndarray, lo: int = 180, hi: int = 250) -> int:
    """Most frequent grey between lo and hi: the panel fill of ggplot-style figures."""
    vals = img[(img >= lo) & (img <= hi)].astype(int)
    if not vals.size:
        raise SystemExit("No panel grey found. Pass --published-grey/--render-grey.")
    return int(np.bincount(vals).argmax())


def panel_box(img: np.ndarray, grey: int, tol: int) -> tuple[int, int, int, int]:
    """(x0, x1, y0, y1) of the union of panels filled with `grey`."""
    m = np.abs(img - grey) <= tol
    cols = np.where(m.sum(0) > img.shape[0] * 0.25)[0]
    rows = np.where(m.sum(1) > img.shape[1] * 0.12)[0]
    if not len(cols) or not len(rows):
        raise SystemExit(f"No panel with grey {grey} ± {tol}.")
    return int(cols.min()), int(cols.max()), int(rows.min()), int(rows.max())


def longest_run(row: np.ndarray) -> tuple[int, int]:
    """(length, start) of the longest run of True in a 1-D mask."""
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    if not len(starts):
        return 0, 0
    k = int((ends - starts).argmax())
    return int(ends[k] - starts[k]), int(starts[k])


def line_box(img: np.ndarray) -> tuple[int, int, int, int]:
    """(x0, x1, y0, y1) of the axes frame of a figure whose panel has no fill.

    The frame is bounded by the outermost long axis lines. Two lines that meet in a corner
    (a left and a bottom axis) are closed by their far ends.
    """
    ink = img < INK
    H, W = ink.shape
    rows = [(n, s, y) for y in range(H) for n, s in [longest_run(ink[y])] if n >= LINE_SHARE * W]
    cols = [(n, s, x) for x in range(W) for n, s in [longest_run(ink[:, x])] if n >= LINE_SHARE * H]
    if not rows or not cols:
        raise SystemExit(
            "No panel fill and no axis lines found. Give the axes box: --published-box / --render-box x0,x1,y0,y1."
        )
    x0, x1 = min(x for _, _, x in cols), max(x for _, _, x in cols)
    y0, y1 = min(y for _, _, y in rows), max(y for _, _, y in rows)
    if x1 - x0 < LINE_SHARE * W:  # one vertical axis: the horizontal lines end at the right edge
        x1 = max(s + n - 1 for n, s, _ in rows)
    if y1 - y0 < LINE_SHARE * H:  # one horizontal axis: the vertical lines end at the top edge
        y0 = min(s for _, s, _ in cols)
    return x0, x1, y0, y1


def find_box(img: np.ndarray, grey, tol: int, given=None) -> tuple[tuple[int, int, int, int], str, int | None]:
    """The axes box of a figure, how it was found (given, fill or lines) and the panel grey when it has a fill."""
    if given is not None:
        return tuple(int(v) for v in given), "given", grey
    try:
        g = panel_grey(img) if grey is None else grey
        return panel_box(img, g, tol), "fill", g
    except SystemExit:
        if grey is not None:
            raise
        return line_box(img), "lines", None


def align(
    render: np.ndarray, rbox, shape, pbox
) -> tuple[np.ndarray, tuple[int, int], float]:
    """Shift render so its panel's top-left corner meets the published one; crop/pad to shape.

    Returns the aligned image, the shift and the fraction of render ink that fell outside the frame.
    """
    dx, dy = pbox[0] - rbox[0], pbox[2] - rbox[2]
    out = np.full(shape, 255.0)
    h, w = render.shape
    ys, xs = max(0, dy), max(0, dx)
    ye, xe = min(shape[0], h + dy), min(shape[1], w + dx)
    if ye > ys and xe > xs:
        out[ys:ye, xs:xe] = render[ys - dy : ye - dy, xs - dx : xe - dx]
    ink_total = int((render < INK).sum())
    lost = 1.0 - (out < INK).sum() / ink_total if ink_total else 0.0
    return out, (dx, dy), float(max(lost, 0.0))


def chamfer(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float | None:
    """Mean symmetric distance (px) between ink pixels of a and b inside mask."""
    A, B = (a < INK) & mask, (b < INK) & mask
    if not A.any() or not B.any():
        return None
    dA = ndimage.distance_transform_edt(~A)
    dB = ndimage.distance_transform_edt(~B)
    return float((dB[A].mean() + dA[B].mean()) / 2)


def best_shift(aligned: np.ndarray, published: np.ndarray, box, window: int) -> dict:
    """Shift (dx, dy) that the reproduction needs inside box, and whether it hit the window edge."""
    x0, x1, y0, y1 = box
    H, W = published.shape
    x0, x1 = max(x0, window), min(x1, W - window - 1)
    y0, y1 = max(y0, window), min(y1, H - window - 1)
    ref = published[y0 : y1 + 1, x0 : x1 + 1]
    best = None
    for dy in range(-window, window + 1):
        for dx in range(-window, window + 1):
            cand = aligned[y0 - dy : y1 - dy + 1, x0 - dx : x1 - dx + 1]
            v = float(np.abs(cand - ref).mean())
            if best is None or v < best[0]:
                best = (v, dx, dy)
    v, dx, dy = best
    return {
        "dx": dx,
        "dy": dy,
        "residual": round(v, 3),
        "at_window_edge": max(abs(dx), abs(dy)) == window,
    }


def compare(
    published: np.ndarray,
    render: np.ndarray,
    pgrey=None,
    rgrey=None,
    tol=4,
    regions=(),
    window=10,
    pbox=None,
    rbox=None,
    frame_tol=2,
) -> tuple[dict, np.ndarray]:
    pbox, phow, pgrey = find_box(published, pgrey, tol, pbox)
    rbox, rhow, rgrey = find_box(render, rgrey, tol, rbox)
    aligned, shift, lost = align(render, rbox, published.shape, pbox)
    d = np.abs(aligned - published)
    inside = np.zeros(published.shape, bool)
    x0, x1, y0, y1 = pbox
    inside[y0 : y1 + 1, x0 : x1 + 1] = True
    size_diff = ((rbox[1] - rbox[0]) - (x1 - x0), (rbox[3] - rbox[2]) - (y1 - y0))
    report = {
        "published_size": list(published.shape[::-1]),
        "render_size": list(render.shape[::-1]),
        "published_panel_grey": pgrey,
        "render_panel_grey": rgrey,
        "published_panel_box": list(pbox),
        "render_panel_box": list(rbox),
        "panel_found_by": {"published": phow, "render": rhow},
        "panel_size_difference_px": list(size_diff),
        "shift_px": list(shift),
        "render_ink_outside_frame": round(lost, 4),
        "mean_abs_grey_difference": round(float(d.mean()), 3),
        "pixels_within_24_pct": round(float((d <= 24).mean() * 100), 2),
        "chamfer_outside_panel_px": chamfer(aligned, published, ~inside),
        "chamfer_inside_panel_px": chamfer(aligned, published, inside),
        "regions": {},
        "warnings": [],
    }
    # The two measured numbers of an item's `layout` in results.json; the axis limits come from the plotting code.
    report["layout"] = {
        "panel_size_difference_px": list(size_diff),
        "ink_outside_frame": round(lost, 4),
    }
    report["same_frame"] = max(abs(v) for v in size_diff) <= frame_tol and lost <= 0.01
    if max(abs(v) for v in size_diff) > 1:
        report["warnings"].append(
            f"Panel size differs by {size_diff} px. Refit the drawing width and height before you tune anything else."
        )
    if lost > 0.01:
        report["warnings"].append(
            f"{lost:.1%} of the reproduction's ink falls outside the published frame."
        )
    if not report["same_frame"]:
        report["warnings"].append(
            "The reproduction is not on the published frame, so the overlay compares nothing. "
            "Draw it at the published size, with its axes at the published box and the published axis limits."
        )
    for r in regions:
        off = best_shift(aligned, published, r["box"], window)
        report["regions"][r["name"]] = off
        if off["at_window_edge"]:
            report["warnings"].append(
                f"Region {r['name']}: offset reached the search window ({window} px). It is not a measurement. Increase --window or start closer."
            )
    return report, aligned


def write_images(published: np.ndarray, aligned: np.ndarray, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(aligned.clip(0, 255).astype(np.uint8)).save(out / "aligned.png")
    rgb = np.stack([published, aligned, aligned], -1).clip(0, 255).astype(np.uint8)
    Image.fromarray(rgb).save(out / "overlay.png")
    diff = 255 - np.minimum(255, np.abs(published - aligned) * 2)
    Image.fromarray(diff.astype(np.uint8)).save(out / "diff.png")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--published", required=True, type=Path, help="published figure (JPEG/PNG)"
    )
    ap.add_argument(
        "--render",
        required=True,
        type=Path,
        help="reproduction rasterized near the published scale",
    )
    ap.add_argument("--out", required=True, type=Path, help="output directory")
    ap.add_argument(
        "--published-grey",
        type=int,
        help="panel fill in the published image (default: auto)",
    )
    ap.add_argument(
        "--render-grey", type=int, help="panel fill in the reproduction (default: auto)"
    )
    ap.add_argument(
        "--tolerance", type=int, default=4, help="grey tolerance for panel detection"
    )
    box = lambda text: [int(v) for v in text.split(",")]  # noqa: E731
    ap.add_argument(
        "--published-box",
        type=box,
        metavar="X0,X1,Y0,Y1",
        help="axes box of the published figure in its pixels (default: found by fill, then by axis lines)",
    )
    ap.add_argument(
        "--render-box",
        type=box,
        metavar="X0,X1,Y0,Y1",
        help="axes box of the reproduction in its pixels (default: found the same way)",
    )
    ap.add_argument(
        "--frame-tolerance",
        type=int,
        default=2,
        help="largest panel-size difference (px) that still counts as the published frame",
    )
    ap.add_argument(
        "--require-frame",
        action="store_true",
        help="exit 1 when the reproduction is not on the published frame",
    )
    ap.add_argument(
        "--regions",
        type=Path,
        help='JSON list of {"name": ..., "box": [x0, x1, y0, y1]} in published pixels',
    )
    ap.add_argument(
        "--window", type=int, default=10, help="search window (px) for region offsets"
    )
    a = ap.parse_args()
    regions = json.loads(a.regions.read_text()) if a.regions else []
    published, render = load(a.published), load(a.render)
    report, aligned = compare(
        published,
        render,
        a.published_grey,
        a.render_grey,
        a.tolerance,
        regions,
        a.window,
        a.published_box,
        a.render_box,
        a.frame_tolerance,
    )
    write_images(published, aligned, a.out)
    (a.out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "shift_px",
                    "panel_size_difference_px",
                    "same_frame",
                    "mean_abs_grey_difference",
                    "chamfer_outside_panel_px",
                )
            }
        )
    )
    for w in report["warnings"]:
        print("WARNING:", w)
    if a.require_frame and not report["same_frame"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
