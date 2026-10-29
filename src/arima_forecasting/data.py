"""Get the daily prices once, keep them as a snapshot with a manifest, and read them back.

This module does I/O: it writes and reads files under `raw_dir()`, and `yfinance_download` talks to
Yahoo. The network call is a parameter of `acquire`, so tests pass a fake and never touch the
network. Everything after the snapshot (cleaning, logs, the split, EDA) is pure and lives in
prep.py and eda.py.

Why a snapshot. Yahoo back-adjusts its history: a new dividend re-scales every earlier adjusted
close. Two downloads made months apart therefore disagree. We download once, write the bytes to
disk, and record their SHA-256 in a manifest. Every later step reads that file, and the `prices`
artifact repeats the SHA-256, so a reader can tell which snapshot produced the numbers.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from arima_forecasting.config import DOWNLOAD_WINDOW, TICKER

# The columns yfinance 1.7.0 returns for one ticker with auto_adjust=True and actions=False. The set
# is closed on purpose: "Adj Close" here would mean auto_adjust was off, so "Close" would not be the
# adjusted close the contract promises; "Dividends" would mean actions were on.
PRICE_COLUMNS = ("Open", "High", "Low", "Close", "Volume")

MANIFEST_VERSION = 1
PROVIDER = "yahoo_via_yfinance"

# The exact keyword arguments passed to yfinance.download: all 19 of its parameters, spelled out
# even where they equal the default, because a default can change between yfinance versions. A
# test checks that these keys are exactly the parameter names of the installed yfinance.download.
# They are written into the manifest, so the snapshot says how it was made, and read_snapshot
# refuses a snapshot whose manifest records a different request.
#   start, end         end is exclusive, so 2026-10-01 means "up to and including 2026-09-30".
#   period=None        with start and end given, yfinance ignores period; None is what its own
#                      default sentinel resolves to in that case (yfinance/scrapers/history.py).
#   session=None       yfinance then makes its own HTTP session.
#   auto_adjust=True   Close is the split- and dividend-adjusted close; no "Adj Close" column.
#   multi_level_index  True is the 1.7.0 default: columns are (Price, Ticker) even for one ticker,
#                      so frame["Close"] is a one-column DataFrame. normalize_download flattens it.
#   keepna=False       Yahoo rows whose prices and volume are all missing are dropped.
#   progress=False     no progress bar on stdout.
DOWNLOAD_REQUEST: Mapping[str, Any] = {
    "tickers": TICKER,
    "start": DOWNLOAD_WINDOW.start.isoformat(),
    "end": DOWNLOAD_WINDOW.end_exclusive.isoformat(),
    "interval": "1d",
    "auto_adjust": True,
    "back_adjust": False,
    "actions": False,
    "repair": False,
    "keepna": False,
    "rounding": False,
    "prepost": False,
    "ignore_tz": True,
    "group_by": "column",
    "multi_level_index": True,
    "threads": False,
    "progress": False,
    "timeout": 30,
    "period": None,
    "session": None,
}

# Every key a manifest must have. read_snapshot refuses a manifest that lacks one, so a damaged
# manifest is reported as a SnapshotError (exit 2 in the exporter), never as a traceback.
MANIFEST_KEYS = frozenset(
    {
        "manifest_version",
        "provider",
        "file",
        "sha256",
        "rows",
        "first_date",
        "last_date",
        "downloaded_at",
        "yfinance_version",
        "pandas_version",
        "request",
        "columns_as_downloaded",
    }
)


class SnapshotError(RuntimeError):
    """The snapshot is missing, incomplete, or does not match its manifest."""


class DownloadError(RuntimeError):
    """yfinance returned something we cannot use. We never fall back to partial data."""


@dataclass(frozen=True)
class Snapshot:
    """The prices as downloaded (flat columns, one row per trading day) and their manifest."""

    frame: pd.DataFrame
    manifest: dict[str, Any]


def snapshot_paths(folder: Path) -> tuple[Path, Path]:
    """(csv, manifest) for this project's snapshot inside `folder`. Builds paths only."""
    stem = (
        f"{TICKER}_{DOWNLOAD_REQUEST['interval']}_"
        f"{DOWNLOAD_REQUEST['start']}_{DOWNLOAD_REQUEST['end']}"
    )
    return folder / f"{stem}.csv", folder / f"{stem}.manifest.json"


