"""Milestone 3: is each fitted model's error white noise? (contract.md 3.8; course module 8)

Pure: a fitted statsmodels result in, plain Python values out.

**The burn-in.** With d >= 1 and statsmodels' default (approximate diffuse) initialisation, the
first d one-step forecast errors are not shocks. The first forecast of the level has nothing to go
on, so the first residual is about the log price itself (3.18 on AAPL, where every later residual
is within about +-0.13), and its standardised value is close to 0 because the forecast variance is
huge. statsmodels marks these observations: SARIMAX sets `loglikelihood_burn` to the number of
diffuse (differencing) states, d here (statsmodels/tsa/statespace/sarimax.py:679-683), leaves them
out of the likelihood, and its own diagnostics drop max(loglikelihood_burn, nobs_diffuse)
(statsmodels/tsa/statespace/mlemodel.py:5345, in plot_diagnostics). `burn_in` uses that rule, so
every statistic below sees n - d residuals. The course's module-8 plots use `model_fit.resid` whole,
first residual included (measured in the milestone-3 walkthrough).

**What is tested, and on which series.** Every test runs on the standardised one-step forecast
errors after the burn-in (statsmodels' `standardized_forecasts_error`, the series its own
`test_serial_correlation`, `test_normality` and `plot_diagnostics` use). A p-value is the
probability, under the test's null hypothesis, of a statistic at least as extreme as the one
observed; "rejected" means p < ALPHA.

- Ljung-Box at LJUNG_BOX_LAGS, with `model_df = p + q`: the statistic sums squared autocorrelations
  of estimated residuals, which uses up p + q degrees of freedom, so it is compared with a
  chi-squared on lag - (p + q). At a lag <= p + q there are no degrees of freedom left, and the
  test is not applied (its p-value is null and `applied` false). Null: no autocorrelation up to
  that lag.
- Jarque-Bera, with the sample skew and kurtosis (Pearson's, so a normal has kurtosis 3). Null:
  skew 0 and kurtosis 3.
- ARCH-LM (Engle's Lagrange-multiplier test, statsmodels' `het_arch`) at ARCH_LM_LAGS: regress the
  squared residuals on their own m lags; (n - m) R^2, with n - m the rows of that regression, is
  chi-squared on m. Null: no autoregressive conditional heteroskedasticity, that is, no
  volatility clustering.

The ACF of the residuals and of the squared residuals runs to NLAGS with the white-noise band
z / sqrt(n): under the null each sample autocorrelation is about N(0, 1/n). (For residuals of a
fitted ARMA the true variance at small lags is a little below 1/n, so the band is slightly wide
there.) Whether a bar is past its band is decided here, |value| > band strictly, and exported.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from statsmodels.stats.stattools import jarque_bera
from statsmodels.tsa.stattools import acf

ALPHA = 0.05
Z = 1.959963984540054  # scipy's norm.ppf(0.975); the same literal as identification.py's z
NLAGS = 50  # the course's lags=50 for its correlograms (identification.py)
LJUNG_BOX_LAGS = (5, 10, 20)
ARCH_LM_LAGS = (5, 10)


def burn_in(result: Any) -> int:
    """How many leading residuals to drop: max(loglikelihood_burn, nobs_diffuse), statsmodels' own
    rule (mlemodel.py:5345). d for the models fitted here."""
    return int(max(result.loglikelihood_burn, result.nobs_diffuse))


def standardized_residuals(result: Any) -> np.ndarray:
    """The standardised one-step forecast errors after the burn-in."""
    return np.asarray(result.standardized_forecasts_error[0, burn_in(result) :], dtype=float)


def outside(value: float, band: float) -> bool:
    """True when a bar reaches past its band: |value| > band."""
    return bool(abs(value) > band)


def correlogram(x: np.ndarray, nlags: int = NLAGS) -> dict[str, Any]:
    """The sample ACF at lags 1..nlags with the white-noise band and the outside flags."""
    values = acf(x, nlags=nlags, fft=False, adjusted=False)
    band = Z / np.sqrt(len(x))
    rows = [{"lag": k, "acf": float(values[k]), "outside": outside(float(values[k]), band)} for k in range(1, nlags + 1)]
    return {"band": float(band), "outside_count": int(sum(r["outside"] for r in rows)), "rows": rows}


def ljung_box(x: np.ndarray, model_df: int, lags: tuple[int, ...] = LJUNG_BOX_LAGS) -> list[dict[str, Any]]:
    """Ljung-Box at each lag, against a chi-squared on lag - model_df; not applied where lag <= model_df."""
    table = acorr_ljungbox(x, lags=list(lags), model_df=model_df)
    rows = []
    for lag in lags:
        applied = lag > model_df
        rows.append(
            {
                "lag": lag,
                "model_df": model_df,
                "df": lag - model_df if applied else None,
                "statistic": float(table.loc[lag, "lb_stat"]),
                "p_value": float(table.loc[lag, "lb_pvalue"]) if applied else None,
                "applied": applied,
            }
        )
    return rows


def arch_lm(x: np.ndarray, lags: tuple[int, ...] = ARCH_LM_LAGS) -> list[dict[str, Any]]:
    """Engle's ARCH-LM test at each number of lags m: the LM statistic (n - m) R^2 and its p-value."""
    rows = []
    for nlags in lags:
        # ddof=0, het_arch's default: Engle's (n - m) R^2 with no correction for the ARMA
        # parameters. het_arch's docstring recommends ddof = p + q for ARMA residuals; ddof scales
        # only the statistic, (n - m - ddof) R^2, and the p-value stays chi-squared on nlags. With
        # ddof = p + q the AIC choice's p-values are 3.6e-50 and 4.1e-53 instead of 2.4e-50 and
        # 2.6e-53, so the verdict is the same (milestone-3 walkthrough, review fix round).
        test = het_arch(x, nlags=nlags, ddof=0, result_object=True)
        rows.append({"lags": nlags, "statistic": float(test.lm), "p_value": float(test.lmpval)})
    return rows


