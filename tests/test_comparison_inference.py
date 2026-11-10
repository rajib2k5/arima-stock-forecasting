"""tools/comparison_inference.py: the frozen plan's hash, the family, the gate, the verdicts, the null
controls and the order the tool runs them in (docs/validation/m5-preregistration.md), and the same for
plan v2 (docs/validation/m5-preregistration-v2.md): its pin, the GARCH series, the size cells, the family
rows and the run order.

Made-up files only: a three-day window worked by hand for the gate, and seeded made-up price paths for
the controls and the run itself, whose evaluation numbers come from milestone 4's evaluation.py (the
producer of the real evaluation.json), never from the tool. The real data is never read.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from arima_forecasting.block_inference import bootstrap_p, c2_block_length, ewc_test, holm
from arima_forecasting.evaluation import dm_test, mae, random_walk_forecasts, rmse
from arima_forecasting.forecasting import artifact_name

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "comparison_inference.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("comparison_inference", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # the tool's dataclass looks its module up there
    spec.loader.exec_module(module)
    return module


tool = load_tool()
FORECASTS = tool.FAMILY_FORECASTS
WINDOWS = ("test", "oos")
LOSSES = ("squared", "absolute")


# --- the plan and the family ----------------------------------------------------------------------------


def test_the_frozen_plan_is_accepted_and_a_changed_one_refused(tmp_path):
    # The hash the plan was committed with (3cecee2), as the task that froze it states it.
    assert tool.SPEC_SHA256 == "4a7e509014a412a06aa4ba5b41fb2479cb77d339f2000f77ae2b3d62f4f275db"
    assert tool.check_spec(tool.SPEC) == tool.SPEC_SHA256
    changed = tmp_path / "plan.md"
    changed.write_bytes(tool.SPEC.read_bytes() + b" ")
    with pytest.raises(tool.SpecMismatch, match="refuses to run"):
        tool.check_spec(changed)
    with pytest.raises(tool.SpecMismatch, match="does not exist"):
        tool.check_spec(tmp_path / "missing.md")


def test_the_tool_refuses_to_run_on_a_changed_plan_and_writes_nothing(tmp_path, monkeypatch, capsys):
    changed = tmp_path / "plan.md"
    changed.write_bytes(tool.SPEC.read_bytes().replace(b"B = 19,999", b"B = 9,999"))
    monkeypatch.setattr(tool, "SPEC", changed)
    monkeypatch.setattr(tool, "OUT_JSON", tmp_path / "out.json")
    monkeypatch.setattr(tool, "OUT_MD", tmp_path / "out.md")
    monkeypatch.setattr(tool, "load", lambda folder: pytest.fail("the data must not be read"))
    assert tool.main([]) == 1
    assert "refuses to run" in capsys.readouterr().err
    assert not (tmp_path / "out.json").exists() and not (tmp_path / "out.md").exists()


def test_the_family_is_the_plans_28_in_its_order():
    # Forecasts, then windows, then losses; the seed is 20261109 + the index.
    fam = tool.family()
    assert len(fam) == 28 and [c.index for c in fam] == list(range(28))
    first = [(c.model_id, c.method, c.window, c.loss) for c in fam[:8]]
    assert first == [
        ("aic", "static", "test", "squared"),
        ("aic", "static", "test", "absolute"),
        ("aic", "static", "oos", "squared"),
        ("aic", "static", "oos", "absolute"),
        ("aic", "walk_forward", "test", "squared"),
        ("aic", "walk_forward", "test", "absolute"),
        ("aic", "walk_forward", "oos", "squared"),
        ("aic", "walk_forward", "oos", "absolute"),
    ]
    assert (fam[8].method, fam[12].model_id, fam[20].model_id, fam[27].model_id, fam[27].method) == ("refit", "bic", "course", "course", "walk_forward")
    assert [c.seed for c in (fam[0], fam[6], fam[27])] == [20261109, 20261115, 20261136]


# --- the gate, on a three-day window worked by hand -----------------------------------------------------

# Origin 1.0; actuals 1.5, 1.0, 1.25 (all exact in binary).
# One step: the model says 1.25, 1.5, 1.0 and the random walk 1.0, 1.5, 1.0 (the day before).
#   Errors: model 0.25, -0.5, 0.25; random walk 0.5, -0.5, 0.25.
#   Squared d: 0.0625 - 0.25, 0, 0 -> mean -0.0625. Absolute d: 0.25 - 0.5, 0, 0 -> mean -1/12.
# Static: the model says 1.25 every day, the random walk 1.0 (the origin).
#   Model errors 0.25, -0.25, 0: RMSE sqrt(0.125 / 3) = 0.2041241452319315, MAE 0.5 / 3.
#   Random-walk errors 0.5, 0, 0.25: RMSE sqrt(0.3125 / 3) = 0.3227486121839514, MAE 0.75 / 3 = 0.25.
ACTUAL = [1.5, 1.0, 1.25]
ONE_STEP = [1.25, 1.5, 1.0]
STATIC = [1.25, 1.25, 1.25]


def tiny_files(one_step=ONE_STEP, mean_diff=(-0.0625, -1 / 12)):
    def window(wid, mean):
        rows = [{"actual_log": a, "actual_usd": math.exp(a), "mean_log": m} for a, m in zip(ACTUAL, mean)]
        return {"id": wid, "origin": {"log_close": 1.0, "close_usd": math.e}, "rows": rows}

    forecasts = {artifact_name(m, method): {"windows": [window(w, STATIC if method == "static" else one_step) for w in WINDOWS]} for m, method in FORECASTS}
    evaluation = {
        "dm": [
            {"model_id": m, "method": method, "window": w, "loss": lo, "n": 3, "mean_diff": mean_diff[i]}
            for m, method in FORECASTS
            if method != "static"
            for w in WINDOWS
            for i, lo in enumerate(LOSSES)
        ],
        "metrics": [{"model_id": m, "method": "static", "window": w, "log": {"rmse": 0.2041241452319315, "mae": 0.5 / 3}} for m, method in FORECASTS if method == "static" for w in WINDOWS],
        "random_walk": [{"kind": "multi_step", "window": w, "log": {"rmse": 0.3227486121839514, "mae": 0.25}} for w in WINDOWS],
    }
    return forecasts, evaluation


def test_the_gate_passes_on_files_that_agree():
    forecasts, evaluation = tiny_files()
    g = tool.gate(forecasts, evaluation, tool.family())
    assert g["passed"] and g["self_check_passed"]
    assert len(g["checks"]) == 16 * 2 + 12 and len(g["self_checks"]) == 12  # n and mean_diff; RMSE or MAE
    assert g["max_relative_error"] < 1e-15


def test_the_gate_tolerance_is_1e_12_relative_and_1e_18_absolute_near_zero():
    forecasts, evaluation = tiny_files()
    evaluation["dm"][0]["mean_diff"] = -0.0625 * (1 + 5e-13)
    assert tool.gate(forecasts, evaluation, tool.family())["passed"]
    evaluation["dm"][0]["mean_diff"] = -0.0625 * (1 + 2e-12)
    assert not tool.gate(forecasts, evaluation, tool.family())["passed"]
    # The model's one-step forecast is the random walk's, so d = 0: 5e-19 off passes, 2e-18 does not.
    forecasts, evaluation = tiny_files(one_step=[1.0, 1.5, 1.0], mean_diff=(5e-19, 0.0))
    assert tool.gate(forecasts, evaluation, tool.family())["passed"]
    forecasts, evaluation = tiny_files(one_step=[1.0, 1.5, 1.0], mean_diff=(2e-18, 0.0))
    assert not tool.gate(forecasts, evaluation, tool.family())["passed"]


def test_the_gate_wants_n_exactly_the_static_metrics_and_every_row():
    forecasts, evaluation = tiny_files()
    evaluation["dm"][3]["n"] = 4
    g = tool.gate(forecasts, evaluation, tool.family())
    assert not g["passed"] and [ch["quantity"] for ch in g["checks"] if not ch["ok"]] == ["dm.n"]
    forecasts, evaluation = tiny_files()
    evaluation["metrics"][5]["log"]["mae"] *= 1 + 1e-11
    g = tool.gate(forecasts, evaluation, tool.family())
    assert not g["passed"] and [ch["quantity"] for ch in g["checks"] if not ch["ok"]] == ["metrics.log.mae"]
    forecasts, evaluation = tiny_files()
    del evaluation["dm"][7]
    g = tool.gate(forecasts, evaluation, tool.family())
    assert not g["passed"] and g["missing"] == [11]  # dm row 7 is aic refit oos absolute: index 2 x 4 + 3


def test_the_self_check_reads_the_static_random_walk():
    forecasts, evaluation = tiny_files()
    evaluation["random_walk"][1]["log"]["rmse"] = 0.3227486121839514 * (1 + 1e-11)  # oos
    g = tool.gate(forecasts, evaluation, tool.family())
    assert g["passed"] and not g["self_check_passed"]
    assert sorted(ch["index"] for ch in g["self_checks"] if not ch["ok"]) == [2, 14, 22]  # the three static oos squared


# --- the decision ---------------------------------------------------------------------------------------


def test_the_verdict_rule():
    assert tool.verdict(False, 0.01, 1e-5) == "worse_than_rw"  # positive: the model's loss is higher
    assert tool.verdict(False, 0.01, -1e-5) == "beats_rw"
    assert tool.verdict(False, 0.05, 1e-5) == "no_difference_detected"  # rejection needs p < alpha
    assert tool.verdict(True, 0.0, 1e-5) == "unresolved"


def test_holm_runs_over_all_rows_with_an_unresolved_one_entering_at_1():
    # Entries 0.01, 1, 0.02: sorted 0.01 x 3 = 0.03, 0.02 x 2 = 0.04, 1 x 1 = 1.
    rows = [
        {"p_raw": 0.01, "unresolved": False, "mean_diff": 2.0},
        {"p_raw": None, "unresolved": True, "mean_diff": 2.0},
        {"p_raw": 0.02, "unresolved": False, "mean_diff": -2.0},
    ]
    tool.decide(rows)
    assert [r["p_entry"] for r in rows] == [0.01, 1.0, 0.02]
    assert [r["p_holm"] for r in rows] == pytest.approx([0.03, 1.0, 0.04], rel=1e-15)
    assert [r["verdict"] for r in rows] == ["worse_than_rw", "unresolved", "beats_rw"]


def test_an_unresolved_series_gets_no_primary_p():
    # n = 40, L = 10: a constant series has no ACF, so b = L + 1 = 11 and 40 // 11 = 3 blocks < 8.
    row = tool.analyse(np.full(40, 0.25), seed=1, replicates=99)
    assert (row["b"], row["blocks"], row["unresolved"], row["p_raw"], row["mde"]) == (11, 3, True, None, None)
    assert row["newey_west"] == {"lag": 10, "t": None, "p": None}
    # The sensitivity runs still report: d is 0.25 every day, so no centred replicate's mean (0) is as far
    # from 0 as 0.25, and p = 1 / (99 + 1) at both block lengths.
    assert [(s["b"], s["blocks"], s["below_floor"], s["p"]) for s in row["sensitivity"]] == [(22, 1, True, 0.01), (1, 40, False, 0.01)]


def test_a_resolved_series_draws_the_primary_then_2b_then_1_from_its_seed():
    # One generator per comparison, default_rng(seed): the primary bootstrap's draws come first, then
    # the sensitivity at 2b, then at b = 1. A made-up series with a small mean, so the p-values depend on the draws.
    d = np.random.default_rng(5).normal(0.15, 1.0, 120)
    row = tool.analyse(d, seed=20261109, replicates=199)
    b = row["b"]
    assert not row["unresolved"] and row["blocks"] == 120 // b
    rng = np.random.default_rng(20261109)
    primary, means = bootstrap_p(d, b, 199, rng)
    double, _ = bootstrap_p(d, 2 * b, 199, rng)
    single, _ = bootstrap_p(d, 1, 199, rng)
    assert 0.01 < primary < 0.99  # not a boundary value that any draws would give
    assert row["p_raw"] == primary and row["mde"] == pytest.approx(2.8 * np.std(means), rel=1e-15)
    assert [(s["b"], s["p"]) for s in row["sensitivity"]] == [(2 * b, double), (1, single)]
    assert row["newey_west"]["lag"] == b - 1


# --- null controls, on made-up price paths ---------------------------------------------------------------


def made_up_files(n=120, seed=11):
    """Seeded made-up log prices for both windows; walk-forward forecasts near the day before, static paths
    drifting from the origin. The evaluation is built with milestone 4's functions, as the real one was."""
    rng = np.random.default_rng(seed)
    base, origin = {}, 5.0
    for wid in WINDOWS:
        actual = origin + np.cumsum(rng.normal(0.0, 0.01, n))
        base[wid], origin = (origin, actual), float(actual[-1])
    forecasts = {}
    for i, (m, method) in enumerate(FORECASTS):
        windows = []
        for wid in WINDOWS:
            o, actual = base[wid]
            if method == "static":
                mean = o + 0.0005 * (i + 1) * np.arange(1, n + 1)
            else:
                mean = np.concatenate([[o], actual[:-1]]) + rng.normal(0.0, 0.002, n)
            rows = [{"actual_log": float(a), "actual_usd": math.exp(a), "mean_log": float(f)} for a, f in zip(actual, mean)]
            windows.append({"id": wid, "origin": {"log_close": o, "close_usd": math.exp(o)}, "rows": rows})
        forecasts[artifact_name(m, method)] = {"windows": windows}
    dm, metrics, rw = [], [], []
    for w in forecasts[artifact_name("aic", "static")]["windows"]:
        actual = [r["actual_log"] for r in w["rows"]]
        static_rw, _ = random_walk_forecasts(w, "multi_step")
        rw.append({"kind": "multi_step", "window": w["id"], "log": {"rmse": rmse(actual, static_rw), "mae": mae(actual, static_rw)}})
    for m, method in FORECASTS:
        for w in forecasts[artifact_name(m, method)]["windows"]:
            actual = np.array([r["actual_log"] for r in w["rows"]])
            mean = np.array([r["mean_log"] for r in w["rows"]])
            metrics.append({"model_id": m, "method": method, "window": w["id"], "log": {"rmse": rmse(actual, mean), "mae": mae(actual, mean)}})
            if method != "static":
                one_rw, _ = random_walk_forecasts(w, "one_step")
                dm += [{"model_id": m, "method": method, "window": w["id"], **dm_test(actual - mean, actual - one_rw, lo)} for lo in LOSSES]
    return forecasts, {"dm": dm, "metrics": metrics, "random_walk": rw}


