"""Acceptance tests for provenance.py: the git commit and the build time.

The git tests build small throwaway repos under tmp_path. The expected commit id is read back
from git itself with `git rev-parse` (an independent source), never from the code under test.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from arima_forecasting.contract import make_envelope, validate_envelope
from arima_forecasting.provenance import build_time, source_commit

UTC = timezone.utc
REPO = Path(__file__).resolve().parent.parent


def git(repo: Path, *args: str) -> str:
    """Run git in `repo`, ignoring the user's global config so the test is hermetic."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env
    )
    return done.stdout.strip()


def new_repo(path: Path, object_format: str | None = None) -> Path:
    path.mkdir()
    git(path, "init", "-q", *([f"--object-format={object_format}"] if object_format else []))
    # Local-only identity and no signing: set in this temp repo's own config, nowhere else.
    git(path, "config", "user.name", "Test User")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "commit.gpgsign", "false")
    return path


def commit_file(repo: Path, name: str, text: str) -> str:
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


# --- 1. source_commit --------------------------------------------------------------------

def test_repo_with_no_commits_is_uncommitted(tmp_path):
    repo = new_repo(tmp_path / "repo")
    assert source_commit(repo) == "uncommitted"


def test_repo_with_no_commits_stays_uncommitted_even_with_files_present(tmp_path):
    repo = new_repo(tmp_path / "repo")
    (repo / "a.txt").write_text("hello")  # untracked, still no commit to point at
    assert source_commit(repo) == "uncommitted"


def test_folder_that_is_not_a_repo_is_uncommitted(tmp_path, monkeypatch):
    # Stop git from walking up into some enclosing repo above tmp_path.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    assert source_commit(plain) == "uncommitted"


def test_missing_folder_is_uncommitted(tmp_path):
    assert source_commit(tmp_path / "does-not-exist") == "uncommitted"


def test_machine_without_git_is_uncommitted(tmp_path, monkeypatch):
    repo = new_repo(tmp_path / "repo")
    commit_file(repo, "a.txt", "one\n")
    # An empty folder as the whole PATH: the `git` program cannot be found.
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert source_commit(repo) == "uncommitted"


def test_clean_repo_returns_the_bare_sha(tmp_path):
    repo = new_repo(tmp_path / "repo")
    sha = commit_file(repo, "a.txt", "one\n")
    assert re.fullmatch(r"[0-9a-f]{40}", sha)  # sanity-check the helper, not the code under test
    assert source_commit(repo) == sha


def test_modified_tracked_file_is_dirty(tmp_path):
    repo = new_repo(tmp_path / "repo")
    sha = commit_file(repo, "a.txt", "one\n")
    (repo / "a.txt").write_text("two\n")
    assert source_commit(repo) == sha + "-dirty"


def test_untracked_file_is_dirty(tmp_path):
    repo = new_repo(tmp_path / "repo")
    sha = commit_file(repo, "a.txt", "one\n")
    (repo / "new.txt").write_text("hello")
    assert source_commit(repo) == sha + "-dirty"


def test_staged_but_uncommitted_change_is_dirty(tmp_path):
    repo = new_repo(tmp_path / "repo")
    sha = commit_file(repo, "a.txt", "one\n")
    (repo / "b.txt").write_text("hello")
    git(repo, "add", "b.txt")
    assert source_commit(repo) == sha + "-dirty"


def test_deleted_tracked_file_is_dirty(tmp_path):
    repo = new_repo(tmp_path / "repo")
    sha = commit_file(repo, "a.txt", "one\n")
    (repo / "a.txt").unlink()
    assert source_commit(repo) == sha + "-dirty"


def test_returns_to_clean_after_committing_the_change(tmp_path):
    repo = new_repo(tmp_path / "repo")
    commit_file(repo, "a.txt", "one\n")
    (repo / "a.txt").write_text("two\n")
    assert source_commit(repo).endswith("-dirty")
    git(repo, "commit", "-q", "-am", "edit")
    new_sha = git(repo, "rev-parse", "HEAD")
    assert source_commit(repo) == new_sha


