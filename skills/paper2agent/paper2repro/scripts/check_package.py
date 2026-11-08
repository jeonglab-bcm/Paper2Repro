#!/usr/bin/env python3
"""Check that a reproduction's Python package installs, runs and teaches.

Usage:
  check_package.py PACKAGE_DIR                check; exit 1 on any failure
  check_package.py PACKAGE_DIR --write        also run tutorial/tutorial.ipynb in the fresh install,
                                              save its outputs and regenerate tutorial/TUTORIAL.md
  check_package.py PACKAGE_DIR --json FILE    write the report; the results.json `package` item reads it
  check_package.py PACKAGE_DIR --layout-only  static checks only: no build, no install, no network
  check_package.py PACKAGE_DIR --keep         keep the scratch folder and print where it is

Steps: layout and metadata; build a wheel from a copy of the folder; install it into a fresh virtual
environment in a folder whose path has a space; import the package from that environment, not the
source tree; run each console script with --help; run the package's tests from a copy outside the
source tree; execute the tutorial notebook and compare its outputs with the committed ones; check that
TUTORIAL.md is the committed notebook rendered. Rules: references/package-and-tutorial.md.

Standard library only (Python 3.11+). Uses uv when it is on PATH, otherwise venv and pip.
Installing the package's dependencies and the test tools needs network access.
An R package (DESCRIPTION, no pyproject.toml) exits with code 2: follow the R steps in the reference.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    sys.exit("check_package.py needs Python 3.11 or later (tomllib).")

SCHEMA = "paper2repro/package-check/v1"
TOOLS = ["pytest", "nbclient", "nbformat", "ipykernel"]
NOTEBOOK = Path("tutorial/tutorial.ipynb")
MARKDOWN = Path("tutorial/TUTORIAL.md")
FILES_DIR = "TUTORIAL_files"
SKIP_TAG = "nondeterministic"
IMAGES = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg"}
LICENSES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING")
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "dist", "build", "*.egg-info", ".venv", ".pytest_cache", ".ipynb_checkpoints"
)
NUM = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
PATH_HACK = re.compile(r"sys\.path\s*(?:\.\s*(?:insert|append|extend)\b|\[|\+?=)")
REL_TOL, ABS_TOL = 1e-9, 1e-12
HEADER = "<!-- Generated from tutorial.ipynb by check_package.py --write. Do not edit by hand. -->"
KERNEL = "paper2repro-package-check"

RUNNER = r"""
import sys
import nbformat
from nbclient import NotebookClient

src, dst, kernel, timeout = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
nb = nbformat.read(src, as_version=4)
NotebookClient(nb, timeout=timeout, kernel_name=kernel, allow_errors=True, record_timing=False,
               resources={"metadata": {"path": "."}}).execute()
