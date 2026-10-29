"""What goes into the JSON files the web app reads. Pure: builds dicts, writes nothing.

`tools/export_app_data.py` is the thin wrapper that wraps these payloads in the envelope
(see contract.py) and writes them to disk. The field-by-field description of every payload is
docs/architecture/contract.md, section 3.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

import pandas as pd

from arima_forecasting import eda
from arima_forecasting.config import (
    COURSE_WINDOW,
    OOS_WINDOW,
    PROJECT_SLUG,
    TICKER,
    TRAIN_FRACTION,
    StudyWindow,
)
from arima_forecasting.data import PROVIDER, Snapshot
from arima_forecasting.prep import clean_close, price_table, segment_bounds

TITLE = "ARIMA stock forecasting, done carefully"

# (id, slug, title, status) for every milestone. Exactly one is "current". When a milestone
# ships, move "current" down one row; the app shows this list as the project's progress bar.
_MILESTONES = (
    (0, "scaffold", "Scaffold, contract and design", "done"),
    (1, "data-eda", "Data and EDA", "current"),
    (2, "stationarity", "Stationarity and identification", "planned"),
    (3, "fit-diagnostics", "Fit and diagnostics", "planned"),
    (4, "forecast-eval", "Forecast and evaluation", "planned"),
    (5, "where-it-goes-wrong", "Where the sample goes wrong, and polish", "planned"),
)

# Every artifact one export writes, in the order the tool writes them. meta lists exactly these, so
# the app knows which views it can switch on.
ARTIFACTS = ("meta", "prices", "eda")

# The owner gate (ADR-0001): artifacts the export writes but the repository does not commit, until
# the owner decides whether Yahoo-derived prices may be published. The root .gitignore ignores
# exactly these files (tests/test_gitignore.py checks it). eda is held as well as prices, because
# its decomposition rows carry observed_log, the training log closes themselves. A fresh clone
# lacks these files; meta lists them as held, so the app and the tests can say why.
HELD_ARTIFACTS = ("prices", "eda")


def _window(window: StudyWindow) -> dict[str, str]:
    # ISO text ("2015-01-01"), because JSON has no date type.
    return {"start": window.start.isoformat(), "end_exclusive": window.end_exclusive.isoformat()}


def meta_payload() -> dict[str, Any]:
    """The `data` part of the "meta" artifact: what this project is and how far along it is.

    Windows and ticker come from config.py, not from retyped literals, so the app can never
    show dates that differ from the dates the Python code actually uses.
    """
    return {
        "project": PROJECT_SLUG,
        "title": TITLE,
        "ticker": TICKER,
        "windows": {window.name: _window(window) for window in (COURSE_WINDOW, OOS_WINDOW)},
        "milestones": [
            {"id": number, "slug": slug, "title": title, "status": status}
            for number, slug, title, status in _MILESTONES
        ],
        "artifacts": list(ARTIFACTS),
        "held_artifacts": list(HELD_ARTIFACTS),
    }


PRICE_BASIS = "adjusted_close"
FILL_METHOD = "ffill"


def source_from_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """The `source` block of `prices`: where the snapshot came from, copied from its manifest.

    `downloaded_at` is the manifest's time, not the export clock, so a re-export of the same
    snapshot writes the same block.
    """
    request = manifest["request"]
    return {
        "provider": PROVIDER,
        "yfinance_version": manifest["yfinance_version"],
        "raw_sha256": manifest["sha256"],
        "raw_rows": int(manifest["rows"]),
        "downloaded_at": manifest["downloaded_at"],
        "request": {
            "start": request["start"],
            "end_exclusive": request["end"],
            "interval": request["interval"],
            "auto_adjust": request["auto_adjust"],
        },
    }


def prices_payload(
    table: pd.DataFrame, filled_dates: Iterable[date], source: Mapping[str, Any]
) -> dict[str, Any]:
    """The `data` part of the "prices" artifact: every trading day of both windows, labelled.

    `table` comes from prep.price_table: close_usd, log_close and segment, indexed by date.
    """
    in_table = set(table.index.date)
    return {
        "ticker": TICKER,
        "price_basis": PRICE_BASIS,
        "source": dict(source),
        "fill": {
            "method": FILL_METHOD,
            "filled_dates": [day.isoformat() for day in sorted(filled_dates) if day in in_table],
        },
        "splits": {"train_fraction": TRAIN_FRACTION, **segment_bounds(table)},
        "rows": [
            {
                "date": ts.date().isoformat(),
                "close_usd": float(close),
                "log_close": float(log_close),
                "segment": segment,
            }
            for ts, close, log_close, segment in zip(
                table.index, table["close_usd"], table["log_close"], table["segment"], strict=True
            )
        ],
    }


def eda_payload(table: pd.DataFrame) -> dict[str, Any]:
    """The `data` part of the "eda" artifact. Only the training rows are used."""
    train = table[table["segment"] == "train"]
    returns = eda.log_returns(train["log_close"])
    return {
        "sample": "train",
        "summary": eda.summary(train),
        "kdes": [
            eda.kde(train["log_close"].to_numpy(), "log_close"),
            eda.kde(returns.to_numpy(), "log_return"),
        ],
        "decomposition": eda.decomposition(train["log_close"]),
    }


def build_payloads(snapshot: Snapshot) -> dict[str, dict[str, Any]]:
    """Every payload one export writes, keyed by artifact name, from one raw snapshot."""
    cleaned = clean_close(snapshot.frame)
    table = price_table(cleaned.close)
    payloads = {
        "meta": meta_payload(),
        "prices": prices_payload(table, cleaned.filled_dates, source_from_manifest(snapshot.manifest)),
        "eda": eda_payload(table),
    }
    if tuple(payloads) != ARTIFACTS:  # pragma: no cover - a guard for whoever edits this list
        raise RuntimeError(f"payloads {tuple(payloads)} do not match ARTIFACTS {ARTIFACTS}")
    return payloads