def normalize_download(frame: object, ticker: str = TICKER) -> pd.DataFrame:
    """Turn what yfinance returned into a flat frame with exactly the five price columns.

    This is the guard against the MultiIndex trap. yfinance 1.7.0 returns (Price, Ticker) columns
    even for a single ticker, so `frame["Close"]` is a DataFrame with one column, not a Series.
    Arithmetic between that DataFrame and a Series aligns the Series' index with the DataFrame's
    columns and gives all NaN. We drop the Ticker level here, once, after checking that it holds
    exactly the ticker we asked for.

    It also refuses an empty frame. On a failed request yfinance prints an error and returns an
    empty frame instead of raising, and an empty frame must never become an empty study.
    """
    if not isinstance(frame, pd.DataFrame):
        raise DownloadError(f"yfinance returned {type(frame).__name__}, not a DataFrame")
    if frame.empty:
        raise DownloadError(
            "yfinance returned no rows; it prints its own error and returns an empty frame "
            "instead of raising"
        )

    columns = frame.columns
    if isinstance(columns, pd.MultiIndex):
        if columns.nlevels != 2 or "Ticker" not in columns.names:
            raise DownloadError(
                f"expected (Price, Ticker) columns, got levels {list(columns.names)}"
            )
        tickers = sorted(set(columns.get_level_values("Ticker")))
        if tickers != [ticker]:
            raise DownloadError(f"expected columns for {ticker!r} only, got tickers {tickers}")
        flat = frame.droplevel("Ticker", axis=1)
    else:
        flat = frame.copy()

    names = [str(name) for name in flat.columns]
    if len(set(names)) != len(names):
        # Two "Close" columns would make flat["Close"] a DataFrame again.
        raise DownloadError(f"duplicate column names: {names}")
    if set(names) != set(PRICE_COLUMNS):
        raise DownloadError(
            f"expected exactly the columns {list(PRICE_COLUMNS)}, got {names}"
            + (
                "; 'Adj Close' means auto_adjust was off, so Close is not the adjusted close"
                if "Adj Close" in names
                else ""
            )
        )
    flat.columns = names
    flat = flat[list(PRICE_COLUMNS)]

    index = flat.index
    if not isinstance(index, pd.DatetimeIndex):
        raise DownloadError(f"expected a DatetimeIndex, got {type(index).__name__}")
    if index.tz is not None:
        raise DownloadError(f"expected trading dates without a time zone, got tz={index.tz}")
    if not (index == index.normalize()).all():
        raise DownloadError("expected one bar per date at midnight; found a time of day")
    if index.has_duplicates:
        raise DownloadError(f"duplicate dates: {sorted(set(index[index.duplicated()].date))}")
    if not index.is_monotonic_increasing:
        raise DownloadError("dates are not in ascending order")
    flat.index = index.rename("Date")

    close = flat["Close"]
    if not isinstance(close, pd.Series):  # pragma: no cover - the duplicate check above prevents it
        raise DownloadError("Close is not a single column")
    return flat


def snapshot_bytes(frame: pd.DataFrame) -> bytes:
    """The exact bytes of the snapshot file: CSV, ISO dates, '\\n' line ends, shortest floats.

    pandas writes each float with Python's shortest round-trip repr, and pandas 3.1's reader parses
    it back to the same 64-bit float (measured on 200,000 random values; tests pin it).
    """
    buffer = io.StringIO()
    frame.to_csv(buffer, index_label="Date", date_format="%Y-%m-%d", lineterminator="\n")
    return buffer.getvalue().encode("utf-8")