def test_the_identical_forecast_control_gives_p_1_everywhere():
    forecasts, _ = made_up_files()
    result = tool.control_identical(forecasts, tool.family(), replicates=99)
    assert result["passed"]
    assert len(result["rows"]) == 28
    assert all(r["mean_diff"] == 0.0 and r["p_entry"] == 1.0 and r["p_holm"] == 1.0 for r in result["rows"])
    assert all(s["p"] == 1.0 for r in result["rows"] for s in r["sensitivity"])


def test_the_shifted_control_rejects_both_losses():
    # 999 replicates: the smallest p is 1 / 1000, and 28 x 0.001 = 0.028 < 0.05.
    forecasts, _ = made_up_files()
    result = tool.control_shift(forecasts, tool.family(), replicates=999)
    assert result["passed"] and result["k"] == 28
    assert [(r["index"], r["loss"]) for r in result["rows"]] == [(6, "squared"), (7, "absolute")]
    for r in result["rows"]:
        assert r["mean_diff"] > 0 and r["p_raw"] == 1 / 1000 and r["holm_bound"] == pytest.approx(0.028, rel=1e-12) and r["rejected"]


def test_the_ar1_simulator_has_the_stated_mean_variance_and_autocorrelation():
    # Stationary AR(1), rho = 0.3, unit shocks: variance 1 / (1 - 0.09) = 1.0989, lag-1 correlation 0.3.
    x = tool.ar1(np.random.default_rng(2), 4, 50_000, 0.3)
    assert x.shape == (4, 50_000)
    flat = x.ravel()
    assert abs(flat.mean()) < 0.02
    assert flat.var() == pytest.approx(1 / 0.91, rel=0.02)
    lag1 = np.mean([np.corrcoef(row[:-1], row[1:])[0, 1] for row in x])
    assert lag1 == pytest.approx(0.3, abs=0.01)
    assert np.var(x[:, 0]) > 0.5  # started from the stationary law, not from 0


