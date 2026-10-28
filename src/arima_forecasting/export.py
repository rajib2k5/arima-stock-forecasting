"""What goes into the JSON files the web app reads. Pure: builds dicts, writes nothing.

`tools/export_app_data.py` is the thin wrapper that wraps these payloads in the envelope
(see contract.py) and writes them to disk.
"""

from __future__ import annotations

from typing import Any

from arima_forecasting.config import COURSE_WINDOW, OOS_WINDOW, PROJECT_SLUG, TICKER, StudyWindow

TITLE = "ARIMA stock forecasting, done carefully"

# (id, slug, title, status) for every milestone. Exactly one is "current". When a milestone
# ships, move "current" down one row; the app shows this list as the project's progress bar.
_MILESTONES = (
    (0, "scaffold", "Scaffold, contract and design", "current"),
    (1, "data-eda", "Data and EDA", "planned"),
    (2, "stationarity", "Stationarity and identification", "planned"),
    (3, "fit-diagnostics", "Fit and diagnostics", "planned"),
    (4, "forecast-eval", "Forecast and evaluation", "planned"),
    (5, "where-it-goes-wrong", "Where the sample goes wrong, and polish", "planned"),
)

ARTIFACTS = ("meta",)


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
    }
