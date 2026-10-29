"""Tests for payloads.py, the Python shape checks; here for `prices` and `eda` (the shared corpus covers all).

A valid payload is built once from a synthetic snapshot. Each test then breaks one rule of
contract.md sections 3.2-3.3 and checks that the validator names it.
"""

from __future__ import annotations

import copy

import pytest
from synthetic import NOT_RUN, write_synthetic_snapshot

from arima_forecasting import selection
from arima_forecasting.data import read_snapshot
from arima_forecasting.export import build_payloads
from arima_forecasting.payloads import PAYLOAD_VALIDATORS, validate_eda, validate_prices


@pytest.fixture(scope="module")
def payloads(tmp_path_factory):
    folder = write_synthetic_snapshot(tmp_path_factory.mktemp("data"))
    with pytest.MonkeyPatch.context() as patch:  # the milestone-2 grid is not what these tests are about
        patch.setattr(selection, "GRID_ORDERS", (0,))
        patch.setattr(selection, "pmdarima_check", lambda y, cells, chosen: dict(NOT_RUN))
        return build_payloads(read_snapshot(folder))


def broken(payload, edit):
    copied = copy.deepcopy(payload)
    edit(copied)
    return copied


def test_the_export_builds_payloads_that_pass_both_validators(payloads):
    assert validate_prices(payloads["prices"]) == []
    assert validate_eda(payloads["eda"]) == []
    assert set(PAYLOAD_VALIDATORS) == {"meta", "prices", "eda", "stationarity", "acf_pacf", "aic_grid"}
    for name in ("stationarity", "acf_pacf", "aic_grid"):
        assert PAYLOAD_VALIDATORS[name](payloads[name]) == [], name


@pytest.mark.parametrize("value", [None, [], "prices"])
def test_a_payload_that_is_not_an_object(value):
    assert validate_prices(value) == [f"data: expected an object, got {type(value).__name__}"]
    assert validate_eda(value) == [f"data: expected an object, got {type(value).__name__}"]


PRICE_BREAKS = [
    ("missing ticker", lambda d: d.pop("ticker"), "data.ticker: missing"),
    ("price basis", lambda d: d.__setitem__("price_basis", "close"), "data.price_basis: expected 'adjusted_close', got 'close'"),
    ("sha", lambda d: d["source"].__setitem__("raw_sha256", "ABC"), "data.source.raw_sha256: 'ABC' is not 64 lowercase hex characters"),
    ("no such day", lambda d: d["source"].__setitem__("downloaded_at", "2026-02-30T12:00:00Z"), "data.source.downloaded_at: '2026-02-30T12:00:00Z' is not a UTC time"),
    ("not adjusted", lambda d: d["source"]["request"].__setitem__("auto_adjust", False), "data.source.request.auto_adjust: expected True, got False"),
    ("raw rows", lambda d: d["source"].__setitem__("raw_rows", 0), "data.source.raw_rows: expected an integer >= 1, got 0"),
    ("bool is not an int", lambda d: d["source"].__setitem__("raw_rows", True), "data.source.raw_rows: expected an integer >= 1, got True"),
    ("empty rows", lambda d: d.__setitem__("rows", []), "data.rows: must not be empty"),
    ("repeated date", lambda d: d["rows"][1].__setitem__("date", d["rows"][0]["date"]), "data.rows[1].date: "),
    ("bad segment", lambda d: d["rows"][0].__setitem__("segment", "holdout"), "data.rows[0].segment: expected one of train, test, oos"),
    ("segment order", lambda d: d["rows"][-1].__setitem__("segment", "train"), "after a later segment"),
    ("zero close", lambda d: d["rows"][0].__setitem__("close_usd", 0.0), "data.rows[0].close_usd: must be positive"),
    ("nan close", lambda d: d["rows"][0].__setitem__("close_usd", float("nan")), "data.rows[0].close_usd: expected a finite number"),
    ("split count", lambda d: d["splits"]["test"].__setitem__("n", 1), "data.splits.test.n: says 1, but"),
    ("split start", lambda d: d["splits"]["oos"].__setitem__("start", "2024-01-03"), "data.splits.oos.start: says 2024-01-03, but the first oos row is"),
    ("fraction", lambda d: d["splits"].__setitem__("train_fraction", 1.0), "data.splits.train_fraction: must be between 0 and 1"),
    ("fill method", lambda d: d["fill"].__setitem__("method", "bfill"), "data.fill.method: expected 'ffill', got 'bfill'"),
    ("filled day not a row", lambda d: d["fill"].__setitem__("filled_dates", ["2015-01-03"]), "data.fill.filled_dates[0]: 2015-01-03 is not one of the rows"),
    ("filled unsorted", lambda d: d["fill"].__setitem__("filled_dates", [d["rows"][2]["date"], d["rows"][1]["date"]]), "dates must be sorted and unique"),
]


