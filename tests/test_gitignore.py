"""The root .gitignore must ignore raw market data in /data/, and nothing the app needs.

A bare `data/` pattern matches a folder named `data` at any depth, so it once hid app/src/data/
(the loader) and app/public/data/ (the exported JSON) from git: the app worked on the machine
that built it and broke on a fresh clone. These tests ask git itself which paths the rules
ignore, so they need a git checkout of this repo.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def ignoring_rule(path: str) -> str | None:
    """The rule that ignores `path`, written "<file>:<line>:<pattern>", or None if none does.

    --no-index asks about the patterns alone. Without it, git never reports a tracked file as
    ignored, so once these files are committed a bad rule would no longer show up here. The path
    does not have to exist. The user's global and system git config are switched off, so a
    personal excludes file cannot change the answer.
    """
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    done = subprocess.run(
        ["git", "-C", str(REPO), "check-ignore", "--no-index", "--verbose", path],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if done.returncode == 1:  # 1 means "not ignored"
        return None
    assert done.returncode == 0, done.stderr  # anything else means git itself failed
    return done.stdout.split("\t")[0]


@pytest.mark.parametrize("path", ["app/src/data/loadArtifact.ts", "app/public/data/meta.json"])
def test_files_the_app_needs_are_not_ignored(path):
    assert (REPO / path).is_file()  # sanity-check: these are real files in the repo
    assert ignoring_rule(path) is None


def test_a_new_file_in_app_src_data_is_not_ignored_either():
    # Not a file yet, so nothing but the patterns can decide; a bare `data/` would hide it.
    assert ignoring_rule("app/src/data/newLoader.ts") is None


def test_raw_data_at_the_repo_root_is_ignored_by_the_anchored_rule():
    # data/raw/AAPL.csv is hypothetical; check-ignore applies the patterns to the path anyway.
    rule = ignoring_rule("data/raw/AAPL.csv")
    assert rule is not None
    assert rule.startswith(".gitignore:") and rule.endswith(":/data/"), rule


# --- Milestone 1: held artifacts, and the second layer for raw data ------------------------

def test_every_held_artifact_is_ignored_and_every_other_artifact_is_not():
    # export.HELD_ARTIFACTS are written locally but not committed. Since the owner's decision of
    # 2026-10-29 none is held: prices.json and eda.json are committed like the other exports.
    from arima_forecasting.export import ARTIFACTS, HELD_ARTIFACTS

    assert set(HELD_ARTIFACTS) == set()
    assert ignoring_rule("app/public/data/prices.json") is None and ignoring_rule("app/public/data/eda.json") is None
    for name in ARTIFACTS:
        rule = ignoring_rule(f"app/public/data/{name}.json")
        if name in HELD_ARTIFACTS:
            assert rule is not None and rule.endswith(f":/app/public/data/{name}.json"), (name, rule)
        else:
            assert rule is None, (name, rule)


@pytest.mark.parametrize(
    "path",
    [
        "snapshots/arima-stock-forecasting/raw/AAPL_1d_2015-01-01_2026-10-01.csv",
        "snapshots/arima-stock-forecasting/raw/AAPL_1d_2015-01-01_2026-10-01.manifest.json",
        "elsewhere/deep/arima-stock-forecasting/cache/cookies.db",
        # VOL_DATA_DIR=<parent of the repo> would write <repo>/raw and <repo>/cache.
        "raw/AAPL_1d_2015-01-01_2026-10-01.csv",
        "cache/tkr-tz.db",
    ],
)
def test_a_snapshot_or_cache_anywhere_in_the_repo_is_ignored(path):
    assert ignoring_rule(path) is not None


def test_result_tables_in_reports_are_not_ignored():
    # *.csv stays allowed on purpose: reports/ will hold result tables from milestone 4.
    assert ignoring_rule("reports/metrics.csv") is None