def parse_snapshot(raw: bytes) -> pd.DataFrame:
    """Read snapshot bytes back into the flat frame that `snapshot_bytes` wrote."""
    frame = pd.read_csv(io.BytesIO(raw), index_col="Date", parse_dates=["Date"])
    return normalize_download(frame)


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utc_stamp(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("downloaded_at must be timezone-aware")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_manifest(
    raw: bytes,
    frame: pd.DataFrame,
    *,
    columns_as_downloaded: list[list[str]],
    downloaded_at: datetime,
    yfinance_version: str,
) -> dict[str, Any]:
    """The manifest that sits beside the snapshot. Pure: the caller passes the time and version."""
    csv_path, _ = snapshot_paths(Path("."))
    return {
        "manifest_version": MANIFEST_VERSION,
        "provider": PROVIDER,
        "file": csv_path.name,
        "sha256": sha256_hex(raw),
        "rows": int(len(frame)),
        "first_date": frame.index[0].date().isoformat(),
        "last_date": frame.index[-1].date().isoformat(),
        "downloaded_at": _utc_stamp(downloaded_at),
        "yfinance_version": yfinance_version,
        "pandas_version": pd.__version__,
        "request": dict(DOWNLOAD_REQUEST),
        "columns_as_downloaded": columns_as_downloaded,
    }


def _write_atomically(path: Path, raw: bytes) -> None:
    # Write a temporary file next to the target, then rename it over the target. A crash midway
    # leaves the old file or the new one, never half of one.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def write_snapshot(folder: Path, raw: bytes, manifest: Mapping[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    csv_path, manifest_path = snapshot_paths(folder)
    # The CSV goes first and the manifest last. If we stop between the two, the old manifest's
    # SHA-256 no longer matches the new CSV, and read_snapshot refuses the pair.
    _write_atomically(csv_path, raw)
    text = json.dumps(dict(manifest), sort_keys=True, indent=2) + "\n"
    _write_atomically(manifest_path, text.encode("utf-8"))


def read_snapshot(folder: Path) -> Snapshot:
    """Read the snapshot and check it against its manifest, or raise SnapshotError."""
    csv_path, manifest_path = snapshot_paths(folder)
    missing = [p for p in (csv_path, manifest_path) if not p.is_file()]
    if missing:
        raise SnapshotError(
            "no complete snapshot: missing "
            + ", ".join(str(p) for p in missing)
            + ". Run: uv run python tools/fetch_prices.py"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotError(f"{manifest_path.name} is not valid JSON ({error}); download again with --refresh") from error
    if not isinstance(manifest, dict) or not MANIFEST_KEYS <= manifest.keys():
        missing_keys = sorted(MANIFEST_KEYS - (manifest.keys() if isinstance(manifest, dict) else set()))
        raise SnapshotError(f"{manifest_path.name} lacks {missing_keys}; download again with --refresh")
    # The types the checks below rely on. A wrong type is a damaged manifest, not a crash.
    for key, kind, label in (("request", dict, "an object"), ("rows", int, "an integer"), ("sha256", str, "a string")):
        if not isinstance(manifest[key], kind) or isinstance(manifest[key], bool):
            raise SnapshotError(
                f"{manifest_path.name}: {key} is {type(manifest[key]).__name__}, not {label}; "
                "download again with --refresh"
            )
    if manifest["request"] != dict(DOWNLOAD_REQUEST):
        # The snapshot was made with other yfinance arguments (an older version of this code, or
        # an edited manifest). Its data may not mean what DOWNLOAD_REQUEST promises.
        changed = sorted(
            key
            for key in set(manifest["request"]) | set(DOWNLOAD_REQUEST)
            if manifest["request"].get(key, "<absent>") != DOWNLOAD_REQUEST.get(key, "<absent>")
        )
        raise SnapshotError(
            f"{manifest_path.name} records a different download request (keys {changed}); "
            "download again with: uv run python tools/fetch_prices.py --refresh"
        )
    raw = csv_path.read_bytes()
    digest = sha256_hex(raw)
    if digest != manifest.get("sha256"):
        raise SnapshotError(
            f"{csv_path.name} has SHA-256 {digest}, but its manifest says "
            f"{manifest.get('sha256')}; the file changed after it was downloaded"
        )
    frame = parse_snapshot(raw)
    if len(frame) != manifest.get("rows"):
        raise SnapshotError(f"{csv_path.name} has {len(frame)} rows; manifest says {manifest.get('rows')}")
    return Snapshot(frame=frame, manifest=manifest)


def acquire(
    folder: Path,
    *,
    download: Callable[..., object],
    now: Callable[[], datetime],
    yfinance_version: str,
    refresh: bool = False,
) -> tuple[Snapshot, bool]:
    """Return (snapshot, reused). Reuse the snapshot on disk unless `refresh` is true.

    `download` is called with DOWNLOAD_REQUEST as keyword arguments; the real one is
    `yfinance_download`. It is called only when there is no snapshot yet or `refresh` is true. On
    a refresh the new data is downloaded and checked before anything is written, so a failed
    refresh leaves the old snapshot as it was.
    """
    csv_path, manifest_path = snapshot_paths(folder)
    if not refresh and (csv_path.exists() or manifest_path.exists()):
        # Half a snapshot is an error, not a reason to download again silently.
        return read_snapshot(folder), True

    downloaded = download(**DOWNLOAD_REQUEST)
    frame = normalize_download(downloaded)
    columns = downloaded.columns  # type: ignore[union-attr]  # normalize_download checked the type
    as_downloaded = [
        [str(part) for part in (col if isinstance(col, tuple) else (col,))] for col in columns
    ]
    raw = snapshot_bytes(frame)
    manifest = build_manifest(
        raw,
        frame,
        columns_as_downloaded=as_downloaded,
        downloaded_at=now(),
        yfinance_version=yfinance_version,
    )
    write_snapshot(folder, raw, manifest)
    # Read back what was written, so the caller gets exactly what every later step will read.
    return read_snapshot(folder), False


def yfinance_download(cache_folder: Path) -> Callable[..., object]:
    """The real download: yfinance.download, with yfinance's own caches kept in `cache_folder`."""

    def run(**request: Any) -> object:
        import yfinance  # imported here so that importing this module never needs the network stack

        cache_folder.mkdir(parents=True, exist_ok=True)
        yfinance.set_tz_cache_location(str(cache_folder))
        with warnings.catch_warnings():
            # yfinance 1.7.0 itself calls pandas methods with inplace=True, which pandas 3.1
            # deprecates; ten such warnings per download say nothing about our data.
            warnings.filterwarnings("ignore", message="The inplace keyword", module=r"yfinance\.")
            return yfinance.download(**request)

    return run
