# 09 · Parameter inference and root cancellation

Course module 7 prints `model_fit.summary()`: one row per coefficient with an estimate, a standard
error, z, a p-value and an interval. This note covers what those columns mean for an ARMA model,
which standard errors statsmodels uses, why a model with eight or nine parameters can have AR and
MA roots that nearly cancel, what that does to the table, and how to read the unit-circle plot.

## First principles

An **estimate** is the value of a coefficient at the maximum of the likelihood. Another sample from
the same process would give a different estimate; the **standard error** (SE) is the standard
deviation of that sampling variation, estimated from the one sample there is. Maximum likelihood
gives it through the **information**: how sharply the log-likelihood falls away from its peak. A
sharp peak means a precise estimate and a small SE; a flat peak or a flat ridge means an imprecise
one.

**z** is the estimate in units of its SE. The **p-value** is the probability, if the true coefficient
were 0, of a z at least as far from 0 as the one observed. The **95% interval** is the estimate ± 1.96
SE. All three rest on the estimate being approximately normal with that SE, which large-sample
theory gives when the model is well identified.

The **lag polynomials** of an ARMA(p, q) model are $\phi(L) = 1 - \phi_1 L - \dots - \phi_p L^p$
(AR) and $\theta(L) = 1 + \theta_1 L + \dots + \theta_q L^q$ (MA), with $L$ the lag operator
(statsmodels' signs). Each factors into terms $(1 - aL)$; the numbers $a$ are the **inverse roots**.
Every inverse root must lie inside the unit circle: for the AR side, so the model is stationary; for
the MA side, so it is invertible (the shocks can be recovered from the data).

A **common factor** is the same $(1 - aL)$ on both sides. Then

$$
(1 - aL)\,\phi(L)\, y_t = (1 - aL)\,\theta(L)\, \varepsilon_t \quad\text{is the same model as}\quad \phi(L)\, y_t = \theta(L)\, \varepsilon_t ,
$$

for **every** value of $a$. An ARMA(p + 1, q + 1) with an exact common factor is an ARMA(p, q) in
disguise, and the data cannot tell one $a$ from another: the likelihood is exactly flat along a line.
ADR-0002 §7 met the simplest case: ARMA(1, 1) with φ = −θ is white noise, for any φ, so pmdarima and
statsmodels stopped at opposite ends of that ridge, 0.24 apart in log-likelihood. **Near-cancelling**
roots, an AR and an MA inverse root close together, leave the likelihood nearly flat along a curve:
the model is close to a smaller one, and the coefficients that move along the curve are poorly
determined.

## The maths

**z, p and the interval.** For an estimate $\hat\beta$ with standard error $s$,

$$
z = \frac{\hat\beta}{s}, \qquad p = 2\,\bigl(1 - \Phi(|z|)\bigr), \qquad \hat\beta \pm 1.959963984540054\, s ,
$$

with $\Phi$ the standard normal distribution function. Worked from the AIC choice's drift in
`fit.json`: $\hat\beta = 0.000902$, $s = 0.000394$, so $z = 2.29$, $p = 0.022$, and the interval is
0.00013 to 0.00167 log points per day. `sigma2` gets a standard error and an interval but no z and
no p-value (both null in `fit.json`): its null value 0 is on the boundary of the parameter space,
since a variance cannot be negative, and there z is not normal, so the test does not apply. (Its z
would be 49.5, and the p-value would underflow to 0.0.)

**Which standard errors.** With $g_t$ the gradient of day t's log-likelihood at the estimate and $H$
the Hessian of the total log-likelihood, three estimates of the covariance are common:

- **OPG** (outer product of gradients), $\bigl(\sum_t g_t g_t^\top\bigr)^{-1}$: statsmodels' default
  for these fits, `cov_type="opg"`;
- **observed information**, $(-H)^{-1}$: `"oim"` (Harvey's analytic form) or `"approx"` (a
  numerical Hessian);
- **sandwich**, $H^{-1}\bigl(\sum_t g_t g_t^\top\bigr)H^{-1}$: `"robust"`, the quasi-maximum
  likelihood covariance.

OPG and the observed information estimate the same matrix when the **information-matrix equality**
holds, $E[g_t g_t^\top] = -E[H_t]$. Which assumptions that needs depends on the parameter:

- **The AR and MA coefficients**: independent shocks with a constant variance, of any
  distribution. The score of an ARMA coefficient is the shock $\varepsilon_t$ times a function of
  the past, so $E[g_t g_t^\top]$ is $E[\varepsilon_t^2]$ times a matrix of the past; with
  independent shocks the fourth moment never enters, and fat tails do not break the equality. Its
  cross moment with `sigma2`'s score is $E[\varepsilon_t^3]$ times the mean of that function of
  the past, which is 0, so skew does not break it either: this block is immune to the shape of the
  shock distribution.
- **The drift or constant**: independent shocks that are also **not skewed**. Its score is
  $\varepsilon_t/\sigma^2$ times a constant, whose cross moment with `sigma2`'s score is
  $E[\varepsilon_t^3]/(2\sigma^6)$, while the matching Hessian term is 0. With skew $\gamma$ and
  Pearson kurtosis $\kappa$, OPG's variance for the constant is the sandwich's divided by
  $1 - \gamma^2/(\kappa - 1)$, so the sandwich-to-OPG ratio of its error is
  $\sqrt{1 - \gamma^2/(\kappa - 1)}$, below 1 for any skewed shock.
- **`sigma2`**: normal shocks as well. Its score is $(\varepsilon_t^2/\sigma^2 - 1)/(2\sigma^2)$,
  whose variance grows with the kurtosis, so fat tails alone inflate the sandwich error of `sigma2`.

What breaks the equality for the AR and MA coefficients is **volatility clustering** (conditional
heteroskedasticity, concept note 08): after large shocks today's $\varepsilon_t^2$ tends to be
large, and those past shocks are what the ARMA score is made of, so $E[\varepsilon_t^2 \times$ the
past$]$ is no longer $E[\varepsilon_t^2]$ times the past. The sandwich stays valid for the AR and
MA coefficients under clustering, as long as the conditional mean is right; it does not need the
variance to be modelled.

A simulation separates the two causes. AR(1) returns with φ = 0.5, n = 2,036 and 40 series per
row, fitted as ARIMA(1, 0, 0) with a constant; the median ratio of the sandwich error to OPG:

| Shocks | Residual kurtosis | `ar.L1` | `sigma2` |
|---|---|---|---|
| independent normal | 3.01 | 1.01 | 1.01 |
| independent Student-t, df 3.4 (fat tails, no clustering) | 12.93 | 0.96 | 5.92 |
| GARCH(1, 1) with normal innovations (clustering) | 4.27 | 1.75 | 1.63 |

Fat tails alone leave the AR coefficient's sandwich error about equal to OPG (0.96) and make
`sigma2`'s about six times OPG; clustering, with far less kurtosis, makes the AR coefficient's
sandwich error 1.75 times OPG.
The script, run from the repository root with `OPENBLAS_NUM_THREADS=1 .venv/bin/python -I
cov_probe.py` (13.0 s):

```python
import math, warnings
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
warnings.simplefilter("ignore")
rng = np.random.default_rng(20261029)
n, burn, reps, phi = 2036, 500, 40, 0.5

def shocks(kind):
    if kind == "iid normal":
        return rng.standard_normal(n + burn)
    if kind == "iid t(3.4)":  # fat tails, no clustering; scaled to variance 1
        return rng.standard_t(3.4, n + burn) / math.sqrt(3.4 / 1.4)
    z, e, s2 = rng.standard_normal(n + burn), np.zeros(n + burn), 1.0  # GARCH(1, 1), normal innovations
    for t in range(1, n + burn):
        s2 = 0.05 + 0.15 * e[t - 1] ** 2 + 0.80 * s2
        e[t] = math.sqrt(s2) * z[t]
    return e

for kind in ("iid normal", "iid t(3.4)", "GARCH(1, 1)"):
    ratios, kurt = [], []
    for _ in range(reps):
        e = shocks(kind)
        x = np.zeros_like(e)
        for t in range(1, len(e)):
            x[t] = phi * x[t - 1] + e[t]
        res = ARIMA(0.01 * x[burn:], order=(1, 0, 0), trend="c").fit()
        se = {c: res.model.smooth(res.params, cov_type=c).bse for c in ("opg", "robust")}
        ratios.append(se["robust"] / se["opg"])
        s = res.standardized_forecasts_error[0]
        kurt.append(np.mean((s - s.mean()) ** 4) / np.var(s) ** 2)
    med = np.median(ratios, axis=0)
    print(f"{kind:12s} residual kurtosis {np.median(kurt):5.2f} | robust/OPG: ar.L1 {med[1]:.2f}, sigma2 {med[2]:.2f}")
```

It printed:

```text
iid normal   residual kurtosis  3.01 | robust/OPG: ar.L1 1.01, sigma2 1.01
iid t(3.4)   residual kurtosis 12.93 | robust/OPG: ar.L1 0.96, sigma2 5.92
GARCH(1, 1)  residual kurtosis  4.27 | robust/OPG: ar.L1 1.75, sigma2 1.63
```

A second simulation shows the drift's exception. The same AR(1) with a constant, 40 series per
row, now also with independent centred chi-squared(4) shocks (skew 1.41, kurtosis 6): the
constant's sandwich error is 0.772 of OPG, where $\sqrt{1 - \gamma^2/(\kappa - 1)} = \sqrt{1 - 2/5}$
gives 0.775, and the observed information agrees with the sandwich (0.771), so it is OPG that is
off; `ar.L1` stays at 0.98. Run from the repository root with `OPENBLAS_NUM_THREADS=1
.venv/bin/python -I skew_probe.py` (15.1 s):

```python
# AR(1) with a constant: the sandwich and observed-information errors against OPG, normal or skewed iid shocks.
import math, warnings
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
warnings.simplefilter("ignore")
rng = np.random.default_rng(7)
n, burn, reps, phi = 2036, 500, 40, 0.5
for kind in ("iid normal", "iid chi2(4) centred (skew 1.41, kurt 6)"):
    ratios = []
    for _ in range(reps):
        e = rng.standard_normal(n + burn) if kind.startswith("iid normal") else (rng.chisquare(4, n + burn) - 4) / math.sqrt(8)
        x = np.zeros_like(e)
        for t in range(1, len(e)):
            x[t] = phi * x[t - 1] + e[t]
        res = ARIMA(0.01 * x[burn:], order=(1, 0, 0), trend="c").fit()
        se = {c: res.model.smooth(res.params, cov_type=c).bse for c in ("opg", "robust", "oim")}
        ratios.append(np.r_[se["robust"] / se["opg"], se["oim"] / se["opg"]])
    med = np.median(ratios, axis=0)
    print(f"{kind}: robust/OPG const {med[0]:.3f} ar.L1 {med[1]:.3f} sigma2 {med[2]:.3f} | oim/OPG const {med[3]:.3f} ar.L1 {med[4]:.3f}; theory sqrt(1-g^2/(k-1)) = {math.sqrt(1-2/5) if 'chi2' in kind else 1.0:.3f}")
```

It printed:

```text
iid normal: robust/OPG const 0.999 ar.L1 0.996 sigma2 0.992 | oim/OPG const 0.999 ar.L1 0.997; theory sqrt(1-g^2/(k-1)) = 1.000
iid chi2(4) centred (skew 1.41, kurt 6): robust/OPG const 0.772 ar.L1 0.982 sigma2 1.907 | oim/OPG const 0.771 ar.L1 0.990; theory sqrt(1-g^2/(k-1)) = 0.775
```

AAPL's residuals have both fat tails (kurtosis 7.03) and strong clustering (ARCH-LM p 2.4e-50). For
the AIC choice's AR and MA coefficients the sandwich-to-OPG ratio, 1.80 to 1.99, looks like the
clustering row, not the fat-tailed one. Measured on the AIC choice, as a ratio to OPG:

| Coefficients | `"oim"` | `"approx"` | `"robust"` |
|---|---|---|---|
| `ar.L1` … `ar.L3`, `ma.L1` … `ma.L4` | 1.30 to 1.37 | 1.37 to 1.45 | 1.80 to 1.99 |
| drift | 0.95 | 0.95 | 0.95 |
| `sigma2` | 1.55 | 1.55 | 2.69 |

With the sandwich errors, `ar.L3`'s z falls from −2.64 to −1.42 and `ma.L3`'s from 1.58 to 0.85:
two of the seven ARMA coefficients are below 1.96 in absolute value. The project keeps OPG, because
it is what the course's `summary()` prints, and records `cov_type` in the file so a reader knows
which errors these are.

**How cancellation inflates the error.** For ARMA(1, 1), $y_t = \phi y_{t-1} + \varepsilon_t + \theta\varepsilon_{t-1}$,
the large-sample variance of $\hat\phi$ is

$$
\operatorname{Var}(\hat\phi) \approx \frac{1}{n}\,\frac{(1 + \phi\theta)^2 (1 - \phi^2)}{(\phi + \theta)^2} .
$$

The inverse roots are $\phi$ (AR) and $-\theta$ (MA), so $\phi + \theta$ is the signed distance
between them. As the roots approach each other the denominator goes to 0 and the variance grows
without bound. Measured with $n = 2036$, $\phi = 0.5$ and 200 simulated series per row:

| θ | AR and MA inverse roots | Distance | Formula SD of $\hat\phi$ | SD of 200 estimates | 5% to 95% of $\hat\phi$ | corr($\hat\phi$, $\hat\theta$) |
|---|---|---|---|---|---|---|
| 0.3 | 0.5 and −0.3 | 0.80 | 0.0276 | 0.0266 | 0.455 to 0.541 | −0.758 |
| −0.3 | 0.5 and 0.3 | 0.20 | 0.0816 | 0.0820 | 0.347 to 0.608 | −0.974 |
| −0.45 | 0.5 and 0.45 | 0.05 | 0.2975 | 0.3793 | −0.420 to 0.866 | −0.998 |

At distance 0.05 the estimate ranges over most of the stationary region, the two estimates move
almost in lockstep (correlation −0.998: along the ridge), and even the formula understates the
spread (0.298 against 0.379), because the normal approximation behind it has not taken hold. The
script and its output are in concept note 08.

The numerator matters too: $(1 - \phi^2)$ shrinks as the AR root approaches the unit circle, where
persistent dynamics are estimated precisely. So **distance alone does not set the standard error.**

## Why an eight- or nine-parameter ARMA cancels

The main reason is that daily log returns are close to white noise. Over lags 1 to 50 their sample
autocorrelations are all below 0.1 in absolute value (the largest, at lag 9, is 0.099; 11 of 50 lie
past Bartlett's band, a band too narrow for returns, concept note 06; `acf_pacf.json`), so the
right model for them is close to "no dynamics". An
ARMA(3, 4) whose three AR factors and four MA factors did not nearly cancel would describe strong
autocorrelation that the data do not have. Fitted to near-white-noise returns, the extra AR and MA
factors must nearly divide out, and what is left after the near-cancellation is a small correction
to white noise.

Why AIC adds them at all: it adds a pair of AR and MA terms when they raise the log-likelihood by
more than 2. A near-common
factor costs two parameters and changes the model only a little everywhere, but it can bend the fit
towards a short episode: milestone 2 found about three quarters of the AIC choice's gain over
ARIMA(0, 1, 1) in 72 days of spring 2020. With p = 3 and q = 4 there are many ways for the two
polynomials to nearly share a factor, and the likelihood surface has ridges and several local
maxima, which is why milestone 2 needed many starts per cell.

## Reading the unit circle

Plot each inverse root as a point in the complex plane: AR roots and MA roots with different marks.

- **Modulus** (distance from 0): how persistent that component is. A root at 0.93 decays by 7% a
  day; a root near 1 is near a unit root (AR) or near over-differencing (MA).
- **Angle**: a complex pair at ±ω degrees is a damped cycle of period 360 / ω days. A real negative
  root (180°) makes consecutive days alternate in sign.
- **An AR root next to an MA root** nearly cancels: that part of the model does almost nothing, and
  the coefficients that build it are poorly identified.

The AIC choice, ARIMA(3, 1, 4) with a drift, measured in the milestone-3 walkthrough:

| Root | AR | MA |
|---|---|---|
| complex pair | −0.842 ± 0.398i: modulus 0.932, ±154.7° | −0.782 ± 0.414i: modulus 0.885, ±152.1° |
| real | −0.465 | −0.683 and 0.155 |

The complex pair is a cycle of 360 / 154.7 = 2.33 days, nearly cancelled: each AR root is 0.0625
from its MA partner. The real AR root −0.465 and MA root −0.683 are 0.218 apart, a looser near-pair.
Its AR and MA coefficients come out large, opposite in sign and imprecise: `ar.L1` −2.150 (SE 0.166)
against `ma.L1` 2.092 (SE 0.169).

The BIC choice, ARIMA(2, 1, 2): AR pair at modulus 0.960 and ±159.0°, MA pair at 0.930 and ±160.3°,
0.0371 apart, closer than the AIC choice's pair, yet its SEs are 0.023 to 0.030 and every |z| is
above 29. Its roots sit nearer the unit circle, where the $(1 - \phi^2)$ factor makes estimates
precise, and it has no second near-pair. Which of these explains the AIC choice's larger errors was
not measured; the comparison shows only that the distance between a pair does not decide it alone.

## The rule the project states, and its threshold

`cancelling_pairs` considers every AR–MA pair whose distance in the complex plane is at most
`CANCEL_DISTANCE` = 0.1, and takes a one-to-one matching of them with as many pairs as possible,
and among those the least total distance (a maximum matching, solved with scipy's
`linear_sum_assignment`; Python's validator restates it by dynamic programming). Closest first is
not the same rule: AR roots {0.5, 0.6} and MA roots {0.51, 0.41} give one pair that way (0.5 with
0.51, 0.01 apart, which leaves 0.6 and 0.41, 0.19 apart), while two pairs within 0.1 exist (0.5 with
0.41 and 0.6 with 0.51, 0.09 each). On AAPL both rules give the same pairs. The rule flags both
complex pairs of the AIC choice (0.0625) and of the BIC choice (0.0371), and not the AIC choice's
real pair (0.218); with a threshold of 0.25 it would flag that one too. The threshold is a **display rule**:
it is stated so that a reader can apply it to the exported roots, and the app rings exactly the
pairs Python exports. It is not a test of a common factor, and a flagged pair says "read these
coefficients together", not "this model is wrong".

## Assumptions

- The estimates are near the true values and approximately normal, so z and the interval mean what
  they say. That fails along a near-flat ridge.
- OPG and observed-information errors assume the information-matrix equality. For the AR and MA
  coefficients that needs independent shocks with a constant variance (any distribution); for the
  drift or constant, shocks that are not skewed as well; for `sigma2`, normal shocks. The sandwich needs only the conditional mean to be right for
  the AR and MA coefficients; it does not need the variance to be modelled.
- Inverse roots are computed from the estimates; they carry the estimates' uncertainty. A pair
  0.06 apart could be closer or farther in another sample.

## Where it breaks

- **On a ridge, individual coefficients are not interpretable.** A p-value for `ar.L2` alone asks
  whether one coordinate of a point on a ridge is 0; the answer depends on where along the ridge the
  optimiser stopped. Test or report the model, or a function of it that is identified (a forecast,
  an impulse response), not the coefficient.
- **The normal approximation fails before the SE looks alarming**, as the 0.05 row of the table
  shows (0.379 measured against 0.298 predicted).
- **A distance threshold has no scale.** Near the unit circle a small distance can still be well
  identified (the BIC choice); far inside it, a larger distance can be poorly identified.
- **OPG is not robust to volatility clustering.** For the AR and MA coefficients it understates the
  errors when the variance clusters (here the sandwich errors of the AIC choice are up to 1.99 times
  OPG); fat tails alone do not do that, but they do inflate `sigma2`'s (the simulation above).

## In this project

- `src/arima_forecasting/fitting.py:130` builds each parameter row: z, the p-value and the interval
  from the estimate and statsmodels' OPG standard error (`COV_TYPE`, `:59`), all null together when
  the error is unusable, and `sigma2`'s z and p-value null always (`:144`).
- `src/arima_forecasting/fitting.py:98` computes the inverse roots and `:110` applies the
  cancelling rule with `CANCEL_DISTANCE` (`:57`).
- `tests/test_fitting.py:108` checks z and p against statsmodels' own, `tests/test_fitting.py:51`
  works the cancelling rule by hand, and `tests/test_fitting.py:69` shows where closest first would
  differ.
- `src/arima_forecasting/payloads.py:1464` restates the rule in Python's validator (the number of
  pairs and their total distance, by dynamic programming); the app draws the exported pairs on the
  unit circle (`app/src/views/FitView.tsx:242`).
- The covariance comparison above came from `m3_probe.py` in the milestone-3 walkthrough
  (Measured results), which recomputes the four covariance types at the refitted estimates with
  statsmodels' `smooth(params, cov_type=…)`.
