#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.4", "pillow==12.2.0", "scipy==1.18.1"]
# ///
"""Align a reproduced figure to the published figure and measure the pixel difference.

The plot panel is found in both images by its fill grey. The reproduction is shifted so the
panel corners coincide, then cropped or padded to the published frame. Outputs: aligned.png,
overlay.png (red = reproduction only, cyan = published only, black = both), diff.png and
report.json. Optional regions give per-element offsets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

INK = 170  # grey level below which a pixel counts as ink (text, lines, marks)


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
) -> tuple[dict, np.ndarray]:
    pgrey = panel_grey(published) if pgrey is None else pgrey
    rgrey = panel_grey(render) if rgrey is None else rgrey
    pbox, rbox = panel_box(published, pgrey, tol), panel_box(render, rgrey, tol)
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
    if max(abs(v) for v in size_diff) > 1:
        report["warnings"].append(
            f"Panel size differs by {size_diff} px. Refit the drawing width and height before you tune anything else."
        )
    if lost > 0.01:
        report["warnings"].append(
            f"{lost:.1%} of the reproduction's ink falls outside the published frame."
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
                    "mean_abs_grey_difference",
                    "chamfer_outside_panel_px",
                )
            }
        )
    )
    for w in report["warnings"]:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
