"""Synthetic price frames shaped like yfinance 1.7.0's output. No test ever touches the network.

`yf_frame` builds what `yfinance.download("AAPL", auto_adjust=True)` returns for one ticker: a
DatetimeIndex named "Date" with no time zone, and two-level (Price, Ticker) columns in yfinance's
own order, Close, High, Low, Open, Volume (alphabetical, from `sort_index(level=0, axis=1)` in
yfinance/multi.py). The real snapshot's manifest records exactly these columns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from arima_forecasting import data
from arima_forecasting.config import DOWNLOAD_WINDOW

YF_COLUMNS = ("Close", "High", "Low", "Open", "Volume")
FIXED_NOW = datetime(2026, 10, 29, 12, 7, 20, tzinfo=timezone.utc)


def yf_frame(dates, closes, ticker: str = "AAPL") -> pd.DataFrame:
    closes = np.asarray(closes, dtype="float64")
    index = pd.DatetimeIndex(pd.to_datetime(list(dates)), name="Date")
    values = {
        "Close": closes,
        "High": closes * 1.01,
        "Low": closes * 0.99,
        "Open": closes,
        "Volume": np.arange(len(closes), dtype="int64") * 1000 + 1_000_000,
    }
    columns = pd.MultiIndex.from_tuples([(name, ticker) for name in YF_COLUMNS], names=["Price", "Ticker"])
    return pd.DataFrame({col: values[col[0]] for col in columns}, index=index, columns=columns)


def study_dates() -> pd.DatetimeIndex:
    """Every weekday of the download window. No holidays, so the longest gap is a weekend."""
    return pd.bdate_range(DOWNLOAD_WINDOW.start, DOWNLOAD_WINDOW.end_exclusive, inclusive="left")


def random_walk(n: int, seed: int = 20261029, start: float = 25.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(0.0008 + 0.018 * rng.standard_normal(n)))


def study_frame(seed: int = 20261029) -> pd.DataFrame:
    dates = study_dates()
    return yf_frame(dates, random_walk(len(dates), seed))


def write_synthetic_snapshot(root: Path, frame: pd.DataFrame | None = None) -> Path:
    """Write a snapshot under `<root>/arima-stock-forecasting/raw` with a fake download.

    Returns the raw folder. Use `{"VOL_DATA_DIR": str(root)}` as the environment of a tool run.
    """
    folder = root / "arima-stock-forecasting" / "raw"
    downloaded = study_frame() if frame is None else frame
    data.acquire(folder, download=lambda **_: downloaded, now=lambda: FIXED_NOW, yfinance_version="1.7.0")
    return folder