def test_the_rejection_rate_counts_rejections_and_unresolved_series():
    rng = np.random.default_rng(4)
    shifted = 5.0 + rng.normal(0.0, 0.01, (10, 60))  # made-up: far from mean 0, so every one is rejected
    run = tool.rejection_rate(shifted, np.random.default_rng(0), 99)
    assert (run["series"], run["rejected"], run["rate"], run["unresolved"]) == (10, 10, 1.0, 0)
    constant = np.zeros((6, 60))  # no ACF: b = L + 1 = 16, 60 // 16 = 3 blocks: UNRESOLVED, not rejected
    run = tool.rejection_rate(constant, np.random.default_rng(0), 99)
    assert (run["rejected"], run["rate"], run["unresolved"], run["b_counts"]) == (0, 0.0, 6, {"16": 6})
    run = tool.rejection_rate(constant, np.random.default_rng(0), 99, force_b=1)
    assert (run["rejected"], run["unresolved"], run["b_counts"]) == (0, 0, {"1": 6})


@pytest.mark.parametrize(
    ("iid", "ar1", "ar1_b1", "passed"),
    [
        (0.03, 0.08, 0.20, True),  # both ends of [3%, 8%] are inside; the b = 1 run is not decisive
        (0.05, 0.0805, 0.05, False),  # AR(1) just above the band
        (0.0295, 0.05, 0.05, False),  # i.i.d. just below it
    ],
)
def test_the_size_control_passes_only_with_both_decisive_rates_in_the_band(monkeypatch, iid, ar1, ar1_b1, passed):
    rates = iter([iid, ar1, ar1_b1])  # control_size runs i.i.d., then AR(1), then AR(1) with b = 1
    monkeypatch.setattr(tool, "rejection_rate", lambda *a, **k: {"rate": next(rates)})
    result = tool.control_size(count=3, n=20, replicates=9)
    assert result["passed"] is passed
    assert [result["runs"][k]["decisive"] for k in ("iid", "ar1", "ar1_b1")] == [True, True, False]


