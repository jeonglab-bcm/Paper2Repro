#!/usr/bin/env python3
"""Compare a fresh pipeline run with the committed outputs, file by file.

Usage: compare_runs.py FRESH_DIR COMMITTED_DIR [--rtol 1e-9] [--atol 1e-12] [--pixel-tol 0]
                       [--ignore GLOB ...]

Every file under COMMITTED_DIR must exist under FRESH_DIR and agree:
  .json            same structure; numbers within rtol/atol
  .csv .tsv        same cells; numbers within rtol/atol
  images           same size and decoded pixels within --pixel-tol (PNG bytes vary with the encoder)
  .html .htm .svg  same text once embedded base64 images are taken out; those images compared as pixels
  .pdf             skipped (embedded dates and IDs differ between runs)
  anything else    same bytes
Prints a Markdown table; exits 1 if anything differs or is missing. Needs Pillow for images.
"""

import argparse
import base64
import csv
import fnmatch
import io
import json
import math
import os
import re
import sys

IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".webp"}
DATA_URI = re.compile(r"data:image/[a-zA-Z+.-]+;base64,([A-Za-z0-9+/=]+)")


def close(a, b, rtol, atol):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isnan(a) and math.isnan(b):
            return True
        return abs(a - b) <= atol + rtol * abs(b)
    return a == b


def diff_json(a, b, rtol, atol, path="$", out=None):
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k} only in {'committed' if k in b else 'fresh'}")
            else:
                diff_json(a[k], b[k], rtol, atol, f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} items, committed {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff_json(x, y, rtol, atol, f"{path}[{i}]", out)
    elif not close(a, b, rtol, atol):
        out.append(f"{path}: {a!r}, committed {b!r}")
    return out


def as_number(s):
    try:
        return float(s)
    except ValueError:
        return s


def diff_table(pa, pb, rtol, atol, delim):
    ra = list(csv.reader(open(pa, newline="", encoding="utf-8"), delimiter=delim))
    rb = list(csv.reader(open(pb, newline="", encoding="utf-8"), delimiter=delim))
    out = [] if len(ra) == len(rb) else [f"{len(ra)} rows, committed {len(rb)}"]
    for i, (x, y) in enumerate(zip(ra, rb)):
        if len(x) != len(y):
            out.append(f"row {i + 1}: {len(x)} cells, committed {len(y)}")
            continue
        for j, (u, v) in enumerate(zip(x, y)):
            if not close(as_number(u), as_number(v), rtol, atol):
                out.append(f"row {i + 1} col {j + 1}: {u!r}, committed {v!r}")
    return out


def diff_image(fa, fb, tol):
    from PIL import Image, ImageChops

    a, b = Image.open(fa).convert("RGBA"), Image.open(fb).convert("RGBA")
    if a.size != b.size:
        return [f"size {a.size}, committed {b.size}"]
    d = ImageChops.difference(a, b)
    worst = max(hi for _, hi in d.getextrema())
    if worst <= tol:
        return []
    n = sum(1 for px in d.getdata() if max(px) > tol)
    return [f"{n} pixels differ (largest channel difference {worst})"]


def diff_html(pa, pb, tol):
    ta, tb = open(pa, encoding="utf-8").read(), open(pb, encoding="utf-8").read()
    ia, ib = DATA_URI.findall(ta), DATA_URI.findall(tb)
    out = []
    if DATA_URI.sub("data:image;base64,", ta) != DATA_URI.sub("data:image;base64,", tb):
        out.append("text differs (embedded images aside)")
    if len(ia) != len(ib):
        out.append(f"{len(ia)} embedded images, committed {len(ib)}")
    for k, (x, y) in enumerate(zip(ia, ib)):
        if x != y:
            d = diff_image(io.BytesIO(base64.b64decode(x)), io.BytesIO(base64.b64decode(y)), tol)
            out += [f"embedded image {k + 1}: {m}" for m in d]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fresh")
    ap.add_argument("committed")
    ap.add_argument("--rtol", type=float, default=1e-9)
    ap.add_argument("--atol", type=float, default=1e-12)
    ap.add_argument("--pixel-tol", type=int, default=0)
    ap.add_argument("--ignore", nargs="*", default=[])
    args = ap.parse_args()

    rows, bad = [], 0
    for dirpath, _, files in os.walk(args.committed):
        for name in sorted(files):
            pb = os.path.join(dirpath, name)
            rel = os.path.relpath(pb, args.committed)
            if any(fnmatch.fnmatch(rel, g) for g in args.ignore):
                continue
            pa = os.path.join(args.fresh, rel)
            ext = os.path.splitext(name)[1].lower()
            if not os.path.exists(pa):
                problems = ["missing from the fresh run"]
            elif ext == ".pdf":
                rows.append((rel, "skipped", "PDF"))
                continue
            elif ext == ".json":
                problems = diff_json(json.load(open(pa)), json.load(open(pb)), args.rtol, args.atol)
            elif ext in (".csv", ".tsv"):
                problems = diff_table(pa, pb, args.rtol, args.atol, "\t" if ext == ".tsv" else ",")
            elif ext in IMAGES:
                problems = diff_image(pa, pb, args.pixel_tol)
            elif ext in (".html", ".htm", ".svg"):
                problems = diff_html(pa, pb, args.pixel_tol)
            else:
                problems = [] if open(pa, "rb").read() == open(pb, "rb").read() else ["bytes differ"]
            bad += bool(problems)
            rows.append((rel, "differs" if problems else "same", "; ".join(problems[:3]) + (" …" if len(problems) > 3 else "")))

    print("| File | Fresh vs committed | Detail |")
    print("| --- | --- | --- |")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    print(f"\n{len(rows) - bad} of {len(rows)} files agree.")
    sys.exit(1 if bad or not rows else 0)


if __name__ == "__main__":
    main()
