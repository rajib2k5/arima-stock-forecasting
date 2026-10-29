"""Tests for prep.py: forward filling, the windows, the coverage check and the 90/10 split.

Expected values are worked out by hand in the comments, never recomputed by the code under test.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from synthetic import random_walk, study_dates, yf_frame

from arima_forecasting.config import COURSE_WINDOW, OOS_WINDOW, StudyWindow
from arima_forecasting.data import normalize_download
from arima_forecasting.prep import (
    DataQualityError,
    check_coverage,
    clean_close,
    price_table,
    segment_bounds,
    select_window,
    train_size,
)


def frame_with(closes, dates=("2015-01-02", "2015-01-05", "2015-01-06", "2015-01-07")):
    return normalize_download(yf_frame(dates[: len(closes)], closes))


# --- 1. Forward filling -----------------------------------------------------------------

def test_ffill_carries_the_last_close_forward_and_records_the_date():
    cleaned = clean_close(frame_with([10.0, np.nan, np.nan, 13.0]))
    assert cleaned.close.tolist() == [10.0, 10.0, 10.0, 13.0]
    assert cleaned.filled_dates == (date(2015, 1, 5), date(2015, 1, 6))


def test_nothing_to_fill_means_no_filled_dates():
    assert clean_close(frame_with([10.0, 11.0])).filled_dates == ()


def test_ffill_cannot_fill_the_first_row_so_that_is_an_error():
    with pytest.raises(DataQualityError, match="first close"):
        clean_close(frame_with([np.nan, 11.0]))


@pytest.mark.parametrize("bad, message", [(0.0, "not positive"), (-1.0, "not positive"), (np.inf, "infinite")])
def test_a_close_whose_log_is_undefined_is_an_error(bad, message):
    with pytest.raises(DataQualityError, match=message):
        clean_close(frame_with([10.0, bad]))


WEEKDAYS = tuple(str(d.date()) for d in pd.bdate_range("2019-02-25", periods=40))  # Mon 2019-02-25 ...


def test_a_fill_may_carry_a_close_up_to_seven_calendar_days():
    # Rows 5-9 are Mon 2019-03-04 .. Fri 2019-03-08; the last real close is Fri 2019-03-01.
    # The furthest fill is 03-08, exactly 7 calendar days later: allowed.
    closes = [10.0 + i for i in range(40)]
    for i in range(5, 10):
        closes[i] = np.nan
    cleaned = clean_close(frame_with(closes, WEEKDAYS))
    assert cleaned.filled_dates == tuple(date(2019, 3, d) for d in (4, 5, 6, 7, 8))
    assert cleaned.close.iloc[5:10].tolist() == [14.0] * 5


def test_a_long_run_of_missing_closes_is_refused_not_filled():
    # Rows 5-10 are 03-04 .. 03-11; 03-11 is 10 calendar days after the last real close (03-01).
    closes = [10.0 + i for i in range(40)]
    for i in range(5, 11):
        closes[i] = np.nan
    with pytest.raises(DataQualityError, match=r"2019-03-11 is missing.*\(2019-03-01\) is 10 calendar days earlier"):
        clean_close(frame_with(closes, WEEKDAYS))


def test_a_missing_tail_is_refused_not_filled():
    # The last 15 closes are missing: a flat tail that check_coverage (rows exist) would accept.
    closes = [10.0 + i for i in range(25)] + [np.nan] * 15
    with pytest.raises(DataQualityError, match="a fill may carry a close at most 7 days"):
        clean_close(frame_with(closes, WEEKDAYS))


def test_the_course_fillna_method_call_no_longer_exists_in_pandas_3_1():
    # The course writes stock_data.fillna(method='ffill'). pandas 3.1 removed the keyword; the
    # pinned pandas must still refuse it, or the walkthrough's pitfall is out of date.
    with pytest.raises(TypeError, match="method"):
        pd.Series([1.0, None, 3.0]).fillna(method="ffill")
    assert pd.Series([1.0, None, 3.0]).ffill().tolist() == [1.0, 1.0, 3.0]


# --- 2. Windows and coverage --------------------------------------------------------------

def test_select_window_includes_the_start_and_excludes_the_end():
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2023-12-29", "2024-01-01", "2024-01-02"]))
    window = StudyWindow("w", date(2024, 1, 1), date(2024, 1, 2))
    assert select_window(s, window).index.tolist() == [pd.Timestamp("2024-01-01")]


def test_check_coverage_accepts_a_four_day_holiday_gap():
    window = StudyWindow("w", date(2015, 1, 1), date(2015, 1, 13))
    check_coverage(pd.DatetimeIndex(["2015-01-02", "2015-01-08", "2015-01-12"]), window)  # 6 and 4 days


@pytest.mark.parametrize(
    "dates, message",
    [
        (["2015-01-09", "2015-01-12"], "first bar is 2015-01-09"),  # 8 days after the start
        (["2015-01-02", "2015-01-05"], "last bar is 2015-01-05"),  # 8 days before the end
        (["2015-01-02", "2015-01-10", "2015-01-12"], "8 calendar days between 2015-01-02 and 2015-01-10"),
        ([], "no bars"),
    ],
)
def test_check_coverage_refuses_truncated_or_holed_data(dates, message):
    window = StudyWindow("w", date(2015, 1, 1), date(2015, 1, 13))
    with pytest.raises(DataQualityError, match=message):
        check_coverage(pd.DatetimeIndex(dates), window)


# --- 3. The split --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "n, train",
    [
        (10, 9),  # 10 * 0.9 = 9.0
        (2264, 2037),  # 2264 * 0.9 = 2037.6, truncated: AAPL's course window
        (2341, 2106),  # 2341 * 0.9 = 2106.9: the background note's simulated frame (235 test rows)
        (11, 9),  # 9.9 -> 9
    ],
)
def test_train_size_truncates_like_the_course(n, train):
    assert train_size(n) == train


def test_train_size_equals_exact_integer_arithmetic_for_every_n_up_to_200000():
    # 0.9 is not exact in binary, so int(n * 0.9) could in principle land one below n * 9 // 10.
    # It never does in this range; if a change of fraction or formula broke that, this fails.
    assert all(train_size(n) == n * 9 // 10 for n in range(2, 200_001))


def test_train_size_refuses_a_split_with_an_empty_side():
    with pytest.raises(DataQualityError, match="leaves 0 train and 1 test"):
        train_size(1)  # int(1 * 0.9) = 0
    with pytest.raises(DataQualityError, match="leaves 9 train and 0 test"):
        train_size(9, fraction=1.0)


# --- 4. The price table ----------------------------------------------------------------------

def synthetic_table(extra_outside: bool = False) -> tuple[pd.DataFrame, pd.Series]:
    dates = study_dates()
    closes = random_walk(len(dates))
    if extra_outside:
        dates = pd.DatetimeIndex([pd.Timestamp("2014-12-31"), *dates, pd.Timestamp("2026-10-01")])
        closes = np.concatenate([[1.0], closes, [1.0]])
    close = clean_close(normalize_download(yf_frame(dates, closes))).close
    return price_table(close), close


def test_price_table_labels_train_test_then_oos_in_one_block_each():
    table, _ = synthetic_table()
    course_days = len(pd.bdate_range("2015-01-01", "2023-12-31"))  # weekdays only, no holidays
    oos_days = len(pd.bdate_range("2024-01-01", "2026-09-30"))
    train = course_days * 9 // 10
    expected = ["train"] * train + ["test"] * (course_days - train) + ["oos"] * oos_days
    assert table["segment"].tolist() == expected


def test_price_table_takes_the_natural_log_of_the_close():
    table, close = synthetic_table()
    assert np.array_equal(table["log_close"].to_numpy(), np.log(close.to_numpy()))
    assert table.index[table["segment"] == "oos"][0] >= pd.Timestamp(OOS_WINDOW.start)


def test_price_table_drops_rows_outside_both_windows():
    table, _ = synthetic_table(extra_outside=True)
    assert table.index[0] == pd.Timestamp("2015-01-01")
    assert table.index[-1] == pd.Timestamp("2026-09-30")


def test_segment_bounds_are_first_and_last_dates_and_counts():
    table = pd.DataFrame(
        {"segment": ["train", "train", "test", "oos"]},
        index=pd.to_datetime(["2015-01-02", "2015-01-05", "2015-01-06", "2024-01-02"]),
    )
    assert segment_bounds(table) == {
        "train": {"start": "2015-01-02", "end": "2015-01-05", "n": 2},
        "test": {"start": "2015-01-06", "end": "2015-01-06", "n": 1},
        "oos": {"start": "2024-01-02", "end": "2024-01-02", "n": 1},
    }


def test_segment_bounds_refuses_an_empty_segment():
    table = pd.DataFrame({"segment": ["train"]}, index=pd.to_datetime(["2015-01-02"]))
    with pytest.raises(DataQualityError, match="'test' is empty"):
        segment_bounds(table)


def test_the_course_window_ends_where_the_oos_window_starts():
    assert COURSE_WINDOW.end_exclusive == OOS_WINDOW.start