# --- the tool's order: gate, controls, family, runs -----------------------------------------------------


@pytest.fixture
def made_up_tool(tmp_path, monkeypatch):
    forecasts, evaluation = made_up_files()
    monkeypatch.setattr(tool, "load", lambda folder: (forecasts, evaluation, {"made_up.json": "0" * 64}))
    monkeypatch.setattr(tool, "OUT_JSON", tmp_path / "out.json")
    monkeypatch.setattr(tool, "OUT_MD", tmp_path / "out.md")
    real_size = tool.control_size
    monkeypatch.setattr(tool, "control_size", lambda: {**real_size(count=40, n=60, replicates=99), "passed": True})
    return tmp_path, evaluation


def test_the_tool_runs_the_family_after_the_controls_and_lists_every_run(made_up_tool, capsys):
    folder, _ = made_up_tool
    assert tool.main(["--controls-only"]) == 0
    assert not (folder / "out.json").exists()  # controls only: nothing written
    assert tool.main([]) == 0
    first = json.loads((folder / "out.json").read_text(encoding="utf-8"))
    assert first["spec"]["sha256"] == tool.SPEC_SHA256 and first["gate"]["passed"] and first["null_controls"]["passed"]
    assert len(first["comparisons"]) == 28 and all(r["verdict"] in tool.VERDICTS for r in first["comparisons"])
    assert [r["change"] for r in first["runs"]] == ["first run"]
    assert tool.main(["--change", "fixed a made-up bug"]) == 0
    second = json.loads((folder / "out.json").read_text(encoding="utf-8"))
    assert [r["change"] for r in second["runs"]] == ["first run", "fixed a made-up bug"]
    assert second["runs"][0] == first["runs"][0] and second["runs"][1]["primary_digest"] == first["runs"][0]["primary_digest"]
    md = (folder / "out.md").read_text(encoding="utf-8")
    assert tool.LABEL in md and "not a fresh holdout" in md
    table = md.split("## The 28 comparisons", 1)[1].split("\n## ", 1)[0]
    assert [line.split(" | ")[0] for line in table.splitlines() if line[:3].strip("| ").isdigit()] == [f"| {i}" for i in range(28)]
    runs = md.split("## Runs", 1)[1].split("\n## ", 1)[0]
    assert "| 1 | " in runs and "| 2 | " in runs and "fixed a made-up bug" in runs


