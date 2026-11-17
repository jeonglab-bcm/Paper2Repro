#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.4", "pillow==12.2.0", "scipy==1.18.1"]
# ///
"""Synthetic tests for compare_figure.py: alignment, metrics, region offsets and warnings."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "compare_figure", HERE / "compare_figure.py"
)
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)


def figure(shape, panel, grey, title_dx=0):
    """White canvas, grey panel, a dark y-title block, x-tick blocks and a zigzag curve in the panel."""
    img = np.full(shape, 255.0)
    x0, x1, y0, y1 = panel
    img[y0 : y1 + 1, x0 : x1 + 1] = grey
    img[
        y0 + 40 : y0 + 100, x0 - 45 + title_dx : x0 - 35 + title_dx
    ] = 20  # y-axis title
    for k in range(4):
        img[y1 + 8 : y1 + 16, x0 + 20 + 50 * k : x0 + 40 + 50 * k] = 120  # tick labels
    for x in range(x0 + 5, x1 - 5):
        y = y0 + (y1 - y0) // 2 + int(30 * np.sin(x / 7.0))
        img[y : y + 2, x] = 0
    return img


def test_alignment_and_metrics():
    pub = figure((220, 320), (70, 300, 20, 170), 233)
    ren = np.full((250, 350), 255.0)
    ren[12 : 12 + 220, 15 : 15 + 320] = figure((220, 320), (70, 300, 20, 170), 229)
    report, _ = cf.compare(pub, ren)
    assert report["published_panel_grey"] == 233 and report["render_panel_grey"] == 229
    assert report["shift_px"] == [-15, -12], report["shift_px"]
    assert report["panel_size_difference_px"] == [0, 0]
    assert (
        report["chamfer_outside_panel_px"] == 0.0
        and report["chamfer_inside_panel_px"] == 0.0
    )
    assert report["mean_abs_grey_difference"] < 4.0
    assert not report["warnings"], report["warnings"]


def test_region_offset_and_edge_warning():
    pub = figure((220, 320), (70, 300, 20, 170), 233)
    ren = figure((220, 320), (70, 300, 20, 170), 233, title_dx=4)
    region = [{"name": "ytitle", "box": [10, 50, 40, 140]}]
    report, _ = cf.compare(pub, ren, regions=region, window=8)
    off = report["regions"]["ytitle"]
    assert (off["dx"], off["dy"]) == (-4, 0) and not off["at_window_edge"], off
    report, _ = cf.compare(pub, ren, regions=region, window=3)
    assert report["regions"]["ytitle"]["at_window_edge"]
    assert any("search window" in w for w in report["warnings"])


def test_panel_size_warning():
    pub = figure((220, 320), (70, 300, 20, 170), 233)
    ren = figure((220, 320), (70, 290, 20, 170), 233)
    report, _ = cf.compare(pub, ren)
    assert report["panel_size_difference_px"] == [-10, 0]
    assert any("Refit" in w for w in report["warnings"])


def plain(shape, box, ylim_shift=0, left_bottom_only=False):
    """White canvas and a white panel: a box of axis lines (or a left and a bottom axis), ticks, and a curve."""
    img = np.full(shape, 255.0)
    x0, x1, y0, y1 = box
    img[y0 : y1 + 1, x0 : x0 + 2] = 0  # left axis
    img[y1 - 1 : y1 + 1, x0 : x1 + 1] = 0  # bottom axis
    if not left_bottom_only:
        img[y0 : y1 + 1, x1 - 1 : x1 + 1] = 0
        img[y0 : y0 + 2, x0 : x1 + 1] = 0
    for k in range(5):
        img[y1 + 1 : y1 + 6, x0 + k * (x1 - x0) // 4 : x0 + k * (x1 - x0) // 4 + 2] = 0  # x ticks
        img[y1 - k * (y1 - y0) // 4 - 1 : y1 - k * (y1 - y0) // 4 + 1, x0 - 5 : x0] = 0  # y ticks
    for x in range(x0 + 6, x1 - 6):
        y = y0 + (y1 - y0) // 2 + int(25 * np.sin(x / 9.0)) + ylim_shift
        img[y : y + 2, x] = 0
    img[y0 + 8 : y0 + 12, x0 + 12 : x0 + 40] = 60  # a legend key
    return img


def test_white_panel_found_by_its_axis_lines():
    box = (60, 290, 25, 180)
    pub = plain((220, 320), box)
    ren = np.full((260, 360), 255.0)
    ren[20 : 20 + 220, 30 : 30 + 320] = plain((220, 320), box)
    report, _ = cf.compare(pub, ren)
    assert report["panel_found_by"] == {"published": "lines", "render": "lines"}
    assert report["published_panel_box"] == list(box), report["published_panel_box"]
    assert report["shift_px"] == [-30, -20] and report["panel_size_difference_px"] == [0, 0]
    assert report["same_frame"] and report["chamfer_inside_panel_px"] == 0.0
    assert report["layout"] == {"panel_size_difference_px": [0, 0], "ink_outside_frame": 0.0}
    # a left and a bottom axis with no box: the far ends of the two lines close the frame
    open_axes = cf.compare(plain((220, 320), box, left_bottom_only=True), ren)[0]
    assert open_axes["published_panel_box"] == list(box) and open_axes["same_frame"], open_axes["published_panel_box"]


def test_another_frame_is_said_and_can_fail():
    pub = plain((220, 320), (60, 290, 25, 180))
    ren = plain((220, 320), (60, 290, 40, 180))  # the panel of ours is 15 px shorter
    report, _ = cf.compare(pub, ren)
    assert report["panel_size_difference_px"] == [0, -15] and not report["same_frame"]
    assert any("not on the published frame" in w for w in report["warnings"])
    assert cf.compare(pub, ren, frame_tol=20)[0]["same_frame"]
    # the boxes can be given, for a figure whose frame cannot be found
    given, _ = cf.compare(pub, ren, pbox=[60, 290, 25, 180], rbox=[60, 290, 40, 180])
    assert given["panel_found_by"] == {"published": "given", "render": "given"} and given["panel_size_difference_px"] == [0, -15]
    blank = np.full((220, 320), 255.0)
    try:
        cf.compare(pub, blank)
        raise AssertionError("a picture with no frame should be refused")
    except SystemExit as err:
        assert "--render-box" in str(err)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        Image.fromarray(pub.astype(np.uint8)).save(d / "pub.png")
        Image.fromarray(ren.astype(np.uint8)).save(d / "ren.png")
        cmd = [sys.executable, str(HERE / "compare_figure.py"), "--published", str(d / "pub.png"), "--render", str(d / "ren.png"), "--out", str(d / "out")]
        assert subprocess.run(cmd, capture_output=True).returncode == 0
        failed = subprocess.run(cmd + ["--require-frame"], capture_output=True, text=True)
        assert failed.returncode == 1 and "not on the published frame" in failed.stdout, failed
        assert json.loads((d / "out" / "report.json").read_text())["same_frame"] is False
        assert subprocess.run(cmd + ["--require-frame", "--render-box", "60,290,25,180"], capture_output=True).returncode == 0


def test_cli_outputs():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        Image.fromarray(
            figure((220, 320), (70, 300, 20, 170), 233).astype(np.uint8)
        ).save(d / "pub.png")
        Image.fromarray(
            figure((220, 320), (70, 300, 20, 170), 229).astype(np.uint8)
        ).save(d / "ren.png")
        subprocess.run(
            [
                sys.executable,
                str(HERE / "compare_figure.py"),
                "--published",
                str(d / "pub.png"),
                "--render",
                str(d / "ren.png"),
                "--out",
                str(d / "out"),
            ],
            check=True,
            capture_output=True,
        )
        for f in ("aligned.png", "overlay.png", "diff.png", "report.json"):
            assert (d / "out" / f).exists(), f
        assert json.loads((d / "out" / "report.json").read_text())["shift_px"] == [0, 0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
