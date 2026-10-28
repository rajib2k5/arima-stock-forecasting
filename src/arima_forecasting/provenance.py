"""Where a generated file came from: the git commit and the build time.

This is the only module in the package that talks to the outside world (the `git` program and
the clock). Everything else is pure, so the I/O stays in one small place.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from arima_forecasting.contract import UNCOMMITTED

SOURCE_DATE_EPOCH_VARIABLE = "SOURCE_DATE_EPOCH"

# The reproducible-builds spec allows only what `date +%s` prints: ASCII digits. int() alone is
# looser: it also accepts "1_000", " 5 ", "5\n", "-86400", "+5" and non-ASCII digits like "١٠".
_EPOCH = re.compile(r"[0-9]+")


# The folder tools/export_app_data.py writes to by default, relative to the repo root.
EXPORT_DIR = "app/public/data"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # `git -C repo` runs git as if started inside `repo`, so we never depend on the caller's
    # current folder. A file name that is not valid UTF-8 (git prints it as raw bytes when
    # core.quotePath is false) must not make the decoding fail, so undecodable bytes are kept as
    # surrogate escapes instead of raising.
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        errors="surrogateescape",
        check=False,
    )


def source_commit(repo: Path) -> str:
    """The commit a file was built from: "<sha>", "<sha>-dirty" or "uncommitted".

    "-dirty" means the working tree had changes that are not in that commit, so the sha alone
    would not let anyone reproduce the file. "uncommitted" covers a repo with no commits yet,
    a folder that is not a git repo, and a machine where git is missing or cannot be run.

    The sha is whatever the repository uses: 40 hex characters, or 64 in a SHA-256 repository.
    A problem with git or the repository never raises: it ends in "uncommitted" or "-dirty".
    """
    try:
        head = _git(repo, "rev-parse", "HEAD")
        if head.returncode != 0:  # no commits yet, or not a repo
            return UNCOMMITTED
        sha = head.stdout.strip()

        # --porcelain is the stable, machine-readable format: one line per changed or untracked
        # file, and no output at all when the tree is clean. We ask for untracked files
        # explicitly because a user's git config can switch them off, and a new file is a change
        # too.
        #
        # The pathspecs after "--" say what counts. ':(top)' is the whole repository, so a change
        # outside `repo` still counts when `repo` is a sub-folder (a bare "." would limit the
        # check to that folder). The exclusion is the exporter's own default output folder: the
        # provenance names the CODE that produced the data, and regenerating the output does not
        # change the code. Without it the first export would modify the tracked meta.json, the
        # second export would then stamp "-dirty", and SOURCE_DATE_EPOCH could no longer give
        # byte-identical files. The exclusion is relative to `repo`, which is the repo root in
        # tools/export_app_data.py.
        #
        # One limit that is git's, not ours: a file marked `git update-index --assume-unchanged`
        # or `--skip-worktree` is not looked at, so editing it leaves `git status` empty.
        status = _git(
            repo,
            "status",
            "--porcelain",
            "--untracked-files=normal",
            "--",
            ":(top)",
            f":(exclude){EXPORT_DIR}",
        )
    except OSError:  # no `git` on PATH, or one we are not allowed to run (PermissionError)
        return UNCOMMITTED
    # If the status command itself fails we cannot show that the tree is clean, so we do not
    # claim it is.
    if status.returncode != 0 or status.stdout.strip():
        return f"{sha}-dirty"
    return sha


def build_time(env: Mapping[str, str] | None = None) -> datetime:
    """The time to stamp on a generated file, in UTC.

    SOURCE_DATE_EPOCH is the reproducible-builds convention: when it is set, the build uses
    that fixed time (seconds since 1970) instead of the clock, so building twice gives
    byte-identical output. An empty value counts as "not set". Anything other than plain ASCII
    digits (no sign, no spaces, no separators) raises ValueError, because silently falling back
    to "now" would hide the mistake.
    """
    if env is None:
        env = os.environ
    epoch = env.get(SOURCE_DATE_EPOCH_VARIABLE)
    if not epoch:
        return datetime.now(timezone.utc)
    if _EPOCH.fullmatch(epoch) is None:
        raise ValueError(
            f"{SOURCE_DATE_EPOCH_VARIABLE} must be a whole number of seconds written in ASCII "
            f"digits only, got {epoch!r}"
        )
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
