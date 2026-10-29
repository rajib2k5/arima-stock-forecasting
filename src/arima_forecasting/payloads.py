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
    transforms = c.array(c.key(root, "transforms", "data"), "data.transforms")
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
    series = c.array(c.key(root, "series", "data"), "data.series")
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
            rows = c.array(c.key(s, "rows", at), f"{at}.rows")
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
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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
    warns = c.array(c.key(cell, "warnings", at), f"{at}.warnings")
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
            for name, value in params.items():
                c.number(value, f"{at}.params.{name}")
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
            if random_starts is not None and int(match.group(1)) > random_starts:
                c.add(at, f"is {match.group(0)!r}, but fit_settings.random_starts is {random_starts}")
            if x["p"] == 0 or x["q"] == 0:
                c.add(at, f"is {match.group(0)!r}, but random starts are drawn only when p and q are both at least 1")
        elif match.group(8) is not None:
            sp, sd, sq, st = int(match.group(8)), int(match.group(9)), int(match.group(10)), match.group(11)
            if sd != x["d"] or sp not in ps or sq not in qs or st not in trends.get(x["d"], []):
                c.add(at, f"is {match.group(0)!r}, which is not a cell of the grid with the same d")
        elif match.group(2) is not None:
            sp, sd, sq, st = int(match.group(2)), int(match.group(3)), int(match.group(4)), match.group(5)
            if match.group(6) is not None and (sp, sq) == (x["p"], x["q"]):
                c.add(at, f"is {match.group(0)!r}, but the step that drops the trend adds no AR or MA coefficient to perturb")
            steps = []
            if x["p"] in ps and ps.index(x["p"]) > 0:
                steps.append((ps[ps.index(x["p"]) - 1], x["q"], x["trend"]))
            if x["q"] in qs and qs.index(x["q"]) > 0:
                steps.append((x["p"], qs[qs.index(x["q"]) - 1], x["trend"]))
            if x["trend"] != "n" and "n" in trends.get(x["d"], []):
                steps.append((x["p"], x["q"], "n"))
            if sd != x["d"] or (sp, sq, st) not in steps:
                c.add(at, f"is {match.group(0)!r}, which is not a model of the grid one step smaller than ({x['p']}, {x['d']}, {x['q']}) {x['trend']}")


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
    items = c.array(value, path)
    if items is None:
        return None
    out = [c.integer(v, f"{path}[{i}]") for i, v in enumerate(items)]
    if not out:
        c.add(path, "must not be empty")
    if None in out:
        return None
    if any(b <= a for a, b in zip(out, out[1:])):  # type: ignore[operator]
        c.add(path, f"must be strictly ascending, got {_show(out)}")
        return None
    return out  # type: ignore[return-value]


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
        raw_specs = c.array(c.key(gd, "specs", "data.grid"), "data.grid.specs")
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
                d = c.integer(c.key(sp, "d", at), f"{at}.d")
                trends = c.array(c.key(sp, "trends", at), f"{at}.trends")
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
    raw_cells = c.array(c.key(root, "cells", "data"), "data.cells")
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
        within = _list_of(c, c.key(sl, "within_2_aic", at), f"{at}.within_2_aic", _NEAR_TIE_FIELDS)
        bic_choice = _fields(c, c.key(sl, "bic_choice", at), f"{at}.bic_choice", _BIC_FIELDS)
        per_d = _best_per_d(c, c.key(sl, "best_per_d", at), f"{at}.best_per_d")
        counts = _list_of(c, c.key(sl, "status_counts", at), f"{at}.status_counts", _COUNT_FIELDS)
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
        runs = c.array(c.key(pc, "runs", at), f"{at}.runs")
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


def _list_of(c: _Checker, value: object, path: str, spec: tuple[tuple[str, str], ...]) -> list[tuple[Any, ...]] | None:
    items = c.array(value, path)
    if items is None:
        return None
    parsed = [_fields(c, item, f"{path}[{i}]", spec) for i, item in enumerate(items)]
    return None if None in parsed else parsed  # type: ignore[return-value]


def _best_per_d(c: _Checker, value: object, path: str) -> list[tuple[int, tuple[Any, ...] | None]] | None:
    items = c.array(value, path)
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
    visited = c.array(c.key(run, "visited", at), f"{at}.visited")
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
    warns = c.array(c.key(run, "warnings", at), f"{at}.warnings")
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


PAYLOAD_VALIDATORS: dict[str, Callable[[object], list[str]]] = {
    "meta": validate_meta,
    "prices": validate_prices,
    "eda": validate_eda,
    "stationarity": validate_stationarity,
    "acf_pacf": validate_acf_pacf,
    "aic_grid": validate_aic_grid,
}