def test_the_family_does_not_run_when_a_null_control_fails(made_up_tool, monkeypatch, capsys):
    folder, _ = made_up_tool
    monkeypatch.setattr(tool, "control_shift", lambda forecasts, comparisons: {"passed": False, "shift": 0.02, "k": 28, "rows": []})
    monkeypatch.setattr(tool, "run_family", lambda *a, **k: pytest.fail("the family must not run"))
    assert tool.main([]) == 1
    out = json.loads((folder / "out.json").read_text(encoding="utf-8"))
    assert out["comparisons"] is None and not out["null_controls"]["passed"] and out["runs"] == []
    assert "**Not run.**" in (folder / "out.md").read_text(encoding="utf-8")


def test_nothing_runs_or_is_written_when_the_gate_fails(made_up_tool, monkeypatch, capsys):
    folder, evaluation = made_up_tool
    evaluation["dm"][0]["mean_diff"] *= 1 + 1e-9
    monkeypatch.setattr(tool, "controls", lambda *a: pytest.fail("the controls must not run"))
    assert tool.main([]) == 1
    assert "the gate failed" in capsys.readouterr().err
    assert not (folder / "out.json").exists() and not (folder / "out.md").exists()



# --- plan v2 --------------------------------------------------------------------------------------------


def test_the_v2_plan_is_pinned_beside_v1_and_a_changed_one_stops_the_run(tmp_path, monkeypatch, capsys):
    # The hash plan v2 was frozen with, as the task that froze it states it; v1's pin stays as it was.
    assert tool.SPEC_V2_SHA256 == "39569d5cb6182cd55b55b7fada2bd937ef3aa784e02255486a255fa18ccef44d"
    assert tool.check_spec(tool.SPEC_V2, tool.SPEC_V2_SHA256) == tool.SPEC_V2_SHA256
    assert tool.SPEC_SHA256 == "4a7e509014a412a06aa4ba5b41fb2479cb77d339f2000f77ae2b3d62f4f275db"
    changed = tmp_path / "plan-v2.md"
    changed.write_bytes(tool.SPEC_V2.read_bytes().replace(b"14 for n = 227", b"15 for n = 227"))
    monkeypatch.setattr(tool, "SPEC_V2", changed)
    for name in ("OUT_JSON", "OUT_MD", "OUT_JSON_V2", "OUT_MD_V2"):
        monkeypatch.setattr(tool, name, tmp_path / f"{name}.out")
    monkeypatch.setattr(tool, "load", lambda folder: pytest.fail("the data must not be read"))
    assert tool.main(["--plan", "v2"]) == 1
    assert "refuses to run" in capsys.readouterr().err
    assert list(tmp_path.glob("*.out")) == []


