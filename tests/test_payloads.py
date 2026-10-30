"""Tests for payloads.py, the Python shape checks; here for `prices` and `eda` (the shared corpus covers all).

A valid payload is built once from a synthetic snapshot. Each test then breaks one rule of
contract.md sections 3.2-3.3 and checks that the validator names it.
"""

from __future__ import annotations

import copy

import pytest
from synthetic import NOT_RUN, write_synthetic_snapshot

from arima_forecasting import config, payloads as payloads_module, prep, selection
from arima_forecasting.data import read_snapshot
from arima_forecasting.export import ARTIFACTS, build_payloads, meta_payload
from arima_forecasting.payloads import PAYLOAD_VALIDATORS, validate_eda, validate_meta, validate_prices


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
    assert set(PAYLOAD_VALIDATORS) == set(ARTIFACTS)
    for name in ARTIFACTS[3:]:  # meta, prices and eda are checked above
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
    ("fraction not the pinned 0.9", lambda d: d["splits"].__setitem__("train_fraction", 0.8), "data.splits.train_fraction: is 0.8, but this reader splits the course window at 0.9"),
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


def test_the_project_constants_the_readers_pin_are_configs():
    assert payloads_module.OOS_START == config.OOS_WINDOW.start.isoformat() == "2024-01-01"
    assert payloads_module.OOS_END_EXCLUSIVE == config.OOS_WINDOW.end_exclusive.isoformat() == "2026-10-01"
    assert payloads_module.TRAIN_FRACTION == config.TRAIN_FRACTION == 0.9
    assert payloads_module.OOS_MAX_GAP_DAYS == prep.MAX_GAP_DAYS == 7  # the app's OOS_MAX_GAP_DAYS is 7 too (contract.payloads.test.ts)
    assert validate_meta(meta_payload()) == []


def test_the_split_rule_is_the_producers_train_size():
    # For every course length, the producer's split passes and the boundary one row either way does not.
    for n in range(2, 5000):
        train = prep.train_size(n)
        for moved, ok in ((0, True), (-1, False), (1, False)):
            if not 0 <= train + moved <= n:
                continue
            c = payloads_module._Checker()
            payloads_module._check_split_rule(c, ["train"] * (train + moved) + ["test"] * (n - train - moved) + ["oos"])
            assert (c.problems == []) == ok, (n, moved, c.problems)


def _without_oos_rows(prices, drop):
    """The prices payload with the oos rows at the given positions (of the oos rows) dropped, its split following."""
    data = copy.deepcopy(prices)
    oos = [i for i, r in enumerate(data["rows"]) if r["segment"] == "oos"]
    gone = {oos[k] for k in drop}
    data["rows"] = [r for i, r in enumerate(data["rows"]) if i not in gone]
    days = [r["date"] for r in data["rows"] if r["segment"] == "oos"]
    data["splits"]["oos"] = {"start": days[0], "end": days[-1], "n": len(days)}
    data["fill"]["filled_dates"] = [d for d in data["fill"]["filled_dates"] if d in set(r["date"] for r in data["rows"])]
    return data


def test_the_oos_rows_must_cover_the_window_as_the_producer_checks_it(payloads):
    # The re-review's oos_shift.py: rows dropped at the start, at the end or inside, the splits rewritten to
    # match, passed every check. prep.check_coverage's rule (MAX_GAP_DAYS) now refuses each.
    prices = payloads["prices"]
    rule = "more than 7 (prep.MAX_GAP_DAYS) means rows are missing"
    n = prices["splits"]["oos"]["n"]
    first = next(i for i, r in enumerate(prices["rows"]) if r["segment"] == "oos")
    assert validate_prices(_without_oos_rows(prices, range(5))) == []  # the synthetic rows are weekdays: 2024-01-08 is 7 days in
    assert validate_prices(_without_oos_rows(prices, range(6))) == [f"data.rows[{first}].date: the first oos row is 2024-01-09, 8 calendar days after the out-of-sample window starts on 2024-01-01; {rule}"]
    assert validate_prices(_without_oos_rows(prices, range(100))) == [f"data.rows[{first}].date: the first oos row is 2024-05-20, 140 calendar days after the out-of-sample window starts on 2024-01-01; {rule}"]
    tail = validate_prices(_without_oos_rows(prices, range(n - 300, n)))
    assert len(tail) == 1 and tail[0].endswith(f"calendar days before the out-of-sample window ends on 2026-10-01 (exclusive); {rule}"), tail
    # Six weekdays out (Monday 2024-03-11 to Monday 03-18): 11 days from Friday 03-08 to Tuesday 03-19.
    assert validate_prices(_without_oos_rows(prices, range(50, 56))) == [f"data.rows[{first + 50}].date: 2024-03-19 is 11 calendar days after the oos row before it, 2024-03-08; {rule}"]
    assert validate_prices(_without_oos_rows(prices, range(50, 54))) == []  # Monday to Thursday out: Friday to Friday is 7 days


def test_meta_must_state_the_pinned_out_of_sample_window():
    for start, end in (("2024-01-02", "2026-10-01"), ("2024-01-01", "2026-09-30")):
        problems = validate_meta(broken(meta_payload(), lambda d: d["windows"].__setitem__("oos", {"start": start, "end_exclusive": end})))
        assert problems == [f"data.windows.oos: is {start} to {end}, but this reader's out-of-sample window is 2024-01-01 to 2026-10-01 (exclusive)"]


