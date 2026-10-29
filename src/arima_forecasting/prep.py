"""Clean the close, take logs, and cut the series into train, test and out-of-sample.

Pure: every function takes pandas objects and returns new ones. Nothing reads files or the clock.

The order of the steps matters for leakage. Forward-filling and taking logs are pointwise: the
value on day t uses only day t and earlier days. So they may run over the whole series before the
split, and they leak nothing from the test period into training.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from arima_forecasting.config import COURSE_WINDOW, OOS_WINDOW, TRAIN_FRACTION, StudyWindow

SEGMENTS = ("train", "test", "oos")

# A gap longer than this many calendar days between two bars, or between a window edge and its
# first or last bar, means rows are missing. The longest regular gap is 4 days (a Friday holiday
# plus a weekend: Thursday to Monday).
MAX_GAP_DAYS = 7


class DataQualityError(ValueError):
    """The price series cannot be used as it is. We stop instead of guessing."""


@dataclass(frozen=True)
class Cleaned:
    """The close after forward filling, and the dates whose close was filled."""

    close: pd.Series
    filled_dates: tuple[date, ...]


def clean_close(frame: pd.DataFrame) -> Cleaned:
    """Forward-fill missing closes with `.ffill()` and record which dates were filled.

    The course calls `fillna(method='ffill')`. pandas 3.1 removed that keyword, and the call raises
    TypeError; `.ffill()` is the same operation. Forward filling only fills rows that exist. It
    does not invent rows for days Yahoo did not return.

    A fill may carry a close at most MAX_GAP_DAYS calendar days. A filled row further than that
    from the last real close (a long run of missing closes, or a missing tail) is refused: ffill
    would otherwise draw a flat line of zero returns that every later check accepts.
    """
    close = frame["Close"].astype("float64")
    missing = close.isna()
    if missing.iloc[0]:
        # ffill has nothing to carry into the first row, so it would stay NaN.
        raise DataQualityError(f"the first close ({close.index[0].date()}) is missing; nothing to fill it from")
    # For every row, the date of the last real close on or before it.
    real_dates = pd.Series(close.index.where(~missing), index=close.index).ffill()
    carried = (close.index - pd.DatetimeIndex(real_dates)).days
    too_far = missing.to_numpy() & (carried > MAX_GAP_DAYS)
    if too_far.any():
        at = int(too_far.argmax())
        raise DataQualityError(
            f"the close on {close.index[at].date()} is missing, and the last real close "
            f"({pd.Timestamp(real_dates.iloc[at]).date()}) is {carried[at]} calendar days earlier; a fill "
            f"may carry a close at most {MAX_GAP_DAYS} days"
        )
    filled = close.ffill()
    if not np.isfinite(filled.to_numpy()).all():
        raise DataQualityError("the close contains an infinite value")
    if (filled <= 0).any():
        bad = filled[filled <= 0].index[0].date()
        raise DataQualityError(f"the close is not positive on {bad}; its log is undefined")
    filled_dates = tuple(ts.date() for ts in close.index[missing.to_numpy()])
    return Cleaned(close=filled.rename("close_usd"), filled_dates=filled_dates)


def select_window(series: pd.Series, window: StudyWindow) -> pd.Series:
    """The rows with start <= date < end_exclusive."""
    index = series.index
    keep = (index >= pd.Timestamp(window.start)) & (index < pd.Timestamp(window.end_exclusive))
    return series[keep]


def check_coverage(index: pd.DatetimeIndex, window: StudyWindow, max_gap_days: int = MAX_GAP_DAYS) -> None:
    """Raise if the bars do not cover `window`: a late start, an early end, or a hole inside.

    yfinance can return a truncated history without an error. This makes that loud.
    """
    if len(index) == 0:
        raise DataQualityError(f"no bars in the {window.name} window")
    first, last = index[0].date(), index[-1].date()
    if (first - window.start).days > max_gap_days:
        raise DataQualityError(f"the {window.name} window starts {window.start}, first bar is {first}")
    if (window.end_exclusive - last).days > max_gap_days:
        raise DataQualityError(
            f"the {window.name} window ends before {window.end_exclusive}, last bar is {last}"
        )
    gaps = np.diff(index.to_numpy()).astype("timedelta64[D]").astype(int)
    if len(gaps) and gaps.max() > max_gap_days:
        at = int(gaps.argmax())
        raise DataQualityError(
            f"{gaps.max()} calendar days between {index[at].date()} and {index[at + 1].date()}"
        )


def train_size(n: int, fraction: float = TRAIN_FRACTION) -> int:
    """The course's split point: int(n * fraction), the first rows train and the rest test.

    int() truncates toward zero, so for fraction 0.9 it equals n * 9 // 10 (tests check every n up
    to 200,000, because 0.9 has no exact binary form and a float product could in principle round
    across an integer).
    """
    size = int(n * fraction)
    if not 0 < size < n:
        raise DataQualityError(f"a {fraction} split of {n} rows leaves {size} train and {n - size} test")
    return size


def price_table(close: pd.Series) -> pd.DataFrame:
    """One row per trading day of the course and OOS windows: close_usd, log_close, segment.

    `close` is the cleaned close over the whole download. The course window is split by position
    into train and test; the OOS window follows. Rows outside both windows are dropped.
    """
    course = select_window(close, COURSE_WINDOW)
    oos = select_window(close, OOS_WINDOW)
    check_coverage(course.index, COURSE_WINDOW)
    check_coverage(oos.index, OOS_WINDOW)
    n_train = train_size(len(course))
    segment = ["train"] * n_train + ["test"] * (len(course) - n_train) + ["oos"] * len(oos)
    both = pd.concat([course, oos])
    return pd.DataFrame(
        {
            "close_usd": both.to_numpy(),
            # np.log is the natural log, the only log this project uses.
            "log_close": np.log(both.to_numpy()),
            "segment": segment,
        },
        index=both.index.rename("date"),
    )


def segment_bounds(table: pd.DataFrame) -> dict[str, dict[str, object]]:
    """For each segment: its first and last trading date (both inclusive) and its row count."""
    bounds: dict[str, dict[str, object]] = {}
    for name in SEGMENTS:
        rows = table.index[table["segment"] == name]
        if len(rows) == 0:
            raise DataQualityError(f"segment {name!r} is empty")
        bounds[name] = {
            "start": rows[0].date().isoformat(),
            "end": rows[-1].date().isoformat(),
            "n": int(len(rows)),
        }
    return bounds
