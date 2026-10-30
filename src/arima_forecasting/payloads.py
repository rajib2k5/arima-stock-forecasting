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
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))


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
    items = c.array(value, path)
    if items is None:
        return None
    out = [c.integer(v, f"{path}[{i}]", minimum=1) for i, v in enumerate(items)]
    if None in out:
        return None
    if not out or any(b <= a for a, b in zip(out, out[1:])):  # type: ignore[operator]
        c.add(path, f"must be a non-empty, strictly ascending list, got {_show(out)}")
        return None
    return out  # type: ignore[return-value]


def _warnings(c: _Checker, value: object, path: str) -> None:
    items = c.array(value, path)
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
    rows = c.array(value, at)
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
            c.add(f"{rat}.name", f"is {name!r}, expected {names[i]!r}")
        library = c.string(c.key(row, "library_name", rat), f"{rat}.library_name")
        if name is not None and library is not None and library != LIBRARY_NAMES.get(name, name):
            c.add(f"{rat}.library_name", f"is {library!r}; statsmodels labels {name!r} as {LIBRARY_NAMES.get(name, name)!r}")
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
    rows = c.array(value, at)
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
    burned = c.array(c.key(dg, "burned", at), f"{at}.burned")
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
    lb = c.array(c.key(dg, "ljung_box", at), f"{at}.ljung_box")
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
    arch = c.array(c.key(dg, "arch_lm", at), f"{at}.arch_lm")
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
    models = c.array(c.key(root, "models", "data"), "data.models")
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
        for i, item in enumerate(c.array(c.key(f, "params", fat), f"{fat}.params") or []):
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
    rows = c.array(c.key(g, "rows", at), f"{at}.rows")
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
    rows = c.array(c.key(root, "rows", "data"), "data.rows")
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
    qq = c.array(c.key(root, "qq", "data"), "data.qq")
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
        if not isinstance(model, dict) or not isinstance(model.get("diagnostics"), dict):
            continue
        name, dg = f"residuals_{model.get('id')}", model["diagnostics"]
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
    extra = sorted(set(residuals) - {f"residuals_{m.get('id')}" for m in models if isinstance(m, dict)})
    problems += [f"{name}: fit.json has no model {name.removeprefix('residuals_')!r}" for name in extra]
    return problems


PAYLOAD_VALIDATORS: dict[str, Callable[[object], list[str]]] = {
    "meta": validate_meta,
    "prices": validate_prices,
    "eda": validate_eda,
    "stationarity": validate_stationarity,
    "acf_pacf": validate_acf_pacf,
    "aic_grid": validate_aic_grid,
    "fit": validate_fit,
    **{f"residuals_{mid}": (lambda data, mid=mid: validate_residuals(data, mid)) for mid in MODEL_IDS},
}
