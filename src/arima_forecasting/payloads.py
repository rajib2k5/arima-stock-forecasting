"""Shape checks for every payload but the envelope: the Python copy of contract.md section 3.

The export tool runs these on every payload before it writes a file, so a malformed payload never
reaches disk. The app has its own TypeScript parsers (app/src/lib/contract.payloads.ts). Two
things keep the copies together: app/src/test/fixtures/payload_cases.json, one list of payloads
with their verdicts that both languages' tests run, and the app's contract.realdata.test.ts, which
runs the TypeScript parsers over the files written here.

Some rules exist only so that the two readers agree on what JSON.parse can see. A JavaScript
number cannot tell 4.0 from 4, so an integer field accepts a float with no fractional part. An
integer beyond +-(2**53 - 1) does not survive JSON.parse, so it is refused, and a number too big
for a double (JavaScript reads it as Infinity) is refused. "Blank" uses one explicit set of
whitespace characters, because Python's str.strip and JavaScript's String.trim strip different
ones.

Each function returns a list of every problem found, with a path such as `data.rows[3].segment`.
An empty list means the payload is valid. Like validate_envelope, it never raises on bad input.
"""

from __future__ import annotations

import functools
import math
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from arima_forecasting.contract import MAX_PROBLEMS, MAX_SAFE_INTEGER, more_problems
from arima_forecasting.contract import shown as _show
from arima_forecasting.prep import MAX_GAP_DAYS, SEGMENTS

_SHA256 = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

KDE_VARIABLES_REQUIRED = ("log_close", "log_return")

# A string made only of these characters counts as empty. The same class is written in
# app/src/lib/contract.payloads.ts: the union of what Python's str.strip and JavaScript's trim
# remove, so neither reader accepts a value the other calls blank.
BLANK = re.compile(
    "[\t\n\v\f\r \x1c-\x1f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]*"
)


class _Full(Exception):
    """Raised by _Checker.add in place of problem MAX_PROBLEMS + 1: the validator stops there (_capped)."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__(len(problems))
        self.problems = problems


class _Checker:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def add(self, path: str, message: str) -> None:
        if len(self.problems) == MAX_PROBLEMS:
            raise _Full(self.problems)
        self.problems.append(f"{path}: {message}")

    def obj(self, value: object, path: str) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.add(path, f"expected an object, got {type(value).__name__}")
            return None
        return value

    def key(self, obj: dict[str, Any], key: str, path: str) -> Any:
        if key not in obj:
            self.add(f"{path}.{key}", "missing")
            return _MISSING
        return obj[key]

    def string(self, value: object, path: str) -> str | None:
        if value is _MISSING:
            return None
        if not isinstance(value, str) or BLANK.fullmatch(value) is not None:
            self.add(path, f"expected a non-empty string, got {_show(value)}")
            return None
        return value

    def date(self, value: object, path: str) -> str | None:
        text = self.string(value, path)
        if text is None:
            return None
        if _DATE.fullmatch(text) is None:
            self.add(path, f"{_show(text)} is not a date written YYYY-MM-DD")
            return None
        try:
            date.fromisoformat(text)
        except ValueError:
            self.add(path, f"{_show(text)} is not a calendar date")
            return None
        return text

    def integer(self, value: object, path: str, minimum: int = 0) -> int | None:
        if value is _MISSING:
            return None
        whole: int | None = None
        if isinstance(value, int) and not isinstance(value, bool):
            whole = value
        elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
            whole = int(value)  # JSON.parse reads 4.0 as 4, so this reader does too
        if whole is None or abs(whole) > MAX_SAFE_INTEGER or whole < minimum:
            self.add(path, f"expected an integer >= {minimum}, got {_show(value)}")
            return None
        return whole

    def number(self, value: object, path: str, *, nullable: bool = False) -> float | None:
        if value is _MISSING:
            return None
        if value is None and nullable:
            return None
        finite: float | None = None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                finite = float(value)  # an int too big for a double raises; JSON.parse reads Infinity
            except OverflowError:
                finite = None
        if finite is None or not math.isfinite(finite):
            self.add(path, f"expected a finite number{' or null' if nullable else ''}, got {_show(value)}")
            return None
        return finite

    def equals(self, value: object, expected: object, path: str) -> None:
        if value is _MISSING:
            return
        if value != expected or type(value) is not type(expected):
            self.add(path, f"expected {expected!r}, got {_show(value)}")

    def array(self, value: object, path: str) -> list[Any] | None:
        if value is _MISSING:
            return None
        if not isinstance(value, list):
            self.add(path, f"expected an array, got {type(value).__name__}")
            return None
        return value


_MISSING = object()


def _capped(validate: Callable[..., list[str]]) -> Callable[..., list[str]]:
    """A validator that stops at MAX_PROBLEMS problems and ends its list with more_problems (contract.md, "Bounds")."""

    @functools.wraps(validate)
    def run(*args: Any, **kwargs: Any) -> list[str]:
        try:
            return validate(*args, **kwargs)
        except _Full as full:
            return [*full.problems, more_problems("data")]

    return run


# Every list is bounded before it is walked, in both readers (contract.md, "Bounds"): a longer one is
# one short problem and is not read, so no file, of 6 MB or 600, makes a reader slow or writes a
# message per item past the bound. Lists of days and points take MAX_LIST: no list of trading days
# can be longer than the download window's 4,291 calendar days, and the KDE grids have 200 points.
# Short lists of names (meta's milestones and artifacts, eda's KDEs, the fit's lag lists) take
# MAX_NAMES: 6, 18, 2 and 3 today. A list that enumerates a pinned set or an order takes that set's
# size (each says so where it is read).
MAX_LIST = 10_000
MAX_NAMES = 100


def _list(c: _Checker, value: object, path: str, most: int, what: str) -> list[Any] | None:
    """An array of at most `most` items, or one short problem and None (the same text in both readers)."""
    items = c.array(value, path)
    if items is not None and len(items) > most:
        c.add(path, f"has {len(items)} {what}, more than the {most} a reader takes")
        return None
    return items


def _check_ascending(checker: _Checker, dates: list[str | None], path: str) -> None:
    previous: str | None = None
    for index, day in enumerate(dates):
        if day is None:
            continue
        if previous is not None and day <= previous:
            checker.add(f"{path}[{index}].date", f"{day} does not come after {previous}")
        previous = day


# Project constants, pinned and never read from the file (config.OOS_WINDOW and config.TRAIN_FRACTION;
# tests/test_payloads.py ties them): the out-of-sample window, as calendar dates with an exclusive end,
# and the course window's train share. meta.windows.oos must state the window; prices.json's oos rows
# must lie inside it and its train and test rows before it, and its train_fraction must be the share.
# The made-up fixtures keep these (their oos day is 2024-01-02); the forecast fixtures do not (their
# windows are in 2021), so the forecast files' windows are tied to prices.json's splits across files
# (validate_forecast_prices), not pinned to dates.
OOS_START = "2024-01-01"
OOS_END_EXCLUSIVE = "2026-10-01"
TRAIN_FRACTION = 0.9
# prep.MAX_GAP_DAYS, imported: the producer's own coverage rule (prep.check_coverage) refuses a window
# whose first bar is more than this many calendar days after its start, whose last bar is more than this
# many before its exclusive end, or that has a longer gap between two bars. A reader applies it to the
# oos rows, so rows dropped at either end or inside are caught (contract.md 3.2).
OOS_MAX_GAP_DAYS = MAX_GAP_DAYS


def _check_split_rule(c: _Checker, segments: list[str]) -> None:
    """The producer's split (prep.train_size): the course window's first int(n x TRAIN_FRACTION) rows are
    train and the rest test, with the pinned fraction, never the file's. A boundary moved by one row (and
    the split counts rewritten to match) is refused here; the counts alone could not see it."""
    n_train, n_test = segments.count("train"), segments.count("test")
    want = int((n_train + n_test) * TRAIN_FRACTION)
    if n_train != want:
        c.add(
            "data.rows",
            f"{n_train} rows are train and {n_test} test, but the course window's {n_train + n_test} rows split at "
            f"{TRAIN_FRACTION} give int({n_train + n_test} x {TRAIN_FRACTION}) = {want} train and {n_train + n_test - want} test (prep.train_size)",
        )


def _check_oos_coverage(c: _Checker, dates: list[str], segments: list[str]) -> None:
    """The producer's coverage rule on the oos rows (prep.check_coverage with MAX_GAP_DAYS): the first at
    most OOS_MAX_GAP_DAYS calendar days after OOS_START, the last at most that many before
    OOS_END_EXCLUSIVE, and no two consecutive ones further apart. The dates are valid calendar dates."""
    oos = [(i, date.fromisoformat(d)) for i, (d, s) in enumerate(zip(dates, segments, strict=True)) if s == "oos"]
    if not oos:
        return
    rule = f"more than {OOS_MAX_GAP_DAYS} (prep.MAX_GAP_DAYS) means rows are missing"
    (first_at, first), (last_at, last) = oos[0], oos[-1]
    if (first - date.fromisoformat(OOS_START)).days > OOS_MAX_GAP_DAYS:
        c.add(f"data.rows[{first_at}].date", f"the first oos row is {first}, {(first - date.fromisoformat(OOS_START)).days} calendar days after the out-of-sample window starts on {OOS_START}; {rule}")
    if (date.fromisoformat(OOS_END_EXCLUSIVE) - last).days > OOS_MAX_GAP_DAYS:
        c.add(f"data.rows[{last_at}].date", f"the last oos row is {last}, {(date.fromisoformat(OOS_END_EXCLUSIVE) - last).days} calendar days before the out-of-sample window ends on {OOS_END_EXCLUSIVE} (exclusive); {rule}")
    for (_, a), (j, b) in zip(oos, oos[1:]):
        if (b - a).days > OOS_MAX_GAP_DAYS:
            c.add(f"data.rows[{j}].date", f"{b} is {(b - a).days} calendar days after the oos row before it, {a}; {rule}")


@_capped
def validate_prices(data: object) -> list[str]:
    """Every problem in a `prices` payload (contract.md section 3.2)."""
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    c.string(c.key(root, "ticker", "data"), "data.ticker")
    c.equals(c.key(root, "price_basis", "data"), "adjusted_close", "data.price_basis")

    source = c.key(root, "source", "data")
    if source is not _MISSING and (src := c.obj(source, "data.source")) is not None:
        c.string(c.key(src, "provider", "data.source"), "data.source.provider")
        c.string(c.key(src, "yfinance_version", "data.source"), "data.source.yfinance_version")
        sha = c.string(c.key(src, "raw_sha256", "data.source"), "data.source.raw_sha256")
        if sha is not None and _SHA256.fullmatch(sha) is None:
            c.add("data.source.raw_sha256", f"{_show(sha)} is not 64 lowercase hex characters")
        c.integer(c.key(src, "raw_rows", "data.source"), "data.source.raw_rows", minimum=1)
        stamp = c.string(c.key(src, "downloaded_at", "data.source"), "data.source.downloaded_at")
        if stamp is not None:
            try:
                valid = _TIMESTAMP.fullmatch(stamp) is not None and bool(
                    datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
                )
            except ValueError:
                valid = False
            if not valid:
                c.add("data.source.downloaded_at", f"{_show(stamp)} is not a UTC time written YYYY-MM-DDTHH:MM:SSZ")
        request = c.key(src, "request", "data.source")
        if request is not _MISSING and (req := c.obj(request, "data.source.request")) is not None:
            start = c.date(c.key(req, "start", "data.source.request"), "data.source.request.start")
            end = c.date(c.key(req, "end_exclusive", "data.source.request"), "data.source.request.end_exclusive")
            if start is not None and end is not None and start >= end:
                c.add("data.source.request", f"start {start} must be before end_exclusive {end}")
            c.string(c.key(req, "interval", "data.source.request"), "data.source.request.interval")
            c.equals(c.key(req, "auto_adjust", "data.source.request"), True, "data.source.request.auto_adjust")

    rows_value = c.key(root, "rows", "data")
    rows = _list(c, rows_value, "data.rows", MAX_LIST, "rows")
    row_dates: list[str | None] = []
    row_segments: list[str | None] = []
    if rows is not None:
        if not rows:
            c.add("data.rows", "must not be empty")
        for index, item in enumerate(rows):
            at = f"data.rows[{index}]"
            row = c.obj(item, at)
            if row is None:
                row_dates.append(None)
                row_segments.append(None)
                continue
            row_dates.append(c.date(c.key(row, "date", at), f"{at}.date"))
            close = c.number(c.key(row, "close_usd", at), f"{at}.close_usd")
            if close is not None and close <= 0:
                c.add(f"{at}.close_usd", f"must be positive, got {close}")
            c.number(c.key(row, "log_close", at), f"{at}.log_close")
            segment = c.key(row, "segment", at)
            if segment is not _MISSING and segment not in SEGMENTS:
                c.add(f"{at}.segment", f"expected one of {', '.join(SEGMENTS)}, got {_show(segment)}")
                segment = None
            row_segments.append(None if segment is _MISSING else segment)
        _check_ascending(c, row_dates, "data.rows")
        # The segments must appear as one block each, in the order train, test, oos.
        order = {name: rank for rank, name in enumerate(SEGMENTS)}
        last_rank = -1
        for index, segment in enumerate(row_segments):
            if segment is None:
                continue
            if order[segment] < last_rank:
                c.add(f"data.rows[{index}].segment", f"{_show(segment)} after a later segment; expected train, then test, then oos")
            last_rank = max(last_rank, order[segment])
        if None not in row_dates and None not in row_segments:
            _check_split_rule(c, row_segments)
            _check_oos_coverage(c, row_dates, row_segments)  # type: ignore[arg-type]

    fill = c.key(root, "fill", "data")
    if fill is not _MISSING and (fl := c.obj(fill, "data.fill")) is not None:
        c.equals(c.key(fl, "method", "data.fill"), "ffill", "data.fill.method")
        filled = _list(c, c.key(fl, "filled_dates", "data.fill"), "data.fill.filled_dates", MAX_LIST, "dates")
        if filled is not None:
            days = [c.date(day, f"data.fill.filled_dates[{i}]") for i, day in enumerate(filled)]
            for i in range(1, len(days)):
                if days[i] is not None and days[i - 1] is not None and days[i] <= days[i - 1]:  # type: ignore[operator]
                    c.add(f"data.fill.filled_dates[{i}]", "dates must be sorted and unique")
            known = {d for d in row_dates if d is not None}
            for i, day in enumerate(days):
                if day is not None and rows is not None and day not in known:
                    c.add(f"data.fill.filled_dates[{i}]", f"{day} is not one of the rows")

    splits = c.key(root, "splits", "data")
    if splits is not _MISSING and (sp := c.obj(splits, "data.splits")) is not None:
        fraction = c.number(c.key(sp, "train_fraction", "data.splits"), "data.splits.train_fraction")
        if fraction is not None and not 0 < fraction < 1:
            c.add("data.splits.train_fraction", f"must be between 0 and 1, got {fraction}")
        elif fraction is not None and fraction != TRAIN_FRACTION:
            c.add("data.splits.train_fraction", f"is {fraction}, but this reader splits the course window at {TRAIN_FRACTION}")
        for name in SEGMENTS:
            at = f"data.splits.{name}"
            block = c.key(sp, name, "data.splits")
            if block is _MISSING or (bl := c.obj(block, at)) is None:
                continue
            start = c.date(c.key(bl, "start", at), f"{at}.start")
            end = c.date(c.key(bl, "end", at), f"{at}.end")
            # The pinned out-of-sample window: the oos segment inside it, train and test before it.
            if name == "oos" and start is not None and end is not None and not (OOS_START <= start and end < OOS_END_EXCLUSIVE):
                c.add(at, f"runs {start} to {end}, but this reader's out-of-sample window is {OOS_START} to {OOS_END_EXCLUSIVE} (exclusive)")
            if name != "oos" and end is not None and not end < OOS_START:
                c.add(f"{at}.end", f"is {end}, but the {name} rows come before the out-of-sample window, which starts {OOS_START}")
            n = c.integer(c.key(bl, "n", at), f"{at}.n", minimum=1)
            if rows is None or None in row_dates or None in row_segments:
                continue
            mine = [d for d, s in zip(row_dates, row_segments, strict=True) if s == name]
            if n is not None and n != len(mine):
                c.add(f"{at}.n", f"says {n}, but {len(mine)} rows have segment {name!r}")
            if mine and start is not None and start != mine[0]:
                c.add(f"{at}.start", f"says {start}, but the first {name} row is {mine[0]}")
            if mine and end is not None and end != mine[-1]:
                c.add(f"{at}.end", f"says {end}, but the last {name} row is {mine[-1]}")
    return c.problems


def _check_kde(c: _Checker, item: object, at: str) -> str | None:
    kde = c.obj(item, at)
    if kde is None:
        return None
    variable = c.string(c.key(kde, "variable", at), f"{at}.variable")
    c.integer(c.key(kde, "n", at), f"{at}.n", minimum=2)
    c.string(c.key(kde, "bandwidth_method", at), f"{at}.bandwidth_method")
    for name in ("bandwidth_factor", "bandwidth"):
        value = c.number(c.key(kde, name, at), f"{at}.{name}")
        if value is not None and value <= 0:
            c.add(f"{at}.{name}", f"must be positive, got {value}")
    points = _list(c, c.key(kde, "points", at), f"{at}.points", MAX_LIST, "points")
    if points is not None:
        if len(points) < 2:
            c.add(f"{at}.points", f"expected at least 2 points, got {len(points)}")
        previous: float | None = None
        for index, item_point in enumerate(points):
            pat = f"{at}.points[{index}]"
            point = c.obj(item_point, pat)
            if point is None:
                continue
            x = c.number(c.key(point, "x", pat), f"{pat}.x")
            for name in ("density", "normal_density"):
                d = c.number(c.key(point, name, pat), f"{pat}.{name}")
                if d is not None and d < 0:
                    c.add(f"{pat}.{name}", f"must not be negative, got {d}")
            if x is not None and previous is not None and x <= previous:
                c.add(f"{pat}.x", f"{x} does not come after {previous}")
            if x is not None:
                previous = x
    return variable


@_capped
def validate_eda(data: object) -> list[str]:
    """Every problem in an `eda` payload (contract.md section 3.3)."""
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    c.equals(c.key(root, "sample", "data"), "train", "data.sample")

    summary = c.key(root, "summary", "data")
    if summary is not _MISSING and (sm := c.obj(summary, "data.summary")) is not None:
        summary_n = c.integer(c.key(sm, "n", "data.summary"), "data.summary.n", minimum=2)
        start = c.date(c.key(sm, "start", "data.summary"), "data.summary.start")
        end = c.date(c.key(sm, "end", "data.summary"), "data.summary.end")
        if start is not None and end is not None and start >= end:
            c.add("data.summary", f"start {start} must be before end {end}")
        close = c.key(sm, "close_usd", "data.summary")
        if close is not _MISSING and (cl := c.obj(close, "data.summary.close_usd")) is not None:
            for name in ("min", "max", "mean", "median"):
                c.number(c.key(cl, name, "data.summary.close_usd"), f"data.summary.close_usd.{name}")
        lr = c.key(sm, "log_return", "data.summary")
        if lr is not _MISSING and (ret := c.obj(lr, "data.summary.log_return")) is not None:
            returns_n = c.integer(c.key(ret, "n", "data.summary.log_return"), "data.summary.log_return.n", minimum=1)
            # n prices give n - 1 daily returns (contract.md section 3.3).
            if summary_n is not None and returns_n is not None and returns_n != summary_n - 1:
                c.add("data.summary.log_return.n", f"is {returns_n}, but data.summary.n - 1 is {summary_n - 1}")
            for name in ("mean", "std", "skew", "excess_kurtosis"):
                c.number(c.key(ret, name, "data.summary.log_return"), f"data.summary.log_return.{name}")

    kdes = _list(c, c.key(root, "kdes", "data"), "data.kdes", MAX_NAMES, "KDEs")
    if kdes is not None:
        variables = [_check_kde(c, item, f"data.kdes[{i}]") for i, item in enumerate(kdes)]
        for required in KDE_VARIABLES_REQUIRED:
            if required not in variables:
                c.add("data.kdes", f"no KDE for {required!r}")
        named = [v for v in variables if v is not None]
        if len(set(named)) != len(named):
            c.add("data.kdes", f"duplicate variables: {_show(next(v for i, v in enumerate(named) if v in named[:i]))} appears more than once")

    decomposition = c.key(root, "decomposition", "data")
    if decomposition is not _MISSING and (dc := c.obj(decomposition, "data.decomposition")) is not None:
        c.equals(c.key(dc, "model", "data.decomposition"), "additive", "data.decomposition.model")
        period = c.integer(c.key(dc, "period", "data.decomposition"), "data.decomposition.period", minimum=2)
        rows = _list(c, c.key(dc, "rows", "data.decomposition"), "data.decomposition.rows", MAX_LIST, "rows")
        if rows is not None:
            dates: list[str | None] = []
            nulls: list[bool] = []
            for index, item in enumerate(rows):
                at = f"data.decomposition.rows[{index}]"
                row = c.obj(item, at)
                if row is None:
                    dates.append(None)
                    continue
                dates.append(c.date(c.key(row, "date", at), f"{at}.date"))
                c.number(c.key(row, "observed_log", at), f"{at}.observed_log")
                c.number(c.key(row, "seasonal_log", at), f"{at}.seasonal_log")
                c.number(c.key(row, "trend_log", at), f"{at}.trend_log", nullable=True)
                c.number(c.key(row, "resid_log", at), f"{at}.resid_log", nullable=True)
                trend_null = row.get("trend_log", 0) is None
                if trend_null != (row.get("resid_log", 0) is None):
                    c.add(at, "trend_log and resid_log must be null on the same rows")
                nulls.append(trend_null)
            _check_ascending(c, dates, "data.decomposition.rows")
            # The centred moving average is undefined for exactly period // 2 rows at each end.
            if period is not None and len(nulls) == len(rows):
                half = period // 2
                expected = [i < half or i >= len(rows) - half for i in range(len(rows))]
                if nulls != expected:
                    c.add(
                        "data.decomposition.rows",
                        f"trend_log must be null on exactly the first and last {half} rows "
                        f"(period {period} // 2), and nowhere else",
                    )
            if summary is not _MISSING and isinstance(summary, dict) and None not in dates:
                if summary.get("n") != len(rows):
                    c.add("data.decomposition.rows", f"{len(rows)} rows, but data.summary.n is {_show(summary.get('n'))}")
                elif dates and (summary.get("start") != dates[0] or summary.get("end") != dates[-1]):
                    c.add(
                        "data.decomposition.rows",
                        f"runs {dates[0]} to {dates[-1]}, but the summary covers "
                        f"{_show(summary.get('start'))} to {_show(summary.get('end'))}",
                    )
    return c.problems


MILESTONE_STATUSES = ("done", "current", "planned")


@_capped
def validate_meta(data: object) -> list[str]:
    """Every problem in a `meta` payload (contract.md section 3.1), the rules of the app's parseMeta.

    Added after the milestone-1 re-review, which found that read_artifact accepted a
    held_artifacts of 5, ["nope"] or [1] while the app refused all three.
    """
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    for name in ("project", "title", "ticker"):
        c.string(c.key(root, name, "data"), f"data.{name}")

    windows = c.key(root, "windows", "data")
    if windows is not _MISSING and (wn := c.obj(windows, "data.windows")) is not None:
        for name in ("course", "oos"):
            at = f"data.windows.{name}"
            if name not in wn:
                c.add(at, "missing")
                continue
            window = c.obj(wn[name], at)
            if window is None:
                continue
            start = c.date(c.key(window, "start", at), f"{at}.start")
            end = c.date(c.key(window, "end_exclusive", at), f"{at}.end_exclusive")
            if start is not None and end is not None and start >= end:
                c.add(at, f"start {start} must be before end_exclusive {end}")
            elif name == "oos" and start is not None and end is not None and (start, end) != (OOS_START, OOS_END_EXCLUSIVE):
                c.add(at, f"is {start} to {end}, but this reader's out-of-sample window is {OOS_START} to {OOS_END_EXCLUSIVE} (exclusive)")

    milestones = _list(c, c.key(root, "milestones", "data"), "data.milestones", MAX_NAMES, "milestones")
    if milestones is not None:
        before = len(c.problems)
        seen: set[int] = set()
        statuses: list[str] = []
        for index, item in enumerate(milestones):
            at = f"data.milestones[{index}]"
            milestone = c.obj(item, at)
            if milestone is None:
                continue
            number = c.integer(c.key(milestone, "id", at), f"{at}.id")
            if number is not None:
                if number in seen:
                    c.add(f"{at}.id", f"duplicate id {number}")
                seen.add(number)
            c.string(c.key(milestone, "slug", at), f"{at}.slug")
            c.string(c.key(milestone, "title", at), f"{at}.title")
            status = c.key(milestone, "status", at)
            if status is not _MISSING and status not in MILESTONE_STATUSES:
                c.add(f"{at}.status", f"expected one of {', '.join(MILESTONE_STATUSES)}, got {_show(status)}")
            elif status is not _MISSING:
                statuses.append(status)
        # Exactly one milestone is current, checked only once every milestone parsed.
        if len(c.problems) == before and statuses.count("current") != 1:
            c.add("data.milestones", f"expected exactly one 'current' milestone, found {statuses.count('current')}")

    artifacts = _list(c, c.key(root, "artifacts", "data"), "data.artifacts", MAX_NAMES, "artifacts")
    names: list[str] = []
    if artifacts is not None:
        for index, item in enumerate(artifacts):
            name = c.string(item, f"data.artifacts[{index}]")
            if name is not None:
                names.append(name)
    if "held_artifacts" in root:  # added in 1.1.0; a 1.0.x file has no such key
        held = _list(c, root["held_artifacts"], "data.held_artifacts", MAX_NAMES, "artifacts")
        if held is not None:
            for index, item in enumerate(held):
                if not isinstance(item, str) or item not in names or item == "meta" or held.index(item) != index:
                    c.add(f"data.held_artifacts[{index}]", f"{_show(item)} must be a listed artifact other than meta, named once")
    return c.problems


# ---- milestone 2: stationarity, acf_pacf and aic_grid (contract.md sections 3.4-3.6) ----------
#
# Written independently of the code that produces these payloads (stationarity.py, identification.py
# and selection.py), so a bug in the producer is not copied into the check. Every rule here is also
# in app/src/lib/contract.order.ts, and the shared corpus runs both.

TRANSFORM_D = {"log": 0, "diff1": 1, "diff2": 2}
TREND_CODES = ("c", "n", "t")
CELL_STATUSES = ("ok", "not_converged", "near_unit_root", "failed")
CHECK_STATUSES = ("ok", "unavailable")
KPSS_BOUNDS = {0.01: "smaller", 0.1: "greater"}
ADF_CRITICAL = ("1%", "5%", "10%")
KPSS_CRITICAL = ("10%", "5%", "2.5%", "1%")


def _boolean(c: _Checker, value: object, path: str) -> bool | None:
    if value is _MISSING:
        return None
    if not isinstance(value, bool):
        c.add(path, f"expected true or false, got {_show(value)}")
        return None
    return value


def _choice(c: _Checker, value: object, options: tuple[str, ...], path: str, *, nullable: bool = False) -> str | None:
    if value is _MISSING or (value is None and nullable):
        return None
    if not isinstance(value, str) or value not in options:
        c.add(path, f"expected one of {', '.join(options)}{' or null' if nullable else ''}, got {_show(value)}")
        return None
    return value


def _text_or_null(c: _Checker, value: object, path: str) -> str | None:
    """A non-empty string or null; returns the string, or None for null, missing or invalid."""
    if value is None or value is _MISSING:
        return None
    return c.string(value, path)


def _is_null(value: object) -> bool:
    return value is None


def _check_critical(c: _Checker, value: object, keys: tuple[str, ...], path: str) -> None:
    if value is _MISSING:
        return
    table = c.obj(value, path)
    if table is not None:
        for key in keys:
            c.number(c.key(table, key, path), f"{path}.{key}")


def _check_adf(c: _Checker, value: object, path: str, regression: str, alpha: float | None) -> bool | None:
    """One ADF result; returns reject_unit_root when every field is valid."""
    if value is _MISSING:
        return None
    adf = c.obj(value, path)
    if adf is None:
        return None
    before = len(c.problems)
    c.number(c.key(adf, "statistic", path), f"{path}.statistic")
    p = c.number(c.key(adf, "p_value", path), f"{path}.p_value")
    if p is not None and not 0 <= p <= 1:
        c.add(f"{path}.p_value", f"must be between 0 and 1, got {p}")
    used = c.integer(c.key(adf, "used_lag", path), f"{path}.used_lag")
    maxlag = c.integer(c.key(adf, "maxlag", path), f"{path}.maxlag")
    if used is not None and maxlag is not None and used > maxlag:
        c.add(f"{path}.used_lag", f"{used} is above maxlag {maxlag}")
    c.integer(c.key(adf, "nobs", path), f"{path}.nobs", minimum=1)
    _check_critical(c, c.key(adf, "critical_values", path), ADF_CRITICAL, f"{path}.critical_values")
    c.equals(c.key(adf, "regression", path), regression, f"{path}.regression")
    c.equals(c.key(adf, "autolag", path), "AIC", f"{path}.autolag")
    reject = _boolean(c, c.key(adf, "reject_unit_root", path), f"{path}.reject_unit_root")
    if reject is not None and p is not None and alpha is not None and reject != (p < alpha):
        c.add(f"{path}.reject_unit_root", f"is {reject}, but p_value {p} < alpha {alpha} is {p < alpha}")
    return reject if len(c.problems) == before else None


def _check_kpss(c: _Checker, value: object, path: str, regression: str, alpha: float | None) -> bool | None:
    """One KPSS result; returns reject_stationarity when every field is valid."""
    if value is _MISSING:
        return None
    kp = c.obj(value, path)
    if kp is None:
        return None
    before = len(c.problems)
    statistic = c.number(c.key(kp, "statistic", path), f"{path}.statistic")
    if statistic is not None and statistic < 0:
        c.add(f"{path}.statistic", f"must not be negative, got {statistic}")
    p = c.number(c.key(kp, "p_value", path), f"{path}.p_value")
    # statsmodels interpolates inside a table that runs from 0.01 to 0.10, and clips at its edges.
    if p is not None and not 0.01 <= p <= 0.1:
        c.add(f"{path}.p_value", f"must be between 0.01 and 0.10, got {p}")
    bound = c.key(kp, "p_value_bound", path)
    if bound is not _MISSING:
        if bound is not None and bound not in ("smaller", "greater"):
            c.add(f"{path}.p_value_bound", f"expected smaller, greater or null, got {_show(bound)}")
        elif p is not None and bound != KPSS_BOUNDS.get(p):
            c.add(f"{path}.p_value_bound", f"is {_show(bound)}, but a p_value of {p} means {_show(KPSS_BOUNDS.get(p))}")
    c.integer(c.key(kp, "nlags", path), f"{path}.nlags")
    c.string(c.key(kp, "nlags_method", path), f"{path}.nlags_method")
    _check_critical(c, c.key(kp, "critical_values", path), KPSS_CRITICAL, f"{path}.critical_values")
    c.equals(c.key(kp, "regression", path), regression, f"{path}.regression")
    reject = _boolean(c, c.key(kp, "reject_stationarity", path), f"{path}.reject_stationarity")
    if reject is not None and p is not None and alpha is not None and reject != (p < alpha):
        c.add(f"{path}.reject_stationarity", f"is {reject}, but p_value {p} < alpha {alpha} is {p < alpha}")
    return reject if len(c.problems) == before else None


def _table_verdict(adf_rejects: bool, kpss_rejects: bool) -> str:
    if adf_rejects:
        return "conflict" if kpss_rejects else "stationary"
    return "unit_root" if kpss_rejects else "inconclusive"


def _check_verdict(c: _Checker, value: object, adf: bool | None, kp: bool | None, path: str) -> None:
    verdict = _choice(c, value, ("stationary", "unit_root", "conflict", "inconclusive"), path)
    if verdict is not None and adf is not None and kp is not None and verdict != _table_verdict(adf, kp):
        c.add(path, f"is {verdict!r}, but ADF reject {adf} and KPSS reject {kp} make it {_table_verdict(adf, kp)!r}")


@_capped
def validate_stationarity(data: object) -> list[str]:
    """Every problem in a `stationarity` payload (contract.md section 3.4)."""
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    c.equals(c.key(root, "sample", "data"), "train", "data.sample")
    n_train = c.integer(c.key(root, "n_train", "data"), "data.n_train", minimum=3)
    alpha = c.number(c.key(root, "alpha", "data"), "data.alpha")
    if alpha is not None and not 0 < alpha < 1:
        c.add("data.alpha", f"must be between 0 and 1, got {alpha}")
        alpha = None
    transforms = _list(c, c.key(root, "transforms", "data"), "data.transforms", len(TRANSFORM_D), "transforms")  # one per transform at most
    tests: list[tuple[int, bool, bool] | None] = []  # (d, adf rejects, kpss rejects) per transform
    if transforms is not None:
        if not transforms:
            c.add("data.transforms", "must not be empty")
        previous: int | None = None
        for index, item in enumerate(transforms):
            at = f"data.transforms[{index}]"
            t = c.obj(item, at)
            if t is None:
                tests.append(None)
                continue
            ident = _choice(c, c.key(t, "id", at), tuple(TRANSFORM_D), f"{at}.id")
            d = c.integer(c.key(t, "d", at), f"{at}.d")
            if ident is not None and d is not None and TRANSFORM_D[ident] != d:
                c.add(f"{at}.d", f"is {d}, but {ident!r} has d = {TRANSFORM_D[ident]}")
            if d is not None:
                if previous is not None and d <= previous:
                    c.add(f"{at}.d", f"{d} does not come after {previous}; transforms are sorted by d")
                previous = d
            n = c.integer(c.key(t, "n", at), f"{at}.n", minimum=1)
            if n is not None and d is not None and n_train is not None and n != n_train - d:
                c.add(f"{at}.n", f"is {n}, but n_train - d is {n_train - d}")
            adf = _check_adf(c, c.key(t, "adf", at), f"{at}.adf", "c", alpha)
            kp = _check_kpss(c, c.key(t, "kpss", at), f"{at}.kpss", "c", alpha)
            _check_verdict(c, c.key(t, "verdict", at), adf, kp, f"{at}.verdict")
            trend = c.key(t, "with_trend", at)
            if trend is not _MISSING and (wt := c.obj(trend, f"{at}.with_trend")) is not None:
                tadf = _check_adf(c, c.key(wt, "adf", f"{at}.with_trend"), f"{at}.with_trend.adf", "ct", alpha)
                tkp = _check_kpss(c, c.key(wt, "kpss", f"{at}.with_trend"), f"{at}.with_trend.kpss", "ct", alpha)
                _check_verdict(c, c.key(wt, "verdict", f"{at}.with_trend"), tadf, tkp, f"{at}.with_trend.verdict")
            tests.append(None if d is None or adf is None or kp is None else (d, adf, kp))

    decision = c.key(root, "decision", "data")
    if decision is not _MISSING and (dc := c.obj(decision, "data.decision")) is not None:
        d_selected = c.integer(c.key(dc, "d_selected", "data.decision"), "data.decision.d_selected")
        c.string(c.key(dc, "rule", "data.decision"), "data.decision.rule")
        conflict = _boolean(c, c.key(dc, "tests_conflict", "data.decision"), "data.decision.tests_conflict")
        if transforms and None not in tests and d_selected is not None and conflict is not None:
            # ADR-0002 section 2: the smallest d where ADF rejects and KPSS does not; else the
            # smallest d where KPSS does not reject; else the largest d. Re-applied here.
            ordered = sorted(t for t in tests if t is not None)
            passing = [d for d, a, k in ordered if a and not k]
            fallback = [d for d, _, k in ordered if not k]
            expected = (passing[0], False) if passing else ((fallback[0], True) if fallback else (ordered[-1][0], True))
            if (d_selected, conflict) != expected:
                c.add("data.decision", f"says d = {d_selected} with tests_conflict {conflict}, but the rule gives d = {expected[0]} with {expected[1]}")
        nd = c.key(dc, "pmdarima_ndiffs", "data.decision")
        if nd is not _MISSING and (ndo := c.obj(nd, "data.decision.pmdarima_ndiffs")) is not None:
            at = "data.decision.pmdarima_ndiffs"
            status = _choice(c, c.key(ndo, "status", at), CHECK_STATUSES, f"{at}.status")
            reason = c.key(ndo, "reason", at)
            version = c.key(ndo, "version", at)
            c.number(c.key(ndo, "alpha", at), f"{at}.alpha")
            max_d = c.integer(c.key(ndo, "max_d", at), f"{at}.max_d")
            found = {test: c.key(ndo, test, at) for test in ("kpss", "adf", "pp")}
            agrees = c.key(ndo, "agrees", at)
            if status == "ok":
                if reason is not _MISSING and reason is not None:
                    c.add(f"{at}.reason", f"must be null when status is ok, got {_show(reason)}")
                if version is not _MISSING:
                    c.string(version, f"{at}.version")
                values = []
                for test, value in found.items():
                    v = c.integer(value, f"{at}.{test}")
                    if v is not None and max_d is not None and v > max_d:
                        c.add(f"{at}.{test}", f"{v} is above max_d {max_d}")
                    values.append(v)
                ok = _boolean(c, agrees, f"{at}.agrees")
                if ok is not None and d_selected is not None and None not in values and ok != all(v == d_selected for v in values):
                    c.add(f"{at}.agrees", f"is {ok}, but kpss, adf and pp are {values} and d_selected is {d_selected}")
            elif status == "unavailable":
                if reason is not _MISSING:
                    c.string(reason, f"{at}.reason")
                if version is not _MISSING:
                    _text_or_null(c, version, f"{at}.version")
                for test, value in [*found.items(), ("agrees", agrees)]:
                    if value is not _MISSING and value is not None:
                        c.add(f"{at}.{test}", f"must be null when status is unavailable, got {_show(value)}")
        if d_selected is not None and transforms and None not in tests and d_selected not in [t[0] for t in tests if t]:
            c.add("data.decision.d_selected", f"{d_selected} is not the d of any transform")
    return c.problems


@_capped
def validate_acf_pacf(data: object) -> list[str]:
    """Every problem in an `acf_pacf` payload (contract.md section 3.5)."""
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    c.equals(c.key(root, "sample", "data"), "train", "data.sample")
    nlags = c.integer(c.key(root, "nlags", "data"), "data.nlags", minimum=1)
    alpha = c.number(c.key(root, "alpha", "data"), "data.alpha")
    if alpha is not None and not 0 < alpha < 1:
        c.add("data.alpha", f"must be between 0 and 1, got {alpha}")
    z = c.number(c.key(root, "z", "data"), "data.z")
    if z is not None and z <= 0:
        c.add("data.z", f"must be positive, got {z}")
    elif z is not None and alpha is not None and Z_FOR_ALPHA.get(alpha) != z:
        known = Z_FOR_ALPHA.get(alpha)
        c.add("data.z", f"is {z}, but the two-sided z for alpha {alpha} is {known}" if known is not None else f"no z is listed for alpha {alpha}; this reader knows {sorted(Z_FOR_ALPHA)}")
    settings = c.key(root, "acf_settings", "data")
    if settings is not _MISSING and (st := c.obj(settings, "data.acf_settings")) is not None:
        for name in ("fft", "adjusted", "bartlett_confint"):
            _boolean(c, c.key(st, name, "data.acf_settings"), f"data.acf_settings.{name}")
    c.string(c.key(root, "pacf_method", "data"), "data.pacf_method")
    series = _list(c, c.key(root, "series", "data"), "data.series", len(TRANSFORM_D), "series")  # one per transform at most
    if series is not None:
        if not series:
            c.add("data.series", "must not be empty")
        previous: int | None = None
        for index, item in enumerate(series):
            at = f"data.series[{index}]"
            s = c.obj(item, at)
            if s is None:
                continue
            ident = _choice(c, c.key(s, "transform", at), tuple(TRANSFORM_D), f"{at}.transform")
            d = c.integer(c.key(s, "d", at), f"{at}.d")
            if ident is not None and d is not None and TRANSFORM_D[ident] != d:
                c.add(f"{at}.d", f"is {d}, but {ident!r} has d = {TRANSFORM_D[ident]}")
            if d is not None:
                if previous is not None and d <= previous:
                    c.add(f"{at}.d", f"{d} does not come after {previous}; series are sorted by d")
                previous = d
            c.integer(c.key(s, "n", at), f"{at}.n", minimum=2)
            counts = {name: c.integer(c.key(s, f"{name}_outside_count", at), f"{at}.{name}_outside_count") for name in ("acf", "pacf")}
            rows = _list(c, c.key(s, "rows", at), f"{at}.rows", MAX_LIST, "rows")
            if rows is None:
                continue
            flags: dict[str, list[bool | None]] = {"acf": [], "pacf": []}
            if nlags is not None and len(rows) != nlags + 1:
                c.add(f"{at}.rows", f"has {len(rows)} rows, but lags 0 to {nlags} make {nlags + 1}")
            for k, item_row in enumerate(rows):
                rat = f"{at}.rows[{k}]"
                row = c.obj(item_row, rat)
                if row is None:
                    continue
                lag = c.integer(c.key(row, "lag", rat), f"{rat}.lag")
                if lag is not None and lag != k:
                    c.add(f"{rat}.lag", f"is {lag}, expected {k}")
                for name in ("acf", "pacf"):
                    v = c.number(c.key(row, name, rat), f"{rat}.{name}")
                    if v is not None and not -1 <= v <= 1:
                        c.add(f"{rat}.{name}", f"must be between -1 and 1, got {v}")
                    if v is not None and k == 0 and v != 1:
                        c.add(f"{rat}.{name}", f"is {v} at lag 0, where it is 1 by definition")
                for name in ("acf_band", "pacf_band"):
                    b = c.number(c.key(row, name, rat), f"{rat}.{name}")
                    if b is not None and (b != 0 if k == 0 else b <= 0):
                        c.add(f"{rat}.{name}", f"is {b}; a band is 0 at lag 0 and positive at every other lag")
                for name in ("acf", "pacf"):
                    flag = _boolean(c, c.key(row, f"{name}_outside", rat), f"{rat}.{name}_outside")
                    flags[name].append(flag)
                    value, band = row.get(name), row.get(f"{name}_band")
                    # Checked only when the value and the band passed their own checks above.
                    if flag is not None and _finite(value) and _finite(band) and -1 <= value <= 1 and (band == 0 if k == 0 else band > 0):  # type: ignore[operator]
                        want = k >= 1 and abs(value) > band  # type: ignore[arg-type, operator]
                        if flag != want:
                            c.add(f"{rat}.{name}_outside", f"is {flag}, but |{name}| {abs(value)} {'>' if abs(value) > band else '<='} band {band} at lag {k}")
            for name in ("acf", "pacf"):
                if counts[name] is not None and None not in flags[name] and counts[name] != sum(flags[name]):  # type: ignore[arg-type]
                    c.add(f"{at}.{name}_outside_count", f"is {counts[name]}, but {sum(flags[name])} rows are flagged")  # type: ignore[arg-type]
    return c.problems


def _finite(value: object) -> bool:
    """A number that is a finite double. An int too big for a double (a JSON integer of 400 digits;
    JSON.parse reads it as Infinity) is not one, and is refused here: math.isfinite would raise."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


