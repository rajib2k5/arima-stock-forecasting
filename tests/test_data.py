"""Tests for data.py: the MultiIndex guard, the snapshot file, its manifest and `acquire`.

Every frame here is synthetic and shaped like yfinance 1.7.0's output (tests/synthetic.py). The
download is a fake passed to `acquire`, so nothing touches the network.
"""

from __future__ import annotations

import hashlib
import json
import sys
import types
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from synthetic import FIXED_NOW, YF_COLUMNS, study_frame, yf_frame

from arima_forecasting import data
from arima_forecasting.data import (
    DOWNLOAD_REQUEST,
    DownloadError,
    SnapshotError,
    acquire,
    normalize_download,
    parse_snapshot,
    read_snapshot,
    snapshot_bytes,
    snapshot_paths,
)

DATES = ["2015-01-02", "2015-01-05", "2015-01-06"]


def fake_download(frame, calls=None):
    def run(**request):
        if calls is not None:
            calls.append(request)
        return frame

    return run


def never(**_):
    raise AssertionError("download must not be called")


# --- 1. The MultiIndex trap and its guard -----------------------------------------------

def test_the_multiindex_trap_is_real_on_a_yfinance_shaped_frame():
    # Sanity-check of the fixture, and the trap itself: under yfinance 1.7.0's default columns,
    # frame["Close"] is a one-column DataFrame, and a Series minus it is all NaN.
    frame = yf_frame(DATES, [10.0, 11.0, 12.0])
    close = frame["Close"]
    assert isinstance(close, pd.DataFrame)
    assert list(close.columns) == ["AAPL"]
    aligned = pd.Series([1.0, 2.0, 3.0], index=frame.index) - close
    assert aligned.shape == (3, 4)  # 3 dates x (the column "AAPL" + the three dates as columns)
    assert aligned.isna().all().all()


def test_normalize_flattens_the_ticker_level_so_close_is_a_series():
    frame = normalize_download(yf_frame(DATES, [10.0, 11.0, 12.0]))
    assert isinstance(frame["Close"], pd.Series)
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame["Close"].tolist() == [10.0, 11.0, 12.0]
    assert frame.index.name == "Date"


def test_normalize_accepts_a_flat_frame_too():
    flat = yf_frame(DATES, [10.0, 11.0, 12.0]).droplevel("Ticker", axis=1)
    assert normalize_download(flat)["Close"].tolist() == [10.0, 11.0, 12.0]


def test_normalize_refuses_an_empty_frame_because_yfinance_does_not_raise():
    empty = yf_frame([], [])
    with pytest.raises(DownloadError, match="no rows"):
        normalize_download(empty)


@pytest.mark.parametrize("value", [None, [], "AAPL"])
def test_normalize_refuses_something_that_is_not_a_frame(value):
    with pytest.raises(DownloadError, match="not a DataFrame"):
        normalize_download(value)


def test_normalize_refuses_two_tickers_and_a_different_ticker():
    two = pd.concat([yf_frame(DATES, [1.0, 2.0, 3.0]), yf_frame(DATES, [4.0, 5.0, 6.0], "MSFT")], axis=1)
    with pytest.raises(DownloadError, match=r"tickers \['AAPL', 'MSFT'\]"):
        normalize_download(two)
    with pytest.raises(DownloadError, match=r"tickers \['MSFT'\]"):
        normalize_download(yf_frame(DATES, [4.0, 5.0, 6.0], "MSFT"))


def test_normalize_refuses_adj_close_because_then_close_is_not_adjusted():
    flat = yf_frame(DATES, [1.0, 2.0, 3.0]).droplevel("Ticker", axis=1)
    flat["Adj Close"] = flat["Close"]
    with pytest.raises(DownloadError, match="auto_adjust was off"):
        normalize_download(flat)


def test_normalize_refuses_a_missing_column_and_unknown_levels():
    flat = yf_frame(DATES, [1.0, 2.0, 3.0]).droplevel("Ticker", axis=1).drop(columns="Volume")
    with pytest.raises(DownloadError, match="expected exactly the columns"):
        normalize_download(flat)
    other = yf_frame(DATES, [1.0, 2.0, 3.0])
    other.columns = other.columns.set_names(["Price", "Symbol"])
    with pytest.raises(DownloadError, match="expected \\(Price, Ticker\\) columns"):
        normalize_download(other)


