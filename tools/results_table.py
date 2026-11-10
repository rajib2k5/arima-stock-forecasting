"""Print the README's two results tables from the committed app/public/data/evaluation.json.

Run:  uv run python tools/results_table.py

Every number is read from the file as Python's evaluation module wrote it; this tool only rounds
for display. `tests/test_results_table.py` fails if the tables between the README's
`<!-- results:start -->` and `<!-- results:end -->` markers differ from what this prints, so the
README cannot quote a number the committed data does not hold.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from arima_forecasting.artifacts import ArtifactError, find_app_data, read_artifact

# Short names for the table; the app shows the long labels from evaluation.json.
METHOD_NAMES = {"static": "static", "walk_forward": "walk-forward", "refit": "walk-forward, refit"}
VERDICT_WORDS = {"beats_rw": "better", "worse_than_rw": "worse", "too_narrow": "too narrow", "too_wide": "too wide", "consistent": "consistent"}


def _p(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def _dm_cell(row: Mapping[str, Any] | None) -> str:
    if row is None:
        return "not tested"
    if row["p_value"] is None:  # same_as_rw: the forecast is the random walk's, no statistic
        return "same as RW"
    text = _p(row["p_value"])
    word = VERDICT_WORDS.get(row["verdict"])
    return f"**{text} {word}**" if word else text


def render(evaluation: Mapping[str, Any]) -> str:
    """The two Markdown tables: errors against the random walk with the DM p-values, then the
    one-step interval coverage. `evaluation` is the `data` of evaluation.json."""
    kinds = {m["id"]: m["kind"] for m in evaluation["methods"]}
    rw = {(r["kind"], r["window"]): r for r in evaluation["random_walk"]}
    dm = {(r["model_id"], r["method"], r["window"], r["loss"]): r for r in evaluation["dm"]}
    lines = [
        "| Model | Method | Window | RMSE $ | Random walk $ | Ratio | DM p: squared; absolute |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in evaluation["metrics"]:
        key = (row["model_id"], row["method"], row["window"])
        base = rw[(kinds[row["method"]], row["window"])]
        ratio = row["ratio_to_rw"]["usd_median"]["rmse"]
        cells = [
            row["model_id"],
            METHOD_NAMES[row["method"]],
            row["window"],
            f"{row['usd_median']['rmse']:.3f}",
            f"{base['usd']['rmse']:.3f}",
            f"**{ratio:.4f}**" if ratio < 1 else f"{ratio:.4f}",
            "not tested" if kinds[row["method"]] != "one_step" else f"{_dm_cell(dm.get((*key, 'squared')))}; {_dm_cell(dm.get((*key, 'absolute')))}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "",
        "| Model | Method | Window | Normal 80% | Normal 95% | t 80% | t 95% |",
        "|---|---|---|---|---|---|---|",
    ]
    coverage = {(c["model_id"], c["method"], c["window"], c["distribution"], c["level"]): c for c in evaluation["coverage"]}
    levels = evaluation["interval_levels"]
    for row in evaluation["metrics"]:
        if kinds[row["method"]] != "one_step":
            continue
        key = (row["model_id"], row["method"], row["window"])
        cells = [row["model_id"], METHOD_NAMES[row["method"]], row["window"]]
        for dist in ("normal", "t"):
            for level in levels:
                c = coverage[(*key, dist, level)]
                cells.append(f"{c['rate']:.4f} {VERDICT_WORDS.get(c['verdict'], c['verdict'])}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # no options
    try:
        evaluation = read_artifact(find_app_data(Path(__file__).resolve().parent), "evaluation")["data"]
    except ArtifactError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(render(evaluation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