# The two-sided normal quantile z = Phi^-1(1 - alpha / 2) for each alpha a payload may use. A table
# rather than a computation, so that both readers hold the same exact double (scipy's
# norm.ppf(0.975)); a new alpha means a new row here and in contract.order.ts.
Z_FOR_ALPHA = {0.05: 1.959963984540054}


def _check_triple(c: _Checker, value: object, path: str) -> list[int] | None:
    triple = c.array(value, path)
    if triple is None:
        return None
    if len(triple) != 3:
        c.add(path, f"expected [p, d, q], got {_show(triple)}")
        return None
    out = [c.integer(v, f"{path}[{i}]") for i, v in enumerate(triple)]
    return None if None in out else out  # type: ignore[return-value]


# The start a cell's kept run came from (selection.py): statsmodels' default, the k-th seeded random
# start, or a nested model one step smaller, padded with zeros; ", polished" when that run did not
# converge and was restarted from its own estimates.
_START = re.compile(
    r"(?:default|random ([1-9][0-9]*)|nested \(([0-9]+), ([0-9]+), ([0-9]+)\) ([nct])(, perturbed [+-])?)(, polished)?"
    r"|polished from \(([0-9]+), ([0-9]+), ([0-9]+)\) ([nct])"
)
# The largest log-likelihood a cell may lose against a model it nests (selection.NESTING_TOLERANCE).
# Pinned here, not read from the file being checked: a file cannot loosen its own check.
NESTING_TOLERANCE = 2e-3
# The grid's dimensions (selection.GRID_ORDERS, GRID_SPECS; tests/test_payloads.py ties them): p and
# q run from 0 to 5 and d from 0 to 2, each d with some of the three trend codes, so a grid has at
# most 6 x 6 x 3 x 3 = 324 cells (the export's has 144). A cell has at most p + q + 2 = 12 parameters.
GRID_MAX_ORDER = 5
GRID_MAX_D = 2
MAX_GRID_CELLS = (GRID_MAX_ORDER + 1) ** 2 * (GRID_MAX_D + 1) * len(TREND_CODES)
MAX_CELL_PARAMS = 2 * GRID_MAX_ORDER + 2
# The pmdarima cross-check (selection.PMDARIMA_RUNS) makes two runs. Each stepwise search fits each
# (order, seasonal order, intercept) once (pmdarima/arima/_auto_solvers.py:230, `results_dict`), with p
# and q up to max_p = max_q = 5 (both runs) and one d, non-seasonal: at most 6 x 6 x 2 = 72 fits.
MAX_PMDARIMA_RUNS = 2
MAX_VISITED = 72
START_GRAMMAR = "'default', 'random <k>', 'nested (p, d, q) <trend>' (optionally ', perturbed +' or '-'), each optionally followed by ', polished', or 'polished from (p, d, q) <trend>'"


def _rank(cell: dict[str, Any], criterion: str) -> tuple[float, int, int, int, str]:
    return (cell[criterion], cell["k_params"], cell["p"] + cell["q"], cell["p"], cell["trend"])


def _check_cell(c: _Checker, item: object, at: str, n_train: int | None, threshold: float | None) -> dict[str, Any] | None:
    """One grid cell; returns its fields when the cell is valid."""
    cell = c.obj(item, at)
    if cell is None:
        return None
    before = len(c.problems)
    d = c.integer(c.key(cell, "d", at), f"{at}.d")
    p = c.integer(c.key(cell, "p", at), f"{at}.p")
    q = c.integer(c.key(cell, "q", at), f"{at}.q")
    trend = _choice(c, c.key(cell, "trend", at), TREND_CODES, f"{at}.trend")
    status = _choice(c, c.key(cell, "status", at), CELL_STATUSES, f"{at}.status")
    k = c.integer(c.key(cell, "k_params", at), f"{at}.k_params", minimum=1)
    if None not in (p, q, trend, k) and k != p + q + (trend != "n") + 1:  # type: ignore[operator]
        c.add(f"{at}.k_params", f"is {k}, but p + q + trend terms + sigma2 is {p + q + (trend != 'n') + 1}")  # type: ignore[operator]
    reason = c.key(cell, "reason", at)
    if reason is not _MISSING and status is not None:
        if status == "ok" and reason is not None:
            c.add(f"{at}.reason", f"must be null for an ok cell, got {_show(reason)}")
        elif status != "ok":
            c.string(reason, f"{at}.reason")
    warns = _list(c, c.key(cell, "warnings", at), f"{at}.warnings", MAX_WARNINGS, "warnings")
    for i, w in enumerate(warns or []):
        wo = c.obj(w, f"{at}.warnings[{i}]")
        if wo is not None:
            c.string(c.key(wo, "category", f"{at}.warnings[{i}]"), f"{at}.warnings[{i}].category")
            message = c.key(wo, "message", f"{at}.warnings[{i}]")
            if message is not _MISSING and not isinstance(message, str):
                c.add(f"{at}.warnings[{i}].message", f"expected a string, got {_show(message)}")
    fields = ("aic", "aicc", "bic", "llf", "nobs_effective", "converged", "iterations", "warnflag", "max_inv_root_ar", "max_inv_root_ma", "delta_aic", "start", "params")
    values = {name: c.key(cell, name, at) for name in (*fields, "error")}
    out: dict[str, Any] = {"d": d, "p": p, "q": q, "trend": trend, "status": status, "k_params": k, "start": None}
    c.integer(c.key(cell, "starts_tried", at), f"{at}.starts_tried", minimum=1)
    if status == "failed":
        for name in fields:
            if values[name] is not _MISSING and values[name] is not None:
                c.add(f"{at}.{name}", f"must be null for a failed cell, got {_show(values[name])}")
        if values["error"] is not _MISSING:
            c.string(values["error"], f"{at}.error")
        out.update(aic=None, delta_aic=None, bic=None, llf=None)
    elif status is not None:
        if values["error"] is not _MISSING and values["error"] is not None:
            c.add(f"{at}.error", f"must be null unless the cell failed, got {_show(values['error'])}")
        for name in ("aic", "aicc", "bic", "llf"):
            out[name] = c.number(values[name], f"{at}.{name}")
        label = c.string(values["start"], f"{at}.start")
        if label is not None:
            out["start"] = _START.fullmatch(label)
            if out["start"] is None:
                c.add(f"{at}.start", f"must be {START_GRAMMAR}, got {_show(label)}")
        params = c.obj(values["params"], f"{at}.params") if values["params"] is not _MISSING else None
        if params is not None:
            if k is not None and len(params) != k:
                c.add(f"{at}.params", f"has {len(params)} entries, but k_params is {k}")
            if len(params) <= MAX_CELL_PARAMS:  # a longer object is refused above (k is at most this), and not walked
                for name, value in params.items():
                    c.number(value, f"{at}.params[{_show(name)}]")  # a key from the file: quoted, as any value is
        nobs = c.integer(values["nobs_effective"], f"{at}.nobs_effective", minimum=1)
        if nobs is not None and n_train is not None and d is not None and nobs != n_train - d:
            c.add(f"{at}.nobs_effective", f"is {nobs}, but n_train - d is {n_train - d}")
        converged = _boolean(c, values["converged"], f"{at}.converged")
        c.integer(values["iterations"], f"{at}.iterations")
        c.integer(values["warnflag"], f"{at}.warnflag")
        roots = {}
        for name, order in (("max_inv_root_ar", p), ("max_inv_root_ma", q)):
            value = values[name]
            if order == 0:
                if value is not _MISSING and value is not None:
                    c.add(f"{at}.{name}", f"must be null when the order is 0, got {_show(value)}")
                roots[name] = None
            else:
                roots[name] = c.number(value, f"{at}.{name}")
                if roots[name] is not None and roots[name] < 0:
                    c.add(f"{at}.{name}", f"must not be negative, got {roots[name]}")
        if converged is not None and threshold is not None and None not in (p, q) and len(c.problems) == before:
            near = any(r is not None and r > threshold for r in roots.values())
            expected = "not_converged" if not converged else ("near_unit_root" if near else "ok")
            if status != expected:
                c.add(f"{at}.status", f"is {status!r}, but converged {converged} and the root moduli make it {expected!r}")
        delta = values["delta_aic"]
        out["delta_aic"] = c.number(delta, f"{at}.delta_aic", nullable=True) if delta is not _MISSING else None
    return out if len(c.problems) == before else None


