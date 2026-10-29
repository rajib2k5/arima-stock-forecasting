"""Acceptance tests for export.py (the payloads) and tools/export_app_data.py (the thin wrapper
that writes them, and its --check mode). Expected values are literals typed from the agreed JSON
contract, never recomputed by the code under test.

The tool reads a raw snapshot. Every tool test here gets a synthetic one (tests/synthetic.py),
pointed to through VOL_DATA_DIR, so no test downloads anything."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from synthetic import FIXED_NOW, write_synthetic_snapshot

from arima_forecasting import config
from arima_forecasting.contract import SCHEMA_VERSION, dumps, validate_envelope
from arima_forecasting.data import read_snapshot
from arima_forecasting.export import ARTIFACTS, build_payloads, meta_payload

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
        {"id": 0, "slug": "scaffold", "title": "Scaffold, contract and design", "status": "done"},
        {"id": 1, "slug": "data-eda", "title": "Data and EDA", "status": "current"},
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
    "artifacts": ["meta", "prices", "eda"],
    "held_artifacts": ["prices", "eda"],
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


# --- 2. prices and eda payloads from a synthetic snapshot ---------------------------------

@pytest.fixture(scope="module")
def snapshot_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("vol-data")
    write_synthetic_snapshot(root)
    return root


@pytest.fixture(scope="module")
def payloads(snapshot_root):
    return build_payloads(read_snapshot(config.raw_dir({"VOL_DATA_DIR": str(snapshot_root)})))


def test_build_payloads_returns_every_artifact_in_order(payloads):
    assert tuple(payloads) == ARTIFACTS == ("meta", "prices", "eda")
    assert payloads["meta"]["artifacts"] == list(ARTIFACTS)


def test_prices_payload_has_exactly_the_contract_fields(payloads):
    prices = payloads["prices"]
    assert set(prices) == {"ticker", "price_basis", "source", "fill", "splits", "rows"}
    assert prices["ticker"] == "AAPL"
    assert prices["price_basis"] == "adjusted_close"
    assert set(prices["rows"][0]) == {"date", "close_usd", "log_close", "segment"}
    assert prices["fill"] == {"method": "ffill", "filled_dates": []}


def test_prices_source_comes_from_the_manifest_not_the_export_clock(payloads, snapshot_root):
    manifest = read_snapshot(config.raw_dir({"VOL_DATA_DIR": str(snapshot_root)})).manifest
    assert payloads["prices"]["source"] == {
        "provider": "yahoo_via_yfinance",
        "yfinance_version": "1.7.0",
        "raw_sha256": manifest["sha256"],
        "raw_rows": manifest["rows"],
        "downloaded_at": "2026-10-29T12:07:20Z",  # synthetic.FIXED_NOW
        "request": {"start": "2015-01-01", "end_exclusive": "2026-10-01", "interval": "1d", "auto_adjust": True},
    }
    assert FIXED_NOW.isoformat() == "2026-10-29T12:07:20+00:00"


def test_prices_splits_follow_the_90_10_rule_on_the_course_window(payloads):
    # The synthetic calendar is every weekday: 2015-01-01 (a Thursday) to 2023-12-29 is the course.
    course = len(pd.bdate_range("2015-01-01", "2023-12-31"))
    train = course * 9 // 10
    splits = payloads["prices"]["splits"]
    assert splits["train_fraction"] == 0.9
    assert splits["train"]["n"] == train
    assert splits["test"]["n"] == course - train
    assert splits["oos"] == {"start": "2024-01-01", "end": "2026-09-30", "n": len(pd.bdate_range("2024-01-01", "2026-09-30"))}
    assert splits["train"]["start"] == "2015-01-01"
    assert splits["test"]["end"] == "2023-12-29"


def test_eda_describes_the_training_rows_only(payloads):
    eda = payloads["eda"]
    train = payloads["prices"]["splits"]["train"]
    assert eda["sample"] == "train"
    assert (eda["summary"]["n"], eda["summary"]["start"], eda["summary"]["end"]) == (train["n"], train["start"], train["end"])
    assert eda["summary"]["log_return"]["n"] == train["n"] - 1
    assert [k["variable"] for k in eda["kdes"]] == ["log_close", "log_return"]
    assert [len(k["points"]) for k in eda["kdes"]] == [200, 200]
    rows = eda["decomposition"]["rows"]
    assert len(rows) == train["n"]
    assert rows[-1]["date"] == train["end"]  # no test-period date leaks in
    assert (eda["decomposition"]["model"], eda["decomposition"]["period"]) == ("additive", 252)


# --- 3. The export tool: end to end ------------------------------------------------------

def run_tool(out: Path, *args: str, data_root: Path | None, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **extra_env}
    env.pop("VOL_DATA_DIR", None)
    if data_root is not None:
        env["VOL_DATA_DIR"] = str(data_root)
    return subprocess.run(
        [sys.executable, str(TOOL), "--out", str(out), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_tool_writes_three_valid_envelopes(tmp_path, snapshot_root):
    out = tmp_path / "does" / "not" / "exist" / "yet"  # the tool must create missing folders
    done = run_tool(out, data_root=snapshot_root, SOURCE_DATE_EPOCH="0")
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in out.iterdir()) == ["eda.json", "meta.json", "prices.json"]
    for name in ARTIFACTS:
        path = out / f"{name}.json"
        assert str(path) in done.stdout
        text = path.read_text(encoding="utf-8")
        envelope = json.loads(text)
        assert validate_envelope(envelope) == []
        assert envelope["artifact"] == name
        assert envelope["schema_version"] == "1.1.0" == SCHEMA_VERSION
        # SOURCE_DATE_EPOCH=0 must reach every file as the Unix epoch.
        assert envelope["generated_at"] == "1970-01-01T00:00:00Z"
        # The file is in the canonical text form: sorted keys, indent 2, one trailing newline.
        assert text == dumps(envelope)
        assert text.endswith("}\n") and not text.endswith("\n\n")
    assert json.loads((out / "meta.json").read_text())["data"] == EXPECTED_META


def test_tool_overwrites_an_existing_file(tmp_path, snapshot_root):
    (tmp_path / "meta.json").write_text("stale")
    assert run_tool(tmp_path, data_root=snapshot_root, SOURCE_DATE_EPOCH="0").returncode == 0
    assert json.loads((tmp_path / "meta.json").read_text())["artifact"] == "meta"


def test_tool_without_a_snapshot_exits_2_and_writes_nothing(tmp_path):
    done = run_tool(tmp_path / "out", data_root=tmp_path / "empty-data-root")
    assert done.returncode == 2
    assert "tools/fetch_prices.py" in done.stderr
    assert not (tmp_path / "out").exists()


def test_tool_with_a_truncated_manifest_exits_2_with_a_message(tmp_path):
    root = tmp_path / "vol-data"
    folder = write_synthetic_snapshot(root)
    manifest = next(folder.glob("*.manifest.json"))
    manifest.write_text(manifest.read_text()[:40])
    done = run_tool(tmp_path / "out", data_root=root)
    assert done.returncode == 2
    assert "is not valid JSON" in done.stderr and "Traceback" not in done.stderr
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("request_value", [None, "1d", []], ids=["null", "string", "list"])
def test_tool_with_a_manifest_request_that_is_not_an_object_exits_2(tmp_path, request_value):
    root = tmp_path / "vol-data"
    folder = write_synthetic_snapshot(root)
    manifest_path = next(folder.glob("*.manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    manifest["request"] = request_value
    manifest_path.write_text(json.dumps(manifest))
    done = run_tool(tmp_path / "out", data_root=root)
    assert done.returncode == 2
    assert "request is" in done.stderr and "Traceback" not in done.stderr


def test_tool_refuses_a_data_root_inside_the_repo_outside_data(tmp_path):
    done = run_tool(tmp_path / "out", data_root=REPO / "snapshots")
    assert done.returncode == 2
    assert "inside the repository" in done.stderr and "Traceback" not in done.stderr


def test_tool_fails_on_a_malformed_source_date_epoch(tmp_path, snapshot_root):
    done = run_tool(tmp_path / "out", data_root=snapshot_root, SOURCE_DATE_EPOCH="not-a-number")
    assert done.returncode != 0
    assert "SOURCE_DATE_EPOCH" in done.stderr
    assert not (tmp_path / "out").exists()


# --- 4. The check mode -------------------------------------------------------------------

@pytest.fixture
def exported(tmp_path, snapshot_root):
    out = tmp_path / "app-data"
    assert run_tool(out, data_root=snapshot_root, SOURCE_DATE_EPOCH="0").returncode == 0
    return out


def test_check_passes_on_a_fresh_export_and_writes_nothing(exported, snapshot_root):
    before = {p.name: p.read_bytes() for p in exported.iterdir()}
    done = run_tool(exported, "--check", data_root=snapshot_root)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "app data is current: meta, prices, eda" in done.stdout
    assert {p.name: p.read_bytes() for p in exported.iterdir()} == before


def test_check_ignores_generated_at_and_source_commit(exported, snapshot_root):
    # The export above used SOURCE_DATE_EPOCH=0; this check runs at today's time, and a hand edit
    # of the commit must not count either. Only schema_version, artifact and data are compared.
    meta = json.loads((exported / "meta.json").read_text())
    meta["source_commit"] = "f" * 40 + "-dirty"
    (exported / "meta.json").write_text(json.dumps(meta))
    assert run_tool(exported, "--check", data_root=snapshot_root, SOURCE_DATE_EPOCH="1700000000").returncode == 0


def test_check_fails_on_a_changed_value_and_names_where(exported, snapshot_root):
    prices = json.loads((exported / "prices.json").read_text())
    old = prices["data"]["rows"][3]["close_usd"]
    prices["data"]["rows"][3]["close_usd"] = old + 0.01
    (exported / "prices.json").write_text(json.dumps(prices))
    done = run_tool(exported, "--check", data_root=snapshot_root)
    assert done.returncode == 1
    assert f"stale: prices: data.rows[3].close_usd: {old + 0.01} != {old}" in done.stdout
    assert "run: uv run python tools/export_app_data.py" in done.stdout


def test_check_fails_on_a_changed_schema_version(exported, snapshot_root):
    eda = json.loads((exported / "eda.json").read_text())
    eda["schema_version"] = "1.0.0"
    (exported / "eda.json").write_text(json.dumps(eda))
    done = run_tool(exported, "--check", data_root=snapshot_root)
    assert done.returncode == 1
    assert 'stale: eda: schema_version: "1.0.0" != "1.1.0"' in done.stdout


def test_check_says_when_the_snapshot_itself_changed(exported, tmp_path):
    other = tmp_path / "other-data"
    from synthetic import study_frame

    write_synthetic_snapshot(other, study_frame(seed=99))
    done = run_tool(exported, "--check", data_root=other)
    assert done.returncode == 1
    assert "note: the committed prices.json was built from snapshot" in done.stdout


@pytest.mark.parametrize(
    "damage, expected",
    [
        (lambda out: (out / "eda.json").unlink(), "stale: eda: "),
        (lambda out: (out / "aic_grid.json").write_text("{}"), "stale: aic_grid: "),
        (lambda out: (out / "meta.json").write_text("{not json"), "stale: meta: "),
        (lambda out: (out / "meta.json").write_text("[]"), "stale: meta: "),
    ],
    ids=["missing file", "extra file", "not json", "not an object"],
)
def test_check_fails_on_missing_extra_or_broken_files(exported, snapshot_root, damage, expected):
    damage(exported)
    done = run_tool(exported, "--check", data_root=snapshot_root)
    assert done.returncode == 1
    assert expected in done.stdout


@pytest.mark.parametrize(
    "damage, expected",
    [
        (lambda env: env.update(generated_at="yesterday"), "generated_at 'yesterday' must be a real UTC time"),
        (lambda env: env.pop("generated_at"), "missing key: generated_at"),
        (lambda env: env.update(source_commit="HEAD"), "source_commit 'HEAD' must be"),
        (lambda env: env.update(extra=1), "unexpected key: extra"),
    ],
    ids=["garbage generated_at", "missing generated_at", "garbage source_commit", "extra top-level key"],
)
def test_check_fails_on_a_committed_envelope_the_app_would_refuse(exported, snapshot_root, damage, expected):
    # generated_at and source_commit are not COMPARED, but a file the app would refuse is not current.
    meta = json.loads((exported / "meta.json").read_text())
    damage(meta)
    (exported / "meta.json").write_text(json.dumps(meta))
    done = run_tool(exported, "--check", data_root=snapshot_root)
    assert done.returncode == 1
    assert "stale: meta: committed file breaks the contract: " + expected in done.stdout


def test_check_fails_on_a_committed_payload_that_breaks_its_validator(exported, snapshot_root):
    prices = json.loads((exported / "prices.json").read_text())
    prices["data"]["ticker"] = "\u001c"
    (exported / "prices.json").write_text(json.dumps(prices))
    done = run_tool(exported, "--check", data_root=snapshot_root)
    assert done.returncode == 1
    assert "stale: prices: committed file breaks the contract: data.ticker: expected a non-empty string" in done.stdout


def test_check_without_a_snapshot_exits_2_instead_of_passing(exported, tmp_path):
    assert run_tool(exported, "--check", data_root=tmp_path / "nothing-here").returncode == 2


# --- 5. The export tool: wiring (in-process, with the clock and git replaced) ------------

@pytest.fixture
def snapshot_env(monkeypatch, snapshot_root):
    monkeypatch.setenv("VOL_DATA_DIR", str(snapshot_root))


def test_tool_uses_build_time_and_source_commit_for_every_envelope(tmp_path, monkeypatch, snapshot_env):
    tool = load_tool()
    fixed_time = datetime(2031, 5, 6, 7, 8, 9, tzinfo=UTC)
    fixed_commit = "ab" * 20  # 40 hex characters
    monkeypatch.setattr(tool, "build_time", lambda: fixed_time)
    monkeypatch.setattr(tool, "source_commit", lambda repo: fixed_commit)

    assert tool.main(["--out", str(tmp_path)]) == 0

    for name in ARTIFACTS:
        envelope = json.loads((tmp_path / f"{name}.json").read_text())
        assert envelope["generated_at"] == "2031-05-06T07:08:09Z"
        assert envelope["source_commit"] == fixed_commit


def test_tool_asks_git_about_this_repo_not_the_current_folder(tmp_path, monkeypatch, snapshot_env):
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


def test_tool_never_writes_nan_to_disk_and_writes_no_file_at_all(tmp_path, monkeypatch, snapshot_env):
    # The NaN is in the LAST payload, so a tool that wrote each file as it went would already
    # have written meta.json and prices.json.
    tool = load_tool()
    real = tool.build_payloads

    def with_nan(snapshot):
        payloads = real(snapshot)
        payloads["eda"]["summary"]["log_return"]["skew"] = float("nan")
        return payloads

    monkeypatch.setattr(tool, "build_payloads", with_nan)
    monkeypatch.setitem(tool.PAYLOAD_VALIDATORS, "eda", lambda data: [])  # let the NaN reach dumps
    with pytest.raises(ValueError, match="not JSON compliant"):
        tool.main(["--out", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


def test_tool_refuses_to_write_an_envelope_that_fails_validation(tmp_path, monkeypatch, capsys, snapshot_env):
    tool = load_tool()
    monkeypatch.setattr(tool, "validate_envelope", lambda envelope: ["something is wrong"])

    assert tool.main(["--out", str(tmp_path / "out")]) == 1

    assert "meta: something is wrong" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_tool_refuses_a_payload_that_fails_its_validator(tmp_path, monkeypatch, capsys, snapshot_env):
    tool = load_tool()
    monkeypatch.setitem(tool.PAYLOAD_VALIDATORS, "prices", lambda data: ["data.rows: broken on purpose"])

    assert tool.main(["--out", str(tmp_path / "out")]) == 1

    assert "prices: data.rows: broken on purpose" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
