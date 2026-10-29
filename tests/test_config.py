"""Acceptance tests for config.py. Expected values are literals worked out by hand (arithmetic
in comments), never recomputed by the code under test."""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from pathlib import Path

import pytest

from arima_forecasting import config
from arima_forecasting.config import COURSE_WINDOW, OOS_WINDOW, StudyWindow

HOME = Path.home()


# --- 1. Constants -----------------------------------------------------------------------

def test_project_constants():
    assert config.PROJECT_SLUG == "arima-stock-forecasting"
    assert config.TICKER == "AAPL"


# --- 2. data_root ------------------------------------------------------------------------

def test_data_root_uses_env_override():
    assert config.data_root({"VOL_DATA_DIR": "/mnt/market"}) == Path("/mnt/market")


def test_data_root_override_expands_tilde():
    # "~/elsewhere" must become <home>/elsewhere, not a folder literally named "~".
    assert config.data_root({"VOL_DATA_DIR": "~/elsewhere"}) == HOME / "elsewhere"


def test_data_root_empty_string_counts_as_unset():
    # An exported-but-empty variable must not turn into "the current folder" (Path("") == ".").
    assert config.data_root({"VOL_DATA_DIR": ""}) == HOME / "data" / "vol-projects"


def test_data_root_default_expands_tilde():
    root = config.data_root({})
    # <home> + "data" + "vol-projects": two parts appended to the home folder.
    assert root == HOME / "data" / "vol-projects"
    assert root.is_absolute()
    assert "~" not in root.parts


def test_data_root_ignores_unrelated_variables():
    # Only the exact name VOL_DATA_DIR counts.
    assert config.data_root({"DATA_DIR": "/nope", "vol_data_dir": "/nope"}) == (
        HOME / "data" / "vol-projects"
    )


def test_data_root_reads_the_real_environment_by_default(monkeypatch):
    # No `env` argument: it must fall back to os.environ. monkeypatch restores it afterwards.
    monkeypatch.setenv("VOL_DATA_DIR", "/from/os/environ")
    assert config.data_root() == Path("/from/os/environ")
    monkeypatch.delenv("VOL_DATA_DIR")
    assert config.data_root() == HOME / "data" / "vol-projects"


# --- 3. raw_dir --------------------------------------------------------------------------

def test_raw_dir_is_root_plus_slug_plus_raw():
    # /mnt/market + arima-stock-forecasting + raw
    assert config.raw_dir({"VOL_DATA_DIR": "/mnt/market"}) == Path(
        "/mnt/market/arima-stock-forecasting/raw"
    )


def test_raw_dir_default():
    assert config.raw_dir({}) == HOME / "data" / "vol-projects" / "arima-stock-forecasting" / "raw"


def test_raw_dir_does_not_create_anything(tmp_path):
    root = tmp_path / "not-yet"
    result = config.raw_dir({"VOL_DATA_DIR": str(root)})
    assert result == root / "arima-stock-forecasting" / "raw"
    assert not root.exists()


# --- 4. StudyWindow ----------------------------------------------------------------------

def test_study_window_accepts_a_one_day_window():
    window = StudyWindow("one-day", date(2024, 1, 1), date(2024, 1, 2))
    assert (window.name, window.start, window.end_exclusive) == (
        "one-day",
        date(2024, 1, 1),
        date(2024, 1, 2),
    )


def test_study_window_rejects_reversed_dates():
    with pytest.raises(ValueError, match="backwards"):
        StudyWindow("backwards", date(2024, 1, 2), date(2024, 1, 1))


def test_study_window_rejects_equal_dates():
    # start == end_exclusive is an empty window: [start, start) contains no day at all.
    with pytest.raises(ValueError, match="empty"):
        StudyWindow("empty", date(2024, 1, 1), date(2024, 1, 1))


def test_study_window_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        COURSE_WINDOW.start = date(2000, 1, 1)  # type: ignore[misc]


# --- 5. The two windows ------------------------------------------------------------------

def test_course_window_dates():
    assert COURSE_WINDOW.name == "course"
    assert COURSE_WINDOW.start == date(2015, 1, 1)
    assert COURSE_WINDOW.end_exclusive == date(2024, 1, 1)


def test_oos_window_dates():
    assert OOS_WINDOW.name == "oos"
    assert OOS_WINDOW.start == date(2024, 1, 1)
    assert OOS_WINDOW.end_exclusive == date(2026, 10, 1)


def test_windows_are_contiguous_and_do_not_overlap():
    # The course window ends where the OOS window starts: no gap day, no shared day.
    assert COURSE_WINDOW.end_exclusive == OOS_WINDOW.start


def test_window_lengths_in_days():
    # Course 2015-01-01 -> 2024-01-01: nine whole years (2015..2023), two of them leap
    # (2016, 2020): 9 * 365 + 2 = 3287 days.
    assert (COURSE_WINDOW.end_exclusive - COURSE_WINDOW.start).days == 3287
    # OOS 2024-01-01 -> 2026-10-01: 2024 (leap, 366) + 2025 (365) = 731 days to 2026-01-01, then
    # Jan 31 + Feb 28 + Mar 31 + Apr 30 + May 31 + Jun 30 + Jul 31 + Aug 31 + Sep 30 = 273.
    # 731 + 273 = 1004 days.
    assert (OOS_WINDOW.end_exclusive - OOS_WINDOW.start).days == 1004