def _nests(small: dict[str, Any], big: dict[str, Any]) -> bool:
    """`small` is a special case of `big`: same d, no more AR or MA lags, the same trend or none."""
    same = all(small[k] == big[k] for k in ("d", "p", "q", "trend"))
    return not same and small["d"] == big["d"] and small["p"] <= big["p"] and small["q"] <= big["q"] and small["trend"] in (big["trend"], "n")


def _whole(digits: str) -> int:
    """A run of digits from a start label as an int; one too long for a safe integer reads as one past
    the largest (int() of more than 4,300 digits raises, and no bound here is near 2**53)."""
    return int(digits) if len(digits) <= 15 else MAX_SAFE_INTEGER + 1


def _check_starts(c: _Checker, cells: list[dict[str, Any]], specs: list[tuple[int, list[str]]], ps: list[int], qs: list[int], random_starts: int | None) -> None:
    """A random start must be one the settings drew; a nested start must be a model of the grid one
    step smaller than the cell (the next smaller p or q, or no trend), so the start existed."""
    trends = dict(specs)
    for i, x in enumerate(cells):
        match = x["start"]
        if match is None:
            continue
        at = f"data.cells[{i}].start"
        if match.group(1) is not None:
            if random_starts is not None and _whole(match.group(1)) > random_starts:
                c.add(at, f"is {_show(match.group(0))}, but fit_settings.random_starts is {random_starts}")
            if x["p"] == 0 or x["q"] == 0:
                c.add(at, f"is {_show(match.group(0))}, but random starts are drawn only when p and q are both at least 1")
        elif match.group(8) is not None:
            sp, sd, sq, st = _whole(match.group(8)), _whole(match.group(9)), _whole(match.group(10)), match.group(11)
            if sd != x["d"] or sp not in ps or sq not in qs or st not in trends.get(x["d"], []):
                c.add(at, f"is {_show(match.group(0))}, which is not a cell of the grid with the same d")
        elif match.group(2) is not None:
            sp, sd, sq, st = _whole(match.group(2)), _whole(match.group(3)), _whole(match.group(4)), match.group(5)
            if match.group(6) is not None and (sp, sq) == (x["p"], x["q"]):
                c.add(at, f"is {_show(match.group(0))}, but the step that drops the trend adds no AR or MA coefficient to perturb")
            steps = []
            if x["p"] in ps and ps.index(x["p"]) > 0:
                steps.append((ps[ps.index(x["p"]) - 1], x["q"], x["trend"]))
            if x["q"] in qs and qs.index(x["q"]) > 0:
                steps.append((x["p"], qs[qs.index(x["q"]) - 1], x["trend"]))
            if x["trend"] != "n" and "n" in trends.get(x["d"], []):
                steps.append((x["p"], x["q"], "n"))
            if sd != x["d"] or (sp, sq, st) not in steps:
                c.add(at, f"is {_show(match.group(0))}, which is not a model of the grid one step smaller than ({x['p']}, {x['d']}, {x['q']}) {x['trend']}")


def _check_nesting(c: _Checker, cells: list[dict[str, Any]], tolerance: float) -> None:
    """No fitted cell may score a lower log-likelihood than a model it nests, by more than the
    tolerance: setting the extra coefficients to zero gives the smaller model, so a maximum of the
    bigger likelihood is at least as high. A lower one is a local optimum."""
    fitted = [(i, x) for i, x in enumerate(cells) if x["llf"] is not None]
    for i, big in fitted:
        for _, small in fitted:
            if _nests(small, big) and big["llf"] < small["llf"] - tolerance:
                c.add(
                    f"data.cells[{i}].llf",
                    f"is {big['llf']}, below the {small['llf']} of ({small['p']}, {small['d']}, {small['q']}) {small['trend']}, a model it nests, by more than {tolerance}",
                )


def _check_grid_axis(c: _Checker, value: object, path: str) -> list[int] | None:
    items = _list(c, value, path, GRID_MAX_ORDER + 1, "orders")
    if items is None:
        return None
    out = [_bounded(c, v, f"{path}[{i}]", GRID_MAX_ORDER) for i, v in enumerate(items)]
    if not out:
        c.add(path, "must not be empty")
    if None in out:
        return None
    if any(b <= a for a, b in zip(out, out[1:])):  # type: ignore[operator]
        c.add(path, f"must be strictly ascending, got {_show(out)}")
        return None
    return out  # type: ignore[return-value]


@_capped
def validate_aic_grid(data: object) -> list[str]:
    """Every problem in an `aic_grid` payload (contract.md section 3.6)."""
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    c.equals(c.key(root, "sample", "data"), "train", "data.sample")
    n_train = c.integer(c.key(root, "n_train", "data"), "data.n_train", minimum=1)
    c.equals(c.key(root, "criterion", "data"), "aic", "data.criterion")

    ps = qs = None
    specs: list[tuple[int, list[str]]] | None = None
    grid = c.key(root, "grid", "data")
    if grid is not _MISSING and (gd := c.obj(grid, "data.grid")) is not None:
        ps = _check_grid_axis(c, c.key(gd, "p", "data.grid"), "data.grid.p")
        qs = _check_grid_axis(c, c.key(gd, "q", "data.grid"), "data.grid.q")
        raw_specs = _list(c, c.key(gd, "specs", "data.grid"), "data.grid.specs", GRID_MAX_D + 1, "specs")
        if raw_specs is not None:
            specs = []
            before = len(c.problems)
            if not raw_specs:
                c.add("data.grid.specs", "must not be empty")
            for i, item in enumerate(raw_specs):
                at = f"data.grid.specs[{i}]"
                sp = c.obj(item, at)
                if sp is None:
                    continue
                d = _bounded(c, c.key(sp, "d", at), f"{at}.d", GRID_MAX_D)
                trends = _list(c, c.key(sp, "trends", at), f"{at}.trends", len(TREND_CODES), "trends")
                codes = [_choice(c, t, TREND_CODES, f"{at}.trends[{j}]") for j, t in enumerate(trends or [])]
                if trends is not None and (not codes or None in codes or any(b <= a for a, b in zip(codes, codes[1:]))):  # type: ignore[operator]
                    c.add(f"{at}.trends", f"must be a non-empty list of trend codes in alphabetical order, got {_show(trends)}")
                if d is not None and specs and d <= specs[-1][0]:
                    c.add(f"{at}.d", f"{d} does not come after {specs[-1][0]}; specs are sorted by d")
                if d is not None and trends is not None:
                    specs.append((d, [t for t in codes if t is not None]))
            if len(c.problems) != before:
                specs = None

    threshold = random_starts = tolerance = None
    settings = c.key(root, "fit_settings", "data")
    if settings is not _MISSING and (fs := c.obj(settings, "data.fit_settings")) is not None:
        at = "data.fit_settings"
        for name in ("library", "version", "model", "method", "optimizer"):
            c.string(c.key(fs, name, at), f"{at}.{name}")
        c.integer(c.key(fs, "maxiter", at), f"{at}.maxiter", minimum=1)
        for name in ("enforce_stationarity", "enforce_invertibility", "concentrate_scale", "simple_differencing"):
            _boolean(c, c.key(fs, name, at), f"{at}.{name}")
        threshold = c.number(c.key(fs, "near_unit_root_threshold", at), f"{at}.near_unit_root_threshold")
        if threshold is not None and not 0 < threshold <= 1:
            c.add(f"{at}.near_unit_root_threshold", f"must be in (0, 1], got {threshold}")
            threshold = None
        c.string(c.key(fs, "starts", at), f"{at}.starts")
        random_starts = c.integer(c.key(fs, "random_starts", at), f"{at}.random_starts")
        c.integer(c.key(fs, "start_seed", at), f"{at}.start_seed")
        keep = c.number(c.key(fs, "keep_tolerance", at), f"{at}.keep_tolerance")
        if keep is not None and keep < 0:
            c.add(f"{at}.keep_tolerance", f"must not be negative, got {keep}")
        tolerance = c.number(c.key(fs, "nesting_tolerance", at), f"{at}.nesting_tolerance")
        if tolerance is not None and tolerance != NESTING_TOLERANCE:
            c.add(f"{at}.nesting_tolerance", f"is {tolerance}, but this reader checks nesting at {NESTING_TOLERANCE}")
        tolerance = NESTING_TOLERANCE  # the reader's own bound, whatever the file says

    cells: list[dict[str, Any]] | None = None
    raw_cells = _list(c, c.key(root, "cells", "data"), "data.cells", MAX_GRID_CELLS, "cells")
    if raw_cells is not None:
        parsed = [_check_cell(c, item, f"data.cells[{i}]", n_train, threshold) for i, item in enumerate(raw_cells)]
        if None not in parsed:
            cells = parsed  # type: ignore[assignment]
    if cells is not None and specs is not None and ps is not None and qs is not None:
        expected = [(d, t, p, q) for d, trends in specs for t in trends for p in ps for q in qs]
        found = [(x["d"], x["trend"], x["p"], x["q"]) for x in cells]
        if found != sorted(expected):
            first = next((i for i, (a, b) in enumerate(zip(found, sorted(expected))) if a != b), min(len(found), len(expected)))
            c.add("data.cells", f"must be one cell per (d, trend, p, q) of the grid, sorted; {len(found)} cells, the first difference is at index {first}")
            cells = None
    if cells is not None and specs is not None and ps is not None and qs is not None:
        _check_starts(c, cells, specs, ps, qs, random_starts)
        if tolerance is not None:
            _check_nesting(c, cells, tolerance)

    best: dict[int, dict[str, Any] | None] = {}
    if cells is not None and specs is not None:
        for d, _ in specs:
            eligible = [x for x in cells if x["d"] == d and x["status"] == "ok"]
            best[d] = min(eligible, key=lambda x: _rank(x, "aic")) if eligible else None
            for i, x in enumerate(cells):
                if x["d"] != d:
                    continue
                want = None if x["aic"] is None or best[d] is None else x["aic"] - best[d]["aic"]
                if x["delta_aic"] != want:
                    c.add(f"data.cells[{i}].delta_aic", f"is {_show(x['delta_aic'])}, but aic minus the lowest eligible AIC of d = {d} is {_show(want)}")

    selection = c.key(root, "selection", "data")
    chosen: dict[str, Any] | None = None
    if selection is not _MISSING and (sl := c.obj(selection, "data.selection")) is not None:
        at = "data.selection"
        d_sel = c.integer(c.key(sl, "d_selected", at), f"{at}.d_selected")
        order = _check_triple(c, c.key(sl, "order", at), f"{at}.order")
        trend = _choice(c, c.key(sl, "trend", at), TREND_CODES, f"{at}.trend")
        aic = c.number(c.key(sl, "aic", at), f"{at}.aic")
        bic = c.number(c.key(sl, "bic", at), f"{at}.bic")
        k = c.integer(c.key(sl, "k_params", at), f"{at}.k_params", minimum=1)
        c.string(c.key(sl, "rule", at), f"{at}.rule")
        within = _list_of(c, c.key(sl, "within_2_aic", at), f"{at}.within_2_aic", _NEAR_TIE_FIELDS, MAX_GRID_CELLS, "cells")
        bic_choice = _fields(c, c.key(sl, "bic_choice", at), f"{at}.bic_choice", _BIC_FIELDS)
        per_d = _best_per_d(c, c.key(sl, "best_per_d", at), f"{at}.best_per_d")
        counts = _list_of(c, c.key(sl, "status_counts", at), f"{at}.status_counts", _COUNT_FIELDS, GRID_MAX_D + 1, "entries")
        if order is not None and d_sel is not None and order[1] != d_sel:
            c.add(f"{at}.order", f"has d = {order[1]}, but d_selected is {d_sel}")
        if specs is not None and d_sel is not None and d_sel not in [d for d, _ in specs]:
            c.add(f"{at}.d_selected", f"{d_sel} is not a d of the grid")
        elif cells is not None and specs is not None and d_sel is not None:
            top = best[d_sel]
            eligible = [x for x in cells if x["d"] == d_sel and x["status"] == "ok"]
            if top is None:
                c.add(at, f"no cell with d = {d_sel} is ok, so nothing can be selected")
            elif order is not None and trend is not None:
                if (top["p"], top["q"], top["trend"]) != (order[0], order[2], trend):
                    c.add(at, f"selects ({order[0]}, {d_sel}, {order[2]}) trend {trend!r}, but the lowest eligible AIC is ({top['p']}, {d_sel}, {top['q']}) trend {top['trend']!r}")
                elif (aic, bic, k) != (top["aic"], top["bic"], top["k_params"]):
                    c.add(at, "aic, bic or k_params differ from the selected cell's")
                else:
                    chosen = {"d": d_sel, "order": order, "trend": trend}
            if within is not None and top is not None:
                want = [
                    (x["p"], x["q"], x["trend"], x["aic"], x["delta_aic"])
                    for x in sorted((x for x in eligible if x["aic"] - top["aic"] <= 2.0), key=lambda x: _rank(x, "aic"))
                ]
                if within != want:
                    c.add(f"{at}.within_2_aic", "must list every ok cell of d_selected within 2 AIC of the best, with its aic and delta_aic, sorted")
            if bic_choice is not None and eligible:
                top_bic = min(eligible, key=lambda x: _rank(x, "bic"))
                if bic_choice != (top_bic["p"], top_bic["q"], top_bic["trend"], top_bic["aic"], top_bic["bic"]):
                    c.add(f"{at}.bic_choice", "must be the ok cell of d_selected with the lowest BIC")
            if per_d is not None:
                want_per_d = [(d, None if best[d] is None else (best[d]["p"], best[d]["q"], best[d]["trend"], best[d]["aic"])) for d, _ in specs]  # type: ignore[index]
                if per_d != want_per_d:
                    c.add(f"{at}.best_per_d", "must give, for each d of the grid in order, its lowest-AIC ok cell or null")
            if counts is not None:
                want_counts = [(d, *[sum(1 for x in cells if x["d"] == d and x["status"] == s) for s in CELL_STATUSES]) for d, _ in specs]
                if counts != want_counts:
                    c.add(f"{at}.status_counts", "must count each status for each d of the grid, in order")

    check = c.key(root, "pmdarima_check", "data")
    if check is not _MISSING and (pc := c.obj(check, "data.pmdarima_check")) is not None:
        at = "data.pmdarima_check"
        status = _choice(c, c.key(pc, "status", at), CHECK_STATUSES, f"{at}.status")
        reason = c.key(pc, "reason", at)
        version = c.key(pc, "version", at)
        runs = _list(c, c.key(pc, "runs", at), f"{at}.runs", MAX_PMDARIMA_RUNS, "runs")
        if status == "ok":
            if reason is not _MISSING and reason is not None:
                c.add(f"{at}.reason", f"must be null when status is ok, got {_show(reason)}")
            if version is not _MISSING:
                c.string(version, f"{at}.version")
            if runs is not None and not runs:
                c.add(f"{at}.runs", "must not be empty when status is ok")
        elif status == "unavailable":
            if reason is not _MISSING:
                c.string(reason, f"{at}.reason")
            if version is not _MISSING:
                _text_or_null(c, version, f"{at}.version")
            if runs:
                c.add(f"{at}.runs", "must be empty when status is unavailable")
        for i, item in enumerate(runs or []):
            _check_run(c, item, f"{at}.runs[{i}]", cells, chosen)
    return c.problems


# Typed views of the small objects inside `selection`: (field, kind) pairs. Unknown keys are ignored,
# as everywhere in `data`; each known field is type-checked before any comparison, so a `true` can
# never pass for a 1 (Python's True == 1 is True; JavaScript's true === 1 is false).
_NEAR_TIE_FIELDS = (("p", "int"), ("q", "int"), ("trend", "trend"), ("aic", "number"), ("delta_aic", "number"))
_BIC_FIELDS = (("p", "int"), ("q", "int"), ("trend", "trend"), ("aic", "number"), ("bic", "number"))
_BEST_FIELDS = (("p", "int"), ("q", "int"), ("trend", "trend"), ("aic", "number"))
_COUNT_FIELDS = (("d", "int"), *((status, "int") for status in CELL_STATUSES))


def _fields(c: _Checker, value: object, path: str, spec: tuple[tuple[str, str], ...]) -> tuple[Any, ...] | None:
    if value is _MISSING:
        return None
    obj = c.obj(value, path)
    if obj is None:
        return None
    before = len(c.problems)
    out: list[Any] = []
    for name, kind in spec:
        raw = c.key(obj, name, path)
        if kind == "int":
            out.append(c.integer(raw, f"{path}.{name}"))
        elif kind == "trend":
            out.append(_choice(c, raw, TREND_CODES, f"{path}.{name}"))
        else:
            out.append(c.number(raw, f"{path}.{name}"))
    return tuple(out) if len(c.problems) == before else None


def _list_of(c: _Checker, value: object, path: str, spec: tuple[tuple[str, str], ...], most: int, what: str) -> list[tuple[Any, ...]] | None:
    items = _list(c, value, path, most, what)
    if items is None:
        return None
    parsed = [_fields(c, item, f"{path}[{i}]", spec) for i, item in enumerate(items)]
    return None if None in parsed else parsed  # type: ignore[return-value]


def _best_per_d(c: _Checker, value: object, path: str) -> list[tuple[int, tuple[Any, ...] | None]] | None:
    items = _list(c, value, path, GRID_MAX_D + 1, "entries")  # one per d at most
    if items is None:
        return None
    before = len(c.problems)
    out: list[tuple[int, tuple[Any, ...] | None]] = []
    for i, item in enumerate(items):
        entry = c.obj(item, f"{path}[{i}]")
        if entry is None:
            continue
        d = c.integer(c.key(entry, "d", f"{path}[{i}]"), f"{path}[{i}].d")
        raw = c.key(entry, "cell", f"{path}[{i}]")
        cell = None if raw is None or raw is _MISSING else _fields(c, raw, f"{path}[{i}].cell", _BEST_FIELDS)
        if d is not None:
            out.append((d, cell))
    return out if len(c.problems) == before else None


def _check_run(c: _Checker, item: object, at: str, cells: list[dict[str, Any]] | None, chosen: dict[str, Any] | None) -> None:
    run = c.obj(item, at)
    if run is None:
        return
    c.string(c.key(run, "label", at), f"{at}.label")
    settings = c.key(run, "settings", at)
    if settings is not _MISSING:
        c.obj(settings, f"{at}.settings")
    order = _check_triple(c, c.key(run, "order", at), f"{at}.order")
    intercept = _boolean(c, c.key(run, "with_intercept", at), f"{at}.with_intercept")
    before = len(c.problems)
    trend = _choice(c, c.key(run, "trend", at), TREND_CODES, f"{at}.trend", nullable=True)
    trend_ok = "trend" in run and len(c.problems) == before  # a valid code, or null
    if order is not None and intercept is not None and trend_ok:
        want = "n" if not intercept else {0: "c", 1: "t"}.get(order[1])
        if trend != want:
            c.add(f"{at}.trend", f"is {_show(trend)}, but d = {order[1]} with_intercept {intercept} is {_show(want)}")
    aic = c.number(c.key(run, "aic", at), f"{at}.aic")
    _boolean(c, c.key(run, "converged", at), f"{at}.converged")
    c.integer(c.key(run, "iterations", at), f"{at}.iterations")
    visited = _list(c, c.key(run, "visited", at), f"{at}.visited", MAX_VISITED, "fits")
    if visited is not None:
        if not visited:
            c.add(f"{at}.visited", "must not be empty: the chosen model is its first entry")
        for j, v in enumerate(visited):
            vat = f"{at}.visited[{j}]"
            vo = c.obj(v, vat)
            if vo is None:
                continue
            vorder = _check_triple(c, c.key(vo, "order", vat), f"{vat}.order")
            vint = _boolean(c, c.key(vo, "with_intercept", vat), f"{vat}.with_intercept")
            vaic = c.number(c.key(vo, "aic", vat), f"{vat}.aic")
            if j == 0 and None not in (vorder, vint, vaic, order, intercept, aic) and (vorder, vint, vaic) != (order, intercept, aic):
                c.add(vat, "must be the chosen model: the same order, with_intercept and aic as the run")
    warns = _list(c, c.key(run, "warnings", at), f"{at}.warnings", MAX_WARNINGS, "warnings")
    for j, w in enumerate(warns or []):
        if (wo := c.obj(w, f"{at}.warnings[{j}]")) is not None:
            c.string(c.key(wo, "category", f"{at}.warnings[{j}]"), f"{at}.warnings[{j}].category")
    agreement = c.key(run, "agreement", at)
    if agreement is _MISSING or (ag := c.obj(agreement, f"{at}.agreement")) is None:
        return
    aat = f"{at}.agreement"
    before = len(c.problems)
    flags = tuple(_boolean(c, c.key(ag, name, aat), f"{aat}.{name}") for name in ("d", "order", "trend"))
    status = _choice(c, c.key(ag, "same_order_status", aat), CELL_STATUSES, f"{aat}.same_order_status", nullable=True)
    gap_raw = c.key(ag, "aic_gap_same_order", aat)
    gap = c.number(gap_raw, f"{aat}.aic_gap_same_order", nullable=True)
    if len(c.problems) != before or order is None or aic is None or not trend_ok:
        return
    if chosen is not None:
        want_flags = (order[1] == chosen["d"], order == chosen["order"], trend == chosen["trend"])
        if flags != want_flags:
            c.add(aat, f"d, order and trend say {flags}, but comparing with the selection gives {want_flags}")
    if cells is not None:
        same = next((x for x in cells if (x["d"], x["p"], x["q"], x["trend"]) == (order[1], order[0], order[2], trend)), None)
        want_status = None if same is None else same["status"]
        want_gap = None if same is None or same["aic"] is None else aic - same["aic"]
        if status != want_status or gap != want_gap:
            c.add(aat, f"same_order_status {_show(status)} and aic_gap_same_order {_show(gap)} must be {_show(want_status)} and {_show(want_gap)}")


# --- milestone 3: fit and residuals_<id> (contract.md 3.7 and 3.8) -----------------------------------
# The app's parsers (contract.fit.ts) check the same shapes, enums, nulls, lengths, bounds and integer
# bookkeeping. The checks below that compare a statistic with a threshold or recompute one (z, each
# p-value from its statistic, the verdicts, |acf| > band, the root moduli, the cancelling rule, the
# information criteria from llf) are Python's alone, by ADR-0001: the export and --check run them, so
# a file that fails them is never written.