def test_the_dm_hln_p_is_milestone_4s_on_the_differential():
    # Made-up errors; milestone 4's dm_test (the producer of evaluation.json's p-values) is the reference.
    rng = np.random.default_rng(6)
    e_rw = rng.normal(0.0, 0.01, 50)
    e_model = e_rw + rng.normal(0.001, 0.004, 50)
    for lo in LOSSES:
        d = tool.differential(e_model, e_rw, lo)
        assert tool.dm_hln_p(d) == pytest.approx(dm_test(e_model, e_rw, lo)["p_value"], rel=1e-12)
    assert tool.dm_hln_p(np.zeros(50)) is None


def test_the_garch_recursion_by_hand():
    # omega = 0.017^2 (1 - 0.08 - 0.90) = 5.78e-6, h_0 = 0.017^2 = 0.000289.
    # Shocks 2, 1: r_0 = 0.017 (2) = 0.034; h_1 = 5.78e-6 + 0.08 (0.034^2) + 0.90 (0.000289)
    # = 5.78e-6 + 9.248e-5 + 2.601e-4 = 3.5836e-4, so r_1 = sqrt(3.5836e-4) = 0.018930398833622075.
    # Shocks 1, -1: r_0^2 = h_0, so h_1 = omega + 0.98 h_0 = h_0 and r_1 = -0.017.
    r = tool.garch_filter([[2.0, 1.0], [1.0, -1.0]])
    assert r == pytest.approx(np.array([[0.034, 0.018930398833622075], [0.017, -0.017]]), rel=1e-12)


def test_the_garch_loss_differentials_by_hand():
    # Returns 0.01, -0.02, 0.03. Day 1: forecast 0.02 (0.01) + 0.0009 = 0.0011, e_model = -0.0211, e_rw = -0.02:
    # squared 0.00044521 - 0.0004 = 4.521e-5, absolute 0.0211 - 0.02 = 0.0011. Day 2: forecast 0.02 (-0.02)
    # + 0.0009 = 0.0005, e_model = 0.0295, e_rw = 0.03: squared 0.00087025 - 0.0009 = -2.975e-5, absolute -0.0005.
    d_sq, d_abs = tool.garch_differentials(np.array([0.01, -0.02, 0.03]))
    assert d_sq == pytest.approx([4.521e-5, -2.975e-5], rel=1e-9)
    assert d_abs == pytest.approx([0.0011, -0.0005], rel=1e-9)


def test_the_garch_returns_have_the_stated_variance():
    # Unit-variance shocks keep the unconditional variance at 0.017^2 = 0.000289. Made-up seed; the t(4)
    # shocks without the 1/sqrt(2) scale would give alpha (2) + beta = 1.06 > 1, a path with no finite variance.
    r = tool.garch_returns(np.random.default_rng(8), 400, 1000)
    assert r.shape == (400, 1000)
    assert float(np.mean(r**2)) == pytest.approx(0.017**2, rel=0.1)


def test_the_size_rates_count_each_tests_rejections():
    rng = np.random.default_rng(0)
    shifted = 5.0 + rng.normal(0.0, 0.01, (3, 60))  # made-up, far from mean 0 (C2 blocks 4, 3, 1): every test rejects
    zero = np.zeros((2, 60))  # EWC p = 1; C2 b = 1 and every replicate mean is 0, p = 1; DM-HLN undefined
    constant = np.full((1, 60), 0.25)  # EWC UNRESOLVED; C2 b = 1 gives p = 1 / (99 + 1): rejected; DM-HLN undefined
    run = tool.size_rates(np.vstack([shifted, zero, constant]), np.random.default_rng(0), 99)
    assert run["series"] == 6
    assert run["ewc"] == {"rejected": 3, "rate": 0.5, "unresolved": 1}
    assert (run["c2"]["rejected"], run["c2"]["unresolved"]) == (4, 0)
    assert run["dm_hln"] == {"rejected": 3, "rate": 0.5}


def test_the_v2_size_control_needs_every_cell_in_the_band():
    def cells(*rates):
        return [{"ewc": {"rate": rate}} for rate in rates]

    assert tool.size_v2_passed(cells(0.03, 0.08, 0.05))  # both ends of [3%, 8%] are inside
    assert not tool.size_v2_passed(cells(0.05, 0.0805, 0.05))
    assert not tool.size_v2_passed(cells(0.05, 0.05, 0.0295))
    assert not tool.size_v2_passed([])


