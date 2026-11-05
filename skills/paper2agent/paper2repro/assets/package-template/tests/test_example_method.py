"""Tests for the installed package. They use only the package and its bundled data.

check_package.py runs them from a copy outside the source tree, so they test the installed wheel.
Do not add the source folder to sys.path.
"""

import math
import subprocess
import sys

import example_method as em
import pytest

FLOATS = ("growth_rate_per_h", "doubling_time_h", "r_squared")


def close(a, b):
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def assert_same(ours, expected):
    assert [r["well"] for r in ours] == [r["well"] for r in expected]
    for o, e in zip(ours, expected):
        assert o["n_points"] == e["n_points"], o["well"]
        for k in FLOATS:
            assert close(o[k], e[k]), (o["well"], k, o[k], e[k])


def test_example_input_gives_expected_output():
    ours = em.doubling_times(em.read_curves(em.example_path("growth_curves.csv")))
    assert_same(ours, em.read_results(em.example_path("growth_curves_expected.csv")))


def test_command_line_matches_expected_output(tmp_path):
    out = tmp_path / "out.csv"
    subprocess.run(
        [sys.executable, "-m", "example_method", str(em.example_path()), "-o", str(out)], check=True
    )
    assert_same(em.read_results(out), em.read_results(em.example_path("growth_curves_expected.csv")))


def test_too_few_points_gives_no_estimate():
    r = em.doubling_time([(0.0, 0.01), (1.0, 0.06), (2.0, 0.8)])
    assert r["n_points"] == 1
    assert r["doubling_time_h"] is None


def test_no_growth_gives_no_doubling_time():
    r = em.doubling_time([(0.0, 0.1), (1.0, 0.1), (2.0, 0.1)])
    assert r["growth_rate_per_h"] == 0
    assert r["doubling_time_h"] is None


def test_bad_window_raises():
    with pytest.raises(ValueError):
        em.doubling_time([(0.0, 0.1)], window=(0.5, 0.05))


def test_missing_column_raises(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("well,time_h\nA1,0\n")
    with pytest.raises(ValueError, match="od600"):
        em.read_curves(path)