MODEL_IDS = ("aic", "bic", "course")
PRIMARY = "aic"  # the owner's default (LEARNING_LOG): the AIC choice is the primary model
SERIAL_VERDICTS = ("found", "not_found", "not_tested")
NORMALITY_VERDICTS = ("rejected", "not_rejected")
ARCH_VERDICTS = ("found", "not_found")
_FIT_FLAGS = ("enforce_stationarity", "enforce_invertibility", "concentrate_scale")
_INFERENCE = ("std_err", "z", "p_value", "ci_low", "ci_high")
_REL = 1e-9  # relative tolerance for a value Python recomputes from other exported doubles
# The largest orders a fit file may state, checked before anything is built from them (the grid's
# p and q stop at 5 and pmdarima's at 5; d is 0, 1 or 2): a stated order of 1e8 must give one short
# problem, not a list of 1e8 parameter names. The burn-in is d for these models, so at most MAX_D.
MAX_PQ = 10
MAX_D = 2
MAX_FIT_PARAMS = 2 * MAX_PQ + 2  # p + q coefficients, a trend term and sigma2: the most a bounded order has
# The refit's log-likelihood tolerance and the cancelling distance (fitting.LLF_TOLERANCE and
# fitting.CANCEL_DISTANCE). Pinned here, not read from the file being checked, as NESTING_TOLERANCE
# is: a file that states another value is refused, so it cannot loosen its own checks.
LLF_TOLERANCE = 1e-6
CANCEL_DISTANCE = 0.1
# The residual tests' settings (diagnostics.ALPHA, LJUNG_BOX_LAGS, ARCH_LM_LAGS, NLAGS, and the ddof the
# exporter gives het_arch). Pinned the same way: the lags decide which rows exist, hence the verdicts, so
# a file that stated others (a Ljung-Box at lag 5 alone) could change a verdict and still be consistent
# with itself. tests/test_diagnostics.py asserts these equal diagnostics.py's.
ALPHA = 0.05
LJUNG_BOX_LAGS = (5, 10, 20)
ARCH_LM_LAGS = (5, 10)
ARCH_LM_DDOF = 0
NLAGS = 50
# A p-value Python recomputes from its statistic must agree to P_REL relative, or within P_FLOOR
# when both are that small (a p-value below about 1e-308 underflows to 0.0, or loses digits).
P_REL = 1e-9
P_FLOOR = 1e-300


def _close(a: float, b: float, rel: float = _REL) -> bool:
    """Equal to `rel` relative, with an absolute floor of `rel`. Never true when either is not finite:
    a recomputed value that overflowed to inf would otherwise match any number (inf <= rel * inf)."""
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= rel * max(1.0, abs(a), abs(b))


def _p_close(p: float, want: float) -> bool:
    return abs(p - want) <= P_REL * max(p, want) + P_FLOOR