def last_weekday_before(day: date) -> date:
    """The latest Monday-to-Friday date strictly before `day` (holidays ignored)."""
    candidate = day - timedelta(days=1)
    while candidate.weekday() >= 5:  # Monday is 0, so 5 and 6 are Saturday and Sunday
        candidate -= timedelta(days=1)
    return candidate


def test_last_bars_match_the_calendar():
    # Course: the day before 2024-01-01 is Sunday 2023-12-31, then Saturday 12-30, so the last
    # weekday is Friday 2023-12-29. That is the last bar the course outline's request
    # (end=2023-12-31, exclusive) returns too.
    assert last_weekday_before(COURSE_WINDOW.end_exclusive) == date(2023, 12, 29)
    # OOS: the day before Thursday 2026-10-01 is Wednesday 2026-09-30, a weekday.
    assert last_weekday_before(OOS_WINDOW.end_exclusive) == date(2026, 9, 30)


# --- 2b. data_root refuses folders inside the repository, except <repo>/data -------------

REPO = config.REPO_ROOT


def test_repo_root_is_this_repository():
    assert (REPO / "pyproject.toml").is_file() and (REPO / "src" / "arima_forecasting").is_dir()


@pytest.mark.parametrize("inside", ["data", "data/vol", "data/arima-stock-forecasting/raw/.."])
def test_data_root_accepts_the_ignored_data_folder_of_the_repo(inside):
    assert config.data_root({"VOL_DATA_DIR": str(REPO / inside)}) == REPO / inside


@pytest.mark.parametrize("inside", ["", "snapshots", "app/public", "data-raw", "data/../tests"])
def test_data_root_refuses_any_other_folder_inside_the_repo(inside):
    # "data-raw" shares a prefix with "data"; "data/../tests" only looks like it is under data/.
    with pytest.raises(ValueError, match="inside the repository"):
        config.data_root({"VOL_DATA_DIR": str(REPO / inside) if inside else str(REPO)})


def test_data_root_refuses_a_relative_folder_that_resolves_inside_the_repo(monkeypatch):
    monkeypatch.chdir(REPO / "app")
    with pytest.raises(ValueError, match="inside the repository"):
        config.data_root({"VOL_DATA_DIR": "public"})
    monkeypatch.chdir(REPO)
    assert config.data_root({"VOL_DATA_DIR": "data"}) == Path("data")


def test_data_root_checks_against_the_repo_it_is_given(tmp_path):
    repo = tmp_path / "repo"
    with pytest.raises(ValueError, match="inside the repository"):
        config.data_root({"VOL_DATA_DIR": str(repo / "snapshots")}, repo=repo)
    assert config.data_root({"VOL_DATA_DIR": str(repo / "data")}, repo=repo) == repo / "data"
    assert config.data_root({"VOL_DATA_DIR": str(tmp_path / "outside")}, repo=repo) == tmp_path / "outside"


def test_raw_dir_and_cache_dir_inherit_the_check():
    with pytest.raises(ValueError, match="inside the repository"):
        config.raw_dir({"VOL_DATA_DIR": str(REPO / "snapshots")})
    with pytest.raises(ValueError, match="inside the repository"):
        config.cache_dir({"VOL_DATA_DIR": str(REPO / "snapshots")})


def test_data_root_refuses_the_repos_parent_when_the_repo_is_named_after_the_project(tmp_path):
    # VOL_DATA_DIR=<parent of repo>: raw_dir would be <repo>/raw, inside the repo but not in data/.
    # Found by the milestone-1 re-review: the old check looked at the root's own path only.
    repo = tmp_path / "arima-stock-forecasting"
    (repo / "data").mkdir(parents=True)
    with pytest.raises(ValueError, match="inside the repository"):
        config.data_root({"VOL_DATA_DIR": str(tmp_path)}, repo=repo)
    # Its data/ folder is still fine, and so is a sibling folder outside the repo.
    assert config.data_root({"VOL_DATA_DIR": str(repo / "data")}, repo=repo) == repo / "data"
    assert config.data_root({"VOL_DATA_DIR": str(tmp_path / "elsewhere")}, repo=repo) == tmp_path / "elsewhere"


def test_data_root_refuses_a_symlink_that_leads_into_the_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "snapshots").mkdir(parents=True)
    link = tmp_path / "looks-outside"
    link.symlink_to(repo / "snapshots", target_is_directory=True)
    with pytest.raises(ValueError, match="inside the repository"):
        config.data_root({"VOL_DATA_DIR": str(link)}, repo=repo)


def test_this_repos_parent_is_refused_when_the_checkout_is_named_after_the_project():
    if REPO.name != config.PROJECT_SLUG:
        pytest.skip(f"this checkout is named {REPO.name!r}, so its parent puts data elsewhere")
    with pytest.raises(ValueError, match="inside the repository"):
        config.raw_dir({"VOL_DATA_DIR": str(REPO.parent)})