def normality(x: np.ndarray) -> dict[str, float]:
    jb, p, skew, kurtosis = jarque_bera(x)
    return {"statistic": float(jb), "p_value": float(p), "skew": float(skew), "kurtosis": float(kurtosis)}


def qq_points(x: np.ndarray) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Every standardised residual, sorted, against normal quantiles (scipy's probplot, the course's
    call), and against the quantiles of a Student-t fitted to them by maximum likelihood, at the
    same plotting positions (Filliben's medians of the uniform order statistics)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df, loc, scale = stats.t.fit(x)
    (normal_q, ordered), _ = stats.probplot(x, dist="norm")
    (t_q, _), _ = stats.probplot(x, dist=stats.t, sparams=(df, loc, scale))
    points = [{"theoretical": float(a), "t_theoretical": float(b), "sample": float(s)} for a, b, s in zip(normal_q, t_q, ordered, strict=True)]
    return points, {"df": float(df), "loc": float(loc), "scale": float(scale)}


def verdicts(lb: list[dict[str, Any]], jb: dict[str, float], arch: list[dict[str, Any]], alpha: float = ALPHA) -> dict[str, str]:
    """Plain verdicts the app keys its fixed text by. Each looks at every row of its test, so with
    several lags a single rejection is enough (no correction for testing several lags)."""
    applied = [r for r in lb if r["applied"]]
    return {
        "serial_correlation": "found" if any(r["p_value"] < alpha for r in applied) else ("not_found" if applied else "not_tested"),
        "normality": "rejected" if jb["p_value"] < alpha else "not_rejected",
        "arch": "found" if any(r["p_value"] < alpha for r in arch) else "not_found",
    }


def model_diagnostics(model_id: str, result: Any, order: list[int], dates: pd.DatetimeIndex) -> tuple[dict[str, Any], dict[str, Any]]:
    """For one fitted model: the test block for `fit.models[].diagnostics`, and the plot series for
    its `residuals_<id>` artifact. `dates` are the training dates, one per observation."""
    burn = burn_in(result)
    std = standardized_residuals(result)
    raw = np.asarray(result.resid, dtype=float)
    p, _, q = order
    lb = ljung_box(std, p + q)
    jb = normality(std)
    arch = arch_lm(std)
    qq, t_fit = qq_points(std)
    acf_rows = correlogram(std)
    acf_squared = correlogram(std**2)
    tests = {
        "n": int(len(std)),
        "burn_excluded": burn,
        # What the course's module-8 plots show first: the residuals the burn-in drops.
        "burned": [
            {"date": dates[i].date().isoformat(), "resid": float(raw[i]), "resid_std": float(result.standardized_forecasts_error[0, i])}
            for i in range(burn)
        ],
        "max_abs_resid_after_burn": float(np.max(np.abs(raw[burn:]))),
        "ljung_box": lb,
        "jarque_bera": jb,
        "arch_lm": arch,
        "verdicts": verdicts(lb, jb, arch),
        "acf_outside_count": acf_rows["outside_count"],
        "acf_squared_outside_count": acf_squared["outside_count"],
    }
    series = {
        "sample": "train",
        "model_id": model_id,
        "n": int(len(std)),
        "burn_excluded": burn,
        "z": Z,
        "nlags": NLAGS,
        "rows": [{"date": dates[burn + i].date().isoformat(), "resid_std": float(v)} for i, v in enumerate(std)],
        "acf": acf_rows,
        "acf_squared": acf_squared,
        "qq": qq,
        "t_fit": t_fit,
    }
    return tests, series


def residual_payloads(fit: dict[str, Any], results: dict[str, Any], dates: pd.DatetimeIndex) -> dict[str, dict[str, Any]]:
    """Add the residual tests to `fit` (each model's `diagnostics`, and the top-level settings and
    clustering verdict), and return the plot series as one `residuals_<id>` payload per model.

    One file per model because three models' series are 1,450,049 bytes together, over the 1 MB
    budget per file (contract.md, size budgets); the app fetches only the model it shows."""
    series = {}
    for model in fit["models"]:
        tests, plot = model_diagnostics(model["id"], results[model["id"]], model["order"], dates)
        model["diagnostics"] = tests
        series[f"residuals_{model['id']}"] = plot
    primary = next(m for m in fit["models"] if m["id"] == fit["primary"])["diagnostics"]
    fit["diagnostic_settings"] = {
        "alpha": ALPHA,
        "series": "standardized_forecasts_error after the burn-in",
        "ljung_box_lags": list(LJUNG_BOX_LAGS),
        "ljung_box_model_df": "p + q",
        "arch_lm_lags": list(ARCH_LM_LAGS),
        "arch_lm_ddof": 0,
        "nlags": NLAGS,
    }
    # Concept note 07 predicted volatility clustering in the primary model's residuals.
    fit["clustering_prediction"] = {
        "model_id": fit["primary"],
        "confirmed": primary["verdicts"]["arch"] == "found",
        "arch_lm_rejections": int(sum(r["p_value"] < ALPHA for r in primary["arch_lm"])),
        "acf_squared_outside_count": primary["acf_squared_outside_count"],
        "acf_squared_expected_by_chance": ALPHA * NLAGS,
    }
    return series