def _moved_day(payload, segment, which, day):
    """The prices payload with the first or last row of a segment moved to `day`, its split following."""
    data = copy.deepcopy(payload)
    index = [i for i, r in enumerate(data["rows"]) if r["segment"] == segment][0 if which == "start" else -1]
    data["rows"][index]["date"] = day
    data["splits"][segment][which] = day
    data["fill"]["filled_dates"] = [d for d in data["fill"]["filled_dates"] if d != day]
    return data


def test_prices_rows_keep_to_the_pinned_out_of_sample_window(payloads):
    # The synthetic snapshot has every weekday: its oos rows run 2024-01-01 (a Monday) to 2026-09-30,
    # the window's first and last calendar days, so both bounds are met exactly.
    prices = payloads["prices"]
    assert (prices["splits"]["oos"]["start"], prices["splits"]["oos"]["end"]) == ("2024-01-01", "2026-09-30")
    assert validate_prices(prices) == []
    window = "this reader's out-of-sample window is 2024-01-01 to 2026-10-01 (exclusive)"
    assert validate_prices(_moved_day(prices, "oos", "end", "2026-10-01")) == [f"data.splits.oos: runs 2024-01-01 to 2026-10-01, but {window}"]
    assert validate_prices(_moved_day(prices, "oos", "start", "2023-12-31")) == [f"data.splits.oos: runs 2023-12-31 to 2026-09-30, but {window}"]
    # The first oos day labelled test instead (its split counts following): the test rows reach the window,
    # and the course window's rows no longer split at 0.9 (2112 train of 2348 is not int(2348 x 0.9)).
    data = copy.deepcopy(prices)
    first = next(i for i, r in enumerate(data["rows"]) if r["segment"] == "oos")
    data["rows"][first]["segment"] = "test"
    data["splits"]["test"].update(end=data["rows"][first]["date"], n=data["splits"]["test"]["n"] + 1)
    data["splits"]["oos"].update(start=data["rows"][first + 1]["date"], n=data["splits"]["oos"]["n"] - 1)
    assert validate_prices(data) == [
        "data.rows: 2112 rows are train and 236 test, but the course window's 2348 rows split at 0.9 give int(2348 x 0.9) = 2113 train and 235 test (prep.train_size)",
        "data.splits.test.end: is 2024-01-01, but the test rows come before the out-of-sample window, which starts 2024-01-01",
    ]


def test_the_list_bounds_follow_the_producers_dimensions():
    # Each bound the readers hold (the shared corpus's size cases run them) against what it bounds.
    from arima_forecasting import eda, export

    assert payloads_module.GRID_MAX_ORDER == max(selection.GRID_ORDERS) == 5 and min(selection.GRID_ORDERS) == 0
    assert payloads_module.GRID_MAX_D == max(d for d, _ in selection.GRID_SPECS) == payloads_module.MAX_D == 2
    assert payloads_module.MAX_GRID_CELLS == 6 * 6 * 3 * 3 >= len(selection.GRID_ORDERS) ** 2 * sum(len(t) for _, t in selection.GRID_SPECS) == 144
    assert payloads_module.MAX_CELL_PARAMS == 2 * 5 + 2
    assert payloads_module.MAX_PMDARIMA_RUNS == len(selection.PMDARIMA_RUNS) == 2
    # pmdarima's auto_arima searches p and q up to max_p and max_q, 5 unless a run says otherwise.
    largest = max(max(settings.get("max_p", 5), settings.get("max_q", 5)) for _, settings in selection.PMDARIMA_RUNS)
    assert payloads_module.MAX_VISITED == (largest + 1) ** 2 * 2 == 72
    assert payloads_module.MAX_FIT_PARAMS == 2 * payloads_module.MAX_PQ + 2
    calendar_days = (config.DOWNLOAD_WINDOW.end_exclusive - config.DOWNLOAD_WINDOW.start).days
    assert payloads_module.MAX_LIST >= max(calendar_days, eda.KDE_POINTS) and calendar_days == 4291
    assert payloads_module.MAX_NAMES >= max(len(ARTIFACTS), len(export._MILESTONES), len(payloads_module.KDE_VARIABLES_REQUIRED))


def test_a_cell_params_object_longer_than_any_cell_has_is_not_walked():
    # 13 entries, one past the 12 a cell of the grid can have: one problem for the count, none per entry
    # (an object of millions of bad entries once gave a problem each). The app reads it the same way.
    import json
    from pathlib import Path

    from arima_forecasting.payloads import validate_aic_grid

    grid = json.loads((Path(__file__).resolve().parent.parent / "app/src/test/fixtures/aic_grid.data.json").read_text())
    grid["cells"][9]["params"] = {f"x{i}": "not a number" for i in range(payloads_module.MAX_CELL_PARAMS + 1)}
    assert validate_aic_grid(grid) == [f"data.cells[9].params: has 13 entries, but k_params is {grid['cells'][9]['k_params']}"]
    grid["cells"][9]["params"] = {f"x{i}": "not a number" for i in range(grid["cells"][9]["k_params"])}
    assert len(validate_aic_grid(grid)) == grid["cells"][9]["k_params"]  # within the bound each entry is read
