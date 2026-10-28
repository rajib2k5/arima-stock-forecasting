"""Where the data lives and which dates we study.

Nothing in this module touches the disk or the network. Every function is pure, so it is safe
to call from a notebook, a test or a tool without side effects.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_SLUG = "arima-stock-forecasting"
TICKER = "AAPL"

# Raw market data stays out of the repo. All of the "vol" projects share one data root, and each
# project gets its own sub-folder named by its slug, so two projects never overwrite each other.
DATA_DIR_VARIABLE = "VOL_DATA_DIR"
DEFAULT_DATA_ROOT = "~/data/vol-projects"


def data_root(env: Mapping[str, str] | None = None) -> Path:
    """The folder that holds raw data for every project.

    `env` is a parameter (it defaults to the real environment) so a test can pass a plain dict
    instead of changing `os.environ`, which would leak into every other test.

    An empty string counts as "not set". Shell scripts often export `VOL_DATA_DIR=` by mistake,
    and an empty path would silently mean "the current folder".
    """
    if env is None:
        env = os.environ
    chosen = env.get(DATA_DIR_VARIABLE)
    if not chosen:
        chosen = DEFAULT_DATA_ROOT
    # Path() does not understand "~" on its own; expanduser turns it into the home folder.
    return Path(chosen).expanduser()


def raw_dir(env: Mapping[str, str] | None = None) -> Path:
    """Where this project's raw downloads go. Only builds the path; it does not create it."""
    return data_root(env) / PROJECT_SLUG / "raw"


@dataclass(frozen=True)
class StudyWindow:
    """A named block of calendar time: `start` is in the window, `end_exclusive` is not.

    The end is exclusive on purpose, the same way yfinance and Python's `range` work. Two
    windows can then touch without sharing a day: one ends on the very date the next one starts.
    With inclusive ends we would have to write "2023-12-31" and "2024-01-01" and keep track of
    off-by-one gaps.
    """

    name: str
    start: date
    end_exclusive: date

    def __post_init__(self) -> None:
        # An empty window (start == end) would silently select no data, so reject it too.
        if self.start >= self.end_exclusive:
            raise ValueError(
                f"StudyWindow {self.name!r}: start {self.start} must be before "
                f"end_exclusive {self.end_exclusive}"
            )


# The course outline asks yfinance for start 2015-01-01 and end 2023-12-31. yfinance treats `end`
# as exclusive, so that request returns bars up to and including Friday 2023-12-29 (the 30th and
# 31st are a weekend). We write the exclusive end as 2024-01-01: the same data, but now the
# window ends exactly where the out-of-sample window begins.
COURSE_WINDOW = StudyWindow("course", date(2015, 1, 1), date(2024, 1, 1))

# A frozen, true out-of-sample period. It is fixed (not "up to today") so that anyone who re-runs
# the study gets the same numbers. Last bar: Wednesday 2026-09-30.
OOS_WINDOW = StudyWindow("oos", date(2024, 1, 1), date(2026, 10, 1))