def test_gitignored_files_do_not_make_the_tree_dirty(tmp_path):
    repo = new_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text("scratch.log\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore")
    sha = git(repo, "rev-parse", "HEAD")
    (repo / "scratch.log").write_text("noise")
    assert source_commit(repo) == sha


def test_subfolder_of_a_repo_reports_the_repo_commit(tmp_path):
    repo = new_repo(tmp_path / "repo")
    (repo / "sub").mkdir()
    sha = commit_file(repo, "sub/a.txt", "one\n")
    assert source_commit(repo / "sub") == sha


def test_untracked_file_is_dirty_even_when_git_config_hides_untracked_files(tmp_path):
    # status.showUntrackedFiles=no makes a plain `git status --porcelain` print nothing for a new
    # file. source_commit passes --untracked-files=normal, which overrides that config.
    repo = new_repo(tmp_path / "repo")
    sha = commit_file(repo, "a.txt", "one\n")
    git(repo, "config", "status.showUntrackedFiles", "no")
    (repo / "new.txt").write_text("hello")
    assert git(repo, "status", "--porcelain") == ""  # sanity-check: the config really hides it
    assert source_commit(repo) == sha + "-dirty"


def test_a_failing_git_status_counts_as_dirty(tmp_path):
    # A corrupt index makes `git status` exit non-zero, while `git rev-parse HEAD` (which does
    # not read the index) still works. A tree we cannot inspect must not be reported as clean.
    repo = new_repo(tmp_path / "repo")
    sha = commit_file(repo, "a.txt", "one\n")
    (repo / ".git" / "index").write_bytes(b"garbage")
    with pytest.raises(subprocess.CalledProcessError):
        git(repo, "status", "--porcelain")  # sanity-check: the status command really fails
    assert source_commit(repo) == sha + "-dirty"


def test_a_file_name_that_is_not_utf8_makes_the_tree_dirty_instead_of_raising(tmp_path):
    # With core.quotePath=false git prints the raw bytes of a file name. Decoding them as strict
    # UTF-8 used to raise UnicodeDecodeError out of source_commit.
    repo = new_repo(tmp_path / "repo")
    sha = commit_file(repo, "a.txt", "one\n")
    git(repo, "config", "core.quotePath", "false")
    try:
        (repo / os.fsdecode(b"\xff.txt")).write_text("new")
    except OSError:
        pytest.skip("this file system refuses file names that are not valid UTF-8")
    raw = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True)
    assert b"\xff" in raw.stdout  # sanity-check: git prints the raw byte, which UTF-8 cannot read
    assert source_commit(repo) == sha + "-dirty"


@pytest.mark.parametrize(
    "content, mode",
    [
        (b"#!/bin/sh\nexit 0\n", 0o644),  # a script that nobody may execute: PermissionError
        (b"not a program\n", 0o755),  # executable, but no program and no #! line: ENOEXEC
    ],
    ids=["not-executable", "not-a-program"],
)
def test_a_git_that_cannot_be_run_is_uncommitted(tmp_path, monkeypatch, content, mode):
    repo = new_repo(tmp_path / "repo")
    commit_file(repo, "a.txt", "one\n")
    broken = tmp_path / "broken-bin"
    broken.mkdir()
    (broken / "git").write_bytes(content)
    (broken / "git").chmod(mode)
    monkeypatch.setenv("PATH", str(broken))
    assert source_commit(repo) == "uncommitted"


