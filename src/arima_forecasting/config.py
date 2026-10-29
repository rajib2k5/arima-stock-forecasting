"""Where the data lives and which dates we study.

Nothing in this module writes to the disk or uses the network. The only read is data_root's
os.path.realpath, which follows symlinks to decide whether the data folder lies inside the repo.
So every function is safe to call from a notebook, a test or a tool without side effects.
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

# The repository this file lives in (src/arima_forecasting/config.py -> two folders up). abspath
# only rewrites the text of the path; it reads nothing from the disk.
REPO_ROOT = Path(os.path.abspath(Path(__file__).parents[2]))
# The one folder inside the repository that may hold raw data: the root .gitignore ignores it
# with the anchored rule `/data/`.
IN_REPO_DATA_DIR = "data"


def _within(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def data_root(env: Mapping[str, str] | None = None, *, repo: Path = REPO_ROOT) -> Path:
    """The folder that holds raw data for every project.

    `env` is a parameter (it defaults to the real environment) so a test can pass a plain dict
    instead of changing `os.environ`, which would leak into every other test.

    An empty string counts as "not set". Shell scripts often export `VOL_DATA_DIR=` by mistake,
    and an empty path would silently mean "the current folder".

    The project's own folder, `<root>/arima-stock-forecasting`, is where raw data actually
    lands. It is refused when it is the repository itself (`VOL_DATA_DIR` set to the repo's
    parent folder, with the repo named after the project: data would land in `<repo>/raw`), or
    when it lies anywhere inside the repository except under `<repo>/data`. Anywhere else in the
    repo, a downloaded snapshot would be one `git add -A` away from being committed. Both paths
    go through os.path.realpath, so a symlink that leads into the repository is caught too.
    """
    if env is None:
        env = os.environ
    chosen = env.get(DATA_DIR_VARIABLE)
    if not chosen:
        chosen = DEFAULT_DATA_ROOT
    # Path() does not understand "~" on its own; expanduser turns it into the home folder.
    root = Path(chosen).expanduser()
    # Check where the files really go: the project folder under the root, symlinks resolved.
    lands = Path(os.path.realpath(root / PROJECT_SLUG))
    repo = Path(os.path.realpath(repo))
    if _within(lands, repo) and not _within(lands, repo / IN_REPO_DATA_DIR):
        raise ValueError(
            f"{DATA_DIR_VARIABLE}={chosen!r} puts raw data in {lands}, inside the repository "
            f"({repo}) but not in its git-ignored {IN_REPO_DATA_DIR}/ folder, where it could be "
            f"committed. Use {repo / IN_REPO_DATA_DIR} or a folder outside the repository."
        )
    return root


def raw_dir(env: Mapping[str, str] | None = None) -> Path:
    """Where this project's raw downloads go. Only builds the path; it does not create it."""
    return data_root(env) / PROJECT_SLUG / "raw"


def cache_dir(env: Mapping[str, str] | None = None) -> Path:
    """Where yfinance may keep its own small caches (cookies, time zones). Only builds the path.

    yfinance writes these to the user's cache folder unless told otherwise. Pointing it here keeps
    every file a data step writes under the one data root.
    """
    return data_root(env) / PROJECT_SLUG / "cache"


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

# One download covers both windows: the course window, then the out-of-sample window, which starts
# on the day the course window ends. Both are cut from this one snapshot, so a later dividend that
# re-scales Yahoo's adjusted history re-scales both windows together.
DOWNLOAD_WINDOW = StudyWindow("download", COURSE_WINDOW.start, OOS_WINDOW.end_exclusive)

# The course splits its window 90/10 by position: the first int(n * 0.9) rows train, the rest test.
TRAIN_FRACTION = 0.9