def test_the_v2_size_cells_their_order_and_their_seeds(monkeypatch):
    # Cell c draws its series from default_rng(20261301 + c) and its bootstrap starts from default_rng(20261311 + c);
    # the GARCH centring path uses default_rng(20261321). n = 227 first; the processes in the plan's order.
    seen = []
    real_centres = tool.garch_centres
    monkeypatch.setattr(tool, "garch_centres", lambda rng, days: seen.append(("centres", rng.bit_generator.state)) or real_centres(rng, days))
    monkeypatch.setattr(tool, "size_rates", lambda series, rng, replicates: seen.append((series.copy(), rng.bit_generator.state)) or {"ewc": {"rate": 0.05}})
    result = tool.control_size_v2(count=3, replicates=9, centre_days=500)
    assert [(c["n"], c["process"]) for c in result["cells"]] == [(n, p) for n in (227, 689) for p in ("iid", "ar03", "ar05", "garch_sq", "garch_abs")]
    assert seen[0] == ("centres", np.random.default_rng(20261321).bit_generator.state)
    for c, (series, state) in enumerate(seen[1:]):
        n, process = result["cells"][c]["n"], result["cells"][c]["process"]
        expected = tool.null_series_v2(process, n, 3, np.random.default_rng(20261301 + c), result["centres"])
        assert np.array_equal(series, expected) and series.shape == (3, n)
        assert state == np.random.default_rng(20261311 + c).bit_generator.state
    assert result["passed"]


def test_the_v2_static_rows_have_no_test_and_enter_holm_at_1():
    forecasts, evaluation = made_up_files()
    rows = tool.run_family_v2(forecasts, evaluation, tool.family(), replicates=99)
    static = [r for r in rows if r["method"] == "static"]
    assert len(static) == 12
    for r in static:
        assert (r["kind"], r["unresolved"], r["p_raw"], r["p_entry"], r["verdict"]) == ("static", True, None, 1.0, "unresolved")
        assert (r["nu"], r["t"], r["mde"], r["c2"], r["dm_hln_p"]) == (None, None, None, None, None)
        assert r["n"] == 120 and r["reason"] == tool.STATIC_REASON


def test_the_v2_one_step_rows_have_ewc_the_c2_bootstrap_and_the_dm_p():
    forecasts, evaluation = made_up_files()
    fam = tool.family()
    rows = tool.run_family_v2(forecasts, evaluation, fam, replicates=99)
    dm = {(r["model_id"], r["method"], r["window"], r["loss"]): r["p_value"] for r in evaluation["dm"]}
    one_step = [(c, r) for c, r in zip(fam, rows) if r["method"] != "static"]
    assert len(one_step) == 16
    for c, r in one_step:
        d = tool.differential(*tool.errors(forecasts, c), c.loss)
        primary = ewc_test(d)
        assert (r["nu"], r["t"], r["p_raw"], r["mde"]) == (9, primary["t"], primary["p"], primary["mde"])  # nu(120) = 9
        b = c2_block_length(d)[0]
        assert r["c2"]["b"] == b and r["c2"]["p"] == bootstrap_p(d, b, 99, np.random.default_rng(20261109 + c.index))[0]
        assert r["dm_hln_p"] == dm[(c.model_id, c.method, c.window, c.loss)]
    entries = [1.0 if r["p_raw"] is None else r["p_raw"] for r in rows]
    assert [r["p_holm"] for r in rows] == pytest.approx(list(holm(entries)), rel=1e-15)


def test_the_v2_identical_forecast_control_gives_p_1_everywhere():
    forecasts, _ = made_up_files()
    result = tool.control_identical_v2(forecasts, tool.family())
    assert result["passed"] and len(result["rows"]) == 28
    assert all(r["mean_diff"] == 0.0 and r["p_entry"] == 1.0 and r["p_holm"] == 1.0 for r in result["rows"])
    assert all(r["p_raw"] == 1.0 and r["omega"] == 0.0 for r in result["rows"] if r["kind"] == "one_step")


def test_the_v2_shifted_control_rejects_both_losses():
    forecasts, _ = made_up_files()
    result = tool.control_shift_v2(forecasts, tool.family())
    assert result["passed"] and result["k"] == 28
    assert [(r["index"], r["loss"]) for r in result["rows"]] == [(6, "squared"), (7, "absolute")]
    for r in result["rows"]:
        assert r["mean_diff"] > 0 and r["holm_bound"] == pytest.approx(28 * r["p_raw"], rel=1e-15) and r["holm_bound"] < 0.05 and r["rejected"]