def test_a_change_outside_a_subfolder_still_counts_when_asked_from_the_subfolder(tmp_path):
    # The check covers the whole repository, not just the folder source_commit was pointed at.
    repo = new_repo(tmp_path / "repo")
    (repo / "sub").mkdir()
    (repo / "sub" / "a.txt").write_text("one\n")
    (repo / "top.txt").write_text("one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "files")
    sha = git(repo, "rev-parse", "HEAD")
    (repo / "top.txt").write_text("two\n")
    assert source_commit(repo / "sub") == sha + "-dirty"


# --- 1b. the exporter's own output folder is not part of "the code" ----------------------

EXPORT_FILE = "app/public/data/meta.json"


def commit_tree(repo: Path, files: dict[str, str]) -> str:
    for name, text in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add files")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def exporter_repo(tmp_path):
    """A repo with a committed export, and committed neighbours that look a little like it."""
    repo = new_repo(tmp_path / "repo")
    sha = commit_tree(
        repo,
        {
            "a.txt": "one\n",
            EXPORT_FILE: "{}\n",
            "app/public/data2/x.json": "x\n",  # shares the folder name as a prefix
            "app/public/other.json": "o\n",  # next to the folder
            "data/meta.json": "d\n",  # a different folder with the same last name
            "sub/app/public/data/meta.json": "s\n",  # the same path, but not at the repo root
        },
    )
    return repo, sha


def test_regenerating_the_exported_file_does_not_make_the_tree_dirty(exporter_repo):
    repo, sha = exporter_repo
    (repo / EXPORT_FILE).write_text('{"regenerated": true}\n')
    assert "meta.json" in git(repo, "status", "--porcelain")  # sanity-check: git sees the edit
    assert source_commit(repo) == sha


def test_a_new_file_in_the_export_folder_does_not_make_the_tree_dirty(exporter_repo):
    repo, sha = exporter_repo
    (repo / "app" / "public" / "data" / "later.json").write_text("{}\n")
    assert "later.json" in git(repo, "status", "--porcelain")  # sanity-check
    assert source_commit(repo) == sha


def test_a_staged_change_in_the_export_folder_does_not_make_the_tree_dirty(exporter_repo):
    repo, sha = exporter_repo
    (repo / EXPORT_FILE).write_text('{"staged": true}\n')
    git(repo, "add", EXPORT_FILE)
    assert source_commit(repo) == sha


def test_a_change_elsewhere_is_still_dirty_beside_regenerated_output(exporter_repo):
    repo, sha = exporter_repo
    (repo / EXPORT_FILE).write_text('{"regenerated": true}\n')
    (repo / "a.txt").write_text("two\n")
    assert source_commit(repo) == sha + "-dirty"


@pytest.mark.parametrize(
    "name",
    [
        "app/public/data2/x.json",
        "app/public/other.json",
        "data/meta.json",
        "sub/app/public/data/meta.json",
    ],
)
def test_only_the_export_folder_itself_is_left_out_of_the_check(exporter_repo, name):
    repo, sha = exporter_repo
    (repo / name).write_text("changed\n")
    assert source_commit(repo) == sha + "-dirty"


def test_two_exports_with_a_fixed_source_date_epoch_are_byte_identical(tmp_path):
    # A committed copy of the project: the export tool, the package it imports, and an earlier
    # export. Running the tool rewrites that tracked meta.json, which used to make the next run
    # stamp "-dirty" and so write a different file.
    repo = new_repo(tmp_path / "repo")
    shutil.copytree(REPO / "src", repo / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (repo / "tools").mkdir()
    shutil.copy(REPO / "tools" / "export_app_data.py", repo / "tools" / "export_app_data.py")
    (repo / ".gitignore").write_text("__pycache__/\n")
    exported = repo / EXPORT_FILE
    exported.parent.mkdir(parents=True)
    exported.write_text("{}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "snapshot")
    sha = git(repo, "rev-parse", "HEAD")

    env = {
        **os.environ,
        "SOURCE_DATE_EPOCH": "1700000000",
        "PYTHONPATH": str(repo / "src"),  # the copy, not the real package
        "PYTHONDONTWRITEBYTECODE": "1",  # no stray __pycache__ to make the copy dirty
    }

    def export() -> bytes:
        done = subprocess.run(
            [sys.executable, str(repo / "tools" / "export_app_data.py")],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return exported.read_bytes()

    first = export()
    assert first != b"{}\n"  # sanity-check: the first run really did rewrite the tracked file
    assert "meta.json" in git(repo, "status", "--porcelain")
    second = export()
    assert second == first
    assert json.loads(first)["source_commit"] == sha  # neither run called the tree dirty
    assert json.loads(first)["generated_at"] == "2023-11-14T22:13:20Z"  # 1_700_000_000 s, as above


# --- 1c. SHA-256 repositories ------------------------------------------------------------

def sha256_repo(tmp_path: Path) -> Path:
    probe = tmp_path / "probe"
    probe.mkdir()
    done = subprocess.run(
        ["git", "-C", str(probe), "init", "-q", "--object-format=sha256"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        pytest.skip(f"this git cannot create SHA-256 repositories: {done.stderr.strip()}")
    return new_repo(tmp_path / "repo", object_format="sha256")


def test_a_sha256_repository_gives_a_commit_the_envelope_accepts(tmp_path):
    repo = sha256_repo(tmp_path)
    sha = commit_file(repo, "a.txt", "one\n")
    assert re.fullmatch(r"[0-9a-f]{64}", sha)  # sanity-check: it really is a 64-hex id

    clean = source_commit(repo)
    assert clean == sha
    noon = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    envelope = make_envelope("meta", {}, generated_at=noon, source_commit=clean)
    assert envelope["source_commit"] == sha
    assert validate_envelope(envelope) == []

    (repo / "a.txt").write_text("two\n")
    dirty = source_commit(repo)
    assert dirty == sha + "-dirty"
    assert validate_envelope(make_envelope("meta", {}, generated_at=noon, source_commit=dirty)) == []


# --- 2. build_time -----------------------------------------------------------------------

def test_build_time_honours_source_date_epoch_zero():
    # Epoch 0 is the Unix epoch: 1970-01-01 00:00:00 UTC.
    moment = build_time({"SOURCE_DATE_EPOCH": "0"})
    assert moment == datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert moment.utcoffset().total_seconds() == 0
    assert moment.isoformat() == "1970-01-01T00:00:00+00:00"


def test_build_time_one_day_after_the_epoch():
    # 86400 seconds = 24 * 60 * 60 = exactly one day.
    assert build_time({"SOURCE_DATE_EPOCH": "86400"}) == datetime(1970, 1, 2, tzinfo=UTC)


def test_build_time_known_timestamp():
    # 1_700_000_000 s = 19675 days + 80_000 s. 19675 days after 1970-01-01 is 2023-11-14, and
    # 80_000 s = 22 h (79_200) + 13 min (780) + 20 s, so 22:13:20 UTC.
    assert build_time({"SOURCE_DATE_EPOCH": "1700000000"}) == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_build_time_without_the_variable_is_now_in_utc():
    before = datetime.now(UTC)
    moment = build_time({})
    after = datetime.now(UTC)
    assert moment.utcoffset().total_seconds() == 0
    assert before <= moment <= after


def test_build_time_empty_value_counts_as_unset():
    before = datetime.now(UTC)
    moment = build_time({"SOURCE_DATE_EPOCH": ""})
    assert before <= moment <= datetime.now(UTC)


@pytest.mark.parametrize("bad", ["abc", "1.5", "0x10", "1e3"])
def test_build_time_rejects_a_value_that_is_not_a_whole_number(bad):
    # A malformed value must fail loudly, not quietly fall back to "now".
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        build_time({"SOURCE_DATE_EPOCH": bad})


@pytest.mark.parametrize(
    "bad",
    [
        "1_000",  # a digit separator
        " 5 ",  # surrounding spaces
        "5\n",  # a trailing newline
        "-86400",  # a sign: the spec's format is what `date +%s` prints
        "+5",
        "١٠",  # Arabic-Indic digits
    ],
)
def test_build_time_rejects_what_int_accepts_but_the_spec_does_not(bad):
    # int() turns every one of these into a number (int("١٠") == 10), so only an explicit
    # ASCII-digits check rejects them.
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        build_time({"SOURCE_DATE_EPOCH": bad})


def test_build_time_reads_the_real_environment_by_default(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "86400")
    assert build_time() == datetime(1970, 1, 2, tzinfo=UTC)
