# 08 · Residual diagnostics: Ljung–Box, Jarque–Bera, ARCH-LM and the burn-in

Course module 8 checks a fitted model by looking at what it leaves over. This note covers the
three tests milestone 3 runs on each model's residuals, what each one's null hypothesis is, why
Ljung–Box loses p + q degrees of freedom, why the first residual of a d = 1 model must be dropped,
and what a p-value does and does not say. Concept note 06 covers the ACF band these tests share.

## First principles

A model of the log price says: tomorrow's change is a predictable part plus a **shock**, and the
shocks are independent draws with mean 0 and one fixed variance. The **one-step forecast error**
(the residual) at day t is the observed value minus the model's forecast of it made on day t − 1.
If the model is right, the residuals estimate the shocks, so they should look like **white noise**:
no autocorrelation, constant variance and, if the model assumed normal shocks, a normal shape.

Each test asks one of those questions. It starts from a **null hypothesis**, the statement that
the residuals have the property, computes a **statistic** that grows when they do not, and reports
a **p-value**: the probability, if the null were true, of a statistic at least as extreme as the one
observed. A small p-value means the data would be surprising under the null. "Rejected at 5%" means
p < 0.05.

| Test | Null hypothesis | What a rejection means |
|---|---|---|
| Ljung–Box at lag h | the residual autocorrelations at lags 1 to h are all zero | the model left a predictable pattern in the mean |
| Jarque–Bera | skew 0 and kurtosis 3, as for a normal distribution | the shocks are not normal: intervals built on the normal are wrong in the tails |
| ARCH-LM with m lags | the squared residuals are not predictable from their own last m values | **volatility clustering**: calm and stormy days come in runs, so the variance is not constant |

The tests run on the **standardised** one-step errors: each residual divided by the standard
deviation the model gave its forecast. Under the model these are independent N(0, 1), whatever the
forecast variance was that day.

## The maths

**Ljung–Box.** With $n$ residuals and sample autocorrelations $r_k$,

$$
Q(h) = n(n + 2) \sum_{k=1}^{h} \frac{r_k^2}{n - k} .
$$

For white noise that nobody fitted, $Q(h)$ is approximately $\chi^2$ with h degrees of freedom. For
the residuals of a fitted ARMA(p, q) it is approximately $\chi^2$ with **h − (p + q)**. The
estimates were chosen to make the residuals as uncorrelated as possible, which pushes the first few
$r_k$ towards zero: p + q of the h squared autocorrelations are "used up" by the fit, so $Q$ is
smaller than it would be for raw noise. Comparing it with $\chi^2_h$ makes the test too lenient.
The trend term and the variance do not enter the ARMA dynamics, so they are not subtracted.

Measured on 400 simulated ARMA(1, 1) series of 1,000 days (φ = 0.5, θ = 0.3), each fitted with
ARMA(1, 1), so the null is true and a 5% test should reject about 5% of the time (each rate is
within about ±1.1 percentage points from sampling):

| Lag | Rejects with h df (`model_df` 0) | Rejects with h − 2 df (`model_df` 2) |
|---|---|---|
| 5 | 1.0% | 2.75% |
| 10 | 1.5% | 4.25% |
| 20 | 2.75% | 4.75% |

Without the correction the test almost never rejects at lag 5. With it the rates move to 5%; at
lag 5 they are still low, because the asymptotic $\chi^2$ is a poor fit when only 3 degrees of
freedom remain.

**At a lag ≤ p + q** there are no degrees of freedom left: $\chi^2_0$ is not a distribution, and
statsmodels' `acorr_ljungbox` returns NaN for the p-value there (measured: lag 2 with `model_df` 2
gives `[nan]`). The project marks such a row `applied: false` with a null p-value. For the AIC
choice, ARIMA(3, 1, 4), p + q = 7, so lag 5 tests nothing.

**A worked Ljung–Box.** The AIC choice at lag 10: $Q = 4.821$ on 10 − 7 = 3 degrees of freedom,
p = 0.185. statsmodels' own `test_serial_correlation(df_adjust=True)` subtracts the number of
estimated parameters minus one (statsmodels/tsa/statespace/mlemodel.py:3745), which here counts the
drift: 8, leaving 2. A $\chi^2_2$ tail is $e^{-Q/2}$, so $p = e^{-4.821/2} = e^{-2.411} = 0.0898$,
the value statsmodels prints. Both are above 0.05. For ARIMA(2, 1, 2) without a drift the two rules
agree (4).

