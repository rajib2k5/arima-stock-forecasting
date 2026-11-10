"""Milestone 5: the pre-registered block-bootstrap inference on the 28 forecast comparisons.

Run:  uv run python tools/comparison_inference.py                    gate, null controls, then the family; writes both outputs
      uv run python tools/comparison_inference.py --controls-only    gate and null controls only; prints them, writes nothing
      uv run python tools/comparison_inference.py --change "TEXT"    a later family run: TEXT says what changed since the last one, and why
      uv run python tools/comparison_inference.py --plan v2          the same under plan v2 (below); --controls-only and --change work there too

The plan is docs/validation/m5-preregistration.md. It was frozen before any block-resampled statistic
was computed, and this tool pins its SHA-256 (SPEC_SHA256): if the file changes, the tool refuses to
run. A new plan needs a new file, and a new tool constant.

It reads the committed files in app/public/data/ (the seven forecast files and evaluation.json; never
the raw snapshot) and runs the plan's steps in the plan's order:

1. The gate. The loss differentials built here must reproduce evaluation.json: n and mean_diff of the
   16 one-step comparisons, the log RMSE and MAE of the 12 static ones. A self-check sits beside it:
   the static random walk's log RMSE and MAE (`random_walk[]`). The plan's gate does not ask for it,
   but the static differentials use that random walk, so a miss is a bug here. If either fails,
   nothing else runs and nothing is written.
2. The null controls: identical forecasts, a shifted forecast, and the size simulation. If one fails,
   the family does not run; the outputs then hold the gate and the controls, and the tool exits 1.
3. The family: for each comparison the block length, the floor, the circular block bootstrap (the
   primary p), the Newey-West t, the sensitivity runs at 2b and b = 1, Holm over all 28, the verdict
   and the minimum detectable effect.

The statistics are src/arima_forecasting/block_inference.py's; this file only wires them to the data
and writes docs/validation/m5-comparison-inference.json and .md (the .md is for a human reader).

**Runs.** The plan's primary result is final. A bug fix may re-run the family; every family run is
listed in the outputs ("runs": the UTC time, the runtime, what changed and why, and a digest of the
primary results). A run reads the list from the JSON already on disk and appends itself, so the list
holds every run. The first run says "first run"; a later run takes its reason from --change.

**What the plan leaves open, fixed here before the first run (and never changed after it):**

- The block starts are drawn as rng.integers(0, n, size=(B, ceil(n / b))).
- One generator per comparison, default_rng(20261109 + index), used in this order: the primary
  bootstrap (b), then the sensitivity at 2b, then at b = 1. The primary's draws are the generator's
  first, so they do not depend on the sensitivity runs.
- The identical-forecast control sets every one of the 28 forecasts to its random walk, with that
  comparison's seed. The shifted control uses the shifted comparisons' own seeds (indices 6 and 7).
- "Rejected" in the shifted control: Holm's adjusted p of any comparison is at most k x its raw p,
  whatever the other p-values are. The control runs before the family, so a rejection is k x p < alpha.
- The size simulation draws its series and its bootstrap starts from default_rng([20261109, 1, process])
  and default_rng([20261109, 2, run]) (process 0 i.i.d., 1 AR(1); run 0 i.i.d., 1 AR(1), 2 AR(1) with
  b = 1), so its streams never coincide with a comparison's. The AR(1) starts from its stationary
  distribution, N(0, 1 / (1 - rho^2)), with N(0, 1) innovations. A rejection is a p below 0.05; an
  UNRESOLVED series counts as not rejected.

**Plan v2** (docs/validation/m5-preregistration-v2.md, pinned as SPEC_V2_SHA256; v1 stays pinned and its
outputs are never written by a v2 run) keeps the gate and the family, and changes the tests:

- The 12 static comparisons are UNRESOLVED by construction and enter Holm with p = 1. Their n and d̄ are
  still reported.
- The 16 one-step comparisons get the EWC t test (block_inference.ewc_test) as the primary test, rule C2's
  circular block bootstrap (B = 19,999, default_rng(20261109 + index)) and milestone 4's DM-HLN p
  (evaluation.json's dm[].p_value) as the two secondary results, which never change a verdict.
- The null controls run the primary test. Control 3 has 10 cells: n = 227 and 689, each with i.i.d.
  N(0, 1), AR(1) with rho = 0.3 and 0.5, and the GARCH loss differential under squared and absolute loss.
  The primary's rate must lie in [3%, 8%] in all 10 cells. The bootstrap (B = 999) and DM-HLN rates on the
  same series are reported only.
- If a control fails, the family is not computed: all 28 are UNRESOLVED and the reason is stated.
- Every v2 run that writes the outputs appends itself to their "runs" list.

**What plan v2 leaves open, fixed here before the first v2 run (and never changed after it):**

- Control seeds, all integers from 20261301: cell c = 0 ... 9 (n = 227 first, then 689; processes in the
  order i.i.d., AR(1) 0.3, AR(1) 0.5, GARCH squared, GARCH absolute) draws its series from
  default_rng(20261301 + c) and its bootstrap starts from default_rng(20261311 + c); the 10^6-day path
  that centres the GARCH differentials uses default_rng(20261321).
- The GARCH process is the design phase's: h_t = omega + 0.08 r_(t-1)^2 + 0.90 h_(t-1) with
  omega = 0.017^2 (1 - 0.98), so the unconditional sd is 0.017; t(4) shocks divided by sqrt(2) (unit
  variance); h_0 = 0.017^2; 500 days of burn-in dropped. A series of n differentials uses n + 1 returns
  r_0 ... r_n: the model's forecast of r_t is 0.02 r_(t-1) + 0.0009 and the random walk's is 0, so
  e_model = r_t - 0.02 r_(t-1) - 0.0009 and e_rw = r_t. Each loss's differential is centred by its mean
  over one 10^6-day path. With t(4) shocks the squared-loss differential has no finite variance.
- DM-HLN in control 3 is milestone 4's statistic applied to d_t directly (dm_hln_p).
- In control 1 the one-step comparisons must give p = 1 exactly (d = 0, so Omega = 0 and the mean is 0),
  and the static ones enter at 1 by construction.
- An UNRESOLVED or undefined test counts as not rejected in control 3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from scipy import stats

from arima_forecasting.artifacts import ArtifactError, read_artifact
from arima_forecasting.block_inference import (
    BAND_Z,
    C2_MULTIPLIER,
    MAX_ACF_LAG,
    MIN_BLOCKS,
    PW_C,
    PW_MIN_KN,
    RUN,
    Z_POWER,
    Z_TEST,
    below_floor,
    block_count,
    block_length,
    bootstrap_p,
    c2_block_length,
    ewc_test,
    holm,
    minimum_detectable_effect,
    newey_west_t,
)
from arima_forecasting.evaluation import hln_factor, loss, random_walk_forecasts
from arima_forecasting.forecasting import KINDS, artifact_name

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "docs" / "validation" / "m5-preregistration.md"
SPEC_SHA256 = "4a7e509014a412a06aa4ba5b41fb2479cb77d339f2000f77ae2b3d62f4f275db"
DATA = REPO / "app" / "public" / "data"
OUT_JSON = REPO / "docs" / "validation" / "m5-comparison-inference.json"
OUT_MD = REPO / "docs" / "validation" / "m5-comparison-inference.md"
SPEC_V2 = REPO / "docs" / "validation" / "m5-preregistration-v2.md"
SPEC_V2_SHA256 = "39569d5cb6182cd55b55b7fada2bd937ef3aa784e02255486a255fa18ccef44d"
OUT_JSON_V2 = REPO / "docs" / "validation" / "m5-comparison-inference-v2.json"
OUT_MD_V2 = REPO / "docs" / "validation" / "m5-comparison-inference-v2.md"

# The plan's settings. Never changed after the first family run.
REPLICATES = 19_999
SEED = 20261109
ALPHA = 0.05
GATE_REL, GATE_ABS = 1e-12, 1e-18
SHIFT = 0.02  # log points added to the shifted control's forecast
SHIFTED = ("aic", "walk_forward", "oos")
SIZE_SERIES, SIZE_N, SIZE_REPLICATES, SIZE_RHO = 2000, 227, 999, 0.3
SIZE_BAND = (0.03, 0.08)

# The family, in the plan's order: forecasts, then windows, then losses. Index i has seed SEED + i.
FAMILY_FORECASTS = (("aic", "static"), ("aic", "walk_forward"), ("aic", "refit"), ("bic", "static"), ("bic", "walk_forward"), ("course", "static"), ("course", "walk_forward"))
FAMILY_WINDOWS = ("test", "oos")
FAMILY_LOSSES = ("squared", "absolute")

LABEL = "The metric is the log forecast loss on AAPL's adjusted close. It is the project's stated forecast metric, not a trading P&L, and no stake depends on it."
VERDICTS = ("worse_than_rw", "beats_rw", "no_difference_detected", "unresolved")
VERDICT_WORDS = {"worse_than_rw": "model worse", "beats_rw": "model better", "no_difference_detected": "no difference detected", "unresolved": "UNRESOLVED"}
METHOD_NAMES = {"static": "static", "walk_forward": "walk-forward", "refit": "walk-forward, refit"}

# Plan v2's settings. Never changed after the first v2 run.
CONTROL_SEED = 20261301
V2_SIZE_NS = (227, 689)
V2_PROCESSES = ("iid", "ar03", "ar05", "garch_sq", "garch_abs")
V2_SIZE_SERIES, V2_SIZE_REPLICATES = 2000, 999
GARCH_ALPHA, GARCH_BETA, GARCH_DF, GARCH_SD = 0.08, 0.90, 4, 0.017
GARCH_OMEGA = GARCH_SD**2 * (1.0 - GARCH_ALPHA - GARCH_BETA)
GARCH_BURN, GARCH_CENTRE_DAYS = 500, 1_000_000
GARCH_PHI, GARCH_DRIFT = 0.02, 0.0009  # the GARCH model's forecast of r_t is GARCH_PHI r_(t-1) + GARCH_DRIFT
PROCESS_NAMES = {"iid": "i.i.d. N(0, 1)", "ar03": "AR(1), ρ = 0.3", "ar05": "AR(1), ρ = 0.5", "garch_sq": "GARCH, squared loss", "garch_abs": "GARCH, absolute loss"}
STATIC_REASON = "static path: its d_t is not a stationary series, so no test in plan v2 applies"


class SpecMismatch(RuntimeError):
    """The plan file is not the frozen one."""


@dataclass(frozen=True)
class Comparison:
    index: int
    model_id: str
    method: str
    window: str
    loss: str

    @property
    def seed(self) -> int:
        return SEED + self.index

    @property
    def ids(self) -> dict[str, Any]:
        return {"index": self.index, "seed": self.seed, "model_id": self.model_id, "method": self.method, "window": self.window, "loss": self.loss}


def family() -> list[Comparison]:
    combos = [(m, method, w, lo) for m, method in FAMILY_FORECASTS for w in FAMILY_WINDOWS for lo in FAMILY_LOSSES]
    return [Comparison(i, *combo) for i, combo in enumerate(combos)]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_spec(path: Path, expected: str = SPEC_SHA256) -> str:
    """The plan's SHA-256, or SpecMismatch if it is not the frozen file's."""
    if not path.is_file():
        raise SpecMismatch(f"{path} does not exist")
    digest = sha256_of(path)
    if digest != expected:
        raise SpecMismatch(f"{path} has SHA-256 {digest}, but the frozen plan's is {expected}: the plan changed, so this tool refuses to run")
    return digest


# --- the series -----------------------------------------------------------------------------------------


def load(folder: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """The forecast payloads by artifact name, the evaluation payload, and each file's SHA-256."""
    names = [artifact_name(m, method) for m, method in FAMILY_FORECASTS]
    forecasts = {name: read_artifact(folder, name)["data"] for name in names}
    evaluation = read_artifact(folder, "evaluation")["data"]
    inputs = {f"{name}.json": sha256_of(folder / f"{name}.json") for name in [*names, "evaluation"]}
    return forecasts, evaluation, inputs


