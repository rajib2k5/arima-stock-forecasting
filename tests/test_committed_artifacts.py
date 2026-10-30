"""The files in app/public/data must be what the current code makes of them.

The full staleness check needs the raw snapshot, which lives outside git: run
`uv run python tools/export_app_data.py --check`. These tests cover every step that does not need
the snapshot:

- meta.json is exactly meta_payload();
- prices.json is exactly what prices_payload() builds from prices.json's own close series, so the
  log, the split and the segment labels match the current code;
- eda.json is exactly what eda_payload() builds from the training rows of prices.json, so a change
  to the summary, the KDE or the decomposition code fails here until someone re-exports;
- stationarity.json and acf_pacf.json are exactly what the current code builds from those rows, and
  in aic_grid.json a sample of cells (the choice, BIC's choice, the best of each d and one cell of
  each status) refits to the same values. All 144 cells are refitted by `--check` (about 8 minutes);
- fit.json and the three residuals_<id>.json files are exactly what the current code builds from
  prices.json's rows and aic_grid.json's estimates.

Every exported file is committed (the owner's decision of 2026-10-29, DATA.md), so all of these
tests run in every copy, a fresh clone included. The held-artifact mechanism stays: a file that
meta.data.held_artifacts names and this copy lacks would SKIP with a message that names it and the
commands that build it, and a missing file that is not held FAILS. Since 2026-10-29 none is held.

The one step not covered is the snapshot -> close series step (normalize_download and clean_close).
JSON keeps every float exactly (Python writes the shortest repr that reads back to the same
double), which is why exact equality is the right test.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from arima_forecasting import selection, stationarity
from arima_forecasting.artifacts import read_artifact, table_from_prices
from arima_forecasting.contract import SCHEMA_VERSION
from arima_forecasting.export import ARTIFACTS, HELD_ARTIFACTS, RESIDUAL_ARTIFACTS, eda_payload, fit_payloads, meta_payload, prices_payload
from arima_forecasting.identification import acf_pacf_payload
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
        f"{name}.json is not in this copy: meta.data.held_artifacts names it as written by the export "
        f"but not committed (ADR-0001). {BUILD_HINT}"
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


@pytest.mark.parametrize("name", [name for name in ARTIFACTS if name != "meta"])
def test_each_data_file_is_within_the_size_budget(name):
    load(name)  # would skip with the held message if the file were held and absent
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


# --- milestone 2: stationarity, acf_pacf and aic_grid -----------------------------------------

def train_log_close():
    prices = load("prices")["data"]
    table = table_from_prices(prices)
    return table.loc[table["segment"] == "train", "log_close"].to_numpy()


def test_the_order_selection_files_are_committed_not_held():
    for name in ("stationarity", "acf_pacf", "aic_grid"):
        assert name not in HELD_ARTIFACTS
        assert (APP_DATA / f"{name}.json").is_file(), f"{name}.json is missing; re-export"


def test_stationarity_json_is_what_the_current_code_builds_from_the_training_rows():
    assert stationarity.stationarity_payload(train_log_close()) == load("stationarity")["data"]


def test_acf_pacf_json_is_what_the_current_code_builds_from_the_training_rows():
    assert acf_pacf_payload(train_log_close()) == load("acf_pacf")["data"]


def test_a_sample_of_aic_grid_cells_refits_to_the_committed_values():
    y = train_log_close()
    grid = load("aic_grid")["data"]
    cells = {(c["d"], c["p"], c["q"], c["trend"]): c for c in grid["cells"]}
    s = grid["selection"]
    sample = {(s["d_selected"], s["order"][0], s["order"][2], s["trend"])}
    sample.add((s["d_selected"], s["bic_choice"]["p"], s["bic_choice"]["q"], s["bic_choice"]["trend"]))
    sample |= {(e["d"], e["cell"]["p"], e["cell"]["q"], e["cell"]["trend"]) for e in s["best_per_d"] if e["cell"]}
    for status in selection.STATUSES:
        first = next((key for key, c in cells.items() if c["status"] == status), None)
        if first:
            sample.add(first)
    assert len(sample) >= 5
    for key in sorted(sample):
        # From the recorded winning start alone (and, for a nested start, the cells it came from).
        refit, _ = selection.refit_cell(y, grid["cells"], key)
        committed = {k: v for k, v in cells[key].items() if k != "delta_aic"}
        if selection.replayable(grid["cells"], key):
            assert refit == committed, key
        else:  # won in the polish stage: its recorded parameters must give its log-likelihood
            assert refit["llf"] == pytest.approx(committed["llf"], abs=1e-6), key


def test_aic_grid_json_is_the_grid_adr_0002_specifies():
    grid = load("aic_grid")["data"]
    assert grid["grid"] == {"p": list(range(6)), "q": list(range(6)), "specs": [{"d": 0, "trends": ["c"]}, {"d": 1, "trends": ["n", "t"]}, {"d": 2, "trends": ["n"]}]}
    assert len(grid["cells"]) == 144
    assert grid["fit_settings"] == selection.FIT_SETTINGS


def test_the_committed_selection_follows_from_the_committed_cells():
    # Pure: re-rank the committed cells with the current code; needs aic_grid.json only.
    grid = load("aic_grid")["data"]
    cells = [dict(c) for c in grid["cells"]]
    for c in cells:
        c.pop("delta_aic")
    selection.add_delta_aic(cells)
    assert [c["delta_aic"] for c in cells] == [c["delta_aic"] for c in grid["cells"]]
    specs = [(spec["d"], tuple(spec["trends"])) for spec in grid["grid"]["specs"]]
    assert selection.select(cells, grid["selection"]["d_selected"], specs) == grid["selection"]


def test_the_committed_d_follows_from_the_committed_tests_and_both_files_use_it():
    st = load("stationarity")["data"]
    for t in st["transforms"]:
        assert t["verdict"] == stationarity.verdict(t["adf"]["reject_unit_root"], t["kpss"]["reject_stationarity"])
    d, conflict = stationarity.decide_d(st["transforms"])
    assert (st["decision"]["d_selected"], st["decision"]["tests_conflict"]) == (d, conflict)
    assert load("aic_grid")["data"]["selection"]["d_selected"] == d


def test_the_three_files_describe_the_same_training_rows():
    st, ap, grid = (load(name)["data"] for name in ("stationarity", "acf_pacf", "aic_grid"))
    assert st["n_train"] == grid["n_train"] == ap["series"][0]["n"]
    assert [s["n"] for s in ap["series"]] == [t["n"] for t in st["transforms"]]
    assert load("prices")["data"]["splits"]["train"]["n"] == st["n_train"]


def test_no_committed_cell_sits_at_the_optimum_of_a_model_it_nests():
    # The round-2 review found seven cells whose llf equalled, to 1e-6, a model one step smaller: a
    # zero-padded start that L-BFGS never left. Perturbed starts and the polish stage remove that.
    cells = [c for c in load("aic_grid")["data"]["cells"] if c["llf"] is not None]
    key = lambda c: (c["d"], c["p"], c["q"], c["trend"])  # noqa: E731
    ties = [(key(s), key(b)) for b in cells for s in cells if selection.nests(key(s), key(b)) and abs(b["llf"] - s["llf"]) <= selection.TIE]
    assert ties == []


# --- milestone 3: fit and residuals_<id> -------------------------------------------------------


def test_fit_and_residuals_are_what_the_current_code_builds_from_the_committed_rows_and_grid():
    # The fits start from the committed grid's estimates, and the course's auto_arima runs on the
    # committed training and test rows, so this rebuilds all four files exactly (a few seconds).
    built = fit_payloads(table_from_prices(load("prices")["data"]), load("aic_grid")["data"])
    assert list(built) == ["fit", *RESIDUAL_ARTIFACTS]
    for name, payload in built.items():
        assert payload == load(name)["data"], name


def test_the_fit_names_the_grid_choices_and_describes_the_same_training_rows():
    fit, grid = load("fit")["data"], load("aic_grid")["data"]
    s = grid["selection"]
    models = {m["id"]: m for m in fit["models"]}
    assert (models["aic"]["order"], models["aic"]["trend"]) == (s["order"], s["trend"])
    bic = s["bic_choice"]
    assert (models["bic"]["order"], models["bic"]["trend"]) == ([bic["p"], s["d_selected"], bic["q"]], bic["trend"])
    assert fit["n_train"] == grid["n_train"] == load("prices")["data"]["splits"]["train"]["n"]
    run = next(r for r in grid["pmdarima_check"]["runs"] if r["label"] == "course")
    assert fit["course_track"]["train_only"] == {k: run[k] for k in ("order", "with_intercept", "trend")}


def test_each_residuals_file_matches_its_model_and_the_training_dates():
    fit = load("fit")["data"]
    train = [r["date"] for r in load("prices")["data"]["rows"] if r["segment"] == "train"]
    for model in fit["models"]:
        series, dg = load(f"residuals_{model['id']}")["data"], model["diagnostics"]
        assert series["model_id"] == model["id"]
        assert (series["n"], series["burn_excluded"]) == (dg["n"], dg["burn_excluded"])
        assert [r["date"] for r in series["rows"]] == train[dg["burn_excluded"] :]
        assert [r["date"] for r in dg["burned"]] == train[: dg["burn_excluded"]]
        assert series["acf"]["outside_count"] == dg["acf_outside_count"]
        assert series["acf_squared"]["outside_count"] == dg["acf_squared_outside_count"]