def _chi2_sf(x: float, k: int) -> float:
    """P(a chi-squared on k degrees of freedom exceeds x), k an integer >= 1: the closed forms
    e^-h (1 + h + ... + h^(m-1) / (m-1)!) for k = 2m, and erfc(sqrt h) plus e^-h times the sum of
    h^(j + 1/2) / Gamma(j + 3/2) over j < m for k = 2m + 1, with h = x / 2 (scipy's chi2.sf to about
    1e-14 relative; no scipy in the readers). Each term is computed in logs, so none overflows. The loop
    runs k / 2 times, so a caller passes only a df the pinned settings can give (a Ljung-Box lag at one
    of LJUNG_BOX_LAGS minus p + q, or one of ARCH_LM_LAGS: at most 20), never a number read from a file."""
    h = x / 2.0
    if h <= 0.0:  # x is 0, or the smallest subnormal, whose half rounds to 0.0 (and has no logarithm): the tail is 1
        return 1.0
    if k % 2 == 0:
        total = sum(math.exp(-h + j * math.log(h) - math.lgamma(j + 1)) for j in range(k // 2))
    else:
        total = math.erfc(math.sqrt(h)) + sum(math.exp(-h + (j + 0.5) * math.log(h) - math.lgamma(j + 1.5)) for j in range(k // 2))
    return min(1.0, total)


def expected_param_names(p: int, q: int, trend: str) -> list[str]:
    """Our parameter names in statsmodels' order: the trend term, the AR lags, the MA lags, sigma2."""
    lead = {"n": [], "c": ["const"], "t": ["drift"]}[trend]
    return [*lead, *(f"ar.L{i}" for i in range(1, p + 1)), *(f"ma.L{i}" for i in range(1, q + 1)), "sigma2"]


LIBRARY_NAMES = {"drift": "x1"}  # statsmodels 0.15.0 labels ARIMA's drift as an exogenous "x1"


def _int_list(c: _Checker, value: object, path: str) -> list[int] | None:
    items = _list(c, value, path, MAX_NAMES, "lags")
    if items is None:
        return None
    out = [c.integer(v, f"{path}[{i}]", minimum=1) for i, v in enumerate(items)]
    if None in out:
        return None
    if not out or any(b <= a for a, b in zip(out, out[1:])):  # type: ignore[operator]
        c.add(path, f"must be a non-empty, strictly ascending list, got {_show(out)}")
        return None
    return out  # type: ignore[return-value]


# The most warnings one fit may list (fit.models[].warnings, course_track's, each forecast refit's),
# checked before the list is walked: a file with millions of warnings gets one short problem (both readers).
MAX_WARNINGS = 100


def _warnings(c: _Checker, value: object, path: str) -> None:
    items = _list(c, value, path, MAX_WARNINGS, "warnings")
    for i, item in enumerate(items or []):
        w = c.obj(item, f"{path}[{i}]")
        if w is not None:
            for name in ("category", "message"):
                c.string(c.key(w, name, f"{path}[{i}]"), f"{path}[{i}].{name}")


def _p_value(c: _Checker, value: object, path: str, *, nullable: bool = False) -> float | None:
    v = c.number(value, path, nullable=nullable)
    if v is not None and not 0 <= v <= 1:
        c.add(path, f"must be between 0 and 1, got {v}")
        return None
    return v


def _bounded(c: _Checker, value: object, path: str, most: int) -> int | None:
    """An integer from 0 to `most`, or one short problem (both readers)."""
    v = c.integer(value, path)
    if v is not None and v > most:
        c.add(path, f"expected an integer from 0 to {most}, got {v}")
        return None
    return v


def _pinned(c: _Checker, stated: object, path: str, pin: object, rule: str) -> None:
    """A setting this reader holds itself, never takes from the file: one problem when the file states another value."""
    if stated is not None and stated != pin:
        c.add(path, f"is {_show(stated)}, but this reader {rule} {_show(pin)}")


def _check_order(c: _Checker, value: object, path: str) -> list[int] | None:
    """[p, d, q] with p and q at most MAX_PQ and d at most MAX_D, checked before anything is built from it."""
    triple = c.array(value, path)
    if triple is None:
        return None
    if len(triple) != 3:
        c.add(path, f"expected [p, d, q], got {_show(triple)}")
        return None
    out = [_bounded(c, v, f"{path}[{i}]", most) for i, (v, most) in enumerate(zip(triple, (MAX_PQ, MAX_D, MAX_PQ), strict=True))]
    return None if None in out else out  # type: ignore[return-value]


def _burn(c: _Checker, value: object, path: str) -> int | None:
    return _bounded(c, value, path, MAX_D)


def _statistic(c: _Checker, value: object, path: str) -> float | None:
    """A test statistic: a chi-squared value, so >= 0 (Python only)."""
    v = c.number(value, path)
    if v is not None and v < 0:
        c.add(path, f"must be >= 0, got {v}")
        return None
    return v


def _check_chi2_p(c: _Checker, p: float | None, statistic: float | None, df: int | None, path: str, test: str) -> None:
    """Python only: the exported p-value is the chi-squared tail of the exported statistic.

    A p of exactly 0.0 is what scipy writes for a tail too small for a double, so it is taken only
    where the tail at that statistic and df is below P_FLOOR (1e-300): Jarque-Bera on 2 df past a
    statistic of about 1382, say. Beside a moderate statistic a 0 is refused, whatever the floor."""
    if p is None or statistic is None or df is None:
        return
    want = _chi2_sf(statistic, df)
    if p == 0.0:
        if want > P_FLOOR:
            c.add(path, f"is 0, but the {test} statistic {statistic} on {df} df gives p = {want}, above the underflow floor {P_FLOOR}: only a smaller tail may be written as 0")
    elif not _p_close(p, want):
        c.add(path, f"is {p}, but the {test} statistic {statistic} on {df} df gives p = {want}")


_NO_TEST = ("z", "p_value")  # sigma2's: null always, a boundary null (contract.md 3.7)


def _check_params(c: _Checker, value: object, at: str, names: list[str] | None) -> None:
    rows = _list(c, value, at, MAX_FIT_PARAMS, "rows")
    if rows is None:
        return
    if names is not None and len(rows) != len(names):
        c.add(at, f"has {len(rows)} rows, but the order and trend have {len(names)} parameters: {', '.join(names)}")
    for i, item in enumerate(rows):
        rat = f"{at}[{i}]"
        row = c.obj(item, rat)
        if row is None:
            continue
        name = c.string(c.key(row, "name", rat), f"{rat}.name")
        if name is not None and names is not None and i < len(names) and name != names[i]:
            c.add(f"{rat}.name", f"is {_show(name)}, expected {names[i]!r}")
        library = c.string(c.key(row, "library_name", rat), f"{rat}.library_name")
        if name is not None and library is not None and library != LIBRARY_NAMES.get(name, name):
            c.add(f"{rat}.library_name", f"is {_show(library)}; statsmodels labels {_show(name)} as {_show(LIBRARY_NAMES.get(name, name))}")
        val = c.number(c.key(row, "value", rat), f"{rat}.value")
        if name == "sigma2" and val is not None and val <= 0:  # Python only
            c.add(f"{rat}.value", f"must be positive, got {val}: sigma2 is a variance")
        raw = {k: c.key(row, k, rat) for k in _INFERENCE}
        nulls = [k for k in _INFERENCE if raw[k] is None]
        if len(nulls) == len(_INFERENCE):
            continue  # a singular covariance
        if name == "sigma2":
            if tuple(nulls) != _NO_TEST:
                c.add(rat, f"sigma2 has std_err and its interval, and z and p_value null (its null value 0 is on the boundary, where the z-test does not apply); got {', '.join(nulls) or 'no'} null")
                continue
        elif nulls:
            c.add(rat, f"{', '.join(nulls)} null but not all of {', '.join(_INFERENCE)}; they are null together")
            continue
        se = c.number(raw["std_err"], f"{rat}.std_err")
        lo, hi = c.number(raw["ci_low"], f"{rat}.ci_low"), c.number(raw["ci_high"], f"{rat}.ci_high")
        z = p = None
        if name != "sigma2":
            z = c.number(raw["z"], f"{rat}.z")
            p = _p_value(c, raw["p_value"], f"{rat}.p_value")
        if se is not None and se <= 0:
            c.add(f"{rat}.std_err", f"must be positive, got {se}")
        elif None not in (val, se, lo, hi):
            if name != "sigma2" and z is not None and p is not None:
                if z != val / se:  # type: ignore[operator]
                    c.add(f"{rat}.z", f"is {z}, but value / std_err is {val / se}")  # type: ignore[operator]
                elif not _close(p, 2.0 * _normal_sf(abs(z))):
                    c.add(f"{rat}.p_value", f"is {p}, but 2 * (1 - Phi(|z|)) is {2.0 * _normal_sf(abs(z))}")
            if not (lo <= val <= hi) or not _close(hi - val, Z_FOR_ALPHA[0.05] * se) or not _close(val - lo, Z_FOR_ALPHA[0.05] * se):  # type: ignore[operator]
                c.add(rat, f"ci_low {lo} and ci_high {hi} are not value +- z * std_err")


def _normal_sf(x: float) -> float:
    """1 - Phi(x) for the standard normal, by math.erfc (no scipy in the readers)."""
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def _check_roots(c: _Checker, value: object, at: str, count: int | None) -> list[complex] | None:
    """The roots, or None when they cannot be used: a list of another length than the order says is
    one problem and nothing else, and no matching is run on it (`_best_matching` is exponential in
    the number of MA roots, so it must only ever see a count the bounded order allows)."""
    rows = c.array(value, at)
    if rows is None:
        return None
    if count is not None and len(rows) != count:
        c.add(at, f"has {len(rows)} roots, expected {count}")
        return None
    if len(rows) > MAX_PQ:  # no count (the order was refused): the list is bounded all the same
        c.add(at, f"has {len(rows)} roots, more than the {MAX_PQ} a reader takes")
        return None
    out: list[complex] = []
    for i, item in enumerate(rows):
        rat = f"{at}[{i}]"
        row = c.obj(item, rat)
        if row is None:
            return None
        re_, im, mod = (c.number(c.key(row, k, rat), f"{rat}.{k}") for k in ("re", "im", "modulus"))
        if None in (re_, im, mod):
            return None
        if not _close(mod, math.hypot(re_, im), 1e-12):  # type: ignore[arg-type]
            c.add(f"{rat}.modulus", f"is {mod}, but |re + i im| is {math.hypot(re_, im)}")  # type: ignore[arg-type]
        if out and mod > abs(out[-1]) + 1e-12:  # type: ignore[operator]
            c.add(f"{rat}.modulus", "roots are sorted by modulus, largest first")
        out.append(complex(re_, im))  # type: ignore[arg-type]
    return out


def _best_matching(ar: list[complex], ma: list[complex], distance: float) -> tuple[int, float]:
    """fitting.cancelling_pairs's rule, restated by another method: the number of pairs and the total
    distance of a one-to-one matching of the AR-MA pairs within `distance` that has the most pairs,
    then the least total. Dynamic programming over the subsets of MA roots already used: 2^len(ma)
    of them, so the caller runs it only on lists of at most MAX_PQ roots (`_check_pairs`), which
    `_check_roots` returns only when their count is the bounded order's."""
    best: dict[int, tuple[int, float]] = {0: (0, 0.0)}  # used MA roots (a bit mask) -> (pairs, total)
    for a in ar:
        step = dict(best)
        for mask, (count, total) in best.items():
            for j, m in enumerate(ma):
                gap = abs(a - m)
                if mask >> j & 1 or gap > distance:
                    continue
                key, cand = mask | 1 << j, (count + 1, total + gap)
                old = step.get(key)
                if old is None or (cand[0], -cand[1]) > (old[0], -old[1]):
                    step[key] = cand
        best = step
    return max(best.values(), key=lambda v: (v[0], -v[1]))


def _check_pairs(c: _Checker, value: object, at: str, ar: list[complex] | None, ma: list[complex] | None, distance: float | None) -> None:
    rows = _list(c, value, at, MAX_PQ, "pairs")  # one root of each kind per pair at most
    if rows is None:
        return
    got: list[tuple[int, int]] = []
    gaps: list[float] = []
    for k, item in enumerate(rows):
        rat = f"{at}[{k}]"
        row = c.obj(item, rat)
        if row is None:
            return
        i, j = c.integer(c.key(row, "ar", rat), f"{rat}.ar"), c.integer(c.key(row, "ma", rat), f"{rat}.ma")
        gap = c.number(c.key(row, "distance", rat), f"{rat}.distance")
        if i is None or j is None or gap is None:
            return
        if ar is not None and ma is not None:
            if i >= len(ar) or j >= len(ma):
                c.add(rat, f"indices ({i}, {j}) are out of range for {len(ar)} AR and {len(ma)} MA roots")
                return
            if not _close(gap, abs(ar[i] - ma[j]), 1e-12):
                c.add(f"{rat}.distance", f"is {gap}, but the roots are {abs(ar[i] - ma[j])} apart")
            elif distance is not None and gap > distance:
                c.add(f"{rat}.distance", f"{gap} is above cancel_distance {distance}: the stated rule does not pair these roots")
        got.append((i, j))
        gaps.append(gap)
    if len({i for i, _ in got}) != len(got) or len({j for _, j in got}) != len(got):
        c.add(at, "a root appears in more than one pair")
    elif got != sorted(got):
        c.add(at, f"pairs are listed by AR index, got {got}")
    elif ar is not None and ma is not None and distance is not None and max(len(ar), len(ma)) <= MAX_PQ:
        # Never past MAX_PQ roots a side: the matching doubles its work with each MA root.
        count, total = _best_matching(ar, ma, distance)
        if len(got) != count or not _close(sum(gaps), total, 1e-12):
            c.add(at, f"is {got} (total distance {sum(gaps)}), but the stated rule (as many pairs within {distance} as possible, one to one, then the least total distance) gives {count} pairs with total distance {total}")


def _check_diagnostics(c: _Checker, value: object, at: str, model: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
    dg = c.obj(value, at) if value is not _MISSING else None
    if dg is None:
        return None
    alpha = settings.get("alpha")
    n = c.integer(c.key(dg, "n", at), f"{at}.n", minimum=2)
    burn = _burn(c, c.key(dg, "burn_excluded", at), f"{at}.burn_excluded")
    if burn is not None and model.get("burn") is not None and burn != model["burn"]:
        c.add(f"{at}.burn_excluded", f"is {burn}, but the fit's loglikelihood_burn is {model['burn']}")
    if n is not None and burn is not None and model.get("nobs") is not None and n != model["nobs"] - burn:
        c.add(f"{at}.n", f"is {n}, but nobs - burn_excluded is {model['nobs'] - burn}")
    burned = _list(c, c.key(dg, "burned", at), f"{at}.burned", MAX_D, "rows")  # burn_excluded is at most MAX_D
    if burned is not None:
        if burn is not None and len(burned) != burn:
            c.add(f"{at}.burned", f"has {len(burned)} rows, but burn_excluded is {burn}")
        for i, item in enumerate(burned):
            row = c.obj(item, f"{at}.burned[{i}]")
            if row is not None:
                c.date(c.key(row, "date", f"{at}.burned[{i}]"), f"{at}.burned[{i}].date")
                for k in ("resid", "resid_std"):
                    c.number(c.key(row, k, f"{at}.burned[{i}]"), f"{at}.burned[{i}].{k}")
    m = c.number(c.key(dg, "max_abs_resid_after_burn", at), f"{at}.max_abs_resid_after_burn")
    if m is not None and m < 0:
        c.add(f"{at}.max_abs_resid_after_burn", f"must be >= 0, got {m}")
    lb = _list(c, c.key(dg, "ljung_box", at), f"{at}.ljung_box", len(LJUNG_BOX_LAGS), "rows")
    lb_rows: list[tuple[bool, float | None]] = []
    previous: tuple[int, float] | None = None  # the last row's lag and Q
    if lb is not None:
        lags = settings.get("ljung_box_lags")
        if lags is not None and len(lb) != len(lags):
            c.add(f"{at}.ljung_box", f"has {len(lb)} rows, but ljung_box_lags has {len(lags)}")
        for i, item in enumerate(lb):
            rat = f"{at}.ljung_box[{i}]"
            row = c.obj(item, rat)
            if row is None:
                continue
            lag = c.integer(c.key(row, "lag", rat), f"{rat}.lag", minimum=1)
            if lag is not None and lags is not None and i < len(lags) and lag != lags[i]:
                c.add(f"{rat}.lag", f"is {lag}, expected {lags[i]}")
            pinned_lag = lag is not None and i < len(LJUNG_BOX_LAGS) and lag == LJUNG_BOX_LAGS[i]
            mdf = c.integer(c.key(row, "model_df", rat), f"{rat}.model_df")
            if mdf is not None and model.get("pq") is not None and mdf != model["pq"]:
                c.add(f"{rat}.model_df", f"is {mdf}, but p + q is {model['pq']}")
            applied = _boolean(c, c.key(row, "applied", rat), f"{rat}.applied")
            stat = _statistic(c, c.key(row, "statistic", rat), f"{rat}.statistic")
            # Q(h) = n (n + 2) sum_{k <= h} r_k^2 / (n - k) is a running sum of terms >= 0, so it
            # cannot fall from one lag to a later one (each row's Q, applied or not).
            if lag is not None and stat is not None:
                if previous is not None and lag > previous[0] and stat < previous[1]:
                    c.add(f"{rat}.statistic", f"is {stat}, below {previous[1]} at lag {previous[0]}: Ljung-Box Q is a running sum of non-negative terms, so it cannot fall as the lag grows")
                previous = (lag, stat)
            df_raw, p_raw = c.key(row, "df", rat), c.key(row, "p_value", rat)
            if applied is None or lag is None or mdf is None:
                continue
            if applied != (lag > mdf):
                c.add(f"{rat}.applied", f"is {applied}, but the test applies exactly when lag {lag} > model_df {mdf}")
            elif applied:
                df = c.integer(df_raw, f"{rat}.df", minimum=1)
                if df is not None and df != lag - mdf:
                    c.add(f"{rat}.df", f"is {df}, but lag - model_df is {lag - mdf}")
                    df = None
                p = _p_value(c, p_raw, f"{rat}.p_value")
                # The chi-squared runs only on a df the pinned lags give: lag - p - q at a pinned lag.
                # A row off the pins is already a problem (lag, model_df or df above), and the tail
                # of a lag of 1e9 is never computed.
                if pinned_lag and mdf == model.get("pq"):
                    _check_chi2_p(c, p, stat, df, f"{rat}.p_value", "Ljung-Box")
                lb_rows.append((True, p))
            elif df_raw is not None or p_raw is not None:
                c.add(rat, "df and p_value must be null where the test is not applied")
    jb = c.key(dg, "jarque_bera", at)
    jb_p = None
    if jb is not _MISSING and (j := c.obj(jb, f"{at}.jarque_bera")) is not None:
        jat = f"{at}.jarque_bera"
        stat = _statistic(c, c.key(j, "statistic", jat), f"{jat}.statistic")
        jb_p = _p_value(c, c.key(j, "p_value", jat), f"{jat}.p_value")
        _check_chi2_p(c, jb_p, stat, 2, f"{jat}.p_value", "Jarque-Bera")
        skew = c.number(c.key(j, "skew", jat), f"{jat}.skew")
        kurtosis = c.number(c.key(j, "kurtosis", jat), f"{jat}.kurtosis")
        # Pearson's kurtosis is at least 1 + skew^2 for any sample (the equality is a two-point
        # sample); to _REL relative. Products, not powers: a huge skew gives inf, not OverflowError.
        least = 1.0 if skew is None else 1.0 + skew * skew
        if kurtosis is not None and kurtosis < least * (1.0 - _REL):
            c.add(f"{jat}.kurtosis", f"is {kurtosis}, but Pearson's kurtosis is at least 1 + skew^2 = {least}")
        elif None not in (stat, skew, kurtosis, n):
            # statsmodels' jarque_bera: JB = n / 6 (S^2 + (K - 3)^2 / 4) from the same skew, kurtosis
            # and n, so the exported statistic must be that to _REL relative (floor _REL). The p-value
            # tie above cannot see a wrong statistic past about 1382, where every tail is below P_FLOOR.
            want = n / 6.0 * (skew * skew + 0.25 * (kurtosis - 3.0) * (kurtosis - 3.0))  # type: ignore[operator]
            if not (math.isfinite(want) and _close(stat, want)):  # type: ignore[arg-type]
                c.add(f"{jat}.statistic", f"is {stat}, but n / 6 (skew^2 + (kurtosis - 3)^2 / 4) with n {n}, skew {skew} and kurtosis {kurtosis} is {want}")
    arch = _list(c, c.key(dg, "arch_lm", at), f"{at}.arch_lm", len(ARCH_LM_LAGS), "rows")
    arch_p: list[float | None] = []
    if arch is not None:
        lags = settings.get("arch_lm_lags")
        if lags is not None and len(arch) != len(lags):
            c.add(f"{at}.arch_lm", f"has {len(arch)} rows, but arch_lm_lags has {len(lags)}")
        for i, item in enumerate(arch):
            rat = f"{at}.arch_lm[{i}]"
            row = c.obj(item, rat)
            if row is None:
                continue
            nl = c.integer(c.key(row, "lags", rat), f"{rat}.lags", minimum=1)
            if nl is not None and lags is not None and i < len(lags) and nl != lags[i]:
                c.add(f"{rat}.lags", f"is {nl}, expected {lags[i]}")
            pinned_lags = nl is not None and i < len(ARCH_LM_LAGS) and nl == ARCH_LM_LAGS[i]
            stat = _statistic(c, c.key(row, "statistic", rat), f"{rat}.statistic")
            p = _p_value(c, c.key(row, "p_value", rat), f"{rat}.p_value")
            # het_arch (acorr_lm): the LM statistic is (n - m - ddof) R^2, with n - m the rows left
            # once m lags are taken, so at most n - m - ddof as R^2 <= 1; its p-value is chi-squared
            # on the m lags.
            if None not in (stat, nl, n):
                most = n - nl - ARCH_LM_DDOF  # type: ignore[operator]
                if stat > most:  # type: ignore[operator]
                    c.add(f"{rat}.statistic", f"is {stat}, but (n - lags - ddof) R^2 is at most n - lags - ddof = {most} (n {n}, lags {nl}, ddof {ARCH_LM_DDOF}), as R^2 <= 1")
            if pinned_lags:  # the chi-squared runs on one of the pinned lags only
                _check_chi2_p(c, p, stat, nl, f"{rat}.p_value", "ARCH-LM")
            arch_p.append(p)
    v = c.key(dg, "verdicts", at)
    verdict: dict[str, str | None] = {}
    if v is not _MISSING and (vd := c.obj(v, f"{at}.verdicts")) is not None:
        for name, options in (("serial_correlation", SERIAL_VERDICTS), ("normality", NORMALITY_VERDICTS), ("arch", ARCH_VERDICTS)):
            verdict[name] = _choice(c, c.key(vd, name, f"{at}.verdicts"), options, f"{at}.verdicts.{name}")
    counts = {k: c.integer(c.key(dg, k, at), f"{at}.{k}") for k in ("acf_outside_count", "acf_squared_outside_count")}
    # Python only: each verdict follows from its p-values and alpha (diagnostics.verdicts).
    if isinstance(alpha, float) and verdict:
        ps = [p for _, p in lb_rows]
        if lb is not None and None not in ps and verdict.get("serial_correlation") is not None:
            want = "found" if any(p < alpha for p in ps) else ("not_found" if ps else "not_tested")  # type: ignore[operator]
            if verdict["serial_correlation"] != want:
                c.add(f"{at}.verdicts.serial_correlation", f"is {verdict['serial_correlation']!r}, but the Ljung-Box p-values give {want!r}")
        if jb_p is not None and verdict.get("normality") is not None and verdict["normality"] != ("rejected" if jb_p < alpha else "not_rejected"):
            c.add(f"{at}.verdicts.normality", f"is {verdict['normality']!r}, but Jarque-Bera's p-value is {jb_p}")
        if arch is not None and arch_p and None not in arch_p and verdict.get("arch") is not None:
            want = "found" if any(p < alpha for p in arch_p) else "not_found"  # type: ignore[operator]
            if verdict["arch"] != want:
                c.add(f"{at}.verdicts.arch", f"is {verdict['arch']!r}, but the ARCH-LM p-values give {want!r}")
    return {"verdicts": verdict, "arch_p": arch_p, "counts": counts}


def _default_trend(d: int) -> str:
    """statsmodels' ARIMA default trend: 'c' without differencing, 'n' with it (arima/model.py:156-160).
    The course refits with that default, so its model's trend is this (both readers)."""
    return "c" if d == 0 else "n"


def _check_information(c: _Checker, vals: dict[str, float | None], llf: float, k: int, n: int | None, at: str) -> None:
    """Python only: statsmodels' criteria from llf, k parameters and n = nobs_effective
    (statsmodels/tools/eval_measures.py, called by mlemodel.py with nobs_effective)."""
    want: dict[str, float | None] = {"aic": -2 * llf + 2 * k}
    if n is not None:
        want["bic"] = -2 * llf + math.log(n) * k
        # statsmodels returns +inf when n - k - 1 <= 0, which no JSON file can hold.
        want["aicc"] = -2 * llf + 2 * k * n / (n - k - 1) if n - k - 1 > 0 else None
    labels = {"aic": "-2 llf + 2 k", "bic": "-2 llf + ln(n) k", "aicc": "-2 llf + 2 k n / (n - k - 1)"}
    for name, expected in want.items():
        got = vals.get(name)
        if got is None:
            continue
        if expected is None:
            c.add(f"{at}.{name}", f"is {got}, but n - k - 1 = {n} - {k} - 1 <= 0, where AICc is undefined (statsmodels gives inf)")
        elif not _close(got, expected):
            c.add(f"{at}.{name}", f"is {got}, but {labels[name]} is {expected}{'' if name == 'aic' else ' (n = nobs_effective)'}")


@_capped
def validate_fit(data: object) -> list[str]:
    """Every problem in a `fit` payload (contract.md section 3.7)."""
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    c.equals(c.key(root, "sample", "data"), "train", "data.sample")
    n_train = c.integer(c.key(root, "n_train", "data"), "data.n_train", minimum=2)
    primary_raw = c.key(root, "primary", "data")
    c.equals(primary_raw, PRIMARY, "data.primary")  # a one-value enum: the AIC choice
    primary = PRIMARY if primary_raw == PRIMARY else None
    fs = c.key(root, "fit_settings", "data")
    if fs is not _MISSING and (f := c.obj(fs, "data.fit_settings")) is not None:
        for name in ("library", "version", "optimizer"):
            c.string(c.key(f, name, "data.fit_settings"), f"data.fit_settings.{name}")
        c.equals(c.key(f, "model", "data.fit_settings"), "ARIMA", "data.fit_settings.model")
        c.equals(c.key(f, "method", "data.fit_settings"), "statespace", "data.fit_settings.method")
        c.equals(c.key(f, "cov_type", "data.fit_settings"), "opg", "data.fit_settings.cov_type")
        c.integer(c.key(f, "maxiter", "data.fit_settings"), "data.fit_settings.maxiter", minimum=1)
        for name in _FIT_FLAGS:
            _boolean(c, c.key(f, name, "data.fit_settings"), f"data.fit_settings.{name}")
    z95 = c.number(c.key(root, "z95", "data"), "data.z95")
    if z95 is not None and z95 != Z_FOR_ALPHA[0.05]:
        c.add("data.z95", f"is {z95}, expected {Z_FOR_ALPHA[0.05]}")
    distance = c.number(c.key(root, "cancel_distance", "data"), "data.cancel_distance")
    if distance is not None and distance != CANCEL_DISTANCE:
        c.add("data.cancel_distance", f"is {distance}, but this reader pairs roots within {CANCEL_DISTANCE}")
    distance = CANCEL_DISTANCE  # the reader's own rule, whatever the file says
    tolerance = c.number(c.key(root, "llf_tolerance", "data"), "data.llf_tolerance")
    if tolerance is not None and tolerance != LLF_TOLERANCE:
        c.add("data.llf_tolerance", f"is {tolerance}, but this reader checks the refit's llf at {LLF_TOLERANCE}")
    tolerance = LLF_TOLERANCE  # the reader's own bound, whatever the file says
    # The reader's own settings, whatever the file says: a stated value other than the pin is refused below.
    settings: dict[str, Any] = {"alpha": ALPHA, "ljung_box_lags": list(LJUNG_BOX_LAGS), "arch_lm_lags": list(ARCH_LM_LAGS), "arch_lm_ddof": ARCH_LM_DDOF, "nlags": NLAGS}
    ds = c.key(root, "diagnostic_settings", "data")
    if ds is not _MISSING and (s := c.obj(ds, "data.diagnostic_settings")) is not None:
        sat = "data.diagnostic_settings"
        _pinned(c, c.number(c.key(s, "alpha", sat), f"{sat}.alpha"), f"{sat}.alpha", ALPHA, "tests at alpha")
        for name in ("series", "ljung_box_model_df"):
            c.string(c.key(s, name, sat), f"{sat}.{name}")
        _pinned(c, _int_list(c, c.key(s, "ljung_box_lags", sat), f"{sat}.ljung_box_lags"), f"{sat}.ljung_box_lags", list(LJUNG_BOX_LAGS), "checks Ljung-Box at lags")
        _pinned(c, _int_list(c, c.key(s, "arch_lm_lags", sat), f"{sat}.arch_lm_lags"), f"{sat}.arch_lm_lags", list(ARCH_LM_LAGS), "checks ARCH-LM at lags")
        _pinned(c, c.integer(c.key(s, "arch_lm_ddof", sat), f"{sat}.arch_lm_ddof"), f"{sat}.arch_lm_ddof", ARCH_LM_DDOF, "checks ARCH-LM with ddof")
        _pinned(c, c.integer(c.key(s, "nlags", sat), f"{sat}.nlags", minimum=1), f"{sat}.nlags", NLAGS, "checks the correlograms at nlags")
    models = _list(c, c.key(root, "models", "data"), "data.models", len(MODEL_IDS), "models")
    parsed: dict[str, dict[str, Any]] = {}
    if models is not None:
        ids = [m.get("id") if isinstance(m, dict) else None for m in models]
        if ids != list(MODEL_IDS):
            c.add("data.models", f"ids are {_show(ids)}, expected {list(MODEL_IDS)} in that order")
        for index, item in enumerate(models):
            at = f"data.models[{index}]"
            m = c.obj(item, at)
            if m is None:
                continue
            ident = _choice(c, c.key(m, "id", at), MODEL_IDS, f"{at}.id")
            c.string(c.key(m, "label", at), f"{at}.label")
            c.string(c.key(m, "source", at), f"{at}.source")
            order = _check_order(c, c.key(m, "order", at), f"{at}.order")
            trend = _choice(c, c.key(m, "trend", at), TREND_CODES, f"{at}.trend")
            if ident == "course" and order is not None and trend is not None and trend != _default_trend(order[1]):
                c.add(f"{at}.trend", f"is {trend!r}, but ARIMA(train, order).fit() at d = {order[1]} has statsmodels' default trend {_default_trend(order[1])!r}")
            nobs = c.integer(c.key(m, "nobs", at), f"{at}.nobs", minimum=2)
            eff = c.integer(c.key(m, "nobs_effective", at), f"{at}.nobs_effective", minimum=1)
            burn = _burn(c, c.key(m, "loglikelihood_burn", at), f"{at}.loglikelihood_burn")
            if nobs is not None and n_train is not None and nobs != n_train:
                c.add(f"{at}.nobs", f"is {nobs}, but n_train is {n_train}")
            if None not in (nobs, eff, burn) and eff != nobs - burn:  # type: ignore[operator]
                c.add(f"{at}.nobs_effective", f"is {eff}, but nobs - loglikelihood_burn is {nobs - burn}")  # type: ignore[operator]
            # Only from a bounded order: p and q of 1e8 must not build 1e8 names.
            names = expected_param_names(order[0], order[2], trend) if order is not None and trend is not None else None
            _check_params(c, c.key(m, "params", at), f"{at}.params", names)
            info = c.key(m, "information", at)
            llf = None
            if info is not _MISSING and (inf := c.obj(info, f"{at}.information")) is not None:
                vals = {k: c.number(c.key(inf, k, f"{at}.information"), f"{at}.information.{k}") for k in ("llf", "aic", "aicc", "bic", "hqic")}
                llf = vals["llf"]
                if names is not None and llf is not None:
                    _check_information(c, vals, llf, len(names), eff, f"{at}.information")
            grid_raw, gap_raw = c.key(m, "grid_llf", at), c.key(m, "llf_gap", at)
            grid = c.number(grid_raw, f"{at}.grid_llf", nullable=True)
            gap = c.number(gap_raw, f"{at}.llf_gap", nullable=True)
            if ident is not None and grid_raw is not _MISSING and gap_raw is not _MISSING:
                if (grid_raw is None) != (ident == "course") or (gap_raw is None) != (ident == "course"):
                    c.add(at, "grid_llf and llf_gap are null exactly for the course model, which is not a grid cell")
                elif grid is not None and gap is not None and llf is not None:
                    if gap != llf - grid:
                        c.add(f"{at}.llf_gap", f"is {gap}, but llf - grid_llf is {llf - grid}")
                    elif tolerance is not None and abs(gap) > tolerance:
                        c.add(f"{at}.llf_gap", f"{gap} is outside llf_tolerance {tolerance}: the refit does not reproduce the grid's point")
            _boolean(c, c.key(m, "converged", at), f"{at}.converged")
            c.integer(c.key(m, "iterations", at), f"{at}.iterations")
            c.integer(c.key(m, "warnflag", at), f"{at}.warnflag")
            _warnings(c, c.key(m, "warnings", at), f"{at}.warnings")
            ar = _check_roots(c, c.key(m, "inv_roots_ar", at), f"{at}.inv_roots_ar", None if order is None else order[0])
            ma = _check_roots(c, c.key(m, "inv_roots_ma", at), f"{at}.inv_roots_ma", None if order is None else order[2])
            _check_pairs(c, c.key(m, "cancelling_pairs", at), f"{at}.cancelling_pairs", ar, ma, distance)
            facts = {"burn": burn, "nobs": nobs, "pq": None if order is None else order[0] + order[2]}
            diag = _check_diagnostics(c, c.key(m, "diagnostics", at), f"{at}.diagnostics", facts, settings)
            if ident is not None:
                parsed[ident] = {"order": order, "trend": trend, "diag": diag}
    _check_course_track(c, c.key(root, "course_track", "data"), n_train, parsed.get("course"))
    cp = c.key(root, "clustering_prediction", "data")
    if cp is not _MISSING and (p := c.obj(cp, "data.clustering_prediction")) is not None:
        at = "data.clustering_prediction"
        mid = _choice(c, c.key(p, "model_id", at), MODEL_IDS, f"{at}.model_id")
        if mid is not None and primary is not None and mid != primary:
            c.add(f"{at}.model_id", f"is {mid!r}, but the primary model is {primary!r}")
        confirmed = _boolean(c, c.key(p, "confirmed", at), f"{at}.confirmed")
        rejections = c.integer(c.key(p, "arch_lm_rejections", at), f"{at}.arch_lm_rejections")
        outside = c.integer(c.key(p, "acf_squared_outside_count", at), f"{at}.acf_squared_outside_count")
        expected = c.number(c.key(p, "acf_squared_expected_by_chance", at), f"{at}.acf_squared_expected_by_chance")
        diag = (parsed.get(mid) or {}).get("diag") if mid is not None else None
        if diag is not None:
            if confirmed is not None and diag["verdicts"].get("arch") is not None and confirmed != (diag["verdicts"]["arch"] == "found"):
                c.add(f"{at}.confirmed", f"is {confirmed}, but the model's ARCH verdict is {diag['verdicts']['arch']!r}")
            if outside is not None and diag["counts"].get("acf_squared_outside_count") is not None and outside != diag["counts"]["acf_squared_outside_count"]:
                c.add(f"{at}.acf_squared_outside_count", f"is {outside}, but the model's diagnostics say {diag['counts']['acf_squared_outside_count']}")
            alpha = settings.get("alpha")
            if rejections is not None and isinstance(alpha, float) and diag["arch_p"] and None not in diag["arch_p"] and rejections != sum(q < alpha for q in diag["arch_p"]):
                c.add(f"{at}.arch_lm_rejections", f"is {rejections}, but {sum(q < alpha for q in diag['arch_p'])} ARCH-LM p-values are below {alpha}")
        if expected is not None and isinstance(settings.get("alpha"), float) and settings.get("nlags") is not None and expected != settings["alpha"] * settings["nlags"]:
            c.add(f"{at}.acf_squared_expected_by_chance", f"is {expected}, but alpha * nlags is {settings['alpha'] * settings['nlags']}")
    return c.problems


def _check_course_track(c: _Checker, value: object, n_train: int | None, course: dict[str, Any] | None) -> None:
    at = "data.course_track"
    if value is _MISSING:
        return
    t = c.obj(value, at)
    if t is None:
        return
    c.obj(c.key(t, "settings", at), f"{at}.settings")
    c.string(c.key(t, "pmdarima_version", at), f"{at}.pmdarima_version")
    n_course = c.integer(c.key(t, "n_course", at), f"{at}.n_course", minimum=2)
    nt = c.integer(c.key(t, "n_train", at), f"{at}.n_train", minimum=2)
    seen = c.integer(c.key(t, "test_rows_seen", at), f"{at}.test_rows_seen")
    if nt is not None and n_train is not None and nt != n_train:
        c.add(f"{at}.n_train", f"is {nt}, but data.n_train is {n_train}")
    if None not in (n_course, nt, seen) and seen != n_course - nt:  # type: ignore[operator]
        c.add(f"{at}.test_rows_seen", f"is {seen}, but n_course - n_train is {n_course - nt}")  # type: ignore[operator]
    full_order = None
    full_trend: object = _MISSING
    fs = c.key(t, "full_series", at)
    if fs is not _MISSING and (f := c.obj(fs, f"{at}.full_series")) is not None:
        fat = f"{at}.full_series"
        full_order = _check_order(c, c.key(f, "order", fat), f"{fat}.order")
        _boolean(c, c.key(f, "with_intercept", fat), f"{fat}.with_intercept")
        trend_raw = c.key(f, "trend", fat)
        if trend_raw is None or _choice(c, trend_raw, TREND_CODES, f"{fat}.trend", nullable=True) is not None:
            full_trend = trend_raw
        c.number(c.key(f, "aic", fat), f"{fat}.aic")
        nobs = c.integer(c.key(f, "nobs", fat), f"{fat}.nobs", minimum=2)
        if nobs is not None and n_course is not None and nobs != n_course:
            c.add(f"{fat}.nobs", f"is {nobs}, but n_course is {n_course}")
        for i, item in enumerate(_list(c, c.key(f, "params", fat), f"{fat}.params", MAX_FIT_PARAMS, "rows") or []):
            row = c.obj(item, f"{fat}.params[{i}]")
            if row is not None:
                c.string(c.key(row, "name", f"{fat}.params[{i}]"), f"{fat}.params[{i}].name")
                c.number(c.key(row, "value", f"{fat}.params[{i}]"), f"{fat}.params[{i}].value")
        _warnings(c, c.key(f, "warnings", fat), f"{fat}.warnings")
    if course is not None and full_order is not None and course["order"] is not None and course["order"] != full_order:
        c.add(f"{at}.full_series.order", f"is {full_order}, but the course model's order is {course['order']}")
    tr_raw = c.key(t, "train_only", at)
    train_only = None
    if tr_raw is not None and tr_raw is not _MISSING and (tr := c.obj(tr_raw, f"{at}.train_only")) is not None:
        train_only = (_check_order(c, c.key(tr, "order", f"{at}.train_only"), f"{at}.train_only.order"), _boolean(c, c.key(tr, "with_intercept", f"{at}.train_only"), f"{at}.train_only.with_intercept"))
        _choice(c, c.key(tr, "trend", f"{at}.train_only"), TREND_CODES, f"{at}.train_only.trend", nullable=True)
    same_raw = c.key(t, "same_order", at)
    if same_raw is not _MISSING:
        if (same_raw is None) != (tr_raw is None):
            c.add(f"{at}.same_order", "is null exactly when train_only is null")
        elif same_raw is not None:
            same = _boolean(c, same_raw, f"{at}.same_order")
            wi = fs.get("with_intercept") if isinstance(fs, dict) else None
            if same is not None and train_only is not None and None not in train_only and full_order is not None and isinstance(wi, bool) and same != (train_only[0] == full_order and train_only[1] == wi):
                c.add(f"{at}.same_order", f"is {same}, but the two searches chose {train_only} and {(full_order, wi)}")
    refit = _choice(c, c.key(t, "refit_trend", at), TREND_CODES, f"{at}.refit_trend")
    if refit is not None and course is not None and course["trend"] is not None and refit != course["trend"]:
        c.add(f"{at}.refit_trend", f"is {refit!r}, but the course model's trend is {course['trend']!r}")
    dd = c.key(t, "drift_dropped", at)
    if dd is not _MISSING and (d := c.obj(dd, f"{at}.drift_dropped")) is not None:
        dat = f"{at}.drift_dropped"
        selected_raw = c.key(d, "selected_trend", dat)
        selected_ok = selected_raw is None or _choice(c, selected_raw, TREND_CODES, f"{dat}.selected_trend", nullable=True) is not None
        if selected_ok and full_trend is not _MISSING and selected_raw is not _MISSING and selected_raw != full_trend:
            c.add(f"{dat}.selected_trend", f"is {_show(selected_raw)}, but full_series.trend, the trend the search selected, is {_show(full_trend)}")
        r2 = _choice(c, c.key(d, "refit_trend", dat), TREND_CODES, f"{dat}.refit_trend")
        if r2 is not None and refit is not None and r2 != refit:
            c.add(f"{dat}.refit_trend", f"is {r2!r}, but refit_trend is {refit!r}")
        without = c.number(c.key(d, "aic_without_drift", dat), f"{dat}.aic_without_drift")
        with_ = c.number(c.key(d, "aic_with_drift", dat), f"{dat}.aic_with_drift")
        gap = c.number(c.key(d, "aic_gap", dat), f"{dat}.aic_gap")
        if None not in (without, with_, gap) and gap != without - with_:  # type: ignore[operator]
            c.add(f"{dat}.aic_gap", f"is {gap}, but aic_without_drift - aic_with_drift is {without - with_}")  # type: ignore[operator]
        drift = c.number(c.key(d, "drift", dat), f"{dat}.drift")
        se_raw, p_raw = c.key(d, "drift_std_err", dat), c.key(d, "drift_p_value", dat)
        se = c.number(se_raw, f"{dat}.drift_std_err", nullable=True)
        p = _p_value(c, p_raw, f"{dat}.drift_p_value", nullable=True)
        if se_raw is not _MISSING and p_raw is not _MISSING and (se_raw is None) != (p_raw is None):
            c.add(dat, "drift_std_err and drift_p_value are null together (a singular covariance)")
        elif se is not None and se <= 0:
            c.add(f"{dat}.drift_std_err", f"must be positive, got {se}")
        elif drift is not None and se is not None and p is not None and not _p_close(p, 2.0 * _normal_sf(abs(drift / se))):  # Python only
            c.add(f"{dat}.drift_p_value", f"is {p}, but 2 * (1 - Phi(|drift / drift_std_err|)) is {2.0 * _normal_sf(abs(drift / se))}")


def _check_correlogram(c: _Checker, value: object, at: str, nlags: int | None, n: int | None, z: float | None) -> int | None:
    if value is _MISSING:
        return None
    g = c.obj(value, at)
    if g is None:
        return None
    band = c.number(c.key(g, "band", at), f"{at}.band")
    if band is not None and band <= 0:
        c.add(f"{at}.band", f"must be positive, got {band}")
        band = None
    elif band is not None and n is not None and z is not None and band != z / math.sqrt(n):
        c.add(f"{at}.band", f"is {band}, but z / sqrt(n) is {z / math.sqrt(n)}")
    count = c.integer(c.key(g, "outside_count", at), f"{at}.outside_count")
    rows = _list(c, c.key(g, "rows", at), f"{at}.rows", MAX_LIST, "rows")
    if rows is None:
        return count
    if nlags is not None and len(rows) != nlags:
        c.add(f"{at}.rows", f"has {len(rows)} rows, but lags 1 to {nlags} make {nlags}")
    flags: list[bool | None] = []
    for k, item in enumerate(rows, start=1):
        rat = f"{at}.rows[{k - 1}]"
        row = c.obj(item, rat)
        if row is None:
            flags.append(None)
            continue
        lag = c.integer(c.key(row, "lag", rat), f"{rat}.lag", minimum=1)
        if lag is not None and lag != k:
            c.add(f"{rat}.lag", f"is {lag}, expected {k}")
        v = c.number(c.key(row, "acf", rat), f"{rat}.acf")
        if v is not None and not -1 <= v <= 1:
            c.add(f"{rat}.acf", f"must be between -1 and 1, got {v}")
            v = None
        flag = _boolean(c, c.key(row, "outside", rat), f"{rat}.outside")
        flags.append(flag)
        if flag is not None and v is not None and band is not None and flag != (abs(v) > band):  # Python only
            c.add(f"{rat}.outside", f"is {flag}, but |acf| {abs(v)} {'>' if abs(v) > band else '<='} band {band}")
    if count is not None and None not in flags and count != sum(flags):  # type: ignore[arg-type]
        c.add(f"{at}.outside_count", f"is {count}, but {sum(flags)} rows are flagged")  # type: ignore[arg-type]
    return count


@_capped
def validate_residuals(data: object, model_id: str) -> list[str]:
    """Every problem in a `residuals_<model_id>` payload (contract.md section 3.8)."""
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    c.equals(c.key(root, "sample", "data"), "train", "data.sample")
    c.equals(c.key(root, "model_id", "data"), model_id, "data.model_id")
    n = c.integer(c.key(root, "n", "data"), "data.n", minimum=2)
    _burn(c, c.key(root, "burn_excluded", "data"), "data.burn_excluded")  # n and nobs: the cross-file check below
    z = c.number(c.key(root, "z", "data"), "data.z")
    if z is not None and z != Z_FOR_ALPHA[0.05]:
        c.add("data.z", f"is {z}, expected {Z_FOR_ALPHA[0.05]}")
        z = None
    nlags = c.integer(c.key(root, "nlags", "data"), "data.nlags", minimum=1)
    rows = _list(c, c.key(root, "rows", "data"), "data.rows", MAX_LIST, "rows")
    if rows is not None:
        if n is not None and len(rows) != n:
            c.add("data.rows", f"has {len(rows)} rows, but n is {n}")
        dates: list[str | None] = []
        for i, item in enumerate(rows):
            row = c.obj(item, f"data.rows[{i}]")
            if row is None:
                dates.append(None)
                continue
            dates.append(c.date(c.key(row, "date", f"data.rows[{i}]"), f"data.rows[{i}].date"))
            c.number(c.key(row, "resid_std", f"data.rows[{i}]"), f"data.rows[{i}].resid_std")
        _check_ascending(c, dates, "data.rows")
    for name in ("acf", "acf_squared"):
        _check_correlogram(c, c.key(root, name, "data"), f"data.{name}", nlags, n, z)
    qq = _list(c, c.key(root, "qq", "data"), "data.qq", MAX_LIST, "points")
    if qq is not None:
        if n is not None and len(qq) != n:
            c.add("data.qq", f"has {len(qq)} points, but n is {n}")
        last: dict[str, float] = {}
        for i, item in enumerate(qq):
            at = f"data.qq[{i}]"
            pt = c.obj(item, at)
            if pt is None:
                continue
            for k in ("theoretical", "t_theoretical", "sample"):
                v = c.number(c.key(pt, k, at), f"{at}.{k}")
                if v is not None:
                    if k in last and v < last[k]:
                        c.add(f"{at}.{k}", f"{v} is below the previous point's {last[k]}; points are sorted")
                    last[k] = v
    tf = c.key(root, "t_fit", "data")
    if tf is not _MISSING and (t := c.obj(tf, "data.t_fit")) is not None:
        for k in ("df", "loc", "scale"):
            v = c.number(c.key(t, k, "data.t_fit"), f"data.t_fit.{k}")
            if v is not None and k != "loc" and v <= 0:
                c.add(f"data.t_fit.{k}", f"must be positive, got {v}")
    return c.problems


def validate_fit_residuals(fit: object, residuals: dict[str, object]) -> list[str]:
    """Problems between `fit` and the `residuals_<id>` payloads (each already valid on its own): each
    model's file must exist and hold that model's id, `n` and `burn_excluded` (so n + burn = nobs),
    the fit's `nlags`, and its two outside counts. The export tool runs this on the files on disk
    after a write, `--only` included, so a fit.json rebuilt alone after a code change cannot sit
    beside residual files from the old code. Like the other validators it never raises."""
    problems: list[str] = []
    data = fit if isinstance(fit, dict) else {}
    models = data.get("models") if isinstance(data.get("models"), list) else []
    settings = data.get("diagnostic_settings") if isinstance(data.get("diagnostic_settings"), dict) else {}
    for model in models:
        # A model whose id is not one of MODEL_IDS is validate_fit's problem; it names no file here.
        if not isinstance(model, dict) or not isinstance(model.get("diagnostics"), dict) or model.get("id") not in MODEL_IDS:
            continue
        name, dg = f"residuals_{model['id']}", model["diagnostics"]
        series = residuals.get(name)
        if not isinstance(series, dict):
            problems.append(f"{name}: missing, but fit has model {model.get('id')!r}")
            continue
        acf, acf_sq = series.get("acf"), series.get("acf_squared")
        checks = [
            ("model_id", series.get("model_id"), model.get("id")),
            ("n", series.get("n"), dg.get("n")),
            ("burn_excluded", series.get("burn_excluded"), dg.get("burn_excluded")),
            ("nlags", series.get("nlags"), settings.get("nlags")),
            ("acf.outside_count", acf.get("outside_count") if isinstance(acf, dict) else None, dg.get("acf_outside_count")),
            ("acf_squared.outside_count", acf_sq.get("outside_count") if isinstance(acf_sq, dict) else None, dg.get("acf_squared_outside_count")),
        ]
        for field, got, want in checks:
            if got != want:
                problems.append(f"{name}: {field} is {_show(got)}, but fit.json says {_show(want)}")
    extra = sorted(set(residuals) - {f"residuals_{m['id']}" for m in models if isinstance(m, dict) and m.get("id") in MODEL_IDS})
    problems += [f"{name}: fit.json has no model {name.removeprefix('residuals_')!r}" for name in extra]
    return problems


# --- milestone 4: forecast_<model>_<method> and evaluation (contract.md 3.9 and 3.10) -----------------
# The app's parsers (contract.forecast.ts) check the same shapes, enums, nulls, bounds, pins and integer
# and date bookkeeping. The checks below that recompute a number from others or compare one with alpha
# (every dollar value from mean_log and sd_log, the t quantiles, each ratio, each DM statistic and
# p-value, Kupiec's LR and its p-value, every verdict) are Python's alone, by ADR-0001.

FORECAST_METHODS = ("static", "walk_forward", "refit")
FORECAST_KINDS = {"static": "multi_step", "walk_forward": "one_step", "refit": "one_step"}
KIND_IDS = ("multi_step", "one_step")
PARAMETER_SOURCES = ("train", "expanding_refit")
# The forecast files, one per (model, method), in the export's order (forecasting.FORECASTS; a test ties them).
FORECASTS = (("aic", "static"), ("aic", "walk_forward"), ("aic", "refit"), ("bic", "static"), ("bic", "walk_forward"), ("course", "static"), ("course", "walk_forward"))
WINDOW_IDS = ("test", "oos")
# Pinned, never read from the file, compared exactly (forecasting.LEVELS, NORMAL_Z, REFIT_EVERY;
# evaluation.ALPHA and the DM settings). tests/test_forecasting.py and tests/test_evaluation.py tie them
# to the producer's constants.
LEVELS = (0.8, 0.95)
NORMAL_Z = (1.2815515655446004, 1.959963984540054)
REFIT_EVERY = 21
HEADLINE_USD = "median"
# The Method picker's text, pinned per method id (evaluation.METHOD_LABELS; a test ties them): free
# text read from the file could say "refit every 5 days" beside a refit every 21.
METHOD_LABELS = {"static": "Static multi-step (the course's)", "walk_forward": "Walk-forward one-step", "refit": "Walk-forward one-step, refit every 21 days"}
# The Model picker's text, pinned per model id as the method labels are (fitting.LABELS; a test ties them):
# free text read from the file could swap two models' names.
MODEL_LABELS = {"aic": "AIC choice (ADR-0002)", "bic": "BIC choice", "course": "Course refit"}
DM_SETTINGS: dict[str, Any] = {"horizon": 1, "errors": "log", "losses": ["squared", "absolute"], "correction": "harvey_leybourne_newbold", "alternative": "two_sided", "baseline": "random_walk", "same_tolerance": 1e-9}
DM_LOSSES = ("squared", "absolute")
DM_VERDICTS = ("beats_rw", "no_difference", "worse_than_rw", "same_as_rw")
DISTRIBUTIONS = ("normal", "t")
COVERAGE_VERDICTS = ("too_narrow", "consistent", "too_wide", "not_tested")
# Rows per window: bounded before any row is read (both readers).
MAX_ROWS = 10_000
# From this t_df on, Python checks a t quantile against the Cornish-Fisher expansion in 1 / df
# (Abramowitz and Stegun 26.7.5, four terms: within 4.5e-16 relative of scipy's t.ppf from df 1e3 up,
# measured), not by evaluating the t's CDF, whose continued fraction needs about sqrt(df) terms. A
# near-normal residual series gives such a df: scipy's t.fit on a simulated Gaussian walk returned
# more than 1e6. The fits on AAPL give 3.2 to 3.4.
T_ASYMPTOTIC_DF = 1e4
T_CDF_TOLERANCE = 1e-10  # |F(t_quantile) - (1 + level) / 2| allowed (Python only)
T_QUANTILE_REL = 1e-12  # |t_quantile / expansion - 1| allowed past T_ASYMPTOTIC_DF (Python only)
ROW_NUMBERS = ("actual_log", "actual_usd", "mean_log", "sd_log", "median_usd", "mean_usd", "lower_80_usd", "upper_80_usd", "lower_95_usd", "upper_95_usd", "t_lower_80_usd", "t_upper_80_usd", "t_lower_95_usd", "t_upper_95_usd")
# Each dollar bound: (field, which multiplier list, its index, the sign of the multiplier).
_BOUNDS = (
    ("lower_80_usd", "normal_z", 0, -1.0),
    ("upper_80_usd", "normal_z", 0, 1.0),
    ("lower_95_usd", "normal_z", 1, -1.0),
    ("upper_95_usd", "normal_z", 1, 1.0),
    ("t_lower_80_usd", "t_multiplier", 0, -1.0),
    ("t_upper_80_usd", "t_multiplier", 0, 1.0),
    ("t_lower_95_usd", "t_multiplier", 1, -1.0),
    ("t_upper_95_usd", "t_multiplier", 1, 1.0),
)
_MULTIPLIER = {"normal": "normal_z", "t": "t_multiplier"}
MAX_ITERATIONS = 10_000


def _near(a: float, b: float, rel: float = _REL) -> bool:
    """Equal to `rel` relative, with no absolute floor: for small quantities (log errors, a mean loss
    differential of 1e-6) where _close's floor of 1 would accept almost anything. Never true when either
    is not finite."""
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= rel * max(abs(a), abs(b))


def _exp(x: float) -> float:
    """math.exp that gives inf instead of raising past about 709.78."""
    try:
        return math.exp(x)
    except OverflowError:
        return math.inf


def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function (modified Lentz), at most MAX_ITERATIONS
    terms; nan if it has not converged by then."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) >= tiny else tiny)
    h = d
    for m in range(1, MAX_ITERATIONS + 1):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) >= tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) >= tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) <= 1e-16:
            return h
    return math.nan


def _lgamma_ratio(a: float, b: float) -> float:
    """ln Gamma(a + b) - ln Gamma(a) for a, b > 0. For a >= 50 by Stirling's series, (a - 1/2) ln(1 +
    b / a) + b ln(a + b) - b + S(a + b) - S(a) with S(z) = 1 / (12 z) - 1 / (360 z^3) + 1 / (1260 z^5) -
    1 / (1680 z^7): the plain difference of two lgamma values near a ln a loses their digits (7e-10
    at a = 1e6, which would move a t tail by as much). Below 50 the plain difference is exact enough."""
    if a < 50.0:
        return math.lgamma(a + b) - math.lgamma(a)

    def stirling(z: float) -> float:
        z2 = z * z
        return 1.0 / (12.0 * z) - 1.0 / (360.0 * z * z2) + 1.0 / (1260.0 * z * z2 * z2) - 1.0 / (1680.0 * z * z2 * z2 * z2)

    return (a - 0.5) * math.log1p(b / a) + b * math.log(a + b) - b + stirling(a + b) - stirling(a)


def _betainc(a: float, b: float, x: float, y: float) -> float:
    """The regularised incomplete beta function I_x(a, b) for a, b > 0, with y = 1 - x passed in so a
    caller can compute it without cancellation. Accurate to relative precision on the side where it
    is small (Numerical Recipes, 6.4: the fraction converges fast for x < (a + 1) / (a + b + 2), and
    I_x(a, b) = 1 - I_y(b, a) on the other side)."""
    if not (a > 0.0 and b > 0.0 and math.isfinite(a) and math.isfinite(b)):
        return math.nan  # a df of 0, or one whose half underflows to 0, has no distribution
    if x <= 0.0:
        return 0.0
    if y <= 0.0:
        return 1.0
    log_front = a * math.log(x) + b * math.log(y) + _lgamma_ratio(a, b) - math.lgamma(b)
    if x < (a + 1.0) / (a + b + 2.0):
        return _exp(log_front) * _betacf(a, b, x) / a
    return 1.0 - _exp(log_front) * _betacf(b, a, y) / b


def _t_sf(x: float, df: float) -> float:
    """P(T > x) for a Student T on df > 0 degrees of freedom: I_z(df / 2, 1 / 2) / 2 with z = df / (df
    + x^2) for x >= 0, and 1 minus that for x < 0 (no scipy in the readers). 0, a subnormal and a huge
    x are handled: x^2 underflows to 0 (the tail is 1/2) or overflows to inf (the tail is 0)."""
    if math.isnan(x):
        return math.nan
    s = abs(x) * abs(x)
    if s == 0.0:
        tail = 0.5
    elif math.isinf(s):
        tail = 0.0
    else:
        tail = 0.5 * _betainc(df / 2.0, 0.5, df / (df + s), s / (df + s))
    return tail if x >= 0 else 1.0 - tail


def _check_t_p(c: _Checker, p: float | None, statistic: float | None, df: int | None, path: str) -> None:
    """Python only: a two-sided p-value is 2 P(T > |statistic|) on df, to P_REL, or within P_FLOOR;
    a 0 only where that tail is below P_FLOOR (as _check_chi2_p)."""
    if p is None or statistic is None or df is None or df < 1:
        return
    if df > MAX_ROWS - 1:
        # A DM row's df is its window's n - 1 (both checked against the windows), and no window has
        # more than MAX_ROWS rows; so a larger df comes only from a file whose windows are already
        # refused, and the p-value is left unchecked there. _t_sf is never called on it: within 1.4e-12
        # relative of scipy up to df 1e4, it is off by 1.2e-9 at 1e7 (past P_REL) and by a factor of 3
        # at 2^53 (measured at x = 1/8 to 59/8).
        return
    want = min(1.0, 2.0 * _t_sf(abs(statistic), df))
    if math.isnan(want):
        c.add(path, f"the t tail at {statistic} on {df} df could not be evaluated")
    elif p == 0.0:
        if want > P_FLOOR:
            c.add(path, f"is 0, but 2 P(T > |{statistic}|) on {df} df is {want}, above the underflow floor {P_FLOOR}: only a smaller tail may be written as 0")
    elif not _p_close(p, want):
        c.add(path, f"is {p}, but 2 P(T > |statistic_hln|) with statistic_hln {statistic} on {df} df is {want}")


def _t_quantile_expansion(z: float, df: float) -> float:
    """The Student-t quantile on df degrees of freedom at the probability whose normal quantile is z,
    by the Cornish-Fisher expansion (Abramowitz and Stegun 26.7.5) to 1 / df^4. Products, not powers:
    a huge df gives z, not an OverflowError."""
    z2 = z * z
    g1 = (z2 + 1.0) * z / 4.0
    g2 = ((5.0 * z2 + 16.0) * z2 + 3.0) * z / 96.0
    g3 = (((3.0 * z2 + 19.0) * z2 + 17.0) * z2 - 15.0) * z / 384.0
    g4 = ((((79.0 * z2 + 776.0) * z2 + 1482.0) * z2 - 1920.0) * z2 - 945.0) * z / 92160.0
    u = 1.0 / df
    return z + u * (g1 + u * (g2 + u * (g3 + u * g4)))


def kupiec_lr(n: int, inside: int, level: float) -> float:
    """Kupiec's unconditional-coverage LR statistic for `inside` of `n` days inside an interval of
    nominal `level` (0 log 0 = 0), as evaluation.kupiec computes it; clamped at 0."""
    rate = inside / n

    def term(count: int, prob: float) -> float:
        return 0.0 if count == 0 else count * math.log(prob)

    lr = -2.0 * (term(inside, level) + term(n - inside, 1.0 - level) - term(inside, rate) - term(n - inside, 1.0 - rate))
    return lr if lr > 0.0 else 0.0


def _row_count(c: _Checker, value: object, path: str, least: int = 1) -> int | None:
    """A window's n: an integer from `least` to MAX_ROWS (both readers), checked before any row is read."""
    v = c.integer(value, path, minimum=0)
    if v is not None and not least <= v <= MAX_ROWS:
        c.add(path, f"expected an integer from {least} to {MAX_ROWS}, got {v}")
        return None
    return v


def _pin_list(c: _Checker, value: object, path: str, pin: tuple[float, ...] | list[Any], rule: str) -> None:
    """A list that must equal this reader's pin exactly: same length, same values, same types (1 and
    1.0 are the same JSON number, so an int equal to a float pin passes, as in JavaScript)."""
    items = c.array(value, path)
    if items is None:
        return
    same = len(items) == len(pin) and all(not isinstance(a, bool) and type(a) in (int, float, str) and a == b and (isinstance(a, str) == isinstance(b, str)) for a, b in zip(items, pin))
    if not same:
        c.add(path, f"is {_show(items)}, but this reader {rule} {_show(list(pin))}")


def _pin_number(c: _Checker, value: object, path: str, pin: float, rule: str, *, integer: bool = False) -> None:
    v = c.integer(value, path, minimum=1) if integer else c.number(value, path)
    if v is not None and v != pin:
        c.add(path, f"is {v}, but this reader {rule} {pin}")


def _above(c: _Checker, value: object, path: str, floor: float, why: str) -> float | None:
    v = c.number(value, path)
    if v is not None and not v > floor:
        c.add(path, f"must be above {floor} ({why}), got {v}")
        return None
    return v


def _numbers(c: _Checker, value: object, path: str, keys: tuple[str, ...]) -> dict[str, float] | None:
    if value is _MISSING:
        return None
    o = c.obj(value, path)
    if o is None:
        return None
    out = {k: c.number(c.key(o, k, path), f"{path}.{k}") for k in keys}
    return None if None in out.values() else out  # type: ignore[return-value]


def _check_forecast_rows(c: _Checker, rows: list[Any], at: str, z: tuple[float, ...], k: list[float] | None, multi_step: bool) -> list[dict[str, Any]] | None:
    """The rows of one window; returns them when every row is complete. Python only: the dollar values
    from mean_log and sd_log, actual_usd from actual_log, and a static path's sd_log never falling."""
    out: list[dict[str, Any]] = []
    complete = True
    previous_date: str | None = None
    previous_sd: float | None = None
    for i, item in enumerate(rows):
        rat = f"{at}[{i}]"
        row = c.obj(item, rat)
        if row is None:
            complete = False
            continue
        day = c.date(c.key(row, "date", rat), f"{rat}.date")
        if day is not None:
            if previous_date is not None and day <= previous_date:
                c.add(f"{rat}.date", f"{day} does not come after {previous_date}")
            previous_date = day
        values = {name: c.number(c.key(row, name, rat), f"{rat}.{name}") for name in ROW_NUMBERS}
        sd = values["sd_log"]
        if sd is not None and not sd > 0:
            c.add(f"{rat}.sd_log", f"must be above 0 (a forecast with no spread), got {sd}")
            sd = None
        if day is None or None in values.values() or sd is None:
            complete = False
            previous_sd = None
            continue
        mu = values["mean_log"]
        # Python only: every dollar value from the two doubles it is made of.
        wants = {"actual_usd": _exp(values["actual_log"]), "median_usd": _exp(mu), "mean_usd": _exp(mu + sd * sd / 2.0)}
        for field, key, index, sign in _BOUNDS:
            multipliers = z if key == "normal_z" else k
            if multipliers is not None:
                wants[field] = _exp(mu + sign * multipliers[index] * sd)
        formulas = {"actual_usd": "exp(actual_log)", "median_usd": "exp(mean_log)", "mean_usd": "exp(mean_log + sd_log^2 / 2)"}
        for field, want in wants.items():
            if not _close(values[field], want):
                formula = formulas.get(field) or f"exp(mean_log {'-' if field.startswith(('lower', 't_lower')) else '+'} m sd_log) with this file's multiplier"
                c.add(f"{rat}.{field}", f"is {values[field]}, but {formula} is {want}")
        if multi_step and previous_sd is not None and sd < previous_sd * (1.0 - _REL):
            c.add(f"{rat}.sd_log", f"is {sd}, below the step before's {previous_sd}: an h-step forecast variance is a running sum of non-negative terms, so it cannot fall as h grows")
        previous_sd = sd
        out.append({"date": day, **values})
    return out if complete else None


def _check_forecast_window(c: _Checker, item: object, at: str, expected: str, z: tuple[float, ...], k: list[float] | None, multi_step: bool) -> dict[str, Any]:
    w = c.obj(item, at)
    if w is None:
        return {}
    ident = _choice(c, c.key(w, "id", at), WINDOW_IDS, f"{at}.id")
    if ident is not None and ident != expected:
        c.add(f"{at}.id", f"is {ident!r}, expected {expected!r} (the windows are 'test' then 'oos')")
    first = c.date(c.key(w, "start", at), f"{at}.start")
    last = c.date(c.key(w, "end", at), f"{at}.end")
    n = _row_count(c, c.key(w, "n", at), f"{at}.n")
    origin_raw = c.key(w, "origin", at)
    origin = None
    if origin_raw is not _MISSING and (o := c.obj(origin_raw, f"{at}.origin")) is not None:
        oat = f"{at}.origin"
        day = c.date(c.key(o, "date", oat), f"{oat}.date")
        if day is not None and first is not None and not day < first:
            c.add(f"{oat}.date", f"is {day}, but the origin is the last day before the window, which starts {first}")
        log_close = c.number(c.key(o, "log_close", oat), f"{oat}.log_close")
        close = c.number(c.key(o, "close_usd", oat), f"{oat}.close_usd")
        if log_close is not None and close is not None and not _close(close, _exp(log_close)):  # Python only
            c.add(f"{oat}.close_usd", f"is {close}, but exp(log_close) is {_exp(log_close)}")
        if None not in (day, log_close, close):
            origin = {"date": day, "log_close": log_close, "close_usd": close}
    rows_raw = c.key(w, "rows", at)
    rows = None
    dates = None
    # The bound first: no row is read when n is out of bounds, and no list longer than MAX_ROWS is walked.
    if n is not None and rows_raw is not _MISSING:
        listed = c.array(rows_raw, f"{at}.rows")
        if listed is not None and len(listed) != n:
            c.add(f"{at}.rows", f"has {len(listed)} rows, but n is {n}")
        if listed is not None and len(listed) <= MAX_ROWS:
            rows = _check_forecast_rows(c, listed, f"{at}.rows", z, k, multi_step)
            if rows:
                if first is not None and rows[0]["date"] != first:
                    c.add(f"{at}.rows[0].date", f"is {rows[0]['date']}, but the window starts {first}")
                if last is not None and rows[-1]["date"] != last:
                    c.add(f"{at}.rows[{len(rows) - 1}].date", f"is {rows[-1]['date']}, but the window ends {last}")
            if rows is not None and len(rows) == n:
                dates = [r["date"] for r in rows]
    return {"id": ident, "start": first, "end": last, "n": n, "origin": origin, "rows": rows, "dates": dates}


def _check_intervals(c: _Checker, value: object, t_df: float | None) -> list[float] | None:
    """The interval block; returns the t multipliers when they are two numbers (Python ties them to
    t_df, so a wrong multiplier is one problem here and the rows are checked against the file's own)."""
    iat = "data.intervals"
    if value is _MISSING:
        return None
    iv = c.obj(value, iat)
    if iv is None:
        return None
    _pin_list(c, c.key(iv, "levels", iat), f"{iat}.levels", LEVELS, "draws the intervals at levels")
    _pin_list(c, c.key(iv, "normal_z", iat), f"{iat}.normal_z", NORMAL_Z, "uses the normal quantiles")
    pair = {}
    for name in ("t_quantile", "t_multiplier"):
        items = c.array(c.key(iv, name, iat), f"{iat}.{name}")
        if items is None:
            continue
        if len(items) != len(LEVELS):
            c.add(f"{iat}.{name}", f"expected {len(LEVELS)} numbers, got {_show(items)}")
            continue
        got = [c.number(v, f"{iat}.{name}[{i}]") for i, v in enumerate(items)]
        if None not in got:
            pair[name] = got
    scale = c.number(c.key(iv, "t_scale", iat), f"{iat}.t_scale")
    # Python only: the scale from t_df, each multiplier = quantile x scale, each quantile by the t's CDF
    # (or, from T_ASYMPTOTIC_DF on, by the Cornish-Fisher expansion).
    if t_df is not None:
        want = math.sqrt((t_df - 2.0) / t_df)
        if scale is not None and not _near(scale, want):
            c.add(f"{iat}.t_scale", f"is {scale}, but sqrt((t_df - 2) / t_df) is {want}")
        for i, (q, level) in enumerate(zip(pair.get("t_quantile", []), LEVELS)):
            target = 0.5 + level / 2.0
            if t_df >= T_ASYMPTOTIC_DF:
                expansion = _t_quantile_expansion(NORMAL_Z[i], t_df)
                if not _near(q, expansion, T_QUANTILE_REL):
                    c.add(f"{iat}.t_quantile[{i}]", f"is {q}, but the t quantile at {target} on {t_df} df is {expansion} (Cornish-Fisher)")
                continue
            cdf = 1.0 - _t_sf(q, t_df)
            if not q > 0 or not abs(cdf - target) <= T_CDF_TOLERANCE:
                c.add(f"{iat}.t_quantile[{i}]", f"is {q}, but the t on {t_df} df puts {cdf} below it, not {target}")
    if scale is not None and "t_quantile" in pair and "t_multiplier" in pair:
        for i, (q, m) in enumerate(zip(pair["t_quantile"], pair["t_multiplier"])):
            if not _near(m, q * scale):
                c.add(f"{iat}.t_multiplier[{i}]", f"is {m}, but t_quantile x t_scale is {q * scale}")
    return pair.get("t_multiplier")


def expected_refits(n_test: int, n_oos: int) -> int:
    """ceil((n_test + n_oos) / REFIT_EVERY) - 1: the first REFIT_EVERY rows keep the training estimates."""
    return -(-(n_test + n_oos) // REFIT_EVERY) - 1


def _check_refits(c: _Checker, value: object, method: str | None, names: list[str] | None, dates: list[str] | None, expected: int | None) -> list[dict[str, Any]] | None:
    at = "data.refits"
    if value is _MISSING or method is None:
        return None
    if method != "refit":
        if value is not None:
            c.add(at, f"must be null for method {method!r}, which keeps the training parameters")
        return None
    if value is None:
        c.add(at, "is null, but the refit method lists every re-estimation")
        return None
    items = c.array(value, at)
    if items is None or expected is None:
        return None
    if len(items) != expected:  # one short problem, however long the list: never a loop over it
        c.add(at, f"has {len(items)} entries, but the test and oos rows take {expected} (one per {REFIT_EVERY} rows after the first {REFIT_EVERY})")
        return None
    out = []
    previous: int | None = None
    for k, item in enumerate(items):
        eat = f"{at}[{k}]"
        e = c.obj(item, eat)
        if e is None:
            previous = None
            continue
        day = c.date(c.key(e, "start_date", eat), f"{eat}.start_date")
        row = REFIT_EVERY * (k + 1)
        if day is not None and dates is not None and day != dates[row]:
            c.add(f"{eat}.start_date", f"is {day}, but row {row} (from 0) of the test and oos rows is {dates[row]}")
        n_obs = c.integer(c.key(e, "n_obs", eat), f"{eat}.n_obs", minimum=1)
        if n_obs is not None and previous is not None and n_obs != previous + REFIT_EVERY:
            c.add(f"{eat}.n_obs", f"is {n_obs}, but the entry before was fitted on {previous} observations and each refit adds {REFIT_EVERY}")
        previous = n_obs
        params = c.array(c.key(e, "params", eat), f"{eat}.params")
        if params is not None and names is not None:
            if len(params) != len(names):
                c.add(f"{eat}.params", f"has {len(params)} parameters, but the order and trend have {len(names)}: {', '.join(names)}")
            else:
                for i, p_item in enumerate(params):
                    pat = f"{eat}.params[{i}]"
                    p = c.obj(p_item, pat)
                    if p is None:
                        continue
                    name = c.string(c.key(p, "name", pat), f"{pat}.name")
                    if name is not None and name != names[i]:
                        c.add(f"{pat}.name", f"is {_show(name)}, expected {names[i]!r}")
                    v = c.number(c.key(p, "value", pat), f"{pat}.value")
                    if name == "sigma2" and v is not None and not v > 0:  # Python only
                        c.add(f"{pat}.value", f"must be positive, got {v}: sigma2 is a variance")
        c.number(c.key(e, "llf", eat), f"{eat}.llf")
        _boolean(c, c.key(e, "converged", eat), f"{eat}.converged")
        c.integer(c.key(e, "iterations", eat), f"{eat}.iterations")
        _warnings(c, c.key(e, "warnings", eat), f"{eat}.warnings")
        out.append({"n_obs": n_obs, "start_date": day})
    return out


@_capped
def validate_forecast(data: object, model_id: str, method: str) -> list[str]:
    """Every problem in a `forecast_<model_id>_<method>` payload (contract.md section 3.9). The caller
    passes the model and method the file name gives."""
    if (model_id, method) not in FORECASTS:
        return [f"no forecast file is made for model {model_id!r} and method {method!r}"]
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    ident = _choice(c, c.key(root, "model_id", "data"), MODEL_IDS, "data.model_id")
    if ident is not None and ident != model_id:
        c.add("data.model_id", f"is {ident!r}, but this is the file of model {model_id!r}")
    label = c.string(c.key(root, "label", "data"), "data.label")
    if label is not None and label != MODEL_LABELS[model_id]:
        c.add("data.label", f"is {_show(label)}, but this reader labels model {model_id!r} {MODEL_LABELS[model_id]!r}")
    stated = _choice(c, c.key(root, "method", "data"), FORECAST_METHODS, "data.method")
    if stated is not None and stated != method:
        c.add("data.method", f"is {stated!r}, but this is the file of method {method!r}")
    kind = _choice(c, c.key(root, "kind", "data"), KIND_IDS, "data.kind")
    if kind is not None and stated is not None and kind != FORECAST_KINDS[stated]:
        c.add("data.kind", f"is {kind!r}, but method {stated!r} makes {FORECAST_KINDS[stated]!r} forecasts")
    order = _check_order(c, c.key(root, "order", "data"), "data.order")
    trend = _choice(c, c.key(root, "trend", "data"), TREND_CODES, "data.trend")
    parameters = _choice(c, c.key(root, "parameters", "data"), PARAMETER_SOURCES, "data.parameters")
    if parameters is not None and stated is not None:
        source = "expanding_refit" if stated == "refit" else "train"
        if parameters != source:
            c.add("data.parameters", f"is {parameters!r}, but method {stated!r} takes its parameters from {source!r}")
    every = c.key(root, "refit_every", "data")
    if every is not _MISSING and stated is not None:
        if stated != "refit":
            if every is not None:
                c.add("data.refit_every", f"must be null for method {stated!r}, which does not re-estimate")
        elif every is None:
            c.add("data.refit_every", f"is null, but the refit method re-estimates every {REFIT_EVERY} rows")
        else:
            _pin_number(c, every, "data.refit_every", REFIT_EVERY, "re-estimates every", integer=True)
    t_df = _above(c, c.key(root, "t_df", "data"), "data.t_df", 2.0, "a Student-t on 2 or fewer degrees of freedom has no finite variance")
    k = _check_intervals(c, c.key(root, "intervals", "data"), t_df)
    windows = c.array(c.key(root, "windows", "data"), "data.windows")
    facts: list[dict[str, Any]] = [{}, {}]
    if windows is not None:
        if len(windows) != len(WINDOW_IDS):
            c.add("data.windows", f"has {len(windows)} windows, expected 2: 'test' then 'oos'")
        else:
            facts = [_check_forecast_window(c, windows[i], f"data.windows[{i}]", wid, NORMAL_Z, k, stated == "static") for i, wid in enumerate(WINDOW_IDS)]
            test, oos = facts
            if test.get("id") == "test" and oos.get("id") == "oos" and test.get("end") is not None and oos.get("start") is not None and not test["end"] < oos["start"]:
                c.add("data.windows[1].start", f"is {oos['start']}, but the test window ends {test['end']}; the oos window starts after it")
    test, oos = facts
    names = expected_param_names(order[0], order[2], trend) if order is not None and trend is not None else None  # only from a bounded order
    dates = test["dates"] + oos["dates"] if test.get("dates") is not None and oos.get("dates") is not None else None
    expected = expected_refits(test["n"], oos["n"]) if test.get("n") is not None and oos.get("n") is not None else None
    _check_refits(c, c.key(root, "refits", "data"), stated, names, dates, expected)
    return c.problems


def _key_fields(c: _Checker, row: dict[str, Any], at: str, fields: tuple[tuple[str, tuple[str, ...]], ...], expected: tuple[Any, ...]) -> list[str | None]:
    """The row's key fields, compared with the key at its position as one tuple: one problem per misplaced row."""
    got = [_choice(c, c.key(row, name, at), options, f"{at}.{name}") for name, options in fields]
    if None not in got and tuple(got) != tuple(expected):
        c.add(at, f"is the row of ({', '.join(got)}), but this position holds ({', '.join(str(e) for e in expected)})")  # type: ignore[arg-type]
    return got


def _row_set(c: _Checker, value: object, at: str, keys: list[tuple[Any, ...]], what: str) -> list[dict[str, Any] | None] | None:
    """Exactly len(keys) rows: a list of another length is one problem and no row is read."""
    items = c.array(value, at)
    if items is None:
        return None
    if len(items) != len(keys):
        c.add(at, f"has {len(items)} rows, expected {len(keys)}: {what}")
        return None
    return [c.obj(item, f"{at}[{i}]") for i, item in enumerate(items)]


def _window_n(c: _Checker, value: object, at: str, window: str | None, ns: dict[str, int], least: int = 1) -> int | None:
    n = c.integer(value, at, minimum=least)
    if n is not None and window is not None and window in ns and n != ns[window]:
        c.add(at, f"is {n}, but the {window} window has {ns[window]} rows")
        return None
    return n


_DM_TESTED = ("statistic", "statistic_hln", "p_value")  # null exactly when the verdict is "same_as_rw"


def _check_hln_factor(c: _Checker, factor: float, n: int, at: str) -> None:
    """Python only: Harvey, Leybourne and Newbold's sqrt((n + 1 - 2h + h (h - 1) / n) / n), h = 1."""
    h = DM_SETTINGS["horizon"]
    want = math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    if not _near(factor, want):
        c.add(f"{at}.hln_factor", f"is {factor}, but sqrt((n + 1 - 2h + h (h - 1) / n) / n) with n {n} and h {h} is {want}")


def _check_dm_row(c: _Checker, row: dict[str, Any], at: str, ns: dict[str, int], window: str | None) -> None:
    n = _window_n(c, c.key(row, "n", at), at + ".n", window, ns, least=2)
    df = c.integer(c.key(row, "df", at), f"{at}.df")
    if df is not None and n is not None and df != n - 1:
        c.add(f"{at}.df", f"is {df}, but n - 1 is {n - 1}")
        df = None
    verdict = _choice(c, c.key(row, "verdict", at), DM_VERDICTS, f"{at}.verdict")
    gap = c.number(c.key(row, "max_forecast_gap", at), f"{at}.max_forecast_gap")
    if gap is not None and gap < 0:
        c.add(f"{at}.max_forecast_gap", f"must be >= 0, got {gap}")
        gap = None
    mean_diff = c.number(c.key(row, "mean_diff", at), f"{at}.mean_diff")
    factor = c.number(c.key(row, "hln_factor", at), f"{at}.hln_factor")
    raw = {k: c.key(row, k, at) for k in _DM_TESTED}
    var_raw = c.key(row, "var_diff", at)
    if verdict == "same_as_rw":
        # The forecasts are the random walk's: nothing is tested, and the differential may be all 0.
        var_diff = c.number(var_raw, f"{at}.var_diff")
        if var_diff is not None and var_diff < 0:
            c.add(f"{at}.var_diff", f"must be >= 0, got {var_diff}")
        nonnull = [k for k in _DM_TESTED if raw[k] is not None and raw[k] is not _MISSING]
        if nonnull:
            c.add(at, f"{', '.join(nonnull)} must be null where the verdict is 'same_as_rw' (the forecasts are the random walk's; nothing is tested)")
        if gap is not None and not gap <= DM_SETTINGS["same_tolerance"]:  # Python only
            c.add(f"{at}.verdict", f"is 'same_as_rw', but the forecasts are up to {gap} log points from the random walk's, more than same_tolerance {DM_SETTINGS['same_tolerance']}")
        if n is not None and factor is not None:
            _check_hln_factor(c, factor, n, at)
        return
    var_diff = _above(c, var_raw, f"{at}.var_diff", 0.0, "a constant loss differential leaves DM undefined")
    nulls = [k for k in _DM_TESTED if raw[k] is None]
    if nulls:
        c.add(at, f"{', '.join(nulls)} null, but only a 'same_as_rw' row has no statistic")
    statistic = None if raw["statistic"] is None else c.number(raw["statistic"], f"{at}.statistic")
    corrected = None if raw["statistic_hln"] is None else c.number(raw["statistic_hln"], f"{at}.statistic_hln")
    p = None if raw["p_value"] is None else _p_value(c, raw["p_value"], f"{at}.p_value")
    if gap is not None and verdict is not None and gap <= DM_SETTINGS["same_tolerance"]:  # Python only
        c.add(f"{at}.verdict", f"is {verdict!r}, but the forecasts are within {gap} log points of the random walk's, at most same_tolerance {DM_SETTINGS['same_tolerance']}: 'same_as_rw'")
    if n is None:
        return
    # Python only: DM from its components, the HLN factor from n, the corrected statistic, its p-value, the verdict.
    if mean_diff is not None and var_diff is not None and statistic is not None:
        scale = math.sqrt(var_diff / n)
        want = mean_diff / scale if scale > 0 else math.nan
        if not (math.isfinite(want) and _near(statistic, want)):
            c.add(f"{at}.statistic", f"is {statistic}, but mean_diff / sqrt(var_diff / n) is {want}")
    if factor is not None:
        _check_hln_factor(c, factor, n, at)
    if corrected is not None and statistic is not None and factor is not None and not _near(corrected, statistic * factor):
        c.add(f"{at}.statistic_hln", f"is {corrected}, but statistic x hln_factor is {statistic * factor}")
    _check_t_p(c, p, corrected, df, f"{at}.p_value")
    if p is not None and mean_diff is not None and verdict is not None:
        want_verdict = "beats_rw" if p < ALPHA and mean_diff < 0 else ("worse_than_rw" if p < ALPHA and mean_diff > 0 else "no_difference")
        if verdict != want_verdict:
            c.add(f"{at}.verdict", f"is {verdict!r}, but p_value {p} and mean_diff {mean_diff} at alpha {ALPHA} give {want_verdict!r}")


def _check_coverage_row(c: _Checker, row: dict[str, Any], at: str, ns: dict[str, int], method: str | None, window: str | None, level_index: int) -> None:
    level = c.number(c.key(row, "level", at), f"{at}.level")
    if level is not None and level != LEVELS[level_index]:
        c.add(f"{at}.level", f"is {level}, but this reader expects at this position the level {LEVELS[level_index]}")
        level = None
    n = _window_n(c, c.key(row, "n", at), f"{at}.n", window, ns)
    inside = c.integer(c.key(row, "inside", at), f"{at}.inside")
    if inside is not None and n is not None and inside > n:
        c.add(f"{at}.inside", f"is {inside}, more than the window's {n} days")
        inside = None
    rate = c.number(c.key(row, "rate", at), f"{at}.rate")
    lr_raw, p_raw = c.key(row, "lr", at), c.key(row, "p_value", at)
    verdict = _choice(c, c.key(row, "verdict", at), COVERAGE_VERDICTS, f"{at}.verdict")
    if rate is not None and inside is not None and n is not None and rate != inside / n:  # Python only
        c.add(f"{at}.rate", f"is {rate}, but inside / n is {inside / n}")
    if method is None or lr_raw is _MISSING or p_raw is _MISSING:
        return
    if FORECAST_KINDS[method] == "multi_step":
        if lr_raw is not None or p_raw is not None:
            c.add(at, "lr and p_value must be null for a multi_step forecast, which is not tested")
        if verdict is not None and verdict != "not_tested":
            c.add(f"{at}.verdict", f"is {verdict!r}, but a multi_step forecast is 'not_tested'")
        return
    if lr_raw is None or p_raw is None:
        c.add(at, "lr and p_value must be numbers for a one_step forecast, which is tested")
        return
    lr = c.number(lr_raw, f"{at}.lr")
    p = _p_value(c, p_raw, f"{at}.p_value")
    if verdict == "not_tested":
        c.add(f"{at}.verdict", "is 'not_tested', but a one_step forecast is tested")
        return
    # Python only: Kupiec's LR from n, inside and the level; its chi-squared tail; the verdict.
    if lr is not None and None not in (n, inside, level):
        want = kupiec_lr(n, inside, level)  # type: ignore[arg-type]
        if not _close(lr, want):
            c.add(f"{at}.lr", f"is {lr}, but Kupiec's LR for {inside} of {n} inside at level {level} is {want}")
        elif lr < 0:
            c.add(f"{at}.lr", f"must be >= 0, got {lr}")
        else:
            _check_chi2_p(c, p, lr, 1, f"{at}.p_value", "Kupiec LR")
    if p is not None and rate is not None and level is not None and verdict is not None:
        want_verdict = "consistent" if p >= ALPHA else ("too_narrow" if rate < level else "too_wide")
        if verdict != want_verdict:
            c.add(f"{at}.verdict", f"is {verdict!r}, but p_value {p}, rate {rate} and level {level} at alpha {ALPHA} give {want_verdict!r}")


_LOG_KEYS = ("rmse", "mae")
_USD_KEYS = ("rmse", "mae", "mape_pct")
_FORECAST_KEY_FIELDS = (("model_id", MODEL_IDS), ("method", FORECAST_METHODS), ("window", WINDOW_IDS))
RW_KEYS = [(kind, w) for kind in KIND_IDS for w in WINDOW_IDS]
METRIC_KEYS = [(m, meth, w) for m, meth in FORECASTS for w in WINDOW_IDS]
DM_KEYS = [(m, meth, w, loss) for m, meth in FORECASTS if FORECAST_KINDS[meth] == "one_step" for w in WINDOW_IDS for loss in DM_LOSSES]
COVERAGE_KEYS = [(m, meth, w, dist, i) for m, meth in FORECASTS for w in WINDOW_IDS for dist in DISTRIBUTIONS for i in range(len(LEVELS))]


def _check_metric_block(c: _Checker, block: dict[str, float] | None, at: str) -> None:
    """Python only: every metric >= 0, and RMSE >= MAE (a quadratic mean is at least the arithmetic one)."""
    if block is None:
        return
    for name, value in block.items():
        if value < 0:
            c.add(f"{at}.{name}", f"must be >= 0, got {value}")
    if block["rmse"] < block["mae"] * (1.0 - _REL):
        c.add(f"{at}.rmse", f"is {block['rmse']}, below the MAE {block['mae']}: a root mean square is never below the mean absolute value")


@_capped
def validate_evaluation(data: object) -> list[str]:
    """Every problem in an `evaluation` payload (contract.md section 3.10)."""
    c = _Checker()
    root = c.obj(data, "data")
    if root is None:
        return c.problems
    _pin_number(c, c.key(root, "alpha", "data"), "data.alpha", ALPHA, "reads the tests at alpha")
    _pin_list(c, c.key(root, "interval_levels", "data"), "data.interval_levels", LEVELS, "scores the intervals at levels")
    _pin_number(c, c.key(root, "refit_every", "data"), "data.refit_every", REFIT_EVERY, "re-estimates every", integer=True)
    c.equals(c.key(root, "headline_usd", "data"), HEADLINE_USD, "data.headline_usd")
    ds = c.key(root, "dm_settings", "data")
    if ds is not _MISSING and (s := c.obj(ds, "data.dm_settings")) is not None:
        sat = "data.dm_settings"
        _pin_number(c, c.key(s, "horizon", sat), f"{sat}.horizon", DM_SETTINGS["horizon"], "tests one-step forecasts, horizon", integer=True)
        _pin_list(c, c.key(s, "losses", sat), f"{sat}.losses", DM_SETTINGS["losses"], "tests the losses")
        for name in ("errors", "correction", "alternative", "baseline"):
            c.equals(c.key(s, name, sat), DM_SETTINGS[name], f"{sat}.{name}")
        _pin_number(c, c.key(s, "same_tolerance", sat), f"{sat}.same_tolerance", DM_SETTINGS["same_tolerance"], "calls a forecast the random walk's within")
    ns: dict[str, int] = {}
    windows = c.array(c.key(root, "windows", "data"), "data.windows")
    if windows is not None:
        if len(windows) != len(WINDOW_IDS):
            c.add("data.windows", f"has {len(windows)} windows, expected 2: 'test' then 'oos'")
        else:
            seen = []
            for i, expected in enumerate(WINDOW_IDS):
                at = f"data.windows[{i}]"
                w = c.obj(windows[i], at)
                if w is None:
                    seen.append(None)
                    continue
                ident = _choice(c, c.key(w, "id", at), WINDOW_IDS, f"{at}.id")
                if ident is not None and ident != expected:
                    c.add(f"{at}.id", f"is {ident!r}, expected {expected!r} (the windows are 'test' then 'oos')")
                first = c.date(c.key(w, "start", at), f"{at}.start")
                last = c.date(c.key(w, "end", at), f"{at}.end")
                if first is not None and last is not None and first > last:
                    c.add(f"{at}.end", f"is {last}, before the window's start {first}")
                n = _row_count(c, c.key(w, "n", at), f"{at}.n")
                if ident == expected and n is not None:
                    ns[expected] = n
                origin = c.date(c.key(w, "origin_date", at), f"{at}.origin_date")
                if origin is not None and first is not None and not origin < first:
                    c.add(f"{at}.origin_date", f"is {origin}, but the origin is the last day before the window, which starts {first}")
                seen.append((ident, first, last))
            if seen[0] and seen[1] and seen[0][0] == "test" and seen[1][0] == "oos" and seen[0][2] is not None and seen[1][1] is not None and not seen[0][2] < seen[1][1]:
                c.add("data.windows[1].start", f"is {seen[1][1]}, but the test window ends {seen[0][2]}; the oos window starts after it")
    models = _row_set(c, c.key(root, "models", "data"), "data.models", [(m,) for m in MODEL_IDS], "'aic', 'bic', 'course' in that order")
    for i, m in enumerate(models or []):
        if m is None:
            continue
        at = f"data.models[{i}]"
        ident = _choice(c, c.key(m, "id", at), MODEL_IDS, f"{at}.id")
        if ident is not None and ident != MODEL_IDS[i]:
            c.add(f"{at}.id", f"is {ident!r}, expected {MODEL_IDS[i]!r}")
        own = ident or MODEL_IDS[i]  # against the row's own id, so a misplaced model is one problem
        _pin_list(c, c.key(m, "methods", at), f"{at}.methods", [meth for mid, meth in FORECASTS if mid == own], f"lists model {own!r}'s forecast files as")
        label = c.string(c.key(m, "label", at), f"{at}.label")
        if label is not None and label != MODEL_LABELS[own]:
            c.add(f"{at}.label", f"is {_show(label)}, but this reader labels model {own!r} {MODEL_LABELS[own]!r}")
        _above(c, c.key(m, "t_df", at), f"{at}.t_df", 2.0, "a Student-t on 2 or fewer degrees of freedom has no finite variance")
    methods = _row_set(c, c.key(root, "methods", "data"), "data.methods", [(m,) for m in FORECAST_METHODS], "'static', 'walk_forward', 'refit' in that order")
    for i, m in enumerate(methods or []):
        if m is None:
            continue
        at = f"data.methods[{i}]"
        ident = _choice(c, c.key(m, "id", at), FORECAST_METHODS, f"{at}.id")
        if ident is not None and ident != FORECAST_METHODS[i]:
            c.add(f"{at}.id", f"is {ident!r}, expected {FORECAST_METHODS[i]!r}")
        own = ident or FORECAST_METHODS[i]
        kind = _choice(c, c.key(m, "kind", at), KIND_IDS, f"{at}.kind")
        if kind is not None and kind != FORECAST_KINDS[own]:
            c.add(f"{at}.kind", f"is {kind!r}, but method {own!r} makes {FORECAST_KINDS[own]!r} forecasts")
        label = c.string(c.key(m, "label", at), f"{at}.label")
        if label is not None and label != METHOD_LABELS[own]:
            c.add(f"{at}.label", f"is {_show(label)}, but this reader labels method {own!r} {METHOD_LABELS[own]!r}")
    rw_rows = _row_set(c, c.key(root, "random_walk", "data"), "data.random_walk", RW_KEYS, "multi_step test, multi_step oos, one_step test, one_step oos")
    rw: dict[tuple[str, str], dict[str, Any]] = {}
    for i, row in enumerate(rw_rows or []):
        if row is None:
            continue
        at = f"data.random_walk[{i}]"
        kind, window = _key_fields(c, row, at, (("kind", KIND_IDS), ("window", WINDOW_IDS)), RW_KEYS[i])
        _window_n(c, c.key(row, "n", at), f"{at}.n", window, ns)
        log = _numbers(c, c.key(row, "log", at), f"{at}.log", _LOG_KEYS)
        usd = _numbers(c, c.key(row, "usd", at), f"{at}.usd", _USD_KEYS)
        _check_metric_block(c, log, f"{at}.log")
        _check_metric_block(c, usd, f"{at}.usd")
        if (kind, window) == RW_KEYS[i] and log is not None and usd is not None:
            rw[RW_KEYS[i]] = {"log": log, "usd": usd}
    metric_rows = _row_set(c, c.key(root, "metrics", "data"), "data.metrics", METRIC_KEYS, "one per forecast file and window, in FORECASTS order, test before oos")
    for i, row in enumerate(metric_rows or []):
        if row is None:
            continue
        at = f"data.metrics[{i}]"
        model, method, window = _key_fields(c, row, at, _FORECAST_KEY_FIELDS, METRIC_KEYS[i])
        _window_n(c, c.key(row, "n", at), f"{at}.n", window, ns)
        blocks = {"log": _numbers(c, c.key(row, "log", at), f"{at}.log", _LOG_KEYS)}
        for name in ("usd_median", "usd_mean"):
            blocks[name] = _numbers(c, c.key(row, name, at), f"{at}.{name}", _USD_KEYS)
        for name, block in blocks.items():
            _check_metric_block(c, block, f"{at}.{name}")
        ratios_raw = c.key(row, "ratio_to_rw", at)
        ratios: dict[str, dict[str, float] | None] = {}
        if ratios_raw is not _MISSING and (r := c.obj(ratios_raw, f"{at}.ratio_to_rw")) is not None:
            rat = f"{at}.ratio_to_rw"
            ratios = {"log": _numbers(c, c.key(r, "log", rat), f"{rat}.log", _LOG_KEYS), **{name: _numbers(c, c.key(r, name, rat), f"{rat}.{name}", _USD_KEYS) for name in ("usd_median", "usd_mean")}}
        bt = _numbers(c, c.key(row, "back_transform", at), f"{at}.back_transform", ("max_pct", "mean_pct"))
        if bt is not None and (bt["mean_pct"] < 0 or bt["max_pct"] < bt["mean_pct"] * (1.0 - _REL)):  # Python only
            c.add(f"{at}.back_transform", f"max_pct {bt['max_pct']} and mean_pct {bt['mean_pct']}: the largest gap is at least the mean one, and both are >= 0 (exp(s^2 / 2) >= 1)")
        # Python only: each ratio is the model's metric over the random walk's, the same division.
        key = (FORECAST_KINDS[method], window) if method is not None and window is not None else None
        base = rw.get(key) if key is not None and (model, method, window) == METRIC_KEYS[i] else None
        if base is not None:
            for name, block in blocks.items():
                ratio = ratios.get(name)
                rw_block = base["log"] if name == "log" else base["usd"]
                if block is None or ratio is None:
                    continue
                for metric, value in ratio.items():
                    denominator = rw_block[metric]
                    if denominator == 0:
                        c.add(f"{at}.ratio_to_rw.{name}.{metric}", f"is {value}, but the random walk's {metric} is 0, so there is no ratio")
                    elif value != block[metric] / denominator:
                        c.add(f"{at}.ratio_to_rw.{name}.{metric}", f"is {value}, but the metric {block[metric]} / the random walk's {denominator} is {block[metric] / denominator}")
    dm_rows = _row_set(c, c.key(root, "dm", "data"), "data.dm", DM_KEYS, "one per one-step forecast file, window and loss (squared, then absolute)")
    for i, row in enumerate(dm_rows or []):
        if row is None:
            continue
        at = f"data.dm[{i}]"
        _model, _method, window, _loss = _key_fields(c, row, at, (*_FORECAST_KEY_FIELDS, ("loss", DM_LOSSES)), DM_KEYS[i])
        _check_dm_row(c, row, at, ns, window)
    coverage_rows = _row_set(c, c.key(root, "coverage", "data"), "data.coverage", COVERAGE_KEYS, "one per forecast file, window, distribution (normal, then t) and level (0.8, then 0.95)")
    for i, row in enumerate(coverage_rows or []):
        if row is None:
            continue
        at = f"data.coverage[{i}]"
        *key, level_index = COVERAGE_KEYS[i]
        _model, method, window, _dist = _key_fields(c, row, at, (*_FORECAST_KEY_FIELDS, ("distribution", DISTRIBUTIONS)), tuple(key))
        _check_coverage_row(c, row, at, ns, method, window, level_index)
    return c.problems


def _fit_models(fit: object) -> dict[str, dict[str, Any]]:
    data = fit if isinstance(fit, dict) else {}
    models = data.get("models") if isinstance(data.get("models"), list) else []
    return {m["id"]: m for m in models if isinstance(m, dict) and isinstance(m.get("id"), str)}


# A one-step forecast's variance (sd_log^2 of a walk-forward or refit row) is the Kalman filter's
# one-step variance F_t, which for these models settles at the parameters' sigma2. statsmodels stops
# updating the state covariance once it changes by less than 1e-19 in a step (its steady-state switch,
# `tolerance`), and that leaves F_t a constant fraction above sigma2: measured on AAPL, 2.67e-5 (bic),
# 2.38e-7 (course) and 5.7e-14 (aic); on the made-up fixtures 0 to 3.4e-7; with the switch off
# (tolerance 0) 5.7e-14 or less for all three. SIGMA2_REL is about 4 times the largest of these, and
# far below any rescaling of sd_log a reader could notice (a factor of 1.0001 on sd_log is 2e-4 on sd_log^2).
SIGMA2_REL = 1e-4


def _sigma2(params: object) -> float | None:
    """The positive finite `sigma2` of a params list ([{name, value}, ...]), or None."""
    for p in params if isinstance(params, list) else []:
        if isinstance(p, dict) and p.get("name") == "sigma2" and _finite(p.get("value")) and p["value"] > 0:
            return float(p["value"])
    return None


def _one_step_variance_problems(name: str, data: dict[str, Any], sigma2: float | None) -> list[str]:
    """Each one-step row's sd_log^2 against the sigma2 its parameters had: the fit's for a walk-forward
    file and for a refit file's first REFIT_EVERY rows, each refit's own for the rows of its block. One
    problem per window at most; only for a file valid on its own (the caller checks)."""
    refits = data.get("refits") if data.get("method") == "refit" else []
    first_row = 0  # the window's first row among the test and oos rows taken together
    problems: list[str] = []
    for w in data["windows"]:
        start, first_row = first_row, first_row + len(w["rows"])  # counted whole, so a break below cannot shift the next window's blocks
        for i, r in enumerate(w["rows"]):
            block = (start + i) // REFIT_EVERY
            source = "fit.json" if block == 0 or not refits else f"refits[{block - 1}]"
            s2 = sigma2 if source == "fit.json" else _sigma2(refits[block - 1].get("params")) if block - 1 < len(refits) else None
            if s2 is None:
                continue
            v = r["sd_log"] * r["sd_log"]
            if not abs(v / s2 - 1.0) <= SIGMA2_REL:
                problems.append(f"{name}: window {_show(w['id'])} row {i} sd_log^2 is {v}, {v / s2 - 1.0:.3g} relative from the sigma2 {s2} of {source}; a one-step variance is sigma2 to within SIGMA2_REL = {SIGMA2_REL}")
                break
    return problems


def validate_forecast_fit(fit: object, residuals: dict[str, object], forecasts: dict[str, object]) -> list[str]:
    """Problems between the forecast files and `fit` and the `residuals_<id>` files (each already valid
    on its own): each file's order, trend and label are its model's, its t_df is that model's residual
    t fit's df, a refit file's first n_obs is n_train + REFIT_EVERY, and each one-step row's sd_log^2
    is its parameters' sigma2 to SIGMA2_REL (`_one_step_variance_problems`; only for a forecast file
    valid on its own). Never raises."""
    problems: list[str] = []
    models = _fit_models(fit)
    n_train = fit.get("n_train") if isinstance(fit, dict) else None
    for model_id, method in FORECASTS:
        name = f"forecast_{model_id}_{method}"
        data = forecasts.get(name)
        if not isinstance(data, dict):
            problems.append(f"{name}: missing")
            continue
        model = models.get(model_id)
        if model is None:
            problems.append(f"{name}: fit.json has no model {model_id!r}")
            continue
        for field in ("order", "trend", "label"):
            if data.get(field) != model.get(field):
                problems.append(f"{name}: {field} is {_show(data.get(field))}, but fit.json says {_show(model.get(field))}")
        series = residuals.get(f"residuals_{model_id}")
        t_fit = series.get("t_fit") if isinstance(series, dict) else None
        df = t_fit.get("df") if isinstance(t_fit, dict) else None
        if data.get("t_df") != df:
            problems.append(f"{name}: t_df is {_show(data.get('t_df'))}, but residuals_{model_id}.json's t fit has df {_show(df)}")
        if method == "refit" and isinstance(data.get("refits"), list) and data["refits"]:
            first = data["refits"][0]
            if isinstance(first, dict) and first.get("n_obs") != (n_train + REFIT_EVERY if isinstance(n_train, int) else None):
                problems.append(f"{name}: refits[0].n_obs is {_show(first.get('n_obs'))}, but fit.n_train + {REFIT_EVERY} is {_show(n_train + REFIT_EVERY if isinstance(n_train, int) else None)}")
        if FORECAST_KINDS[method] == "one_step" and not validate_forecast(data, model_id, method):
            problems += _one_step_variance_problems(name, data, _sigma2(model.get("params")))
    # The refits' parameter names need no tie here: validate_forecast names them from the file's order
    # and trend, tied to the fit's just above, and validate_fit names the fit's from the same two.
    return problems


def _fsum_mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def _recompute_metrics(actual: list[float], forecast: list[float], *, mape: bool) -> dict[str, float]:
    errors = [a - f for a, f in zip(actual, forecast, strict=True)]
    out = {"rmse": math.sqrt(_fsum_mean([e * e for e in errors])), "mae": _fsum_mean([abs(e) for e in errors])}
    if mape:
        out["mape_pct"] = 100.0 * _fsum_mean([abs(e) / abs(a) for e, a in zip(errors, actual, strict=True)])
    return out


def _window_facts(window: dict[str, Any]) -> tuple[Any, ...]:
    """What every file must agree on about a window: its id, bounds, origin, and each row's date and actuals."""
    rows = window.get("rows") if isinstance(window.get("rows"), list) else []
    return (window.get("id"), window.get("start"), window.get("end"), window.get("n"), window.get("origin"), [(r.get("date"), r.get("actual_log"), r.get("actual_usd")) for r in rows if isinstance(r, dict)])


def _same_windows(forecasts: dict[str, object]) -> list[str]:
    """Every forecast file's windows equal the first file's: the same ids, bounds, origins, dates and
    actuals, exactly. One problem per file and window at most."""
    names = [f"forecast_{m}_{meth}" for m, meth in FORECASTS]
    present = [n for n in names if isinstance(forecasts.get(n), dict) and isinstance(forecasts[n].get("windows"), list)]
    if not present:
        return []
    reference = present[0]
    ref = [_window_facts(w) for w in forecasts[reference]["windows"] if isinstance(w, dict)]
    problems = []
    for name in present[1:]:
        mine = [_window_facts(w) for w in forecasts[name]["windows"] if isinstance(w, dict)]
        if len(mine) != len(ref):
            problems.append(f"{name}: has {len(mine)} windows, but {reference} has {len(ref)}")
            continue
        for a, b in zip(mine, ref):
            if a != b:
                field = next(label for label, x, y in zip(("id", "start", "end", "n", "origin", "rows (date, actual_log, actual_usd)"), a, b) if x != y)
                problems.append(f"{name}: window {_show(a[0])} differs from {reference}'s in its {field}: every forecast file describes the same days and actuals")
    return problems


def validate_forecast_prices(prices: object, forecasts: dict[str, object]) -> list[str]:
    """Problems between the forecast files and `prices` (each already valid on its own): each window's
    rows are that segment's rows of prices.json (date, log_close, close_usd, exactly), its origin is the
    row before the segment, and its start, end and n are the segment's; and its start, end, n and origin
    date are prices.json's `splits` (the window's segment, and the end of the segment before it), which
    validate_prices ties to the rows and to the pinned out-of-sample window. One problem per file and
    window at most for each tie. Never raises."""
    data = prices if isinstance(prices, dict) else {}
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    table = [r for r in rows if isinstance(r, dict)]
    splits = data.get("splits") if isinstance(data.get("splits"), dict) else {}
    problems = []
    for name in (f"forecast_{m}_{meth}" for m, meth in FORECASTS):
        forecast = forecasts.get(name)
        if not isinstance(forecast, dict) or not isinstance(forecast.get("windows"), list):
            problems.append(f"{name}: missing")
            continue
        for w in forecast["windows"]:
            if not isinstance(w, dict) or w.get("id") not in WINDOW_IDS:
                continue
            index = [i for i, r in enumerate(table) if r.get("segment") == w["id"]]
            want_rows = [(table[i].get("date"), table[i].get("log_close"), table[i].get("close_usd")) for i in index]
            before = table[index[0] - 1] if index and index[0] > 0 else {}
            want = (w["id"], want_rows[0][0] if want_rows else None, want_rows[-1][0] if want_rows else None, len(want_rows), {"date": before.get("date"), "log_close": before.get("log_close"), "close_usd": before.get("close_usd")}, want_rows)
            got = _window_facts(w)
            if got != want:
                field = next(label for label, x, y in zip(("id", "start", "end", "n", "origin", "rows (date, actual_log, actual_usd)"), got, want) if x != y)
                problems.append(f"{name}: window {_show(w['id'])} does not match prices.json in its {field}")
            prior = SEGMENTS[SEGMENTS.index(w["id"]) - 1]  # the segment whose last day is the origin
            span, before = (splits[k] if isinstance(splits.get(k), dict) else {} for k in (w["id"], prior))
            origin = w.get("origin") if isinstance(w.get("origin"), dict) else {}
            for field, mine, theirs in (("start", w.get("start"), span.get("start")), ("end", w.get("end"), span.get("end")), ("n", w.get("n"), span.get("n")), ("origin date", origin.get("date"), before.get("end"))):
                if mine != theirs:
                    problems.append(f"{name}: window {_show(w['id'])} {field} is {_show(mine)}, but prices.json's splits say {_show(theirs)}")
                    break
    return problems


def validate_forecast_evaluation(evaluation: object, forecasts: dict[str, object]) -> list[str]:
    """Problems between `evaluation` and the forecast files: every file describes the same days and
    actuals (`_same_windows`), the windows and t_df agree, and every metric, every random-walk metric,
    each DM mean_diff, var_diff and max_forecast_gap, each coverage count and each back-transform gap
    is recomputed from the forecast rows (to _REL relative; counts and the gap exactly).

    The checks assume each file is valid on its own, as the export tool's are; a file that is not
    (validate_forecast, validate_evaluation) is named once and left out of them, so a malformed file
    cannot make them raise. Never raises: a number that cannot be recomputed (an overflow, a division
    by a zero actual) is reported as a problem."""
    problems: list[str] = []
    valid: dict[str, object] = {}
    for model_id, method in FORECASTS:
        name = f"forecast_{model_id}_{method}"
        if name not in forecasts:
            problems.append(f"{name}: missing")
        elif validate_forecast(forecasts[name], model_id, method):
            problems.append(f"{name}: not valid on its own (validate_forecast), so the checks across files leave it out")
        else:
            valid[name] = forecasts[name]
    if validate_evaluation(evaluation):
        problems.append("evaluation: not valid on its own (validate_evaluation), so it is not checked against the forecast rows")
        evaluation = {}
    problems += _same_windows(valid)
    try:
        _evaluation_from_rows(evaluation, valid, problems)
    except (ArithmeticError, ValueError, TypeError, KeyError) as error:
        problems.append(f"evaluation: a number could not be recomputed from the forecast rows ({type(error).__name__}: {error})")
    return problems


def _evaluation_from_rows(evaluation: object, forecasts: dict[str, object], problems: list[str]) -> None:
    ev = evaluation if isinstance(evaluation, dict) else {}
    files = {name: data for name, data in forecasts.items() if isinstance(data, dict)}

    def window(model_id: str, method: str, wid: str) -> dict[str, Any] | None:
        data = files.get(f"forecast_{model_id}_{method}")
        ws = data.get("windows") if data else None
        found = [w for w in ws if isinstance(w, dict) and w.get("id") == wid] if isinstance(ws, list) else []
        return found[0] if len(found) == 1 and isinstance(found[0].get("rows"), list) else None

    def compare(where: str, got: object, want: float) -> None:
        if not isinstance(got, (int, float)) or not _near(float(got), want):
            problems.append(f"evaluation: {where} is {_show(got)}, but the forecast rows give {want}")

    for w in ev.get("windows", []) if isinstance(ev.get("windows"), list) else []:
        if not isinstance(w, dict):
            continue
        for name, data in files.items():
            mine = [x for x in data.get("windows", []) if isinstance(x, dict) and x.get("id") == w.get("id")] if isinstance(data.get("windows"), list) else []
            if len(mine) != 1:
                continue
            ours = {"start": mine[0].get("start"), "end": mine[0].get("end"), "n": mine[0].get("n"), "origin_date": (mine[0].get("origin") or {}).get("date")}
            for field, value in ours.items():
                if w.get(field) != value:
                    problems.append(f"evaluation: windows {_show(w.get('id'))}.{field} is {_show(w.get(field))}, but {name} says {_show(value)}")
    for m in ev.get("models", []) if isinstance(ev.get("models"), list) else []:
        if isinstance(m, dict):
            for model_id, method in FORECASTS:
                data = files.get(f"forecast_{model_id}_{method}")
                if model_id == m.get("id") and data is not None and data.get("t_df") != m.get("t_df"):
                    problems.append(f"evaluation: models {model_id!r}.t_df is {_show(m.get('t_df'))}, but forecast_{model_id}_{method} says {_show(data.get('t_df'))}")
    # Each model's label is its forecast files' (which validate_forecast_fit ties to fit.json's).
    for m in ev.get("models", []) if isinstance(ev.get("models"), list) else []:
        if isinstance(m, dict):
            for model_id, method in FORECASTS:
                data = files.get(f"forecast_{model_id}_{method}")
                if model_id == m.get("id") and data is not None and data.get("label") != m.get("label"):
                    problems.append(f"evaluation: models {model_id!r}.label is {_show(m.get('label'))}, but forecast_{model_id}_{method} says {_show(data.get('label'))}")
    # Forecasts made from the same state with the same parameters are the same numbers: each static
    # path's first day is that model's walk-forward first day (one step from the same origin), and the
    # refit's first REFIT_EVERY days use the training parameters, so they are the walk-forward's.
    for model_id in dict.fromkeys(m for m, _ in FORECASTS):
        walk = files.get(f"forecast_{model_id}_walk_forward")
        for method, count in (("static", 1), ("refit", REFIT_EVERY)):
            other = files.get(f"forecast_{model_id}_{method}")
            if walk is None or other is None or not isinstance(walk.get("windows"), list) or not isinstance(other.get("windows"), list):
                continue
            for w_walk, w_other in zip(walk["windows"], other["windows"]):
                if method == "refit" and w_walk.get("id") != "test":
                    continue  # the first block's rows are the test window's (or both, if it is short)
                for i, (a, b) in enumerate(zip(w_walk.get("rows", [])[:count], w_other.get("rows", [])[:count])):
                    for field in ("mean_log", "sd_log"):
                        if not _near(float(a[field]), float(b[field])):
                            problems.append(f"forecast_{model_id}_{method}: window {_show(w_other.get('id'))} row {i} {field} is {b[field]}, but forecast_{model_id}_walk_forward's, made from the same state and parameters, is {a[field]}")
                            break
    # The random walk: the origin on every row (multi_step) or the row before (one_step).
    reference = files.get(f"forecast_{FORECASTS[0][0]}_{FORECASTS[0][1]}")
    for row in ev.get("random_walk", []) if isinstance(ev.get("random_walk"), list) else []:
        if not isinstance(row, dict) or reference is None:
            continue
        w = window(*FORECASTS[0], row.get("window"))  # type: ignore[arg-type]
        if w is None or not isinstance(w.get("origin"), dict):
            continue
        rows, origin = w["rows"], w["origin"]
        a_log, a_usd = [r["actual_log"] for r in rows], [r["actual_usd"] for r in rows]
        if row.get("kind") == "multi_step":
            f_log, f_usd = [origin["log_close"]] * len(rows), [origin["close_usd"]] * len(rows)
        else:
            f_log, f_usd = [origin["log_close"], *a_log[:-1]], [origin["close_usd"], *a_usd[:-1]]
        where = f"random_walk {row.get('kind')} {row.get('window')}"
        for block, (actual, forecast, mape) in (("log", (a_log, f_log, False)), ("usd", (a_usd, f_usd, True))):
            for metric, want in _recompute_metrics(actual, forecast, mape=mape).items():
                compare(f"{where} {block}.{metric}", (row.get(block) or {}).get(metric), want)
    for row in ev.get("metrics", []) if isinstance(ev.get("metrics"), list) else []:
        if not isinstance(row, dict):
            continue
        w = window(row.get("model_id"), row.get("method"), row.get("window"))  # type: ignore[arg-type]
        if w is None:
            continue
        rows = w["rows"]
        a_log, a_usd = [r["actual_log"] for r in rows], [r["actual_usd"] for r in rows]
        where = f"metrics {row.get('model_id')} {row.get('method')} {row.get('window')}"
        for block, actual, forecast, mape in (("log", a_log, [r["mean_log"] for r in rows], False), ("usd_median", a_usd, [r["median_usd"] for r in rows], True), ("usd_mean", a_usd, [r["mean_usd"] for r in rows], True)):
            for metric, want in _recompute_metrics(actual, forecast, mape=mape).items():
                compare(f"{where} {block}.{metric}", (row.get(block) or {}).get(metric), want)
        gaps = [100.0 * math.expm1(r["sd_log"] * r["sd_log"] / 2.0) for r in rows]
        compare(f"{where} back_transform.max_pct", (row.get("back_transform") or {}).get("max_pct"), max(gaps))
        compare(f"{where} back_transform.mean_pct", (row.get("back_transform") or {}).get("mean_pct"), _fsum_mean(gaps))
    for row in ev.get("dm", []) if isinstance(ev.get("dm"), list) else []:
        if not isinstance(row, dict):
            continue
        w = window(row.get("model_id"), row.get("method"), row.get("window"))  # type: ignore[arg-type]
        if w is None or not isinstance(w.get("origin"), dict) or row.get("loss") not in DM_LOSSES:
            continue
        rows = w["rows"]
        previous = [w["origin"]["log_close"], *(r["actual_log"] for r in rows[:-1])]
        square = row["loss"] == "squared"

        def loss(e: float, square: bool = square) -> float:
            return e * e if square else abs(e)

        d = [loss(r["actual_log"] - r["mean_log"]) - loss(r["actual_log"] - prev) for r, prev in zip(rows, previous, strict=True)]
        gap = max(abs(r["mean_log"] - prev) for r, prev in zip(rows, previous, strict=True))
        if row.get("max_forecast_gap") != gap:
            problems.append(f"evaluation: dm {row.get('model_id')} {row.get('method')} {row.get('window')} {row.get('loss')} max_forecast_gap is {_show(row.get('max_forecast_gap'))}, but the forecast rows give {gap}")
        mean = _fsum_mean(d)
        where = f"dm {row.get('model_id')} {row.get('method')} {row.get('window')} {row.get('loss')}"
        # The mean of a differential of mixed signs: compared at the scale of its terms.
        got = row.get("mean_diff")
        scale = max(abs(mean), _fsum_mean([abs(x) for x in d]))
        if not isinstance(got, (int, float)) or not abs(float(got) - mean) <= _REL * scale:
            problems.append(f"evaluation: {where} mean_diff is {_show(got)}, but the forecast rows give {mean}")
        compare(f"{where} var_diff", row.get("var_diff"), _fsum_mean([(x - mean) * (x - mean) for x in d]))
    for row in ev.get("coverage", []) if isinstance(ev.get("coverage"), list) else []:
        if not isinstance(row, dict):
            continue
        data = files.get(f"forecast_{row.get('model_id')}_{row.get('method')}")
        w = window(row.get("model_id"), row.get("method"), row.get("window"))  # type: ignore[arg-type]
        intervals = data.get("intervals") if data else None
        key = _MULTIPLIER.get(row.get("distribution"))  # type: ignore[arg-type]
        if w is None or not isinstance(intervals, dict) or key is None or row.get("level") not in LEVELS or not isinstance(intervals.get(key), list):
            continue
        m = intervals[key][LEVELS.index(row["level"])]
        inside = sum(1 for r in w["rows"] if r["mean_log"] - m * r["sd_log"] <= r["actual_log"] <= r["mean_log"] + m * r["sd_log"])
        if row.get("inside") != inside:
            problems.append(f"evaluation: coverage {row.get('model_id')} {row.get('method')} {row.get('window')} {row.get('distribution')} {row.get('level')} inside is {_show(row.get('inside'))}, but {inside} rows lie inside mean_log -+ {m} sd_log")



PAYLOAD_VALIDATORS: dict[str, Callable[[object], list[str]]] = {
    "meta": validate_meta,
    "prices": validate_prices,
    "eda": validate_eda,
    "stationarity": validate_stationarity,
    "acf_pacf": validate_acf_pacf,
    "aic_grid": validate_aic_grid,
    "fit": validate_fit,
    **{f"residuals_{mid}": (lambda data, mid=mid: validate_residuals(data, mid)) for mid in MODEL_IDS},
    **{f"forecast_{mid}_{meth}": (lambda data, mid=mid, meth=meth: validate_forecast(data, mid, meth)) for mid, meth in FORECASTS},
    "evaluation": validate_evaluation,
}
