"""example_method: doubling time from OD600 growth curves.

Paper2Repro package template. Replace the method and cite the paper here:
<Authors>. <Title>. <Journal> <volume>:<pages> (<year>). doi:<doi>
"""

from importlib import resources
from pathlib import Path

from .core import (
    DEFAULT_WINDOW,
    doubling_time,
    doubling_times,
    read_curves,
    read_results,
    write_results,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_WINDOW",
    "doubling_time",
    "doubling_times",
    "example_path",
    "read_curves",
    "read_results",
    "write_results",
]


def example_path(name: str = "growth_curves.csv") -> Path:
    """Path of a bundled example file. See data/README.md for what each file is."""
    path = resources.files(__name__) / "data" / name
    if not path.is_file():
        raise FileNotFoundError(f"no bundled example file {name!r}")
    return Path(str(path))