def _window(forecasts: Mapping[str, Any], c: Comparison) -> Mapping[str, Any]:
    return next(w for w in forecasts[artifact_name(c.model_id, c.method)]["windows"] if w["id"] == c.window)


def errors(forecasts: Mapping[str, Any], c: Comparison, shift: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """The model's and the random walk's log errors, actual_log - forecast, on the comparison's window.
    The random walk is the one of the method's kind (evaluation.random_walk_forecasts); `shift` is added
    to the model's forecast (the shifted control)."""
    w = _window(forecasts, c)
    actual = np.array([r["actual_log"] for r in w["rows"]], dtype=float)
    forecast = np.array([r["mean_log"] for r in w["rows"]], dtype=float)
    if shift:
        forecast = forecast + shift
    rw_log, _ = random_walk_forecasts(w, KINDS[c.method])
    return actual - forecast, actual - rw_log


def differential(e_model: np.ndarray, e_rw: np.ndarray, loss_kind: str) -> np.ndarray:
    """d_t = L(e_model) - L(e_rw)."""
    return loss(e_model, loss_kind) - loss(e_rw, loss_kind)


# --- the gate -------------------------------------------------------------------------------------------


def _relative_error(got: float, expected: float) -> float:
    if got == expected:
        return 0.0
    return abs(got - expected) / abs(expected) if expected != 0 else math.inf


def _check(c: Comparison, quantity: str, expected: float, got: float, exact: bool = False) -> dict[str, Any]:
    ok = got == expected if exact else abs(got - expected) <= max(GATE_REL * abs(expected), GATE_ABS)
    return {"index": c.index, "quantity": quantity, "expected": expected, "got": got, "relative_error": _relative_error(got, expected), "ok": bool(ok)}


def _from_losses(losses: np.ndarray, loss_kind: str) -> float:
    """RMSE from squared losses, MAE from absolute ones."""
    return float(np.sqrt(np.mean(losses))) if loss_kind == "squared" else float(np.mean(losses))


def gate(forecasts: Mapping[str, Any], evaluation: Mapping[str, Any], comparisons: Sequence[Comparison]) -> dict[str, Any]:
    """The plan's gate (n and mean_diff of the one-step comparisons, log RMSE / MAE of the static ones),
    and the static random walk's self-check (module docstring)."""
    dm = {(r["model_id"], r["method"], r["window"], r["loss"]): r for r in evaluation["dm"]}
    metrics = {(r["model_id"], r["method"], r["window"]): r for r in evaluation["metrics"]}
    rw = {(r["kind"], r["window"]): r for r in evaluation["random_walk"]}
    checks, self_checks, missing = [], [], []
    for c in comparisons:
        e_model, e_rw = errors(forecasts, c)
        metric = "rmse" if c.loss == "squared" else "mae"
        if KINDS[c.method] == "one_step":
            row = dm.get((c.model_id, c.method, c.window, c.loss))
            if row is None:
                missing.append(c.index)
                continue
            d = differential(e_model, e_rw, c.loss)
            checks.append(_check(c, "dm.n", row["n"], len(d), exact=True))
            checks.append(_check(c, "dm.mean_diff", row["mean_diff"], float(np.mean(d))))
        else:
            row = metrics.get((c.model_id, c.method, c.window))
            if row is None:
                missing.append(c.index)
                continue
            checks.append(_check(c, f"metrics.log.{metric}", row["log"][metric], _from_losses(loss(e_model, c.loss), c.loss)))
            base = rw[("multi_step", c.window)]["log"][metric]
            self_checks.append(_check(c, f"random_walk.multi_step.log.{metric}", base, _from_losses(loss(e_rw, c.loss), c.loss)))
    one_step = sum(1 for c in comparisons if KINDS[c.method] == "one_step")
    passed = not missing and len(checks) == 2 * one_step + (len(comparisons) - one_step) and all(ch["ok"] for ch in checks)
    return {
        "passed": bool(passed),
        "self_check_passed": bool(not missing and all(ch["ok"] for ch in self_checks)),
        "missing": missing,
        "max_relative_error": max((ch["relative_error"] for ch in checks), default=None),
        "self_check_max_relative_error": max((ch["relative_error"] for ch in self_checks), default=None),
        "checks": checks,
        "self_checks": self_checks,
    }


# --- one comparison, and the family ---------------------------------------------------------------------


def analyse(d: np.ndarray, seed: int, replicates: int = REPLICATES) -> dict[str, Any]:
    """Everything the plan reports for one loss-differential series, before the correction: n, the mean,
    b and the block count, the primary p and the MDE (null when UNRESOLVED), the Newey-West t at lag
    b - 1, and the sensitivity p-values at 2b and b = 1 (with their block counts)."""
    n = len(d)
    b = block_length(d)
    unresolved = below_floor(n, b)
    rng = np.random.default_rng(seed)
    row: dict[str, Any] = {"n": n, "mean_diff": float(np.mean(d)), "b": b, "blocks": block_count(n, b), "unresolved": unresolved, "p_raw": None, "mde": None}
    if not unresolved:
        p, means = bootstrap_p(d, b, replicates, rng)
        row["p_raw"], row["mde"] = p, minimum_detectable_effect(means)
    try:
        t, p_nw = newey_west_t(d, b - 1)
    except ValueError:  # a constant series: no long-run variance
        t = p_nw = None
    row["newey_west"] = {"lag": b - 1, "t": t, "p": p_nw}
    row["sensitivity"] = []
    for size in (2 * b, 1):
        p_s = bootstrap_p(d, size, replicates, rng)[0] if size <= n else None
        row["sensitivity"].append({"b": size, "blocks": block_count(n, size), "below_floor": below_floor(n, size), "p": p_s})
    return row


def verdict(unresolved: bool, p_holm: float, mean_diff: float, alpha: float = ALPHA) -> str:
    if unresolved:
        return "unresolved"
    if p_holm < alpha and mean_diff > 0:
        return "worse_than_rw"
    if p_holm < alpha and mean_diff < 0:
        return "beats_rw"
    return "no_difference_detected"


def decide(rows: list[dict[str, Any]], alpha: float = ALPHA) -> None:
    """Holm over the rows' primary p-values (an UNRESOLVED row enters at 1), then each verdict. In place."""
    entry = [1.0 if r["p_raw"] is None else r["p_raw"] for r in rows]
    for r, p_entry, p_holm in zip(rows, entry, holm(entry)):
        r["p_entry"] = p_entry
        r["p_holm"] = float(p_holm)
        r["verdict"] = verdict(r["unresolved"], r["p_holm"], r["mean_diff"], alpha)


def run_family(forecasts: Mapping[str, Any], comparisons: Sequence[Comparison], replicates: int = REPLICATES) -> list[dict[str, Any]]:
    rows = [{**c.ids, **analyse(differential(*errors(forecasts, c), c.loss), c.seed, replicates)} for c in comparisons]
    decide(rows)
    return rows


# --- null controls --------------------------------------------------------------------------------------


def control_identical(forecasts: Mapping[str, Any], comparisons: Sequence[Comparison], replicates: int = REPLICATES) -> dict[str, Any]:
    """Control 1: each model's forecast set to the random walk's, so d is 0 on every day. Passes when every
    p entering the correction is 1 and nothing is rejected."""
    rows = []
    for c in comparisons:
        _, e_rw = errors(forecasts, c)
        rows.append({**c.ids, **analyse(differential(e_rw, e_rw, c.loss), c.seed, replicates)})
    decide(rows)
    passed = all(r["p_entry"] == 1.0 for r in rows) and not any(r["verdict"] in ("worse_than_rw", "beats_rw") for r in rows)
    return {"passed": bool(passed), "rows": rows}


def control_shift(forecasts: Mapping[str, Any], comparisons: Sequence[Comparison], replicates: int = REPLICATES, k: int | None = None) -> dict[str, Any]:
    """Control 2: SHIFT added to the aic walk-forward log forecast on oos. Passes when both losses' comparisons
    are rejected (k x raw p < alpha, which bounds Holm's adjusted p in any family of k) with mean_diff > 0."""
    k = len(comparisons) if k is None else k
    rows = []
    for c in comparisons:
        if (c.model_id, c.method, c.window) != SHIFTED:
            continue
        row = {**c.ids, **analyse(differential(*errors(forecasts, c, shift=SHIFT), c.loss), c.seed, replicates)}
        row["holm_bound"] = None if row["p_raw"] is None else min(1.0, k * row["p_raw"])
        row["rejected"] = row["holm_bound"] is not None and row["holm_bound"] < ALPHA and row["mean_diff"] > 0
        rows.append(row)
    passed = len(rows) == len(FAMILY_LOSSES) and all(r["rejected"] for r in rows)
    return {"passed": bool(passed), "shift": SHIFT, "k": k, "rows": rows}


def ar1(rng: np.random.Generator, count: int, n: int, rho: float) -> np.ndarray:
    """`count` AR(1) series of length n, x_t = rho x_(t-1) + e_t with e_t ~ N(0, 1), started from N(0, 1 / (1 - rho^2))."""
    x = np.empty((count, n))
    x[:, 0] = rng.standard_normal(count) / math.sqrt(1.0 - rho * rho)
    shocks = rng.standard_normal((count, n - 1))
    for t in range(1, n):
        x[:, t] = rho * x[:, t - 1] + shocks[:, t - 1]
    return x


def rejection_rate(series: np.ndarray, rng: np.random.Generator, replicates: int, force_b: int | None = None, alpha: float = ALPHA) -> dict[str, Any]:
    """How often the primary test rejects at alpha (unadjusted) over the rows of `series`, each with its own
    block length (or `force_b`). An UNRESOLVED series counts as not rejected."""
    rejected = unresolved = 0
    lengths: Counter[int] = Counter()
    for x in series:
        b = force_b if force_b is not None else block_length(x)
        lengths[b] += 1
        if below_floor(len(x), b):
            unresolved += 1
            continue
        rejected += bootstrap_p(x, b, replicates, rng)[0] < alpha
    count = len(series)
    return {"series": count, "rejected": int(rejected), "rate": rejected / count, "unresolved": unresolved, "b_counts": {str(b): lengths[b] for b in sorted(lengths)}}


def control_size(count: int = SIZE_SERIES, n: int = SIZE_N, replicates: int = SIZE_REPLICATES) -> dict[str, Any]:
    """Control 3: the rejection rate on series with mean 0, i.i.d. N(0, 1) and AR(1) with rho = SIZE_RHO; both must
    fall in SIZE_BAND. The AR(1) series with b = 1 forced is reported only."""
    iid = np.random.default_rng([SEED, 1, 0]).standard_normal((count, n))
    dependent = ar1(np.random.default_rng([SEED, 1, 1]), count, n, SIZE_RHO)
    runs = {
        "iid": rejection_rate(iid, np.random.default_rng([SEED, 2, 0]), replicates),
        "ar1": rejection_rate(dependent, np.random.default_rng([SEED, 2, 1]), replicates),
        "ar1_b1": rejection_rate(dependent, np.random.default_rng([SEED, 2, 2]), replicates, force_b=1),
    }
    low, high = SIZE_BAND
    for name, run in runs.items():
        run["in_band"] = bool(low <= run["rate"] <= high)
        run["decisive"] = name != "ar1_b1"
    passed = runs["iid"]["in_band"] and runs["ar1"]["in_band"]
    return {"passed": bool(passed), "n": n, "replicates": replicates, "rho": SIZE_RHO, "band": list(SIZE_BAND), "runs": runs}


def controls(forecasts: Mapping[str, Any], comparisons: Sequence[Comparison]) -> dict[str, Any]:
    out = {"identical": control_identical(forecasts, comparisons), "shifted": control_shift(forecasts, comparisons), "size": control_size()}
    return {"passed": all(v["passed"] for v in out.values()), **out}


# --- outputs --------------------------------------------------------------------------------------------


def primary_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    """A short digest of the primary results, so the runs list shows whether a re-run changed them."""
    key = [[r["index"], r["b"], r["mean_diff"], r["p_raw"], r["p_holm"], r["verdict"]] for r in rows]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]