def test_normalize_refuses_duplicate_column_names():
    flat = yf_frame(DATES, [1.0, 2.0, 3.0]).droplevel("Ticker", axis=1)
    doubled = pd.concat([flat, flat[["Close"]]], axis=1)
    assert isinstance(doubled["Close"], pd.DataFrame)  # sanity-check: the trap again, flat this time
    with pytest.raises(DownloadError, match="duplicate column names"):
        normalize_download(doubled)


@pytest.mark.parametrize(
    "dates, message",
    [
        (["2015-01-02", "2015-01-02", "2015-01-05"], "duplicate dates"),
        (["2015-01-05", "2015-01-02", "2015-01-06"], "not in ascending order"),
        (["2015-01-02 09:30", "2015-01-05 00:00", "2015-01-06 00:00"], "time of day"),
    ],
)
def test_normalize_refuses_a_bad_date_index(dates, message):
    with pytest.raises(DownloadError, match=message):
        normalize_download(yf_frame(dates, [1.0, 2.0, 3.0]))


def test_normalize_refuses_a_time_zone_and_a_non_date_index():
    zoned = yf_frame(DATES, [1.0, 2.0, 3.0])
    zoned.index = zoned.index.tz_localize("America/New_York")
    with pytest.raises(DownloadError, match="time zone"):
        normalize_download(zoned)
    numbered = yf_frame(DATES, [1.0, 2.0, 3.0]).reset_index(drop=True)
    with pytest.raises(DownloadError, match="DatetimeIndex"):
        normalize_download(numbered)


# --- 2. The snapshot file ----------------------------------------------------------------

def test_snapshot_bytes_exact_text():
    frame = normalize_download(yf_frame(DATES[:2], [1.25, 2.5]))
    assert snapshot_bytes(frame).decode() == (
        "Date,Open,High,Low,Close,Volume\n"
        "2015-01-02,1.25,1.2625,1.2375,1.25,1000000\n"
        "2015-01-05,2.5,2.525,2.475,2.5,1001000\n"
    )


def test_snapshot_round_trips_every_float_bit_for_bit():
    # 17 significant digits is what a double needs; random values exercise every digit position.
    rng = np.random.default_rng(7)
    closes = rng.random(5000) * 300
    dates = pd.bdate_range("2015-01-02", periods=5000)
    frame = normalize_download(yf_frame(dates, closes))
    back = parse_snapshot(snapshot_bytes(frame))
    assert np.array_equal(back["Close"].to_numpy(), frame["Close"].to_numpy())
    assert np.array_equal(back["High"].to_numpy(), frame["High"].to_numpy())
    assert back.index.equals(frame.index)


def test_snapshot_paths_name_the_ticker_interval_and_window(tmp_path):
    csv, manifest = snapshot_paths(tmp_path)
    assert csv == tmp_path / "AAPL_1d_2015-01-01_2026-10-01.csv"
    assert manifest == tmp_path / "AAPL_1d_2015-01-01_2026-10-01.manifest.json"


# --- 3. acquire: download once, reuse, refresh ---------------------------------------------