**Jarque–Bera.** With sample skew $S$ and sample kurtosis $K$ (Pearson's, so a normal has 3),

$$
JB = \frac{n}{6}\left(S^2 + \frac{(K - 3)^2}{4}\right) ,
$$

approximately $\chi^2_2$ under the null. Worked for the AIC choice ($n = 2036$, $S = -0.3242$,
$K = 7.0324$): $\tfrac{2036}{6}(0.1051 + 16.261/4) = 339.33 \times 4.1702 = 1415.10$, the exported
statistic. The $\chi^2_2$ tail is again $e^{-JB/2} = e^{-707.55} \approx 5.2 \times 10^{-308}$, near the
smallest positive double. For the BIC and course models the statistic is larger and the p-value
underflows to 0.0.

**ARCH-LM (Engle's test).** Regress the squared residual on a constant and its own last m values:

$$
e_t^2 = a_0 + a_1 e_{t-1}^2 + \dots + a_m e_{t-m}^2 + u_t .
$$

The statistic is $(n - m) R^2$, the number of rows in the regression times its $R^2$, and it is
approximately $\chi^2_m$ under the null of no ARCH effect. $R^2$ is the share of the day-to-day
variation in squared residuals that the last m squared residuals explain. Worked for the AIC choice
with 5 lags: LM = 242.39 on 2,031 rows, so $R^2 = 0.119$; with 10 lags, $R^2 = 0.136$. About 12%
of the variation in the size of each day's shock is predictable from the sizes of the shocks just
before it: volatility clusters. statsmodels' `het_arch` squares the residuals itself, and the
project uses `ddof=0`, Engle's form, without subtracting the ARMA parameters.

**The squared-residual ACF** shows the same thing as a picture. Under the null each autocorrelation
of $e_t^2$ is about N(0, 1/n), so the band is $z/\sqrt n = 1.959964/\sqrt{2036} = 0.04344$ at every
lag, and about 2.5 of 50 bars cross it by chance. For the AIC choice 29 of 50 do.

## The burn-in: why the first residual is the price

A d = 1 model forecasts the change in the log price. To forecast the first observation it would
need the level the day before, which nobody has. statsmodels' state-space ARIMA handles this with
an **approximate diffuse** start: the unknown level begins at 0 with a huge variance, 10⁶ by default
(`initial_variance=1e6`, statsmodels/tsa/statespace/representation.py:249). So:

- the forecast of the first log price is 0 (plus the drift, for a model with one), and the first
  residual is the first log price itself: 3.1852 on AAPL, 3.1843 for the drift model;
- its forecast variance is about 10⁶, so its standardised value is about 3.185 / 1000 = 0.0032.
  Measured: (resid / resid_std)² = 1,000,000.00036.

That observation carries no information about the shocks. statsmodels knows it: SARIMAX sets
`loglikelihood_burn` to the number of diffuse states, d (statsmodels/tsa/statespace/sarimax.py:679-683),
and leaves those observations out of the likelihood. Its own `plot_diagnostics` drops
max(`loglikelihood_burn`, `nobs_diffuse`) residuals before plotting (statsmodels/tsa/statespace/mlemodel.py:5345).
The project uses the same rule; it gives 1 for all three models.

The raw residual of 3.185 against later ones within 0.13 dominates anything drawn from `resid`
whole. A normal QQ plot of the course model's raw residuals has its top point at 3.185 and the next
at 0.105; the lowest is −0.129, so every other point is squeezed into the bottom 7% of the vertical
axis ((0.105 + 0.129) / (3.185 + 0.129) = 0.071). The
standardised value, 0.0032, sits in the middle of the cloud and would hide instead.

## What a p-value is not

- **Not the probability that the null is true.** p = 0.185 for Ljung–Box does not mean an 18.5%
  chance that the residuals are white noise. It means a statistic this large or larger would occur
  18.5% of the time if they were.
- **Not "the null is true" when large.** A test that does not reject has found no evidence against
  the null at that lag, with that sample. The AIC choice's lag-10 and lag-20 results say the
  residuals carry no autocorrelation these lags can detect, not that there is none.
- **Not a size of effect.** With 2,036 residuals a tiny departure gives a tiny p-value. A Jarque–Bera
  p of 10⁻³⁰⁸ says the sample is large as much as it says the tails are fat; the kurtosis, 7.03, is
  the size.
- **Not corrected for several looks.** Each test here runs at several lags (Ljung–Box at 5, 10 and
  20; ARCH-LM at 5 and 10), and the verdict is "found" if any row rejects. That raises the chance of
  a false alarm above 5%. In the simulation above, with the null true and `model_df` 2, at least one
  of the three Ljung–Box lags rejected in 7.75% of the 400 series. Three independent tests would give
  1 − 0.95³ = 14.3%; the three statistics share their first lags, so they are strongly correlated and
  the inflation is smaller. Likewise, of 50 ACF bars about 2.5 cross the band by chance. The project
  states this and applies no correction.

## Assumptions

- The model's parameters are estimated consistently, so the residuals approach the shocks as n
  grows.
- For Ljung–Box: the shocks are independent with constant variance (the $\chi^2$ approximation uses
  both). For Jarque–Bera: they are independent and n is large (the $\chi^2_2$ is asymptotic).
- For ARCH-LM: the conditional mean is right, so what is left in the squares is variance, not a
  missed pattern in the mean.
- The burn-in rule assumes statsmodels' default initialisation; an exact diffuse start reports the
  same observations through `nobs_diffuse` instead.

## Where it breaks

- **Volatility clustering distorts Ljung–Box.** Concept note 06 measured that under GARCH(1, 1) a
  lag-1 band is crossed 12.1% of the time instead of 5%. The same excess variance inflates $Q$, so on
  residuals that cluster Ljung–Box rejects too often. A non-rejection, as for the AIC choice, is
  therefore not weakened by clustering; a rejection, as for the BIC and course models, may be partly
  caused by it.
- **Outliers drive all three.** One crash week can supply most of a large ARCH-LM statistic or a
  large kurtosis. The tests do not say whether the effect is persistent or one episode; milestone 2
  found much of the AIC choice's gain in spring 2020.
- **Few degrees of freedom left.** At lag h just above p + q the $\chi^2$ approximation is poor (the
  table above, lag 5).
- **The order of the lags matters for power.** A pattern at lag 7 shows in $Q(10)$ diluted by nine
  other lags. Ljung–Box is a portmanteau test: broad, not sharp.
- **Jarque–Bera with large n** rejects any visible departure from normality; read the skew and
  kurtosis, and the QQ plot, for how far.

## In this project

- `src/arima_forecasting/diagnostics.py:59` is the burn-in rule and `:65` the series every test sees.
- `src/arima_forecasting/diagnostics.py:83` runs Ljung–Box with `model_df` = p + q, passed at `:152`,
  and marks a lag ≤ p + q not applied (`:88`).
- `src/arima_forecasting/diagnostics.py:102` runs ARCH-LM with `ddof=0`, `:116` Jarque–Bera, and `:75`
  the residual ACFs with the band z/√n.
- `src/arima_forecasting/diagnostics.py:134` turns the p-values into the verdicts the app shows, "any
  row rejects", without a correction.
- `tests/test_diagnostics.py:52` checks the p + q rule and the skipped lags, `tests/test_diagnostics.py:91`
  that ARCH-LM finds clustering where there is some and not in white noise, and
  `tests/test_diagnostics.py:43` that the burned residual is the level.
- The milestone-3 walkthrough has every measured value for the three models.

### The script behind the simulation and the worked numbers

Run from the repository root with `OPENBLAS_NUM_THREADS=1 .venv/bin/python -I concept_probe.py`
(21.5 s). Section 2 is used by concept note 09.

```python
import json, warnings
import numpy as np
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.arima.model import ARIMA
warnings.simplefilter("ignore")
rng = np.random.default_rng(20261029)

def arma11(phi, theta, n):
    e = rng.standard_normal(n + 200); x = np.zeros(n + 200)
    for t in range(1, n + 200):
        x[t] = phi * x[t - 1] + e[t] + theta * e[t - 1]
    return x[200:]

# 1. Ljung-Box on the residuals of a fitted ARMA(1, 1), the null true: how often p < 0.05.
reps, rej, any3 = 400, {0: np.zeros(3), 2: np.zeros(3)}, 0
for _ in range(reps):
    s = ARIMA(arma11(0.5, 0.3, 1000), order=(1, 0, 1), trend="n").fit().standardized_forecasts_error[0]
    for df in (0, 2):
        p = acorr_ljungbox(s, lags=[5, 10, 20], model_df=df)["lb_pvalue"].to_numpy()
        rej[df] += p < 0.05
    any3 += (p < 0.05).any()
print("LB rejection rate, lags 5/10/20: model_df 0", rej[0] / reps, "model_df 2", rej[2] / reps, "any of the three (df 2)", any3 / reps)
print("lag 2 with model_df 2:", acorr_ljungbox(s, lags=[2], model_df=2)["lb_pvalue"].tolist())

# 2. ARMA(1, 1): the spread of phi-hat against the asymptotic formula, as the roots approach each other.
n = 2036
for phi, theta in ((0.5, 0.3), (0.5, -0.3), (0.5, -0.45)):
    formula = np.sqrt((1 + phi * theta) ** 2 * (1 - phi**2) / (phi + theta) ** 2 / n)
    est = np.array([ARIMA(arma11(phi, theta, n), order=(1, 0, 1), trend="n").fit().params[:2] for _ in range(200)])
    print(f"phi {phi} theta {theta} (inverse roots {phi} and {-theta}, {abs(phi + theta):.2f} apart): formula sd {formula:.4f},"
          f" sd of 200 estimates {est[:, 0].std():.4f}, phi-hat 5-95% {np.percentile(est[:, 0], 5):.3f} to {np.percentile(est[:, 0], 95):.3f},"
          f" corr(phi-hat, theta-hat) {np.corrcoef(est.T)[0, 1]:.3f}")

# 3. Arithmetic on the committed fit.json (the AIC choice).
m = json.load(open("app/public/data/fit.json"))["data"]["models"][0]; g = m["diagnostics"]; jb = g["jarque_bera"]
print("JB by hand", g["n"] / 6 * (jb["skew"] ** 2 + (jb["kurtosis"] - 3) ** 2 / 4), "file", jb["statistic"])
for row in g["arch_lm"]:
    print("ARCH-LM", row["lags"], "lags: R^2 =", row["statistic"] / (g["n"] - row["lags"]))
for kind in ("inv_roots_ar", "inv_roots_ma"):
    print(kind, [(round(r["modulus"], 3), round(float(np.degrees(np.arctan2(r["im"], r["re"]))), 1)) for r in m[kind]])
b = g["burned"][0]; print("burned: resid", b["resid"], "resid_std", b["resid_std"], "implied forecast variance", (b["resid"] / b["resid_std"]) ** 2)
```

It printed:

```text
LB rejection rate, lags 5/10/20: model_df 0 [0.01   0.015  0.0275] model_df 2 [0.0275 0.0425 0.0475] any of the three (df 2) 0.0775
lag 2 with model_df 2: [nan]
phi 0.5 theta 0.3 (inverse roots 0.5 and -0.3, 0.80 apart): formula sd 0.0276, sd of 200 estimates 0.0266, phi-hat 5-95% 0.455 to 0.541, corr(phi-hat, theta-hat) -0.758
phi 0.5 theta -0.3 (inverse roots 0.5 and 0.3, 0.20 apart): formula sd 0.0816, sd of 200 estimates 0.0820, phi-hat 5-95% 0.347 to 0.608, corr(phi-hat, theta-hat) -0.974
phi 0.5 theta -0.45 (inverse roots 0.5 and 0.45, 0.05 apart): formula sd 0.2975, sd of 200 estimates 0.3793, phi-hat 5-95% -0.420 to 0.866, corr(phi-hat, theta-hat) -0.998
JB by hand 1415.102202051986 file 1415.102202051986
ARCH-LM 5 lags: R^2 = 0.11934344463928515
ARCH-LM 10 lags: R^2 = 0.13586966242080012
inv_roots_ar [(0.932, -154.7), (0.932, 154.7), (0.465, 180.0)]
inv_roots_ma [(0.885, -152.1), (0.885, 152.1), (0.683, 180.0), (0.155, 0.0)]
burned: resid 3.1842828594658132 resid_std 0.003184282858899791 implied forecast variance 1000000.0003555102
```

The ±1.1 points of sampling error is $\sqrt{0.05 \times 0.95 / 400} = 0.011$. The worked
$e^{-Q/2}$ and $e^{-JB/2}$ values use the exported statistics; the first matches statsmodels'
printed 0.08976588 (walkthrough, Q4), the second the exported 5.18e-308.