def previous_runs(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("runs", []))


def _p(p: float | None) -> str:
    if p is None:
        return "—"
    return f"{p:.1e}" if p < 0.0001 else f"{p:.4f}"


def _name(r: Mapping[str, Any]) -> str:
    return f"{r['model_id']} {METHOD_NAMES[r['method']]}, {r['window']}, {r['loss']}"


def render_md(result: Mapping[str, Any]) -> str:
    """The human-readable report: plain English, short sentences."""
    g, ctl, rows = result["gate"], result["null_controls"], result.get("comparisons")
    lines = [
        "# Milestone 5: block-bootstrap inference for the forecast comparisons",
        "",
        "This file is generated by `uv run python tools/comparison_inference.py`. Do not edit it by hand.",
        f"It follows the frozen plan `docs/validation/m5-preregistration.md` (SHA-256 `{result['spec']['sha256']}`).",
        "",
        "## What the numbers measure",
        "",
        LABEL,
        "",
        "## Read this first",
        "",
        "- Both windows were already scored once, in milestone 4 (commit `800a0a8`).",
        "  That run did one Diebold–Mariano test per comparison, with no correction for multiple tests.",
        "  So this is **not a fresh holdout**. It changes only the inference, not a model, a forecast or a loss.",
        "- A fresh test needs the trading days after 2026-10-01. This analysis does not use them.",
        "- Each test asks one question: is the mean loss differential d̄ zero?",
        "  d_t is the model's loss minus the random walk's loss on day t. Positive d̄ means the model did worse.",
        "",
        "## How the test works",
        "",
        f"- The block length b comes from the measured autocorrelation of d_t. It is the first lag where {RUN} lags in a row are inside the band 1.96/√n.",
        f"- If fewer than {MIN_BLOCKS} whole blocks fit in the window, the comparison is UNRESOLVED. It has no p-value. It enters the correction with p = 1.",
        f"- The primary p comes from a circular block bootstrap of the centred d_t, with {result['settings']['replicates']:,} replicates.",
        f"- Holm's correction runs over all {result['settings']['k']} comparisons at α = {ALPHA}. A comparison is rejected when its Holm p is below {ALPHA}.",
        "- \"No difference detected\" does not mean \"equal\". The minimum detectable effect (MDE) says how large a difference the test could see.",
        "- The Newey–West t and the runs at 2b and at b = 1 are reported for context. They never change a verdict.",
        "",
        "## Gate",
        "",
    ]
    lines.append(
        f"The gate {'passed' if g['passed'] else 'FAILED'}. The {len(g['checks'])} checks compare the series built here with `evaluation.json`. "
        f"The largest relative error is {g['max_relative_error']:.3g}. The tolerance is {GATE_REL:g} (absolute {GATE_ABS:g} near zero)."
    )
    lines.append(
        f"A self-check of the static random walk {'passed' if g['self_check_passed'] else 'FAILED'} ({len(g['self_checks'])} checks, largest relative error {g['self_check_max_relative_error']:.3g}). The plan does not ask for it."
    )
    failed = [name for name in ("identical", "shifted", "size") if not ctl[name]["passed"]]
    summary = "All three controls passed." if not failed else f"Not all controls passed. Failed: {', '.join(failed)}."
    lines += ["", "## Null controls", "", summary, ""]
    ident = ctl["identical"]
    rows_ident = ident["rows"]
    unresolved_ident = sum(r["unresolved"] for r in rows_ident)
    rejected_ident = sum(r["verdict"] in ("worse_than_rw", "beats_rw") for r in rows_ident)
    entries_one = all(r["p_entry"] == 1.0 for r in rows_ident)
    single_one = all(r["sensitivity"][1]["p"] == 1.0 for r in rows_ident)
    lines += [
        f"**1. Identical forecasts: {'passed' if ident['passed'] else 'FAILED'}.** Each model's forecast was set to the random walk's, so d_t = 0 on every day.",
        f"{'Every' if entries_one else 'NOT every'} p that enters the correction is 1. {rejected_ident} of {len(rows_ident)} comparisons are rejected.",
        f"d_t is constant, so its autocorrelation is 0/0 and undefined. The block rule then finds no lag and sets b = L + 1. {unresolved_ident} of {len(rows_ident)} comparisons fall below the floor and are UNRESOLVED.",
        f"The bootstrap at b = 1 gives p = 1 on {'every one' if single_one else 'NOT every one'}. So the control does not depend on that branch of the rule.",
        "",
    ]
    shift = ctl["shifted"]
    lines.append(f"**2. Shifted forecast: {'passed' if shift['passed'] else 'FAILED'}.** {shift['shift']} was added to the aic walk-forward log forecast on oos.")
    for r in shift["rows"]:
        lines.append(f"- {r['loss']}: d̄ = {r['mean_diff']:+.3e}, b = {r['b']}, raw p = {_p(r['p_raw'])}, {shift['k']} × p = {_p(r['holm_bound'])}. {'Rejected' if r['rejected'] else 'Not rejected'}.")
    lines.append(f"{shift['k']} × p is the most Holm can raise a p-value in a family of {shift['k']}, so these are rejections in any family.")
    size = ctl["size"]
    lines += [
        "",
        f"**3. Size: {'passed' if size['passed'] else 'FAILED'}.** {size['runs']['iid']['series']:,} simulated series of n = {size['n']} with mean 0. Each used the block rule and {size['replicates']} replicates.",
        f"The rejection rate at 5% must be from {size['band'][0]:.0%} to {size['band'][1]:.0%}.",
        "",
        "| Process | Block length | Rejected | Rate | UNRESOLVED | In band | Decisive |",
        "|---|---|---|---|---|---|---|",
    ]
    names = {"iid": "i.i.d. N(0, 1)", "ar1": f"AR(1), ρ = {size['rho']}", "ar1_b1": f"AR(1), ρ = {size['rho']}"}
    for key, run in size["runs"].items():
        rule = "b = 1 forced" if key == "ar1_b1" else "the rule"
        lines.append(f"| {names[key]} | {rule} | {run['rejected']} | {run['rate']:.2%} | {run['unresolved']} | {'yes' if run['in_band'] else 'no'} | {'yes' if run['decisive'] else 'no (shown for contrast)'} |")
    lines.append("")
    lines.append("Block lengths the rule chose: " + "; ".join(f"{names[k]} " + ", ".join(f"b={b}: {c}" for b, c in run["b_counts"].items()) for k, run in size["runs"].items() if k != "ar1_b1") + ".")
    if rows is None:
        lines += [
            "",
            "## The 28 comparisons",
            "",
            "**Not run.** The plan says the null controls must pass before the results are read. A control failed, so the tool did not compute the family.",
            "No setting was changed to make a control pass. A changed method needs a new plan file with a new name (the plan's own rule).",
            "",
            "## Runs",
            "",
            "No family run has happened.",
        ]
        return "\n".join(lines) + "\n"
    counts = Counter(r["verdict"] for r in rows)
    lines += [
        "",
        "## Result",
        "",
        f"- Model worse than the random walk: {counts['worse_than_rw']}.",
        f"- Model better than the random walk: {counts['beats_rw']}.",
        f"- No difference detected: {counts['no_difference_detected']}.",
        f"- UNRESOLVED (too few blocks): {counts['unresolved']}.",
        "",
    ]
    claims = [r for r in rows if r["verdict"] in ("worse_than_rw", "beats_rw")]
    if claims:
        lines.append("These claims survive Holm's correction:")
        lines.append("")
        for r in claims:
            word = "worse" if r["verdict"] == "worse_than_rw" else "better"
            lines.append(f"- {_name(r)}: the model is {word} than the random walk (d̄ = {r['mean_diff']:+.3e}, Holm p = {_p(r['p_holm'])}).")
    else:
        lines.append("No claim that a model is better or worse than the random walk survives Holm's correction.")
    lines += [
        "",
        "## The 28 comparisons",
        "",
        "d̄ is in squared or absolute log points. MDE is the smallest |E[d_t]| a 5% test finds with 80% power at this n, before the correction.",
        "",
        "| # | Model | Method | Window | Loss | n | b | Blocks | d̄ | Raw p | Holm p | Verdict | MDE |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        mde = "—" if r["mde"] is None else f"{r['mde']:.2e}"
        cells = [r["index"], r["model_id"], METHOD_NAMES[r["method"]], r["window"], r["loss"], r["n"], r["b"], r["blocks"], f"{r['mean_diff']:+.3e}", _p(r["p_raw"]), _p(r["p_holm"]), VERDICT_WORDS[r["verdict"]], mde]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    lines += [
        "",
        "## Secondary statistics (not decisive)",
        "",
        "The Newey–West t uses a Bartlett kernel with lag b − 1 and a normal p. The sensitivity runs repeat the bootstrap with block 2b and with b = 1 (the i.i.d. case).",
        "",
        "| # | Comparison | NW lag | NW t | NW p | p at 2b (blocks) | p at b = 1 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        nw, (s2, s1) = r["newey_west"], r["sensitivity"]
        t = "—" if nw["t"] is None else f"{nw['t']:+.3f}"
        flag = ", below floor" if s2["below_floor"] else ""
        lines.append(f"| {r['index']} | {_name(r)} | {nw['lag']} | {t} | {_p(nw['p'])} | {_p(s2['p'])} ({s2['blocks']}{flag}) | {_p(s1['p'])} |")
    lines += ["", "## Runs", "", "Every family run is listed. The primary result of the first run is final unless a bug was fixed.", "", "| Run | Time (UTC) | Runtime | What changed, and why | Primary digest |", "|---|---|---|---|---|"]
    for i, run in enumerate(result["runs"], start=1):
        lines.append(f"| {i} | {run['time_utc']} | {run['runtime_seconds']:.1f} s | {run['change']} | `{run['primary_digest']}` |")
    s = result["settings"]
    lines += [
        "",
        "## Settings",
        "",
        f"B = {s['replicates']:,} replicates. Seed {s['seed']} + the comparison's index. α = {s['alpha']}. k = {s['k']}. Floor: {s['min_blocks']} blocks.",
        f"ACF lags up to min(⌊n/4⌋, {s['max_acf_lag']}); band {s['band_z']}/√n. MDE = ({s['z_test']} + {s['z_power']}) × the standard deviation of the bootstrap means.",
    ]
    return "\n".join(lines) + "\n"


def settings() -> dict[str, Any]:
    return {
        "replicates": REPLICATES,
        "seed": SEED,
        "alpha": ALPHA,
        "k": len(family()),
        "min_blocks": MIN_BLOCKS,
        "band_z": BAND_Z,
        "max_acf_lag": MAX_ACF_LAG,
        "run_inside_band": RUN,
        "z_test": Z_TEST,
        "z_power": Z_POWER,
        "gate_rel": GATE_REL,
        "gate_abs": GATE_ABS,
        "block_starts": "rng.integers(0, n, size=(B, ceil(n / b)))",
        "generator_order": "one generator per comparison, default_rng(seed + index): primary b, then 2b, then b = 1",
    }


def _write(result: Mapping[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    out_md.write_text(render_md(result), encoding="utf-8")


# --- plan v2: the series of control 3 -------------------------------------------------------------------


def dm_hln_p(d: np.ndarray) -> float | None:
    """Milestone 4's DM-HLN p at h = 1 (evaluation.dm_test) on a loss-differential series: the mean over
    sqrt(gamma_0 / n), gamma_0 with divisor n, times the HLN factor, on Student's t with n - 1 df. None for
    a constant series."""
    d = np.asarray(d, dtype=float)
    n = len(d)
    mean = float(np.mean(d))
    gamma0 = float(np.mean((d - mean) ** 2))
    if not gamma0 > 0:
        return None
    corrected = mean / math.sqrt(gamma0 / n) * hln_factor(n, 1)
    return float(2.0 * stats.t.sf(abs(corrected), n - 1))


def garch_filter(z: np.ndarray) -> np.ndarray:
    """GARCH(1,1) returns r_t = sqrt(h_t) z_t from unit-variance shocks z (one path per row), with
    h_0 = GARCH_SD^2 and h_t = omega + alpha r_(t-1)^2 + beta h_(t-1)."""
    z = np.atleast_2d(np.asarray(z, dtype=float))
    r = np.empty_like(z)
    h = np.full(z.shape[0], GARCH_SD**2)
    for t in range(z.shape[1]):
        if t:
            h = GARCH_OMEGA + GARCH_ALPHA * r[:, t - 1] ** 2 + GARCH_BETA * h
        r[:, t] = np.sqrt(h) * z[:, t]
    return r


def garch_returns(rng: np.random.Generator, count: int, length: int) -> np.ndarray:
    """`count` GARCH paths of `length` days, after GARCH_BURN days of burn-in; t(4) shocks scaled to variance 1."""
    z = rng.standard_t(GARCH_DF, size=(count, GARCH_BURN + length)) / math.sqrt(GARCH_DF / (GARCH_DF - 2.0))
    return garch_filter(z)[:, GARCH_BURN:]


def garch_differentials(r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Squared and absolute d_t, t = 1 ..., from returns r_0 ...: e_model = r_t - (0.02 r_(t-1) + 0.0009), e_rw = r_t."""
    prev, cur = r[..., :-1], r[..., 1:]
    e_model = cur - (GARCH_PHI * prev + GARCH_DRIFT)
    return differential(e_model, cur, "squared"), differential(e_model, cur, "absolute")


def garch_centres(rng: np.random.Generator, days: int = GARCH_CENTRE_DAYS) -> dict[str, float]:
    """Each GARCH differential's mean over one path of `days` days (the plan's 10^6-day mean)."""
    d_sq, d_abs = garch_differentials(garch_returns(rng, 1, days + 1)[0])
    return {"squared": float(d_sq.mean()), "absolute": float(d_abs.mean())}


def null_series_v2(process: str, n: int, count: int, rng: np.random.Generator, centres: Mapping[str, float]) -> np.ndarray:
    """`count` series of length n with mean 0 under `process` (one of V2_PROCESSES)."""
    if process == "iid":
        return rng.standard_normal((count, n))
    if process in ("ar03", "ar05"):
        return ar1(rng, count, n, 0.3 if process == "ar03" else 0.5)
    d_sq, d_abs = garch_differentials(garch_returns(rng, count, n + 1))
    return d_sq - centres["squared"] if process == "garch_sq" else d_abs - centres["absolute"]


def size_rates(series: np.ndarray, rng: np.random.Generator, replicates: int, alpha: float = ALPHA) -> dict[str, Any]:
    """Rejections at alpha (unadjusted) over the rows of `series` by the primary (EWC), the secondary
    bootstrap (rule C2, `replicates` replicates, starts from `rng`) and DM-HLN. A test that is UNRESOLVED
    or undefined on a series counts as not rejected."""
    count = len(series)
    ewc_rejected = ewc_unresolved = c2_rejected = c2_unresolved = dm_rejected = 0
    sizes = []
    for x in series:
        primary = ewc_test(x)
        ewc_unresolved += primary["unresolved"]
        ewc_rejected += primary["p"] is not None and primary["p"] < alpha
        b = c2_block_length(x)[0]
        sizes.append(b)
        if below_floor(len(x), b):
            c2_unresolved += 1
        else:
            c2_rejected += bootstrap_p(x, b, replicates, rng)[0] < alpha
        p_dm = dm_hln_p(x)
        dm_rejected += p_dm is not None and p_dm < alpha
    return {
        "series": count,
        "ewc": {"rejected": int(ewc_rejected), "rate": ewc_rejected / count, "unresolved": int(ewc_unresolved)},
        "c2": {"rejected": int(c2_rejected), "rate": c2_rejected / count, "unresolved": int(c2_unresolved), "b_median": float(np.median(sizes)), "b_max": int(max(sizes))},
        "dm_hln": {"rejected": int(dm_rejected), "rate": dm_rejected / count},
    }


def size_v2_passed(cells: Sequence[Mapping[str, Any]], band: tuple[float, float] = SIZE_BAND) -> bool:
    """Control 3 passes when the primary's rate lies in the band in every cell."""
    low, high = band
    return bool(cells) and all(low <= cell["ewc"]["rate"] <= high for cell in cells)


def control_size_v2(count: int = V2_SIZE_SERIES, ns: Sequence[int] = V2_SIZE_NS, replicates: int = V2_SIZE_REPLICATES, centre_days: int = GARCH_CENTRE_DAYS) -> dict[str, Any]:
    """Control 3 of plan v2: the rejection rates at 5% in each (n, process) cell (module docstring)."""
    centres = garch_centres(np.random.default_rng(CONTROL_SEED + 20), centre_days)
    low, high = SIZE_BAND
    cells = []
    for c, (n, process) in enumerate((n, process) for n in ns for process in V2_PROCESSES):
        series = null_series_v2(process, n, count, np.random.default_rng(CONTROL_SEED + c), centres)
        cell = {"cell": c, "n": n, "process": process, "series_seed": CONTROL_SEED + c, "bootstrap_seed": CONTROL_SEED + 10 + c}
        cell |= size_rates(series, np.random.default_rng(CONTROL_SEED + 10 + c), replicates)
        cell["in_band"] = bool(low <= cell["ewc"]["rate"] <= high)
        cells.append(cell)
    return {"passed": size_v2_passed(cells), "series": count, "replicates": replicates, "band": list(SIZE_BAND), "centre_seed": CONTROL_SEED + 20, "centre_days": centre_days, "centres": centres, "cells": cells}


# --- plan v2: one comparison, the family and controls 1 and 2 -------------------------------------------


def primary_row(c: Comparison, d: np.ndarray) -> dict[str, Any]:
    """n, d̄ and the primary test of one comparison: EWC for a one-step one, none for a static one."""
    row: dict[str, Any] = {**c.ids, "n": len(d), "mean_diff": float(np.mean(d))}
    if KINDS[c.method] != "one_step":
        return row | {"kind": "static", "unresolved": True, "reason": STATIC_REASON, "nu": None, "omega": None, "t": None, "p_raw": None, "mde": None}
    e = ewc_test(d)
    reason = "Ω̂ = 0 while d̄ ≠ 0" if e["unresolved"] else None
    return row | {"kind": "one_step", "unresolved": e["unresolved"], "reason": reason, "nu": e["nu"], "omega": e["omega"], "t": e["t"], "p_raw": e["p"], "mde": e["mde"]}


def c2_bootstrap(d: np.ndarray, seed: int, replicates: int = REPLICATES) -> dict[str, Any]:
    """The secondary bootstrap: rule C2's block, the floor, and the circular block bootstrap p from default_rng(seed)."""
    n = len(d)
    b, b_v1, b_pw = c2_block_length(d)
    unresolved = below_floor(n, b)
    p = None if unresolved else bootstrap_p(d, b, replicates, np.random.default_rng(seed))[0]
    return {"b": b, "b_v1": b_v1, "b_pw": b_pw, "blocks": block_count(n, b), "unresolved": unresolved, "p": p}


def run_family_v2(forecasts: Mapping[str, Any], evaluation: Mapping[str, Any], comparisons: Sequence[Comparison], replicates: int = REPLICATES) -> list[dict[str, Any]]:
    dm = {(r["model_id"], r["method"], r["window"], r["loss"]): r for r in evaluation["dm"]}
    rows = []
    for c in comparisons:
        d = differential(*errors(forecasts, c), c.loss)
        row = primary_row(c, d)
        if row["kind"] == "one_step":
            row["c2"] = c2_bootstrap(d, c.seed, replicates)
            row["dm_hln_p"] = dm[(c.model_id, c.method, c.window, c.loss)]["p_value"]
        else:
            row["c2"] = row["dm_hln_p"] = None
        rows.append(row)
    decide(rows)
    return rows


def unresolved_family(comparisons: Sequence[Comparison], reason: str) -> list[dict[str, Any]]:
    """The 28 rows when a control failed: no test was run, so every one is UNRESOLVED with the reason."""
    return [{**c.ids, "unresolved": True, "reason": reason, "p_raw": None, "p_entry": 1.0, "p_holm": 1.0, "verdict": "unresolved"} for c in comparisons]


def control_identical_v2(forecasts: Mapping[str, Any], comparisons: Sequence[Comparison]) -> dict[str, Any]:
    """Control 1 of plan v2: d = 0 on every day of all 28. Passes when every one-step p is 1, every p that
    enters Holm is 1 and nothing is rejected."""
    rows = []
    for c in comparisons:
        _, e_rw = errors(forecasts, c)
        rows.append(primary_row(c, differential(e_rw, e_rw, c.loss)))
    decide(rows)
    one_step_ones = all(r["p_raw"] == 1.0 for r in rows if r["kind"] == "one_step")
    passed = one_step_ones and all(r["p_entry"] == 1.0 for r in rows) and not any(r["verdict"] in ("worse_than_rw", "beats_rw") for r in rows)
    return {"passed": bool(passed), "rows": rows}


def control_shift_v2(forecasts: Mapping[str, Any], comparisons: Sequence[Comparison]) -> dict[str, Any]:
    """Control 2 of plan v2: SHIFT added to the aic walk-forward log forecast on oos. Passes when the primary
    rejects both losses (k x p < alpha) with d̄ > 0."""
    k = len(comparisons)
    rows = []
    for c in comparisons:
        if (c.model_id, c.method, c.window) != SHIFTED:
            continue
        row = primary_row(c, differential(*errors(forecasts, c, shift=SHIFT), c.loss))
        row["holm_bound"] = None if row["p_raw"] is None else min(1.0, k * row["p_raw"])
        row["rejected"] = row["holm_bound"] is not None and row["holm_bound"] < ALPHA and row["mean_diff"] > 0
        rows.append(row)
    passed = len(rows) == len(FAMILY_LOSSES) and all(r["rejected"] for r in rows)
    return {"passed": bool(passed), "shift": SHIFT, "k": k, "rows": rows}


def controls_v2(forecasts: Mapping[str, Any], comparisons: Sequence[Comparison]) -> dict[str, Any]:
    out = {"identical": control_identical_v2(forecasts, comparisons), "shifted": control_shift_v2(forecasts, comparisons), "size": control_size_v2()}
    return {"passed": all(v["passed"] for v in out.values()), **out}


# --- plan v2: outputs -----------------------------------------------------------------------------------


def primary_digest_v2(rows: Sequence[Mapping[str, Any]]) -> str:
    key = [[r["index"], r.get("nu"), r.get("mean_diff"), r["p_raw"], r["p_holm"], r["verdict"]] for r in rows]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]


def _rate_range(cells: Sequence[Mapping[str, Any]], n: int, test: str) -> str:
    rates = [cell[test]["rate"] for cell in cells if cell["n"] == n]
    return "—" if not rates else f"{min(rates):.1%} to {max(rates):.1%}"


def _units(loss_kind: str) -> str:
    return "squared log points" if loss_kind == "squared" else "log points"


def render_md_v2(result: Mapping[str, Any]) -> str:
    """The human-readable report of a plan v2 run: plain English, short sentences."""
    g, ctl, rows = result["gate"], result["null_controls"], result["comparisons"]
    computed = result["family_computed"]
    size = ctl["size"]
    lines = [
        "# Milestone 5: inference for the forecast comparisons (plan version 2)",
        "",
        "This file is generated by `uv run python tools/comparison_inference.py --plan v2`. Do not edit it by hand.",
        f"It follows the frozen plan `docs/validation/m5-preregistration-v2.md` (SHA-256 `{result['spec']['sha256']}`).",
        f"Version 1 of the plan is `docs/validation/m5-preregistration.md` (SHA-256 `{result['spec_v1']['sha256']}`). Its outputs stay as the record.",
        "",
        "## What the numbers measure",
        "",
        LABEL,
        "",
        "## Read this first",
        "",
        "- Both windows were already scored once, in milestone 4 (commit `800a0a8`).",
        "  That run did one Diebold–Mariano test per comparison, with no correction for multiple tests.",
        "  So this is **not a fresh holdout**. It changes only the inference, not a model, a forecast or a loss.",
        "- A fresh test needs the trading days after 2026-10-01. This analysis does not use them.",
        "- Each test asks one question: is the mean loss differential d̄ zero?",
        "  d_t is the model's loss minus the random walk's loss on day t. Positive d̄ means the model did worse.",
        "",
        "## Why there is a version 2",
        "",
        "- Version 1 stopped at its size control, before any of its 28 results was computed.",
        "  Its block bootstrap rejected 194 of 2,000 true nulls (9.70%) for AR(1) with ρ = 0.3 at n = 227. The limit was 8%.",
        "  The block rule mostly chose b = 2, which is too short for that dependence.",
        "- A design phase followed, on simulated data only. It tried three longer block rules (C1, C2, C3).",
        "  All three still rejected more than 8% of true nulls for AR(1) with ρ = 0.5 at n = 227 (9.70%, 8.60% and 8.85%).",
        "  The DM-HLN test was worse: 16.4% at ρ = 0.3 and 26.0% at ρ = 0.5.",
        "- So version 2 changes the primary test. The family, the windows, the losses, d_t, the gate, α and Holm stay as in version 1.",
        "",
        "## How the test works",
        "",
        "- **Static comparisons (12): no test.** A static path's errors come from one origin and add up over the horizon.",
        "  Its d_t is not a stationary series. Each static comparison is UNRESOLVED and enters the correction with p = 1.",
        "- **One-step comparisons (16): the EWC t test** (Lazarus, Lewis, Stock and Watson, 2018).",
        "  It estimates the long-run variance of d_t from ν cosine weights, with ν = ⌊0.4 n^(2/3)⌋: 14 at n = 227 and 31 at n = 689.",
        "  The p-value comes from Student's t with ν degrees of freedom.",
        f"- Holm's correction runs over all {result['settings']['k']} comparisons at α = {ALPHA}. A comparison is rejected when its Holm p is below {ALPHA}.",
        "- \"No difference detected\" does not mean \"equal\". The minimum detectable effect (MDE) says how large a difference the test could see.",
        "- Two secondary results are shown for each one-step comparison. They never change a verdict:",
        "  a circular block bootstrap with rule C2's block, and milestone 4's DM-HLN p. Each is shown beside its own measured size from control 3.",
        "",
        "## Gate",
        "",
        f"The gate {'passed' if g['passed'] else 'FAILED'}. The {len(g['checks'])} checks compare the series built here with `evaluation.json`. "
        f"The largest relative error is {g['max_relative_error']:.3g}. The tolerance is {GATE_REL:g} (absolute {GATE_ABS:g} near zero).",
        f"A self-check of the static random walk {'passed' if g['self_check_passed'] else 'FAILED'} ({len(g['self_checks'])} checks, largest relative error {g['self_check_max_relative_error']:.3g}). The plan does not ask for it.",
    ]
    failed = [name for name in ("identical", "shifted", "size") if not ctl[name]["passed"]]
    lines += ["", "## Null controls", "", "All three controls passed." if not failed else f"Not all controls passed. Failed: {', '.join(failed)}.", ""]
    ident = ctl["identical"]
    one_step = [r for r in ident["rows"] if r["kind"] == "one_step"]
    lines += [
        f"**1. Identical forecasts: {'passed' if ident['passed'] else 'FAILED'}.** Each model's forecast was set to the random walk's, so d_t = 0 on every day.",
        f"The EWC p is 1 on {sum(r['p_raw'] == 1.0 for r in one_step)} of {len(one_step)} one-step comparisons. "
        f"{sum(r['p_entry'] == 1.0 for r in ident['rows'])} of {len(ident['rows'])} p-values enter the correction at 1. "
        f"{sum(r['verdict'] in ('worse_than_rw', 'beats_rw') for r in ident['rows'])} comparisons are rejected.",
        "",
    ]
    shift = ctl["shifted"]
    lines.append(f"**2. Shifted forecast: {'passed' if shift['passed'] else 'FAILED'}.** {shift['shift']} was added to the aic walk-forward log forecast on oos.")
    for r in shift["rows"]:
        t = "—" if r["t"] is None else f"{r['t']:+.2f}"
        lines.append(f"- {r['loss']}: d̄ = {r['mean_diff']:+.3e}, ν = {r['nu']}, t = {t}, p = {_p(r['p_raw'])}, {shift['k']} × p = {_p(r['holm_bound'])}. {'Rejected' if r['rejected'] else 'Not rejected'}.")
    lines.append(f"{shift['k']} × p is the most Holm can raise a p-value in a family of {shift['k']}, so these are rejections in any family.")
    lines += [
        "",
        f"**3. Size: {'passed' if size['passed'] else 'FAILED'}.** {size['series']:,} simulated series with mean 0 in each cell. "
        f"The EWC rejection rate at 5% must be from {size['band'][0]:.0%} to {size['band'][1]:.0%} in every cell.",
        f"The bootstrap ({size['replicates']} replicates, rule C2) and DM-HLN ran on the same series. Their rates are reported only.",
        "A test that cannot run on a series (UNRESOLVED) counts as not rejected.",
        "",
        "| n | Process | EWC rate | In band | Bootstrap (C2) rate | C2 UNRESOLVED | DM-HLN rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for cell in size["cells"]:
        lines.append(f"| {cell['n']} | {PROCESS_NAMES[cell['process']]} | {cell['ewc']['rate']:.2%} | {'yes' if cell['in_band'] else 'no'} | {cell['c2']['rate']:.2%} | {cell['c2']['unresolved']} | {cell['dm_hln']['rate']:.2%} |")
    lines += ["", "The GARCH squared-loss differential has heavy tails: with t(4) shocks its variance is not finite."]
    lines += ["", "## Result", ""]
    if not computed:
        lines += [
            f"**No result.** {result['unresolved_reason']}",
            "The plan says the null controls must pass before any result is read. So no primary p-value is reported for any comparison.",
            "All 28 comparisons are UNRESOLVED. No setting was changed to make a control pass.",
            "The next evidence is the trading days after 2026-10-01 (live periods). The plan rules out a version 3 for this milestone.",
            "",
            "## The 28 comparisons",
            "",
            "| # | Model | Method | Window | Loss | Verdict |",
            "|---|---|---|---|---|---|",
        ]
        lines += [f"| {r['index']} | {r['model_id']} | {METHOD_NAMES[r['method']]} | {r['window']} | {r['loss']} | UNRESOLVED |" for r in rows]
    else:
        counts = Counter(r["verdict"] for r in rows)
        lines += [
            f"- Model worse than the random walk: {counts['worse_than_rw']}.",
            f"- Model better than the random walk: {counts['beats_rw']}.",
            f"- No difference detected: {counts['no_difference_detected']}.",
            f"- UNRESOLVED: {counts['unresolved']} ({sum(r['kind'] == 'static' for r in rows)} static, by construction).",
            "",
        ]
        claims = [r for r in rows if r["verdict"] in ("worse_than_rw", "beats_rw")]
        if claims:
            lines += ["These claims survive Holm's correction:", ""]
            for r in claims:
                word = "worse" if r["verdict"] == "worse_than_rw" else "better"
                lines.append(f"- {_name(r)}: the model is {word} than the random walk (d̄ = {r['mean_diff']:+.3e}, Holm p = {_p(r['p_holm'])}).")
        else:
            lines.append("No claim that a model is better or worse than the random walk survives Holm's correction.")
        lines += [
            "",
            "## The 28 comparisons",
            "",
            "d̄ is in squared log points (squared loss) or log points (absolute loss). The MDE is in the same units.",
            "",
            "| # | Model | Method | Window | Loss | n | ν | d̄ | t | p | Holm p | Verdict | MDE |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            t = "—" if r["t"] is None else f"{r['t']:+.2f}"
            nu = "—" if r["nu"] is None else r["nu"]
            mde = "—" if r["mde"] is None else f"{r['mde']:.2e}"
            cells = [r["index"], r["model_id"], METHOD_NAMES[r["method"]], r["window"], r["loss"], r["n"], nu, f"{r['mean_diff']:+.3e}", t, _p(r["p_raw"]), _p(r["p_holm"]), VERDICT_WORDS[r["verdict"]], mde]
            lines.append("| " + " | ".join(str(c) for c in cells) + " |")
        quiet = [r for r in rows if r["verdict"] == "no_difference_detected"]
        lines += ["", "## Minimum detectable effects", ""]
        if quiet:
            lines += ["The MDE is the smallest |E[d_t]| that a 5% EWC test finds with 80% power at this n, before the correction.", ""]
            lines += [f"- {_name(r)}: MDE {r['mde']:.2e} {_units(r['loss'])} (d̄ = {r['mean_diff']:+.2e})." for r in quiet]
        else:
            lines.append("No comparison has the verdict \"no difference detected\".")
        lines += [
            "",
            "**In dollars: not given.** The conversion is not exact for either loss.",
            "A log error x (actual log minus forecast log) on a day with price P is a dollar error of P(1 − exp(−x)), which is not P·x.",
            "Squared loss: the dollar loss is P²(1 − exp(−x))², so its mean is not P̄² times the mean of x².",
            "Absolute loss: the mean of P |1 − exp(−x)| is not P̄ times the mean of |x|.",
            "So the MDE is given in log units only.",
            "",
            "## Secondary results (never decisive)",
            "",
            f"Bootstrap: rule C2, b = max(b_v1, ⌈{C2_MULTIPLIER} b_PW⌉), {result['settings']['c2_replicates']:,} replicates, seed 20261109 + the index, UNRESOLVED below {MIN_BLOCKS} blocks.",
            "DM-HLN: milestone 4's p, copied from `evaluation.json`, with no correction for multiple tests.",
            "Each size column is the test's rejection rate on true nulls in control 3, over the five processes at the comparison's n.",
            "",
            "| # | Comparison | C2 b (b_v1, b_PW) | Blocks | Bootstrap p | Bootstrap size at this n | DM-HLN p | DM-HLN size at this n |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            if r["kind"] != "one_step":
                continue
            c2 = r["c2"]
            parts = "constant series" if c2["b_v1"] is None else f"{c2['b_v1']}, {c2['b_pw']:.2f}"
            p_c2 = "UNRESOLVED" if c2["unresolved"] else _p(c2["p"])
            lines.append(f"| {r['index']} | {_name(r)} | {c2['b']} ({parts}) | {c2['blocks']} | {p_c2} | {_rate_range(size['cells'], r['n'], 'c2')} | {_p(r['dm_hln_p'])} | {_rate_range(size['cells'], r['n'], 'dm_hln')} |")
    lines += ["", "## Runs", "", "Every v2 run that wrote these files is listed. The primary result of the first run is final unless a bug was fixed.", "", "| Run | Time (UTC) | Runtime | Outcome | What changed, and why | Primary digest |", "|---|---|---|---|---|---|"]
    for i, run in enumerate(result["runs"], start=1):
        lines.append(f"| {i} | {run['time_utc']} | {run['runtime_seconds']:.1f} s | {run['outcome']} | {run['change']} | `{run['primary_digest']}` |")
    s = result["settings"]
    lines += [
        "",
        "## Settings",
        "",
        f"α = {s['alpha']}, k = {s['k']}, Holm. EWC: ν = ⌊0.4 n^(2/3)⌋, MDE = (t_ν,0.975 + t_ν,0.80) √(Ω̂/n).",
        f"Bootstrap: B = {s['c2_replicates']:,}, floor {s['min_blocks']} blocks, Politis–White with c = {PW_C:g} and K_n = max({PW_MIN_KN}, ⌈√log10 n⌉).",
        f"Control 3: {s['size_series']:,} series per cell, B = {s['size_replicates']} for the bootstrap, seeds {CONTROL_SEED} onwards (the tool's docstring gives the allocation).",
    ]
    return "\n".join(lines) + "\n"


def settings_v2() -> dict[str, Any]:
    return {
        "alpha": ALPHA,
        "k": len(family()),
        "primary": "EWC t test (Lazarus, Lewis, Stock and Watson 2018): nu = floor(0.4 n^(2/3)), Student's t on nu df",
        "ewc_mde": "(t_{nu,0.975} + t_{nu,0.80}) sqrt(Omega / n)",
        "static": "UNRESOLVED by construction; enters Holm with p = 1",
        "c2_rule": f"max(b_v1, ceil({C2_MULTIPLIER} b_PW)); b = 1 for a constant series",
        "c2_replicates": REPLICATES,
        "c2_seed": "20261109 + index",
        "min_blocks": MIN_BLOCKS,
        "politis_white": {"c": PW_C, "kn": f"max({PW_MIN_KN}, ceil(sqrt(log10 n)))", "M": "min(2 m_hat, m_max); m_max if no m_hat", "cap": "ceil(min(3 sqrt(n), n / 3))"},
        "gate_rel": GATE_REL,
        "gate_abs": GATE_ABS,
        "shift": SHIFT,
        "size_series": V2_SIZE_SERIES,
        "size_ns": list(V2_SIZE_NS),
        "size_processes": list(V2_PROCESSES),
        "size_replicates": V2_SIZE_REPLICATES,
        "size_band": list(SIZE_BAND),
        "size_seeds": f"series {CONTROL_SEED} + cell, bootstrap {CONTROL_SEED + 10} + cell, GARCH centring {CONTROL_SEED + 20}",
        "garch": {"alpha": GARCH_ALPHA, "beta": GARCH_BETA, "shock_df": GARCH_DF, "sd": GARCH_SD, "omega": GARCH_OMEGA, "burn_in": GARCH_BURN, "centre_days": GARCH_CENTRE_DAYS, "forecast": f"{GARCH_PHI} r_(t-1) + {GARCH_DRIFT}"},
    }


def main_v2(args: argparse.Namespace) -> int:
    start = time.perf_counter()
    try:
        digest_v2 = check_spec(SPEC_V2, SPEC_V2_SHA256)
        digest_v1 = check_spec(SPEC)
    except SpecMismatch as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    try:
        forecasts, evaluation, inputs = load(DATA)
    except ArtifactError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    comparisons = family()
    g = gate(forecasts, evaluation, comparisons)
    print(f"gate: {'passed' if g['passed'] else 'FAILED'}, {len(g['checks'])} checks, largest relative error {g['max_relative_error']}")
    print(f"self-check (static random walk): {'passed' if g['self_check_passed'] else 'FAILED'}, largest relative error {g['self_check_max_relative_error']}")
    if not g["passed"] or not g["self_check_passed"]:
        for ch in [*g["checks"], *g["self_checks"]]:
            if not ch["ok"]:
                print(f"  comparison {ch['index']} {ch['quantity']}: expected {ch['expected']!r}, got {ch['got']!r}", file=sys.stderr)
        print("error: the gate failed, so nothing else runs and nothing is written", file=sys.stderr)
        return 1
    checks = controls_v2(forecasts, comparisons)
    for name in ("identical", "shifted", "size"):
        print(f"null control {name}: {'passed' if checks[name]['passed'] else 'FAILED'}")
    for r in checks["shifted"]["rows"]:
        print(f"  shifted {r['loss']}: mean_diff {r['mean_diff']:+.4e}, nu {r['nu']}, t {r['t']}, p {r['p_raw']}, k x p {r['holm_bound']}")
    for cell in checks["size"]["cells"]:
        print(f"  size n {cell['n']} {cell['process']:9s}: EWC {cell['ewc']['rate']:.2%} ({'in' if cell['in_band'] else 'OUT OF'} band), C2 {cell['c2']['rate']:.2%} ({cell['c2']['unresolved']} UNRESOLVED), DM-HLN {cell['dm_hln']['rate']:.2%}")
    if args.controls_only:
        print(f"runtime {time.perf_counter() - start:.1f} s (controls only; nothing written)")
        return 0 if checks["passed"] else 1
    result: dict[str, Any] = {
        "plan": "v2",
        "spec": {"path": SPEC_V2.relative_to(REPO).as_posix(), "sha256": digest_v2},
        "spec_v1": {"path": SPEC.relative_to(REPO).as_posix(), "sha256": digest_v1},
        "label": LABEL,
        "already_scored": "Both windows were scored once in milestone 4 (commit 800a0a8): one DM-HLN test per comparison, no correction. This is not a fresh holdout.",
        "inputs": inputs,
        "settings": settings_v2(),
        "family_order": "forecasts (aic static, aic walk_forward, aic refit, bic static, bic walk_forward, course static, course walk_forward), then windows (test, oos), then losses (squared, absolute)",
        "gate": g,
        "null_controls": checks,
    }
    if checks["passed"]:
        rows = run_family_v2(forecasts, evaluation, comparisons)
        reason, outcome = None, "family computed"
    else:
        failed = [name for name in ("identical", "shifted", "size") if not checks[name]["passed"]]
        reason = f"Null control {', '.join(failed)} failed, so the family was not computed."
        rows, outcome = unresolved_family(comparisons, reason), f"control failed: {', '.join(failed)}"
    runs = previous_runs(OUT_JSON_V2)
    change = args.change or ("first run" if not runs else "re-run; no change stated")
    elapsed = time.perf_counter() - start
    runs.append({"time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "runtime_seconds": round(elapsed, 1), "outcome": outcome, "change": change, "primary_digest": primary_digest_v2(rows)})
    result |= {"family_computed": checks["passed"], "unresolved_reason": reason, "comparisons": rows, "runs": runs}
    OUT_JSON_V2.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    OUT_MD_V2.write_text(render_md_v2(result), encoding="utf-8")
    for r in rows:
        if checks["passed"]:
            c2 = r["c2"]
            c2_text = "" if c2 is None else f" | C2 b {c2['b']} p {_p(c2['p'])} | DM {_p(r['dm_hln_p'])}"
            print(f"{r['index']:2d} {_name(r):45s} n {r['n']:3d} nu {str(r['nu']):>4s} mean {r['mean_diff']:+.3e} p {_p(r['p_raw']):>7s} holm {_p(r['p_holm']):>7s} {r['verdict']}{c2_text}")
    print(f"wrote {OUT_JSON_V2} and {OUT_MD_V2}; runtime {elapsed:.1f} s")
    return 0 if checks["passed"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Milestone 5's pre-registered inference on the 28 forecast comparisons.")
    parser.add_argument("--controls-only", action="store_true", help="run the gate and the null controls, print them, write nothing")
    parser.add_argument("--change", help="for a later family run: what changed since the last one, and why")
    parser.add_argument("--plan", choices=("v1", "v2"), default="v1", help="which frozen plan to run (default v1)")
    args = parser.parse_args(argv)
    if args.plan == "v2":
        return main_v2(args)
    start = time.perf_counter()
    try:
        digest = check_spec(SPEC)
    except SpecMismatch as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    try:
        forecasts, evaluation, inputs = load(DATA)
    except ArtifactError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    comparisons = family()
    g = gate(forecasts, evaluation, comparisons)
    print(f"gate: {'passed' if g['passed'] else 'FAILED'}, {len(g['checks'])} checks, largest relative error {g['max_relative_error']}")
    print(f"self-check (static random walk): {'passed' if g['self_check_passed'] else 'FAILED'}, largest relative error {g['self_check_max_relative_error']}")
    if not (g["passed"] and g["self_check_passed"]):
        for ch in [*g["checks"], *g["self_checks"]]:
            if not ch["ok"]:
                print(f"  comparison {ch['index']} {ch['quantity']}: expected {ch['expected']!r}, got {ch['got']!r}", file=sys.stderr)
        print("error: the gate failed, so nothing else runs and nothing is written", file=sys.stderr)
        return 1
    ctl = controls(forecasts, comparisons)
    for name in ("identical", "shifted", "size"):
        print(f"null control {name}: {'passed' if ctl[name]['passed'] else 'FAILED'}")
    for r in ctl["shifted"]["rows"]:
        print(f"  shifted {r['loss']}: mean_diff {r['mean_diff']:+.4e}, b {r['b']}, p {r['p_raw']}, k x p {r['holm_bound']}")
    for key, run in ctl["size"]["runs"].items():
        print(f"  size {key}: {run['rejected']} of {run['series']} rejected ({run['rate']:.2%}), {run['unresolved']} UNRESOLVED, b {run['b_counts']}")
    if args.controls_only:
        print(f"runtime {time.perf_counter() - start:.1f} s (controls only; nothing written)")
        return 0 if ctl["passed"] else 1
    result: dict[str, Any] = {
        "spec": {"path": SPEC.relative_to(REPO).as_posix(), "sha256": digest},
        "label": LABEL,
        "already_scored": "Both windows were scored once in milestone 4 (commit 800a0a8): one DM-HLN test per comparison, no correction. This is not a fresh holdout.",
        "inputs": inputs,
        "settings": settings(),
        "family_order": "forecasts (aic static, aic walk_forward, aic refit, bic static, bic walk_forward, course static, course walk_forward), then windows (test, oos), then losses (squared, absolute)",
        "gate": g,
        "null_controls": ctl,
    }
    if not ctl["passed"]:
        result |= {"comparisons": None, "runs": previous_runs(OUT_JSON)}
        _write(result, OUT_JSON, OUT_MD)
        print("error: a null control failed, so the family was not run; the outputs hold the gate and the controls", file=sys.stderr)
        return 1
    rows = run_family(forecasts, comparisons)
    runs = previous_runs(OUT_JSON)
    change = args.change or ("first run" if not runs else "re-run; no change stated")
    elapsed = time.perf_counter() - start
    runs.append({"time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "runtime_seconds": round(elapsed, 1), "change": change, "primary_digest": primary_digest(rows)})
    result |= {"comparisons": rows, "runs": runs}
    _write(result, OUT_JSON, OUT_MD)
    for r in rows:
        print(f"{r['index']:2d} {_name(r):45s} n {r['n']:3d} b {r['b']:3d} blocks {r['blocks']:3d} mean {r['mean_diff']:+.3e} p {_p(r['p_raw']):>7s} holm {_p(r['p_holm']):>7s} {r['verdict']}")
    print(f"wrote {OUT_JSON} and {OUT_MD}; runtime {elapsed:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
