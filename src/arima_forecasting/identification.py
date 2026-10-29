"""ACF and PACF of the training series at d = 0, 1 and 2, with their 95% bands (contract.md 3.5).

Pure: numpy values in, plain Python values out.

The settings are the ones the course's pictures use. The course calls `plot_acf(x, lags=50)` and
`plot_pacf(x, lags=50)`, and those plotting functions have their own defaults, which differ from
the defaults of the `acf` and `pacf` functions they wrap:

- `plot_acf` passes `fft=False` (`acf` itself defaults to `fft=True`); the two agree to about 1e-16;
- `plot_pacf` uses `method="ywm"`, Yule-Walker with the MLE denominator n (`pacf` itself defaults
  to `"ywadjusted"`, which divides by n - k and can give a value outside [-1, 1]).

The band is the half-width of the shaded area `plot_acf` draws around zero: the upper confidence
limit minus the value (statsmodels/graphics/tsaplots.py:146). For the ACF it is Bartlett's formula,
z * sqrt((1 + 2 * (r_1^2 + ... + r_{k-1}^2)) / n), so it widens with the lag; for the PACF it is
z / sqrt(n) at every lag. z is the 97.5% normal quantile, 1.959963984540054.

Whether a bar reaches past its band is decided here, once, and exported as `acf_outside` and
`pacf_outside` per lag, with the counts per series. The app draws those flags; its reader compares
each value with its band only to check Python's flag, and refuses a file where they disagree. "Past" means |value| > band, strictly; lag 0 is never past (its band is
0 and its value 1 by definition), and the counts run over lags 1 to nlags.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import norm
from statsmodels.tsa.stattools import acf, pacf

from arima_forecasting.stationarity import TRANSFORMS, difference

NLAGS = 50  # the course's lags=50
ALPHA = 0.05
ACF_FFT = False
ACF_ADJUSTED = False
BARTLETT = True
PACF_METHOD = "ywm"


def correlogram(x: np.ndarray, nlags: int = NLAGS, alpha: float = ALPHA) -> list[dict[str, Any]]:
    """One row per lag 0..nlags: the ACF, the PACF and the half-width of each 95% band."""
    if nlags < 1 or nlags >= len(x) // 2:
        raise ValueError(f"nlags must be between 1 and n // 2 - 1 = {len(x) // 2 - 1}, got {nlags}")
    a = acf(x, nlags=nlags, alpha=alpha, fft=ACF_FFT, adjusted=ACF_ADJUSTED, bartlett_confint=BARTLETT, result_object=True)
    p = pacf(x, nlags=nlags, alpha=alpha, method=PACF_METHOD, result_object=True)
    rows = []
    for lag in range(nlags + 1):
        row = {
            "lag": lag,
            "acf": float(a.acf[lag]),
            "pacf": float(p.pacf[lag]),
            "acf_band": float(a.confint[lag, 1] - a.acf[lag]),
            "pacf_band": float(p.confint[lag, 1] - p.pacf[lag]),
        }
        for name in ("acf", "pacf"):
            row[f"{name}_outside"] = outside(lag, row[name], row[f"{name}_band"])
        rows.append(row)
    return rows


def outside(lag: int, value: float, band: float) -> bool:
    """True when the bar at `lag` reaches past its band: |value| > band, at lags 1 and above."""
    return lag >= 1 and abs(value) > band


def acf_pacf_payload(log_close: object, nlags: int = NLAGS, alpha: float = ALPHA) -> dict[str, Any]:
    """The `data` part of the "acf_pacf" artifact. Correlations only; no series values."""
    values = difference(log_close, 0)
    series = []
    for transform_id, d in TRANSFORMS:
        x = difference(values, d)
        rows = correlogram(x, nlags, alpha)
        counts = {f"{name}_outside_count": sum(row[f"{name}_outside"] for row in rows) for name in ("acf", "pacf")}
        series.append({"transform": transform_id, "d": d, "n": int(len(x)), **counts, "rows": rows})
    return {
        "sample": "train",
        "nlags": nlags,
        "alpha": alpha,
        "z": float(norm.ppf(1.0 - alpha / 2.0)),
        "acf_settings": {"fft": ACF_FFT, "adjusted": ACF_ADJUSTED, "bartlett_confint": BARTLETT},
        "pacf_method": PACF_METHOD,
        "series": series,
    }
