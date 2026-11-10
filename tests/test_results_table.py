"""tools/results_table.py prints the README's results tables from evaluation.json.

The first test holds the README to the committed data: the block between its results markers must be
exactly what the tool prints, so a re-export that moves a number fails here until the README follows.
The others feed the formatter made-up rows and check each display rule on its own.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from arima_forecasting.artifacts import read_artifact

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "results_table.py"
START, END = "<!-- results:start -->", "<!-- results:end -->"


def load_tool():
    spec = importlib.util.spec_from_file_location("results_table", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def test_the_readme_quotes_exactly_what_the_tool_prints_from_the_committed_file():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert text.count(START) == 1 and text.count(END) == 1, "the README needs one results block"
    block = text.split(START, 1)[1].split(END, 1)[0]
    evaluation = read_artifact(REPO / "app" / "public" / "data", "evaluation")["data"]
    assert block.strip("\n") + "\n" == tool.render(evaluation), "README results are stale: run uv run python tools/results_table.py"


RATES = {("normal", 0.8): 0.81, ("normal", 0.95): 0.95, ("t", 0.8): 0.79, ("t", 0.95): 0.94}


def made_up(*, ratio=1.25, p_sq=0.5, verdict_sq="no_difference", p_abs=0.00001, verdict_abs="worse_than_rw", cov_verdict="too_wide"):
    """An evaluation payload with one static and one one-step row; every value made up."""
    metric = lambda method, r: {  # noqa: E731
        "model_id": "aic", "method": method, "window": "test",
        "usd_median": {"rmse": 2.0}, "ratio_to_rw": {"usd_median": {"rmse": r}},
    }
    cov = lambda dist, level: {  # noqa: E731
        "model_id": "aic", "method": "walk_forward", "window": "test", "distribution": dist, "level": level, "rate": RATES[(dist, level)], "verdict": cov_verdict,
    }
    return {
        "methods": [{"id": "static", "kind": "multi_step"}, {"id": "walk_forward", "kind": "one_step"}],
        "random_walk": [{"kind": "multi_step", "window": "test", "usd": {"rmse": 4.0}}, {"kind": "one_step", "window": "test", "usd": {"rmse": 1.6}}],
        "metrics": [metric("static", 0.5), metric("walk_forward", ratio)],
        "dm": [
            {"model_id": "aic", "method": "walk_forward", "window": "test", "loss": "squared", "p_value": p_sq, "verdict": verdict_sq},
            {"model_id": "aic", "method": "walk_forward", "window": "test", "loss": "absolute", "p_value": p_abs, "verdict": verdict_abs},
        ],
        "interval_levels": [0.8, 0.95],
        "coverage": [cov(d, lv) for d in ("normal", "t") for lv in (0.8, 0.95)],
    }


def rows_of(text):
    return [line for line in text.splitlines() if line.startswith("| aic")]


def test_a_static_row_is_not_tested_and_a_ratio_below_one_is_bold():
    static, one_step, coverage = rows_of(tool.render(made_up()))
    assert static == "| aic | static | test | 2.000 | 4.000 | **0.5000** | not tested |"
    assert "| 1.2500 |" in one_step  # above 1: not bold
    assert coverage.startswith("| aic | walk-forward | test |")


def test_dm_cells_mark_only_a_rejection_and_floor_tiny_p_values():
    one_step = rows_of(tool.render(made_up()))[1]
    assert one_step.endswith("| 0.5000; **< 0.0001 worse** |")
    better = rows_of(tool.render(made_up(p_sq=0.01, verdict_sq="beats_rw")))[1]
    assert "**0.0100 better**;" in better


def test_a_forecast_that_is_the_random_walk_shows_no_p_value():
    one_step = rows_of(tool.render(made_up(p_sq=None, verdict_sq="same_as_rw", p_abs=None, verdict_abs="same_as_rw")))[1]
    assert one_step.endswith("| same as RW; same as RW |")


def test_coverage_cells_follow_normal_then_t_and_carry_the_verdict():
    coverage = rows_of(tool.render(made_up(cov_verdict="consistent")))[2]
    assert coverage == "| aic | walk-forward | test | 0.8100 consistent | 0.9500 consistent | 0.7900 consistent | 0.9400 consistent |"
