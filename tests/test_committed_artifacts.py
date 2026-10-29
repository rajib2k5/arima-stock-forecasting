"""The files in app/public/data must be what the current code makes of them.

The full staleness check needs the raw snapshot, which lives outside git: run
`uv run python tools/export_app_data.py --check`. These tests cover every step that does not need
the snapshot:

- meta.json is exactly meta_payload();
- prices.json is exactly what prices_payload() builds from prices.json's own close series, so the
  log, the split and the segment labels match the current code;
- eda.json is exactly what eda_payload() builds from the training rows of prices.json, so a change
  to the summary, the KDE or the decomposition code fails here until someone re-exports.

The owner gate (ADR-0001): prices.json and eda.json are git-ignored until the owner decides whether
Yahoo-derived prices may be published, so a fresh clone has only meta.json. A test that needs a held
file SKIPS with a message that names the file and the commands that build it. A missing file that
is not held FAILS: only the gate may explain an absence.

The one step not covered is the snapshot -> close series step (normalize_download and clean_close).
JSON keeps every float exactly (Python writes the shortest repr that reads back to the same
double), which is why exact equality is the right test.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from arima_forecasting.artifacts import read_artifact, table_from_prices
from arima_forecasting.contract import SCHEMA_VERSION
from arima_forecasting.export import ARTIFACTS, HELD_ARTIFACTS, eda_payload, meta_payload, prices_payload
from arima_forecasting.prep import price_table

REPO = Path(__file__).resolve().parent.parent
APP_DATA = REPO / "app" / "public" / "data"

# contract.md section 2, "Size budgets": aim for at most 1 MB per file before compression.
SIZE_BUDGET_BYTES = 1_000_000

BUILD_HINT = (
    "Build it locally with: uv run python tools/fetch_prices.py, then "
    "uv run python tools/export_app_data.py"
)


def held_reason(name: str) -> str:
    return (
        f"{name}.json is not in this copy: it is git-ignored until the owner decides whether "
        f"Yahoo-derived prices may be published (ADR-0001). {BUILD_HINT}"
    )


def load(name: str) -> dict:
    """The envelope of `name`, or a skip if the file is held and absent, or a failure otherwise."""
    if not (APP_DATA / f"{name}.json").is_file():
        if name in HELD_ARTIFACTS:
            pytest.skip(held_reason(name))
        pytest.fail(f"{name}.json is missing, and it is not a held artifact; re-export")
    return read_artifact(APP_DATA, name)


def test_the_folder_holds_only_exported_artifacts_and_lacks_only_held_ones():
    present = {p.stem for p in APP_DATA.glob("*.json")}
    assert present <= set(ARTIFACTS), f"unexpected files: {sorted(present - set(ARTIFACTS))}"
    assert set(ARTIFACTS) - present <= set(HELD_ARTIFACTS), "a missing file that is not held"
    assert "meta" in present


def test_meta_lists_the_held_artifacts():
    assert load("meta")["data"]["held_artifacts"] == list(HELD_ARTIFACTS)


@pytest.mark.parametrize("name", ARTIFACTS)
def test_every_file_carries_the_current_schema_version(name):
    assert load(name)["schema_version"] == SCHEMA_VERSION


def test_meta_json_is_the_current_meta_payload():
    assert load("meta")["data"] == meta_payload()


def test_prices_json_is_what_the_current_code_builds_from_its_own_closes():
    data = load("prices")["data"]
    table = table_from_prices(data)
    rebuilt = prices_payload(
        price_table(table["close_usd"]),
        [date.fromisoformat(d) for d in data["fill"]["filled_dates"]],
        data["source"],
    )
    assert rebuilt == data


def test_eda_json_is_what_the_current_code_builds_from_the_committed_prices():
    prices, eda = load("prices"), load("eda")
    assert eda_payload(table_from_prices(prices["data"])) == eda["data"]


def test_eda_json_used_the_training_rows_and_nothing_after_them():
    train = load("prices")["data"]["splits"]["train"]
    summary = load("eda")["data"]["summary"]
    assert (summary["n"], summary["start"], summary["end"]) == (train["n"], train["start"], train["end"])


@pytest.mark.parametrize("name", ["prices", "eda"])
def test_each_data_file_is_within_the_size_budget(name):
    load(name)  # skips with the owner-gate message when the file is held and absent
    size = (APP_DATA / f"{name}.json").stat().st_size
    assert size <= SIZE_BUDGET_BYTES, f"{name}.json is {size:,} bytes; contract.md sets a 1 MB budget"


def test_the_skip_message_names_the_file_the_gate_and_the_commands():
    message = held_reason("prices")
    assert "prices.json" in message and "ADR-0001" in message
    assert "tools/fetch_prices.py" in message and "tools/export_app_data.py" in message


def test_table_from_prices_keeps_the_dates_and_floats():
    data = {
        "rows": [
            {"date": "2015-01-02", "close_usd": 10.123456789012345, "log_close": 2.3148, "segment": "train"},
            {"date": "2024-01-02", "close_usd": 20.5, "log_close": 3.0204, "segment": "oos"},
        ]
    }
    table = table_from_prices(data)
    assert table.index.tolist() == [pd.Timestamp("2015-01-02"), pd.Timestamp("2024-01-02")]
    assert table["close_usd"].tolist() == [10.123456789012345, 20.5]  # made-up values
    assert table["segment"].tolist() == ["train", "oos"]