nbformat.write(nb, dst)
"""


class Report:
    def __init__(self):
        self.checks = []

    def add(self, name, passed, detail=""):
        self.checks.append({"name": name, "passed": bool(passed), "detail": detail})
        print(f"{'ok  ' if passed else 'FAIL'} {name}" + (f": {detail}" if detail else ""), flush=True)
        return bool(passed)

    @property
    def passed(self):
        return all(c["passed"] for c in self.checks)


# ---------- notebook helpers (also used by the self-test) ----------

def join(text):
    return "".join(text) if isinstance(text, list) else (text or "")


def output_text(out):
    """The text a reader sees for one output; empty for images."""
    kind = out.get("output_type")
    if kind == "stream":
        return join(out.get("text"))
    if kind in ("execute_result", "display_data"):
        data = out.get("data") or {}
        if any(m in data for m in IMAGES):
            return ""
        return join(data.get("text/plain"))
    if kind == "error":
        return ANSI.sub("", "\n".join(out.get("traceback") or [f"{out.get('ename')}: {out.get('evalue')}"]))
    return ""


def normalize(text):
    lines = [ANSI.sub("", line).rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


def same_text(a, b):
    """Equal after normalizing whitespace, with numbers equal within REL_TOL / ABS_TOL."""
    a, b = normalize(a), normalize(b)
    if a == b:
        return True
    if NUM.split(a) != NUM.split(b):
        return False
    return all(
        math.isclose(float(x), float(y), rel_tol=REL_TOL, abs_tol=ABS_TOL)
        for x, y in zip(NUM.findall(a), NUM.findall(b))
    )


def code_cells(nb):
    return [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]


def compare_notebooks(committed, fresh):
    """Compare the outputs of a fresh run with the committed notebook.

    Returns (compared, skipped, problems): text outputs are compared with same_text and images by count.
    Cells tagged 'nondeterministic' are skipped. Any error output in the fresh run is a problem.
    """
    a, b = code_cells(committed), code_cells(fresh)
    problems, compared, skipped = [], 0, 0
    if len(a) != len(b):
        return 0, 0, [f"{len(a)} code cells committed, {len(b)} in the fresh run"]
    for n, (ca, cb) in enumerate(zip(a, b), 1):
        errors = [o for o in cb.get("outputs", []) if o.get("output_type") == "error"]
        if errors:
            problems.append(f"code cell {n} raised {errors[0].get('ename')}: {errors[0].get('evalue')}")
            continue
        if join(ca.get("source")) != join(cb.get("source")):
            problems.append(f"code cell {n}: source differs")
            continue
        if SKIP_TAG in (ca.get("metadata") or {}).get("tags", []):
            skipped += 1
            continue
        compared += 1
        ta = "".join(output_text(o) for o in ca.get("outputs", []))
        tb = "".join(output_text(o) for o in cb.get("outputs", []))
        if not same_text(ta, tb):
            problems.append(f"code cell {n}: output differs\n  committed: {normalize(ta)[:300]!r}\n  fresh:     {normalize(tb)[:300]!r}")
        ia = sum(any(m in (o.get("data") or {}) for m in IMAGES) for o in ca.get("outputs", []))
        ib = sum(any(m in (o.get("data") or {}) for m in IMAGES) for o in cb.get("outputs", []))
        if ia != ib:
            problems.append(f"code cell {n}: {ia} images committed, {ib} in the fresh run")
    return compared, skipped, problems


def render_markdown(nb):
    """TUTORIAL.md text and its image files {name: bytes}, from an executed notebook."""
    parts, files = [HEADER], {}
    for n, cell in enumerate(nb.get("cells", []), 1):
        src = join(cell.get("source")).strip("\n")
        if cell.get("cell_type") == "markdown":
            if src.strip():
                parts.append(src)
            continue
        if cell.get("cell_type") != "code":
            continue
        if src.strip():
            parts.append(f"```python\n{src}\n```")
        k, text = 0, ""
        for out in cell.get("outputs", []):
            text += output_text(out)
            data = out.get("data") or {}
            mime = next((m for m in IMAGES if m in data), None)
            if not mime:
                continue
            if normalize(text):
                parts.append(f"```text\n{normalize(text)}\n```")
            text = ""
            k += 1
            name = f"cell-{n:02d}-{k}.{IMAGES[mime]}"
            raw = join(data[mime])
            files[name] = raw.encode() if mime == "image/svg+xml" else base64.b64decode(raw)
            parts.append(f"![Output of cell {n}]({FILES_DIR}/{name})")
        if normalize(text):
            parts.append(f"```text\n{normalize(text)}\n```")
    return "\n\n".join(parts) + "\n", files


def write_markdown(pkg, nb):
    text, files = render_markdown(nb)
    md = pkg / MARKDOWN
    md.write_text(text, encoding="utf-8")
    folder = md.parent / FILES_DIR
    if folder.exists():
        shutil.rmtree(folder)
    if files:
        folder.mkdir()
        for name, data in files.items():
            (folder / name).write_bytes(data)


def check_markdown(pkg, nb, rep):
    md = pkg / MARKDOWN
    if not md.is_file():
        return rep.add("TUTORIAL.md matches the notebook", False, f"{MARKDOWN} is missing; run with --write")
    text, files = render_markdown(nb)
    problems = []
    if md.read_text(encoding="utf-8") != text:
        problems.append("text differs from the rendered notebook")
    folder = md.parent / FILES_DIR
    for name, data in files.items():
        f = folder / name
        if not f.is_file() or f.read_bytes() != data:
            problems.append(f"{FILES_DIR}/{name} missing or different")
    extra = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
    extra = [p for p in extra if p not in files]
    if extra:
        problems.append(f"stale files in {FILES_DIR}: {extra}")
    return rep.add(
        "TUTORIAL.md matches the notebook",
        not problems,
        "; ".join(problems) + ("; run with --write" if problems else "") or f"{len(files)} images",
    )


# ---------- static checks ----------

def check_layout(pkg, rep, max_data_kb, write):
    """Layout and metadata. Returns (project table, import name, notebook) or None where missing."""
    project, name, nb = None, None, None
    pyproject = pkg / "pyproject.toml"
    try:
        meta = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        rep.add("pyproject.toml", False, str(e))
        meta = {}
    if meta:
        project = meta.get("project") or {}
        missing = [k for k in ("name", "version", "description", "readme", "requires-python") if not project.get(k)]
        if not (project.get("license") or project.get("license-files")):
            missing.append("license")
        if not project.get("scripts"):
            missing.append("scripts (a command-line entry point)")
        if not (meta.get("build-system") or {}).get("build-backend"):
            missing.append("build-system.build-backend")
        if "dependencies" not in project:
            missing.append("dependencies (an empty list is fine)")
        rep.add("pyproject.toml metadata", not missing, f"missing {missing}" if missing else f"{project['name']} {project['version']}")

    pkgs = sorted(p.parent.name for p in (pkg / "src").glob("*/__init__.py")) if (pkg / "src").is_dir() else []
    if len(pkgs) == 1:
        name = pkgs[0]
        rep.add("src layout", True, f"src/{name}")
        init = (pkg / "src" / name / "__init__.py").read_text(encoding="utf-8")
        m = re.search(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", init, re.MULTILINE)
        if m and project and m.group(1) != project.get("version"):
            rep.add("__version__ matches pyproject", False, f"{m.group(1)} != {project.get('version')}")
    else:
        rep.add("src layout", False, f"expected one package under src/, found {pkgs or 'none'}")

    readme = pkg / "README.md"
    text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    rep.add("README.md with an install command", "pip install" in text,
            "" if "pip install" in text else "README.md is missing or has no `pip install` command")
    lic = [f for f in LICENSES if (pkg / f).is_file()]
    rep.add("licence file", bool(lic), lic[0] if lic else f"none of {LICENSES}")

    tests = sorted((pkg / "tests").glob("test_*.py")) if (pkg / "tests").is_dir() else []
    hacks = [t.name for t in tests + sorted((pkg / "tests").glob("conftest.py")) if PATH_HACK.search(t.read_text(encoding="utf-8"))]
    rep.add("tests", tests and not hacks,
            f"{len(tests)} test files" if tests and not hacks else
            ("no tests/test_*.py" if not tests else f"tests must import the installed package; sys.path changed in {hacks}"))

    if name:
        data = pkg / "src" / name / "data"
        files = [p for p in data.rglob("*") if p.is_file() and "__pycache__" not in p.parts] if data.is_dir() else []
        size_kb = sum(p.stat().st_size for p in files) / 1024
        problems = []
        if not (data / "README.md").is_file():
            problems.append("data/README.md (provenance, licence) is missing")
        if len([p for p in files if p.name != "README.md"]) < 2:
            problems.append("needs an example input and its expected output")
        if size_kb > max_data_kb:
            problems.append(f"{size_kb:.0f} KB is over {max_data_kb} KB")
        rep.add("example data", not problems, "; ".join(problems) or f"{len(files)} files, {size_kb:.1f} KB")

    try:
        nb = json.loads((pkg / NOTEBOOK).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        rep.add("tutorial notebook", False, f"{NOTEBOOK}: {e}")
        return project, name, None
    problems = []
    if nb.get("nbformat") != 4:
        problems.append("not nbformat 4")
    markdown = "".join(join(c.get("source")) for c in nb.get("cells", []) if c.get("cell_type") == "markdown")
    if "pip install" not in markdown:
        problems.append("no markdown cell with the `pip install` command")
    cells = code_cells(nb)
    if not cells:
        problems.append("no code cells")
    if not write:
        unrun = [n for n, c in enumerate(cells, 1) if c.get("execution_count") is None]
        if unrun:
            problems.append(f"code cells {unrun} have no saved outputs; run with --write")
        errors = [n for n, c in enumerate(cells, 1) if any(o.get("output_type") == "error" for o in c.get("outputs", []))]
        if errors:
            problems.append(f"code cells {errors} saved an error")
    rep.add("tutorial notebook", not problems, "; ".join(problems) or f"{len(cells)} code cells")
    return project, name, nb


# ---------- build, install, run ----------

def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, check=False, **kw)


def tail(p, n=1500):
    return (p.stdout + p.stderr).strip()[-n:]


def clean_env(venv, scratch):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTHONSTARTUP")}
    bindir = venv / ("Scripts" if os.name == "nt" else "bin")
    env.update(
        PATH=str(bindir) + os.pathsep + env.get("PATH", ""),
        VIRTUAL_ENV=str(venv),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONHASHSEED="0",
        MPLBACKEND="Agg",
        IPYTHONDIR=str(scratch / "ipython"),
        JUPYTER_PATH=str(scratch / "jupyter"),
        JUPYTER_PLATFORM_DIRS="1",
    )
    return env


def check_install(pkg, project, name, nb, rep, args, scratch):
    uv = shutil.which("uv")
    installer = "uv" if uv else "pip"
    venv = scratch / "venv"
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    p = run([uv, "venv", "--quiet", "--python", args.python, venv] if uv else [args.python, "-m", "venv", venv])
    if not rep.add("fresh environment", p.returncode == 0, tail(p) if p.returncode else f"{installer}, {venv}"):
        return {}
    env = clean_env(venv, scratch)

    def install(*specs):
        cmd = [uv, "pip", "install", "--quiet", "--python", py, *specs] if uv else \
            [py, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *specs]
        return run(cmd, env=env)

    # Build from a copy so nothing is written into the repository.
    src = scratch / "source"
    shutil.copytree(pkg, src, ignore=IGNORE)
    dist = scratch / "dist"
    p = run([uv, "build", "--wheel", "--quiet", "--out-dir", dist, src] if uv else
            [py, "-m", "pip", "wheel", "--no-deps", "--quiet", "--disable-pip-version-check", "-w", dist, src], env=env)
    wheels = sorted(dist.glob("*.whl")) if dist.is_dir() else []
    if not rep.add("wheel builds", p.returncode == 0 and len(wheels) == 1, tail(p) if p.returncode else wheels[0].name if wheels else "no wheel"):
        return {}
    wheel = wheels[0]
    names = zipfile.ZipFile(wheel).namelist()
    data = pkg / "src" / name / "data"
    want = [f"{name}/data/{p.relative_to(data).as_posix()}" for p in data.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts] if data.is_dir() else []
    lost = [w for w in want if w not in names]
    rep.add("wheel holds the example data", not lost, f"missing {lost}" if lost else f"{len(want)} files")
    info = {"file": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "files": len(names)}

    p = install(wheel)
    if not rep.add("wheel installs with its dependencies", p.returncode == 0, tail(p)):
        return info
    workdir = scratch / "run"
    workdir.mkdir()
    probe = ("import importlib, importlib.metadata as md, json, sys; m = importlib.import_module(sys.argv[1]); "
             "print(json.dumps({'file': m.__file__, 'version': getattr(m, '__version__', None), "
             "'dist': md.version(sys.argv[2])}))")
    p = run([py, "-c", probe, name, project["name"]], cwd=workdir, env=env)
    if p.returncode == 0:
        got = json.loads(p.stdout.strip().splitlines()[-1])
        inside = Path(got["file"]).resolve().is_relative_to(venv.resolve())
        versions = {got["dist"], got["version"] or got["dist"]} == {project["version"]}
        rep.add("imports from the installed wheel", inside and versions,
                f"{got['file']} version {got['version'] or got['dist']}" if inside and versions else
                f"imported {got['file']} (version {got['version']}, dist {got['dist']}, pyproject {project['version']})")
    else:
        rep.add("imports from the installed wheel", False, tail(p))

    bindir = py.parent
    for script in project.get("scripts", {}):
        exe = bindir / (script + (".exe" if os.name == "nt" else ""))
        p = run([exe, "--help"], cwd=workdir, env=env)
        rep.add(f"command `{script} --help`", p.returncode == 0, tail(p, 300) if p.returncode else "")

    p = install(*TOOLS)
    if not rep.add("test tools install", p.returncode == 0, tail(p) if p.returncode else ", ".join(TOOLS)):
        return info

    shutil.copytree(pkg / "tests", workdir / "tests", ignore=IGNORE)
    p = run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=workdir, env=env, timeout=args.timeout)
    m = re.search(r"(\d+) passed", p.stdout)
    rep.add("package tests pass", p.returncode == 0, f"{m.group(1)} passed" if p.returncode == 0 and m else tail(p))

    if nb is None:
        return info
    kdir = scratch / "jupyter" / "kernels" / KERNEL
    kdir.mkdir(parents=True)
    (kdir / "kernel.json").write_text(json.dumps({
        "argv": [str(py), "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Python (package check)", "language": "python"}))
    tut = workdir / "tutorial"
    shutil.copytree(pkg / NOTEBOOK.parent, tut, ignore=IGNORE)
    (scratch / "run_notebook.py").write_text(RUNNER)
    out = scratch / "executed.ipynb"
    started = time.time()
    p = run([py, scratch / "run_notebook.py", tut / NOTEBOOK.name, out, KERNEL, args.timeout], cwd=tut, env=env)
    if not rep.add("tutorial runs", p.returncode == 0 and out.is_file(),
                   tail(p) if p.returncode else f"{time.time() - started:.0f} s"):
        return info
    fresh = json.loads(out.read_text(encoding="utf-8"))
    errors = [f"code cell {n}: {o.get('ename')}: {o.get('evalue')}" for n, c in enumerate(code_cells(fresh), 1)
              for o in c.get("outputs", []) if o.get("output_type") == "error"]
    if args.write:
        if not rep.add("tutorial runs without errors", not errors, "; ".join(errors)):
            return info
        fresh["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
        fresh["metadata"].get("language_info", {}).pop("version", None)
        (pkg / NOTEBOOK).write_text(json.dumps(fresh, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        write_markdown(pkg, fresh)
        rep.add("tutorial outputs saved", True, f"saved to {NOTEBOOK} and {MARKDOWN.name}")
        check_markdown(pkg, fresh, rep)
    else:
        compared, skipped, problems = compare_notebooks(nb, fresh)
        rep.add("tutorial outputs match the committed notebook", not problems,
                "\n".join(problems) if problems else f"{compared} cells compared, {skipped} skipped ({SKIP_TAG})")
    return info


def summary(rep, project, layout_only):
    by = {c["name"]: c for c in rep.checks}
    tests = by.get("package tests pass", {}).get("detail", "")
    tut = by.get("tutorial outputs match the committed notebook") or by.get("tutorial outputs saved") or {}
    if not rep.passed:
        failed = [c["name"] for c in rep.checks if not c["passed"]]
        return f"Failed: {', '.join(failed)}"
    if layout_only:
        return f"{project['name']} {project['version']}: layout, tutorial notebook and TUTORIAL.md checked (not built)"
    return (f"{project['name']} {project['version']}: wheel installed in a fresh environment and imported from it; "
            f"tests {tests}; tutorial {tut.get('detail', '')}; TUTORIAL.md in sync")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package", help="the package folder (holds pyproject.toml)")
    ap.add_argument("--write", action="store_true", help="save fresh tutorial outputs and regenerate TUTORIAL.md")
    ap.add_argument("--json", help="write the report to this file")
    ap.add_argument("--layout-only", action="store_true", help="static checks only (no build or install)")
    ap.add_argument("--keep", action="store_true", help="keep the scratch folder")
    ap.add_argument("--python", default=sys.executable, help="interpreter for the fresh environment")
    ap.add_argument("--max-data-kb", type=int, default=1024, help="size limit for the bundled example data")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per notebook cell and for the test run")
    args = ap.parse_args()

    pkg = Path(args.package).resolve()
    if (pkg / "DESCRIPTION").is_file() and not (pkg / "pyproject.toml").is_file():
        print(f"{pkg} is an R package. check_package.py checks Python packages only; run the R steps in "
              "references/package-and-tutorial.md (Check an R package).", file=sys.stderr)
        sys.exit(2)
    rep = Report()
    project, name, nb = check_layout(pkg, rep, args.max_data_kb, args.write)
    if nb is not None and not args.write:
        check_markdown(pkg, nb, rep)

    info = {}
    if not args.layout_only:
        if project and name:
            scratch = Path(tempfile.mkdtemp(prefix="paper2repro package check "))
            try:
                info = check_install(pkg, project, name, nb, rep, args, scratch)
            finally:
                if args.keep:
                    print(f"scratch folder kept: {scratch}")
                else:
                    shutil.rmtree(scratch, ignore_errors=True)
        else:
            rep.add("build and install", False, "skipped: fix pyproject.toml and the src layout first")

    report = {
        "schema": SCHEMA,
        "package": (project or {}).get("name"),
        "import": name,
        "version": (project or {}).get("version"),
        "python": sys.version.split()[0],
        "installer": None if args.layout_only else ("uv" if shutil.which("uv") else "pip"),
        "layout_only": args.layout_only,
        "passed": rep.passed,
        "detail": summary(rep, project or {"name": "?", "version": "?"}, args.layout_only),
        "wheel": info or None,
        "checks": rep.checks,
    }
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(("OK " if rep.passed else "FAILED ") + report["detail"])
    sys.exit(0 if rep.passed else 1)


if __name__ == "__main__":
    main()