def test_acquire_downloads_once_with_the_explicit_request_and_writes_a_manifest(tmp_path):
    calls = []
    frame = study_frame()
    snapshot, reused = acquire(tmp_path, download=fake_download(frame, calls), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    assert reused is False
    assert calls == [dict(DOWNLOAD_REQUEST)]
    request = calls[0]
    assert request["auto_adjust"] is True and request["multi_level_index"] is True
    assert (request["start"], request["end"], request["interval"]) == ("2015-01-01", "2026-10-01", "1d")

    csv, manifest_path = snapshot_paths(tmp_path)
    raw = csv.read_bytes()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["rows"] == len(frame) == len(snapshot.frame)
    assert manifest["downloaded_at"] == "2026-10-29T12:07:20Z"
    assert manifest["yfinance_version"] == "1.7.0"
    assert manifest["request"] == dict(DOWNLOAD_REQUEST)
    assert manifest["columns_as_downloaded"] == [[name, "AAPL"] for name in YF_COLUMNS]
    assert manifest["first_date"] == "2015-01-01"  # a Thursday: the synthetic calendar has no holidays
    assert manifest["last_date"] == str(frame.index[-1].date())
    assert snapshot.manifest == manifest


def test_acquire_reuses_the_snapshot_without_calling_download(tmp_path):
    first, _ = acquire(tmp_path, download=fake_download(study_frame()), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    again, reused = acquire(tmp_path, download=never, now=lambda: FIXED_NOW, yfinance_version="9.9.9")
    assert reused is True
    assert again.manifest == first.manifest
    assert again.frame.equals(first.frame)


def test_refresh_downloads_again_and_replaces_the_snapshot(tmp_path):
    acquire(tmp_path, download=fake_download(study_frame(seed=1)), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    old = snapshot_paths(tmp_path)[0].read_bytes()
    _, reused = acquire(tmp_path, download=fake_download(study_frame(seed=2)), now=lambda: FIXED_NOW, yfinance_version="1.7.0", refresh=True)
    assert reused is False
    assert snapshot_paths(tmp_path)[0].read_bytes() != old


def test_a_failed_refresh_keeps_the_old_snapshot(tmp_path):
    acquire(tmp_path, download=fake_download(study_frame()), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    csv, manifest = snapshot_paths(tmp_path)
    before = (csv.read_bytes(), manifest.read_bytes())
    with pytest.raises(DownloadError, match="no rows"):
        acquire(tmp_path, download=fake_download(yf_frame([], [])), now=lambda: FIXED_NOW, yfinance_version="1.7.0", refresh=True)
    assert (csv.read_bytes(), manifest.read_bytes()) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([csv.name, manifest.name])  # no .tmp left


def test_half_a_snapshot_is_an_error_not_a_reason_to_download(tmp_path):
    acquire(tmp_path, download=fake_download(study_frame()), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    snapshot_paths(tmp_path)[1].unlink()
    with pytest.raises(SnapshotError, match="manifest.json"):
        acquire(tmp_path, download=never, now=lambda: FIXED_NOW, yfinance_version="1.7.0")


def test_read_snapshot_refuses_a_file_that_changed_after_download(tmp_path):
    acquire(tmp_path, download=fake_download(study_frame()), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    csv = snapshot_paths(tmp_path)[0]
    text = csv.read_text()
    csv.write_text(text.replace("\n2015-01-05,", "\n2015-01-05,0", 1))
    with pytest.raises(SnapshotError, match="SHA-256"):
        read_snapshot(tmp_path)


def test_read_snapshot_refuses_a_row_count_that_disagrees_with_the_manifest(tmp_path):
    acquire(tmp_path, download=fake_download(study_frame()), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    manifest_path = snapshot_paths(tmp_path)[1]
    manifest = json.loads(manifest_path.read_text())
    manifest["rows"] += 1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SnapshotError, match="rows"):
        read_snapshot(tmp_path)


def test_download_request_names_exactly_the_parameters_of_yfinance_download():
    # Every argument is explicit: a key missing here would silently take yfinance's default, and a
    # key yfinance does not know would fail at download time. Reads the installed signature.
    import inspect

    import yfinance

    assert set(DOWNLOAD_REQUEST) == set(inspect.signature(yfinance.download).parameters)
    assert len(DOWNLOAD_REQUEST) == 19
    assert DOWNLOAD_REQUEST["period"] is None and DOWNLOAD_REQUEST["session"] is None


@pytest.mark.parametrize(
    "edit, changed",
    [
        (lambda r: r.update(interval="1wk"), "['interval']"),
        (lambda r: r.update(repair=True), "['repair']"),
        (lambda r: r.pop("period"), "['period']"),
    ],
)
def test_reuse_refuses_a_manifest_made_with_another_request(tmp_path, edit, changed):
    acquire(tmp_path, download=fake_download(study_frame()), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    manifest_path = snapshot_paths(tmp_path)[1]
    manifest = json.loads(manifest_path.read_text())
    edit(manifest["request"])
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SnapshotError, match=r"different download request \(keys " + changed.replace("[", r"\[").replace("]", r"\]")):
        acquire(tmp_path, download=never, now=lambda: FIXED_NOW, yfinance_version="1.7.0")


@pytest.mark.parametrize(
    "text, message",
    [
        ('{"sha256": "ab', "not valid JSON"),
        ("[]", "lacks"),
        ('{"sha256": "x"}', "lacks"),
    ],
    ids=["truncated", "not an object", "missing keys"],
)
def test_a_damaged_manifest_is_a_snapshot_error_not_a_traceback(tmp_path, text, message):
    acquire(tmp_path, download=fake_download(study_frame()), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    snapshot_paths(tmp_path)[1].write_text(text)
    with pytest.raises(SnapshotError, match=message):
        read_snapshot(tmp_path)


def test_read_snapshot_says_how_to_create_a_missing_snapshot(tmp_path):
    with pytest.raises(SnapshotError, match="tools/fetch_prices.py"):
        read_snapshot(tmp_path)


def test_the_manifest_refuses_a_naive_download_time(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        acquire(tmp_path, download=fake_download(study_frame()), now=lambda: datetime(2026, 10, 29), yfinance_version="1.7.0")


# --- 4. The real download wrapper, with yfinance replaced -----------------------------------

def test_yfinance_download_keeps_yfinance_caches_in_the_given_folder(tmp_path, monkeypatch):
    seen = {}
    fake = types.ModuleType("yfinance")
    fake.set_tz_cache_location = lambda folder: seen.setdefault("cache", folder)
    fake.download = lambda **request: seen.setdefault("request", request) and "frame"
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    run = data.yfinance_download(tmp_path / "cache")
    assert run(**DOWNLOAD_REQUEST) == "frame"
    assert seen["cache"] == str(tmp_path / "cache")
    assert (tmp_path / "cache").is_dir()
    assert seen["request"] == dict(DOWNLOAD_REQUEST)


# --- 5. tools/fetch_prices.py, with the download replaced --------------------------------

def load_fetch_tool():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "tools" / "fetch_prices.py"
    spec = importlib.util.spec_from_file_location("fetch_prices", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_tool_downloads_then_reuses(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path))
    tool = load_fetch_tool()
    calls = []
    monkeypatch.setattr(tool, "yfinance_download", lambda cache: fake_download(study_frame(), calls))
    assert tool.main([]) == 0
    first = capsys.readouterr().out
    assert first.startswith("downloaded " + str(tmp_path / "arima-stock-forecasting" / "raw"))
    assert tool.main([]) == 0
    assert capsys.readouterr().out.startswith("reused ")
    assert len(calls) == 1  # the second run reused the snapshot
    assert tool.main(["--refresh"]) == 0
    assert len(calls) == 2


def test_fetch_tool_reports_a_failed_download_and_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path))
    tool = load_fetch_tool()
    monkeypatch.setattr(tool, "yfinance_download", lambda cache: fake_download(yf_frame([], [])))
    assert tool.main([]) == 1
    assert "no rows" in capsys.readouterr().err
    assert not (tmp_path / "arima-stock-forecasting" / "raw").exists()


def test_fetch_tool_refuses_a_data_root_inside_the_repo(monkeypatch, capsys):
    from arima_forecasting.config import REPO_ROOT

    monkeypatch.setenv("VOL_DATA_DIR", str(REPO_ROOT / "snapshots"))
    tool = load_fetch_tool()
    monkeypatch.setattr(tool, "yfinance_download", lambda cache: never)
    assert tool.main([]) == 1
    assert "inside the repository" in capsys.readouterr().err
    assert not (REPO_ROOT / "snapshots").exists()


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("request", None, "request is NoneType, not an object"),
        ("request", "1d", "request is str, not an object"),
        ("request", [], "request is list, not an object"),
        ("rows", "2953", "rows is str, not an integer"),
        ("rows", True, "rows is bool, not an integer"),
        ("sha256", None, "sha256 is NoneType, not a string"),
    ],
)
def test_a_manifest_field_of_the_wrong_type_is_a_snapshot_error(tmp_path, key, value, message):
    # Found by the milestone-1 re-review: "request": null crashed with a TypeError (exit 1).
    acquire(tmp_path, download=fake_download(study_frame()), now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    manifest_path = snapshot_paths(tmp_path)[1]
    manifest = json.loads(manifest_path.read_text())
    manifest[key] = value
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SnapshotError, match=message):
        read_snapshot(tmp_path)
