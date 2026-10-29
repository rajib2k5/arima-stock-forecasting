"""Shape checks for the `prices` and `eda` payloads, the Python copy of contract.md sections 3.2-3.3.

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

import math
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from arima_forecasting.contract import MAX_SAFE_INTEGER
from arima_forecasting.prep import SEGMENTS

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


def _show(value: object) -> str:
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


class _Checker:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def add(self, path: str, message: str) -> None:
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
            self.add(path, f"{text!r} is not a date written YYYY-MM-DD")
            return None
        try:
            date.fromisoformat(text)
        except ValueError:
            self.add(path, f"{text!r} is not a calendar date")
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


def _check_ascending(checker: _Checker, dates: list[str | None], path: str) -> None:
    previous: str | None = None
    for index, day in enumerate(dates):
        if day is None:
            continue
        if previous is not None and day <= previous:
            checker.add(f"{path}[{index}].date", f"{day} does not come after {previous}")
        previous = day


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
            c.add("data.source.raw_sha256", f"{sha!r} is not 64 lowercase hex characters")
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
                c.add("data.source.downloaded_at", f"{stamp!r} is not a UTC time written YYYY-MM-DDTHH:MM:SSZ")
        request = c.key(src, "request", "data.source")
        if request is not _MISSING and (req := c.obj(request, "data.source.request")) is not None:
            start = c.date(c.key(req, "start", "data.source.request"), "data.source.request.start")
            end = c.date(c.key(req, "end_exclusive", "data.source.request"), "data.source.request.end_exclusive")
            if start is not None and end is not None and start >= end:
                c.add("data.source.request", f"start {start} must be before end_exclusive {end}")
            c.string(c.key(req, "interval", "data.source.request"), "data.source.request.interval")
            c.equals(c.key(req, "auto_adjust", "data.source.request"), True, "data.source.request.auto_adjust")

    rows_value = c.key(root, "rows", "data")
    rows = c.array(rows_value, "data.rows")
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
                c.add(f"{at}.segment", f"expected one of {', '.join(SEGMENTS)}, got {segment!r}")
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
                c.add(f"data.rows[{index}].segment", f"{segment!r} after a later segment; expected train, then test, then oos")
            last_rank = max(last_rank, order[segment])

    fill = c.key(root, "fill", "data")
    if fill is not _MISSING and (fl := c.obj(fill, "data.fill")) is not None:
        c.equals(c.key(fl, "method", "data.fill"), "ffill", "data.fill.method")
        filled = c.array(c.key(fl, "filled_dates", "data.fill"), "data.fill.filled_dates")
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
        for name in SEGMENTS:
            at = f"data.splits.{name}"
            block = c.key(sp, name, "data.splits")
            if block is _MISSING or (bl := c.obj(block, at)) is None:
                continue
            start = c.date(c.key(bl, "start", at), f"{at}.start")
            end = c.date(c.key(bl, "end", at), f"{at}.end")
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
    points = c.array(c.key(kde, "points", at), f"{at}.points")
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

    kdes = c.array(c.key(root, "kdes", "data"), "data.kdes")
    if kdes is not None:
        variables = [_check_kde(c, item, f"data.kdes[{i}]") for i, item in enumerate(kdes)]
        for required in KDE_VARIABLES_REQUIRED:
            if required not in variables:
                c.add("data.kdes", f"no KDE for {required!r}")
        named = [v for v in variables if v is not None]
        if len(set(named)) != len(named):
            c.add("data.kdes", f"duplicate variables: {named}")

    decomposition = c.key(root, "decomposition", "data")
    if decomposition is not _MISSING and (dc := c.obj(decomposition, "data.decomposition")) is not None:
        c.equals(c.key(dc, "model", "data.decomposition"), "additive", "data.decomposition.model")
        period = c.integer(c.key(dc, "period", "data.decomposition"), "data.decomposition.period", minimum=2)
        rows = c.array(c.key(dc, "rows", "data.decomposition"), "data.decomposition.rows")
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
                        f"{summary.get('start')} to {summary.get('end')}",
                    )
    return c.problems


MILESTONE_STATUSES = ("done", "current", "planned")


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

    milestones = c.array(c.key(root, "milestones", "data"), "data.milestones")
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

    artifacts = c.array(c.key(root, "artifacts", "data"), "data.artifacts")
    names: list[str] = []
    if artifacts is not None:
        for index, item in enumerate(artifacts):
            name = c.string(item, f"data.artifacts[{index}]")
            if name is not None:
                names.append(name)
    if "held_artifacts" in root:  # added in 1.1.0; a 1.0.x file has no such key
        held = c.array(root["held_artifacts"], "data.held_artifacts")
        if held is not None:
            for index, item in enumerate(held):
                if not isinstance(item, str) or item not in names or item == "meta" or held.index(item) != index:
                    c.add(f"data.held_artifacts[{index}]", f"{_show(item)} must be a listed artifact other than meta, named once")
    return c.problems


PAYLOAD_VALIDATORS: dict[str, Callable[[object], list[str]]] = {
    "meta": validate_meta,
    "prices": validate_prices,
    "eda": validate_eda,
}