@pytest.fixture
def made_up_tool_v2(tmp_path, monkeypatch):
    forecasts, evaluation = made_up_files()
    monkeypatch.setattr(tool, "load", lambda folder: (forecasts, evaluation, {"made_up.json": "0" * 64}))
    for name in ("OUT_JSON", "OUT_MD", "OUT_JSON_V2", "OUT_MD_V2"):
        monkeypatch.setattr(tool, name, tmp_path / f"{name.lower()}.out")
    real_size = tool.control_size_v2
    monkeypatch.setattr(tool, "control_size_v2", lambda: {**real_size(count=20, replicates=99, centre_days=2000), "passed": True})
    return tmp_path


def test_the_v2_tool_runs_the_family_after_the_controls_and_lists_every_run(made_up_tool_v2):
    folder = made_up_tool_v2
    assert tool.main(["--plan", "v2", "--controls-only"]) == 0
    assert list(folder.glob("*.out")) == []  # controls only: nothing written
    assert tool.main(["--plan", "v2"]) == 0
    assert sorted(f.name for f in folder.glob("*.out")) == ["out_json_v2.out", "out_md_v2.out"]  # never v1's outputs
    first = json.loads((folder / "out_json_v2.out").read_text(encoding="utf-8"))
    assert (first["plan"], first["spec"]["sha256"], first["spec_v1"]["sha256"]) == ("v2", tool.SPEC_V2_SHA256, tool.SPEC_SHA256)
    assert first["family_computed"] and first["gate"]["passed"] and len(first["comparisons"]) == 28
    assert [(r["change"], r["outcome"]) for r in first["runs"]] == [("first run", "family computed")]
    assert tool.main(["--plan", "v2", "--change", "fixed a made-up bug"]) == 0
    second = json.loads((folder / "out_json_v2.out").read_text(encoding="utf-8"))
    assert [r["change"] for r in second["runs"]] == ["first run", "fixed a made-up bug"]
    assert second["runs"][0] == first["runs"][0] and second["runs"][1]["primary_digest"] == first["runs"][0]["primary_digest"]
    md = (folder / "out_md_v2.out").read_text(encoding="utf-8")
    assert tool.LABEL in md and "not a fresh holdout" in md and "## Why there is a version 2" in md
    table = md.split("## The 28 comparisons", 1)[1].split("\n## ", 1)[0]
    assert [line.split(" | ")[0] for line in table.splitlines() if line[:3].strip("| ").isdigit()] == [f"| {i}" for i in range(28)]
    runs = md.split("## Runs", 1)[1].split("\n## ", 1)[0]
    assert "| 1 | " in runs and "| 2 | " in runs and "fixed a made-up bug" in runs


def test_the_v2_family_is_not_computed_when_a_control_fails(made_up_tool_v2, monkeypatch):
    folder = made_up_tool_v2
    monkeypatch.setattr(tool, "control_shift_v2", lambda forecasts, comparisons: {"passed": False, "shift": 0.02, "k": 28, "rows": []})
    monkeypatch.setattr(tool, "run_family_v2", lambda *a, **k: pytest.fail("the family must not run"))
    assert tool.main(["--plan", "v2"]) == 1
    out = json.loads((folder / "out_json_v2.out").read_text(encoding="utf-8"))
    assert not out["family_computed"] and not out["null_controls"]["passed"]
    assert len(out["comparisons"]) == 28 and all(r["verdict"] == "unresolved" and r["p_raw"] is None and "shifted" in r["reason"] for r in out["comparisons"])
    assert [r["outcome"] for r in out["runs"]] == ["control failed: shifted"]
    assert "**No result.**" in (folder / "out_md_v2.out").read_text(encoding="utf-8")


def test_the_v2_report_lists_the_surviving_claims_and_each_mde(made_up_tool_v2):
    folder = made_up_tool_v2
    assert tool.main(["--plan", "v2"]) == 0
    result = json.loads((folder / "out_json_v2.out").read_text(encoding="utf-8"))
    rows = result["comparisons"]
    rows[4]["verdict"] = "worse_than_rw"  # made-up: one claim, to see where the report puts it
    md = tool.render_md_v2(result)
    claims = md.split("These claims survive Holm's correction:", 1)[1].split("\n## ", 1)[0]
    assert "aic walk-forward, test, squared: the model is worse" in claims and claims.count("- ") == 1
    mdes = md.split("## Minimum detectable effects", 1)[1].split("\n## ", 1)[0]
    quiet = [r for r in rows if r["verdict"] == "no_difference_detected"]
    assert quiet and all(f"MDE {r['mde']:.2e} {'squared log points' if r['loss'] == 'squared' else 'log points'}" in mdes for r in quiet)
    assert "In dollars: not given" in mdes
