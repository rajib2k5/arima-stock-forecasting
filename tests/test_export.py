"""Acceptance tests for export.py (the "meta" payload) and tools/export_app_data.py (the thin
wrapper that writes it). Expected values are literals typed from the agreed JSON contract, never
recomputed by the code under test."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from arima_forecasting import config
from arima_forecasting.contract import dumps, validate_envelope
from arima_forecasting.export import meta_payload

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "export_app_data.py"
UTC = timezone.utc


def load_tool():
    """Import tools/export_app_data.py by path (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location("export_app_data", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXPECTED_META = {
    "project": "arima-stock-forecasting",
    "title": "ARIMA stock forecasting, done carefully",
    "ticker": "AAPL",
    "windows": {
        "course": {"start": "2015-01-01", "end_exclusive": "2024-01-01"},
        "oos": {"start": "2024-01-01", "end_exclusive": "2026-10-01"},
    },
    "milestones": [
        {"id": 0, "slug": "scaffold", "title": "Scaffold, contract and design", "status": "current"},
        {"id": 1, "slug": "data-eda", "title": "Data and EDA", "status": "planned"},
        {"id": 2, "slug": "stationarity", "title": "Stationarity and identification", "status": "planned"},
        {"id": 3, "slug": "fit-diagnostics", "title": "Fit and diagnostics", "status": "planned"},
        {"id": 4, "slug": "forecast-eval", "title": "Forecast and evaluation", "status": "planned"},
        {
            "id": 5,
            "slug": "where-it-goes-wrong",
            "title": "Where the sample goes wrong, and polish",
            "status": "planned",
        },
    ],
    "artifacts": ["meta"],
}


# --- 1. meta_payload ---------------------------------------------------------------------

def test_meta_payload_matches_the_agreed_contract_exactly():
    assert meta_payload() == EXPECTED_META


def test_meta_payload_windows_equal_the_config_constants():
    windows = meta_payload()["windows"]
    assert set(windows) == {"course", "oos"}
    for key, constant in (("course", config.COURSE_WINDOW), ("oos", config.OOS_WINDOW)):
        assert date.fromisoformat(windows[key]["start"]) == constant.start
        assert date.fromisoformat(windows[key]["end_exclusive"]) == constant.end_exclusive


def test_meta_payload_takes_ticker_and_project_from_config(monkeypatch):
    # If the payload retyped "AAPL" it would ignore this change; derived values follow config.
    import arima_forecasting.export as export

    monkeypatch.setattr(export, "TICKER", "MSFT")
    monkeypatch.setattr(export, "PROJECT_SLUG", "other-project")
    payload = export.meta_payload()
    assert payload["ticker"] == "MSFT"
    assert payload["project"] == "other-project"


def test_meta_payload_milestones_are_numbered_in_order_with_one_current():
    milestones = meta_payload()["milestones"]
    assert [m["id"] for m in milestones] == [0, 1, 2, 3, 4, 5]
    assert len({m["slug"] for m in milestones}) == 6
    assert [m["status"] for m in milestones].count("current") == 1
    assert {m["status"] for m in milestones} <= {"current", "planned", "done"}


def test_meta_payload_is_plain_json_with_no_nan():
    # allow_nan=False makes json.dumps raise on NaN/Infinity, and only dicts, lists, strings and
    # numbers survive a round trip unchanged.
    payload = meta_payload()
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_meta_payload_returns_a_fresh_object_each_call():
    first = meta_payload()
    first["milestones"][0]["status"] = "tampered"
    first["windows"]["course"]["start"] = "1999-01-01"
    assert meta_payload() == EXPECTED_META


# --- 2. The export tool: end to end ------------------------------------------------------

def run_tool(out: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **extra_env}
    return subprocess.run(
        [sys.executable, str(TOOL), "--out", str(out)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_tool_writes_a_valid_meta_envelope(tmp_path):
    out = tmp_path / "does" / "not" / "exist" / "yet"  # the tool must create missing folders
    done = run_tool(out, SOURCE_DATE_EPOCH="0")
    assert done.returncode == 0, done.stderr
    path = out / "meta.json"
    assert path.is_file()
    assert str(path) in done.stdout

    text = path.read_text(encoding="utf-8")
    envelope = json.loads(text)
    assert validate_envelope(envelope) == []
    assert envelope["artifact"] == "meta"
    assert envelope["schema_version"] == "1.0.0"
    assert envelope["data"] == EXPECTED_META
    # SOURCE_DATE_EPOCH=0 must reach the file as the Unix epoch.
    assert envelope["generated_at"] == "1970-01-01T00:00:00Z"
    # The file is in the canonical text form: sorted keys, indent 2, one trailing newline.
    assert text == dumps(envelope)
    assert text.endswith("}\n") and not text.endswith("\n\n")


def test_tool_overwrites_an_existing_file(tmp_path):
    (tmp_path / "meta.json").write_text("stale")
    assert run_tool(tmp_path, SOURCE_DATE_EPOCH="0").returncode == 0
    assert json.loads((tmp_path / "meta.json").read_text())["artifact"] == "meta"


def test_tool_fails_on_a_malformed_source_date_epoch(tmp_path):
    done = run_tool(tmp_path / "out", SOURCE_DATE_EPOCH="not-a-number")
    assert done.returncode != 0
    assert "SOURCE_DATE_EPOCH" in done.stderr
    assert not (tmp_path / "out" / "meta.json").exists()


# --- 3. The export tool: wiring (in-process, with the clock and git replaced) ------------

def test_tool_uses_build_time_and_source_commit_for_the_envelope(tmp_path, monkeypatch):
    tool = load_tool()
    fixed_time = datetime(2031, 5, 6, 7, 8, 9, tzinfo=UTC)
    fixed_commit = "ab" * 20  # 40 hex characters
    monkeypatch.setattr(tool, "build_time", lambda: fixed_time)
    monkeypatch.setattr(tool, "source_commit", lambda repo: fixed_commit)

    assert tool.main(["--out", str(tmp_path)]) == 0

    envelope = json.loads((tmp_path / "meta.json").read_text())
    assert envelope["generated_at"] == "2031-05-06T07:08:09Z"
    assert envelope["source_commit"] == fixed_commit


def test_tool_asks_git_about_this_repo_not_the_current_folder(tmp_path, monkeypatch):
    # Change folder BEFORE importing the tool, so a REPO_ROOT taken from the current folder
    # would be computed from tmp_path, not from the tool file's own location.
    monkeypatch.chdir(tmp_path)
    tool = load_tool()
    seen = []
    monkeypatch.setattr(tool, "source_commit", lambda repo: seen.append(repo) or "uncommitted")

    assert tool.main(["--out", str(tmp_path / "out")]) == 0
    assert seen == [REPO]


def test_tool_default_output_folder_is_app_public_data():
    assert load_tool().DEFAULT_OUT == REPO / "app" / "public" / "data"


def test_tool_never_writes_nan_to_disk(tmp_path, monkeypatch):
    tool = load_tool()
    monkeypatch.setattr(tool, "meta_payload", lambda: {"value": float("nan")})
    with pytest.raises(ValueError, match="not JSON compliant"):
        tool.main(["--out", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


def test_tool_refuses_to_write_an_envelope_that_fails_validation(tmp_path, monkeypatch, capsys):
    tool = load_tool()
    monkeypatch.setattr(tool, "validate_envelope", lambda envelope: ["something is wrong"])

    assert tool.main(["--out", str(tmp_path / "out")]) == 1

    assert "something is wrong" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