@pytest.mark.parametrize("name, edit, expected", PRICE_BREAKS, ids=[b[0] for b in PRICE_BREAKS])
def test_validate_prices_names_each_broken_rule(payloads, name, edit, expected):
    problems = validate_prices(broken(payloads["prices"], edit))
    assert any(expected in p for p in problems), problems


EDA_BREAKS = [
    ("sample", lambda d: d.__setitem__("sample", "test"), "data.sample: expected 'train', got 'test'"),
    ("missing summary moment", lambda d: d["summary"]["log_return"].pop("skew"), "data.summary.log_return.skew: missing"),
    ("no log_return kde", lambda d: d["kdes"].pop(), "data.kdes: no KDE for 'log_return'"),
    ("duplicate kde", lambda d: d["kdes"][1].__setitem__("variable", "log_close"), "data.kdes: duplicate variables"),
    ("kde x order", lambda d: d["kdes"][0]["points"][1].__setitem__("x", d["kdes"][0]["points"][0]["x"]), "data.kdes[0].points[1].x: "),
    ("negative density", lambda d: d["kdes"][0]["points"][0].__setitem__("density", -1.0), "data.kdes[0].points[0].density: must not be negative"),
    ("zero bandwidth", lambda d: d["kdes"][1].__setitem__("bandwidth", 0.0), "data.kdes[1].bandwidth: must be positive"),
    ("model", lambda d: d["decomposition"].__setitem__("model", "multiplicative"), "data.decomposition.model: expected 'additive', got 'multiplicative'"),
    ("null mismatch", lambda d: d["decomposition"]["rows"][0].__setitem__("resid_log", 0.0), "data.decomposition.rows[0]: trend_log and resid_log must be null on the same rows"),
    ("null in the middle", lambda d: d["decomposition"]["rows"][500].update(trend_log=None, resid_log=None), "trend_log must be null on exactly the first and last 126 rows"),
    ("no nulls at the end", lambda d: d["decomposition"]["rows"][-1].update(trend_log=1.0, resid_log=0.0), "trend_log must be null on exactly the first and last 126 rows"),
    ("rows vs summary", lambda d: d["decomposition"]["rows"].pop(), "but data.summary.n is"),
    ("null observed", lambda d: d["decomposition"]["rows"][3].__setitem__("observed_log", None), "data.decomposition.rows[3].observed_log: expected a finite number, got None"),
]


@pytest.mark.parametrize("name, edit, expected", EDA_BREAKS, ids=[b[0] for b in EDA_BREAKS])
def test_validate_eda_names_each_broken_rule(payloads, name, edit, expected):
    problems = validate_eda(broken(payloads["eda"], edit))
    assert any(expected in p for p in problems), problems


def test_validators_report_every_problem_in_one_pass(payloads):
    def edit(d):
        d.pop("ticker")
        d["price_basis"] = "close"
        d["rows"][0]["segment"] = "x"

    problems = validate_prices(broken(payloads["prices"], edit))
    assert len(problems) >= 3
    assert problems[0] == "data.ticker: missing"
