# Background: forecasting a daily stock price with ARIMA, from first principles

**Status:** milestone-0 concept note, written 2026-10-28. It contains no AAPL results. Every
number below comes either from a cited source or from a probe run on **simulated** data against
the pinned library versions. No market data was downloaded.

**How to read it.** Each section builds one idea from first principles and ends with two lists:
**Assumptions** (what must hold for the idea to work) and **Where it breaks** (what goes wrong on
real prices). Library facts carry `file:line` footnotes into the installed packages.[^versions]
The sample course this repo follows is called "the course".

**Notation.** $t = 1, \dots, T$ indexes trading days, with $T$ observations used for fitting.
$P_t$ is the adjusted close (Section 10 explains "adjusted"). $y_t = \log P_t$ is the log price.
$r_t = y_t - y_{t-1}$ is the daily log return. $\varepsilon_t$ is white noise: mean 0, variance
$\sigma^2$, uncorrelated over time. $\hat y_{T+h \mid T}$ is the forecast of $y_{T+h}$ made with
data up to day $T$, at horizon $h$.

---

## 1. Prices, log prices and log returns

A **time series** is a sequence of observations whose order carries information: shuffle the
rows of a price series and it means nothing.

Prices compound. With simple return $R_t = P_t/P_{t-1} - 1$, we have $P_t = P_{t-1}(1 + R_t)$.
Taking logs turns the product into a sum:

$$
y_t = y_{t-1} + r_t, \qquad r_t = \log(1 + R_t), \qquad y_{t+h} - y_t = \sum_{j=1}^{h} r_{t+j}.
$$

Multi-day log returns are sums of daily ones, and linear models like ARIMA work with sums.

The log scale also **stabilises the variance**. If percentage moves have a roughly constant
spread, $\operatorname{sd}(R_t) \approx \sigma$, then the dollar change $P_{t-1}R_t$ has spread
$\approx \sigma P_{t-1}$: the series gets noisier as the price rises. The log step
$r_t \approx R_t$ keeps spread $\sigma$ at any price level, which matches ARIMA's assumption of a
constant innovation variance. And since $P_t = e^{y_t} > 0$, a model for $y_t$ can never forecast
a negative price.

**Jensen's inequality** is the catch. For a random $X > 0$, $\mathbb{E}[\log X] \le \log \mathbb{E}[X]$
because $\log$ is concave. If $r_t \sim N(\mu, \sigma^2)$, then
$\mathbb{E}[1 + R_t] = \mathbb{E}[e^{r_t}] = e^{\mu + \sigma^2/2}$. With an illustrative
$\mu = 0.0008$ and $\sigma = 0.018$, the mean simple return is 0.096% a day against a mean log
return of 0.080%. The same gap returns in Section 8, when a log forecast is turned back into
dollars.

**Assumptions**

- Percentage moves, not dollar moves, have a roughly stable distribution.
- Prices are strictly positive.

**Where it breaks**

- The spread of returns clusters in calm and turbulent spells (Section 7). The log removes the
  dependence on the price *level*, not on volatility *regimes*.
- $\exp$ of a mean log forecast is a median, not a mean (Section 8).
- The course decomposes the *log* series *multiplicatively*. The log already made the structure
  additive, so this treats $\log P_t$ as a product of components. statsmodels' default
  decomposition is also a centred moving average that uses future values.[^decomp]

---

## 2. The random walk with drift: the null model for prices

The **random walk with drift** for the log price is

$$
y_t = \mu + y_{t-1} + \varepsilon_t \quad\Longleftrightarrow\quad r_t = \mu + \varepsilon_t,
$$

with drift $\mu$ (the mean daily log return) and $\varepsilon_t$ independent and identically
distributed (iid). From a start value $y_0$, $y_t = y_0 + t\mu + \sum_{j=1}^{t}\varepsilon_j$, so
$\operatorname{Var}(y_t \mid y_0) = t\sigma^2$ grows without bound. In ARIMA terms this is
ARIMA(0,1,0) with a constant.

**Efficient markets.** Fama (1970, pp. 384–387) sets out three nested models. In the
**fair-game** model, returns in excess of their equilibrium expected value have zero mean given
the information set, so no rule based on that information beats the equilibrium return. The
**submartingale** adds that expected returns are non-negative. The **random walk** adds that
returns are iid, which Fama calls much more than efficiency requires (p. 387). In a footnote he
says the accurate name is "random walk with drift", and that if *returns* are iid then it is not
the dollar price that walks, because dollar changes scale with the price level (p. 386, fn. 4).
That is the log-price model above. He sorts tests into **weak form** (past prices only),
**semi-strong form** (all public information) and **strong form** (any information) (p. 383), and
describes the hypothesis as "obviously an extreme null hypothesis" (p. 388).

Efficiency does **not** imply:

- **iid returns.** The fair-game model constrains only the conditional *mean*: the mean return
  does not depend on the information set. The random walk adds that the *whole* distribution
  does not depend on it, an extra independence assumption that Fama calls superfluous for
  expected-return efficiency (p. 387). So predictable volatility (Section 7) is consistent with
  the fair-game model, but not with the random walk. Fama's footnote 5 (p. 387) makes the
  second point: under the random walk, past returns still help estimate the (stationary) return
  distribution, but their order "is of no consequence".
- **Zero expected return.** A positive drift (a risk premium) is consistent with it.
- **A standalone test.** Every test assumes a model of equilibrium expected returns, so a
  rejection may mean a wrong return model rather than an inefficient market (p. 384).

**Why the random walk is the baseline.** Weak-form efficiency says past prices should not predict
the expected return beyond the drift, and ARIMA uses nothing but past prices. ARIMA(0,1,0) is
nested in every ARIMA($p$,1,$q$): if the larger model cannot beat its own special case out of
sample, its extra parameters are fitting noise. It is hard to beat in practice (Section 9). And a
price RMSE means nothing alone: \$4 is good or bad only relative to "tomorrow equals today" on
the same days.

**The drift is hard to see.** The t-statistic of the mean return after $n$ days is about
$\mu\sqrt{n}/\sigma$: with the numbers above, 0.71 after one year and 2.23 after ten. In one
simulated 2,000-day path with true $\mu = 0.0008$, the estimate was 0.00029 and AIC preferred no
drift.[^probe-drift] Yet over long horizons the drift moves the forecast more than $p$ and $q$
do, so the repo treats it as a decision in its own right
([ADR-0002](../adr/0002-order-selection.md)).

**Assumptions**

- Log returns are iid with one mean and variance over the whole sample, or at least uncorrelated
  in mean.

**Where it breaks**

- Volatility clusters, so returns are uncorrelated but not independent. The mean forecast
  survives; the intervals do not.
- Lo & MacKinlay (1988) reject the random walk for weekly US index and size-portfolio returns over
  1962–1985, mostly because of small stocks. Rejecting a null is not the same as beating it on
  forecast error.
- One drift over nine years ignores regime changes.

---

## 3. Stationarity, unit roots and differencing

A series $x_t$ is **weakly stationary** if, for all $t$ and lags $k$,
$\mathbb{E}[x_t] = m$, $\operatorname{Var}(x_t) = \gamma_0 < \infty$ and
$\operatorname{Cov}(x_t, x_{t-k}) = \gamma_k$, where the mean $m$ and variance $\gamma_0$ are
constants and the autocovariance $\gamma_k$ depends only on $k$. Sample autocorrelations,
standard errors and information criteria all assume this.

**Backshift operator.** $Bx_t = x_{t-1}$ and $B^k x_t = x_{t-k}$. The first difference is
$\nabla x_t = (1 - B)x_t = x_t - x_{t-1}$
([FPP3 §9.2](https://otexts.com/fpp3/arima.html#sec-backshift)).

**Unit roots.** The AR(1) model $x_t = \phi x_{t-1} + \varepsilon_t$ is $(1 - \phi B)x_t = \varepsilon_t$.
Replacing $B$ by a number $z$, the polynomial $1 - \phi z$ has root $z = 1/\phi$.

- $|\phi| < 1$: the root lies outside the unit circle, shocks decay like $\phi^k$, and the series
  is stationary with $\gamma_0 = \sigma^2/(1 - \phi^2)$.
- $\phi = 1$: the root is $z = 1$, a **unit root**. This is the random walk: shocks never decay
  and the variance grows with $t$.

For a general AR polynomial $\phi(B) = 1 - \phi_1 B - \dots - \phi_p B^p$, a unit root means
$\phi(1) = 0$, so $\phi(B) = \phi^\ast(B)(1 - B)$, where all roots of $\phi^\ast$ lie outside the
unit circle.

**Why differencing works.** If $\phi^\ast(B)(1 - B)y_t = \varepsilon_t$, then $w_t = \nabla y_t$
obeys $\phi^\ast(B)w_t = \varepsilon_t$, which is stationary: differencing cancels the unit-root
factor. A series needing $d$ differences is **integrated of order $d$**, I($d$). Log prices are
treated as I(1), so $w_t = r_t$.

**Over-differencing.** Differencing a series that is already stationary does damage. If
$x_t = \varepsilon_t$, then $\nabla x_t = \varepsilon_t - \varepsilon_{t-1}$: an MA(1) with
coefficient $-1$, variance $2\sigma^2$ and lag-1 autocorrelation $-1/2$. Its MA root sits on the
unit circle, so it is non-invertible (Section 5). The signature is a lag-1 autocorrelation near
$-0.5$ and a fitted MA(1) coefficient near $-1$ (Plosser & Schwert 1977). On simulated white noise
these came out at $-0.486$ and $-0.995$.[^probe-overdiff]

**Assumptions**

- The non-stationarity is a unit root, not a deterministic trend or a structural break.
- One difference suffices (prices are I(1), not I(2)).

**Where it breaks**

- You see one finite path of the process. Tests give evidence, not proof.
- A 12-day rolling mean and standard deviation, as the course plots them, are a visual aid, not a
  test.
- A KDE of log-price *levels* describes one path. A non-stationary series has no fixed marginal
  distribution for it to estimate.

---

## 4. Testing for a unit root: ADF and KPSS

**Augmented Dickey–Fuller.** Dickey & Fuller (1979) derived the distribution of the least-squares
AR(1) estimate when the true $\phi = 1$. The test regression is

$$
\Delta y_t = \alpha + \beta t + \gamma\, y_{t-1} + \sum_{i=1}^{k} \delta_i\, \Delta y_{t-i} + e_t,
$$

where $\alpha$ (constant) and $\beta t$ (linear trend) are the optional **deterministic terms**,
$\gamma = \phi - 1$, the $k$ lagged differences with coefficients $\delta_i$ are the
**augmentation**, and $e_t$ is the error.

- $H_0: \gamma = 0$ (unit root) against $H_1: \gamma < 0$ (stationary around the deterministic
  terms).
- The statistic $\hat\gamma/\operatorname{se}(\hat\gamma)$ is *not* t-distributed under $H_0$. At
  5%, statsmodels' asymptotic critical values (MacKinnon 1994, 2010) are $-1.94$ with no
  deterministic terms, $-2.86$ with a constant and $-3.41$ with a constant and trend, against
  $-1.645$ for a one-sided normal test.[^adf]
- The lagged differences absorb autocorrelation. Said & Dickey (1984) showed that letting $k$ grow
  slowly with the sample size gives a valid test when the errors are ARMA of unknown order.
- statsmodels picks $k$ by AIC (`autolag='AIC'`) over $0, \dots, \lceil 12(n/100)^{1/4}\rceil$
  (Schwert 1989), on a common sample.[^adf]

**Deterministic terms matter for a trending price.** The default `regression='c'` has the
alternative "stationary around a fixed mean". A log price that rose for nine years cannot be that,
so the test pits the unit root against an alternative that cannot fit the data. `'ct'` makes the
alternative "stationary around a linear trend", the real rival to a random walk with drift, at
the cost of a more negative critical value. On a simulated random walk with drift, both correctly
failed to reject: $\tau = -1.47$ ($p = 0.55$) with `'c'` and $\tau = -1.77$ ($p = 0.72$) with
`'ct'`. On the differences, $\tau = -45.0$.[^probe-adf]

**KPSS** (Kwiatkowski et al. 1992) reverses the null. Write
$y_t = \xi t + r_t + u_t$ with $r_t = r_{t-1} + v_t$: a trend $\xi t$, a random walk $r_t$ driven
by shocks of variance $\sigma_v^2$, and a stationary error $u_t$. $H_0: \sigma_v^2 = 0$, meaning
stationary around a level (`'c'`, $\xi = 0$) or a trend (`'ct'`). The statistic is

$$
\eta = \frac{1}{T^2 \hat\sigma^2_{\text{LR}}} \sum_{t=1}^{T} S_t^2, \qquad S_t = \sum_{i=1}^{t} \hat u_i,
$$

where $\hat u_i$ are residuals from regressing $y_t$ on a constant (or constant and trend), $S_t$
their partial sums and $\hat\sigma^2_{\text{LR}}$ a Newey–West long-run variance. A wandering
series has partial sums far from zero, so $\eta$ is large. The 5% critical values are 0.463
(level) and 0.146 (trend).[^kpss]

**statsmodels clips the KPSS p-value.** It interpolates within a four-entry table, so the p-value
can only lie between 0.01 and 0.10. Beyond the table it returns the boundary and issues an
`InterpolationWarning` saying the true value is smaller (or greater).[^kpss] On the simulated
levels, $\eta = 4.36$ came back as $p = 0.01$ with the "smaller" warning; on the differences,
$\eta = 0.090$ came back as $p = 0.10$ with "greater".[^probe-adf] Read "0.01" as "0.01 or less".

**Using both tests:**

| | KPSS does not reject | KPSS rejects |
|---|---|---|
| **ADF rejects** | Stationary: do not difference. | Conflict: possibly a break or near-unit-root persistence. Investigate. |
| **ADF does not reject** | Both lack power: the data cannot tell. | Unit root: difference and re-test. |

[FPP3 §9.1](https://otexts.com/fpp3/arima.html#unit-root-tests) uses KPSS to choose $d$, and so
does pmdarima by default (Section 10). The repo's combination rule is in
[ADR-0002](../adr/0002-order-selection.md).

**Assumptions**

- The deterministic terms match how the series behaves under each hypothesis.
- One regime over the sample.

**Where it breaks**

- ADF has low power against a root just below 1. Failing to reject is not evidence *for* a unit
  root, which is why KPSS runs alongside.
- Structural breaks can mimic a unit root, and the reverse.
- Two tests at $d = 0, 1, 2$ is multiple testing, so 5% is not the overall error rate.

---

## 5. ARIMA(p, d, q)

Box & Jenkins (1970) combined three pieces: **AR($p$)**,
$x_t = c + \phi_1 x_{t-1} + \dots + \phi_p x_{t-p} + \varepsilon_t$ (today depends on the last
$p$ values); **MA($q$)**, $x_t = c + \varepsilon_t + \theta_1\varepsilon_{t-1} + \dots + \theta_q\varepsilon_{t-q}$
(today depends on the last $q$ shocks); and **I($d$)**, modelling $\nabla^d y_t$. With
$\phi(B) = 1 - \phi_1 B - \dots - \phi_p B^p$ and $\theta(B) = 1 + \theta_1 B + \dots + \theta_q B^q$:

$$
\phi(B)\,(1 - B)^d\, y_t = c + \theta(B)\, \varepsilon_t .
$$

statsmodels and FPP3 write the MA part with $+\theta$; Box & Jenkins use minus signs, so
published $\theta$ values can differ in sign. The over-differencing probe (estimate $-0.995$ for
$\varepsilon_t - \varepsilon_{t-1}$) confirms that statsmodels uses $+\theta$.

**Constant versus drift: two parameterisations.** With $d = 1$ and $w_t = \nabla y_t$, the form
above makes $w_t$ an ARMA with mean $\mu = c/(1 - \phi_1 - \dots - \phi_p)$. That $\mu$ is the
drift: long-run forecasts of $y_t$ follow a line of slope $\mu$, and with $c = 0$ they level off
([FPP3 §9.5](https://otexts.com/fpp3/arima.html#sec-non-seasonal-arima)). pmdarima uses this form.
statsmodels' `ARIMA` uses **regression with ARIMA errors** instead:[^trend]

$$
y_t = \delta_0 + \delta_1 t + u_t, \qquad \phi(B)(1 - B)^d u_t = \theta(B)\varepsilon_t ,
$$

with intercept $\delta_0$, slope $\delta_1$ and ARIMA error $u_t$. With $d = 1$, differencing
wipes out $\delta_0$, so statsmodels rejects `trend='c'` with a `ValueError` and accepts
`trend='t'`, where $\delta_1$ *is* the drift. Its default for $d \ge 1$ is no trend, so
`ARIMA(y, order=(p, 1, q))` has **no drift** unless you ask for it (Section 10).

**Stationarity and invertibility.** The AR part is stationary when all roots of $\phi(z) = 0$ lie
outside the unit circle: $|\phi_1| < 1$ for AR(1); $-1 < \phi_2 < 1$, $\phi_1 + \phi_2 < 1$ and
$\phi_2 - \phi_1 < 1$ for AR(2). The MA part is **invertible** when all roots of $\theta(z) = 0$
lie outside it ($|\theta_1| < 1$ for MA(1)), so the shocks can be recovered uniquely from the data
([FPP3 §9.3–9.4](https://otexts.com/fpp3/arima.html#sec-AR)). statsmodels enforces both by
default.[^trend]

**ACF and PACF.** The sample autocorrelation at lag $k$ is
$r_k = \sum_{t=k+1}^{T}(x_t - \bar x)(x_{t-k} - \bar x) \big/ \sum_{t=1}^{T}(x_t - \bar x)^2$,
with $\bar x$ the sample mean. The partial autocorrelation is the correlation at lag $k$ after
removing the lags in between (the last coefficient of a fitted AR($k$)). For the differenced
series ([FPP3 §9.5](https://otexts.com/fpp3/arima.html#acf-and-pacf-plots)): an AR($p$) has a
decaying ACF and a PACF that cuts off after lag $p$; an MA($q$) has an ACF that cuts off after lag
$q$ and a decaying PACF; a mixed ARMA has both decaying, and the plots cannot pin down $p$ and $q$.

**Why the signatures are weak on returns.** The $\pm 1.96/\sqrt{T}$ bands assume iid data; with
$T = 2000$ they are $\pm 0.044$, and about one lag in 20 crosses by chance. Under volatility
clustering, $\sqrt{T}\,r_k$ has variance $\mathbb{E}[\varepsilon_t^2\varepsilon_{t-k}^2]/\sigma^4 > 1$,
so the bands are too narrow. In 1,000 simulated GARCH(1,1) paths, the lag-1 band was crossed 12.1%
of the time instead of 5%.[^probe-acf] Real daily returns show generally insignificant linear
autocorrelation (Cont 2001, as restated by Ratliff-Crain et al. 2023), so the plots mostly show
noise.

Box & Jenkins treat modelling as a loop: identify, estimate, check the residuals, repeat
([FPP3 §9.7](https://otexts.com/fpp3/arima.html#modelling-procedure)).

**Assumptions**

- After $d$ differences, the series is a stationary, invertible ARMA with fixed parameters and
  constant innovation variance. The likelihood and intervals also assume Gaussian innovations.

**Where it breaks**

- If $\phi_1 \approx -\theta_1$ in an ARMA(1,1), the factors $(1 - \phi_1 B)$ and $(1 + \theta_1 B)$
  nearly cancel: the model is close to white noise and both estimates are poorly identified. This
  is common on returns.
- Constant innovation variance is false for returns (Section 7).

---

## 6. Estimation: maximum likelihood through the Kalman filter

statsmodels' `ARIMA` is a **state-space model**. It subclasses `SARIMAX`, which subclasses
`MLEModel` ("State space model for maximum likelihood estimation"), and `fit()` defaults to the
`'statespace'` method.[^statespace] The ARIMA equations are rewritten as a state equation (how a
hidden state vector evolves) and an observation equation (how $y_t$ reads off the state). The
**Kalman filter** then produces, step by step, the one-step prediction error
$v_t = y_t - \hat y_{t \mid t-1}$ and its variance $F_t$. The Gaussian log-likelihood is the
**prediction-error decomposition** (Harvey 1989; Durbin & Koopman 2012):

$$
\log L(\psi) = -\frac{1}{2} \sum_{t} \left[ \log(2\pi) + \log F_t + \frac{v_t^2}{F_t} \right],
$$

where $\psi$ holds the parameters ($\phi$'s, $\theta$'s, trend, $\sigma^2$) and the sum runs over
the observations in the likelihood. An optimiser maximises it.

"Exact" needs a qualification. The stationary ARMA states start from their stationary
distribution, so that part is exact. The $d$ integration states get an *approximate diffuse*
prior (a huge variance: "starting level unknown"), and the first $d$ observations are left out of
the likelihood. With $d = 1$ and $T = 2000$, a probe showed `loglikelihood_burn = 1` and
`nobs_effective = 1999`.[^statespace] [ADR-0002](../adr/0002-order-selection.md) measures that the
$d = 1$ likelihood equals the likelihood of the differences.

**Information criteria.** With maximised log-likelihood $\log L$, $k$ estimated parameters
(including $\sigma^2$) and $n$ observations in the likelihood:

$$
\text{AIC} = -2\log L + 2k, \qquad
\text{AICc} = \text{AIC} + \frac{2k(k+1)}{n - k - 1}, \qquad
\text{BIC} = -2\log L + k\log n .
$$

Lower is better. AIC (Akaike 1974) targets out-of-sample predictive fit; AICc (Hurvich & Tsai
1989) corrects AIC's tendency to pick oversized models in small samples; BIC (Schwarz 1978) charges
$\log n$ per parameter (about 7.7 at $n = 2264$) instead of 2, so it picks smaller models.
statsmodels uses $k$ = `df_model` and $n$ = `nobs_effective`, and writes AICc as
$-2\log L + 2kn/(n-k-1)$, which is algebraically identical.[^ic]

**Why AIC is not used to choose $d$.** It is not because the two likelihoods are on different
scales. Differencing maps $(y_1, y_2, \dots, y_n)$ to $(y_1, \Delta y_2, \dots, \Delta y_n)$, a
linear map with Jacobian 1, so densities carry over unchanged. statsmodels' $d = 1$
log-likelihood, with its diffuse start and its burn of one observation, is
$\log p(\Delta y_2, \dots, \Delta y_n) = \log p(y_2, \dots, y_n \mid y_1)$: a conditional density
of $n - 1$ observations. The $d = 0$ log-likelihood is the joint
$\log p(y_1, \dots, y_n) = \log p(y_1) + \log p(y_2, \dots, y_n \mid y_1)$. So the two differ by
the term $\log p(y_1)$ and by what is conditioned on. On ADR-0002's simulated training series,
$\log p(y_1)$ under the fitted $d = 0$ model is $-1.074$ nats; taking it out shrinks the AIC gap
between ARIMA(1,0,0) with a constant and ARIMA(0,1,0) with a drift from 8.50 to
6.35.[^probe-aicd]

Even after that correction, the comparison is not one AIC can make. A $d = 1$ model is a $d = 0$
model with one AR root fixed at $z = 1$, so "$d = 0$ or $d = 1$?" is a test for a unit root.
AIC's $2k$ penalty comes from asymptotics for regular models: the true parameter inside the
parameter space, and estimates that are asymptotically normal at rate $\sqrt{T}$. A unit root
breaks both. It sits on the boundary of the stationary region the $d = 0$ model is fitted in,
and there $\hat\phi$ converges faster than $\sqrt{T}$ (at rate $T$ for a driftless random walk,
with the Dickey–Fuller limit of Section 4). So the penalty is not calibrated for this
comparison. That is why $d$ comes first, from unit-root tests (ADF and KPSS) whose critical
values are derived for exactly this case, and AIC then compares $p$, $q$ and the trend within
that one $d$. This is also the practitioners' convention: FPP3 says information criteria are a
guide to $p$ and $q$ but not to $d$
([FPP3 §9.6](https://otexts.com/fpp3/arima.html#information-criteria)). Its stated reason, that
differencing changes the data the likelihood is computed on, corresponds to the
$\log p(y_1)$ term and the conditioning above; the boundary problem is why removing that term
does not fix the comparison.

**Assumptions**

- Correct specification and Gaussian innovations. Without normality this is quasi-maximum
  likelihood: the estimates can still be reasonable, but the standard errors and information
  criteria are less reliable.

**Where it breaks**

- Heavy-tailed returns make the Gaussian likelihood an approximation.
- Flat likelihoods (near-cancelling roots) give unstable estimates and many orders with almost
  the same AIC. A difference of 1–2 AIC points is noise, not a ranking.

---

## 7. Residual diagnostics

If the model captured the linear structure, the standardised one-step errors
$\hat e_t = v_t/\sqrt{F_t}$ should look like white noise.

**Ljung–Box.** With $r_k$ the lag-$k$ residual autocorrelation and $m$ lags tested,

$$
Q^\ast = T(T+2)\sum_{k=1}^{m} \frac{r_k^2}{T-k}
$$

(Ljung & Box 1978). $H_0$: no autocorrelation up to lag $m$. For residuals of an ARMA($p,q$),
compare with $\chi^2_{m-p-q}$, because the fitted coefficients use up $p + q$ degrees of freedom
(Box & Pierce 1970;
[FPP3 §9.7](https://otexts.com/fpp3/arima.html#portmanteau-tests-of-residuals-for-arima-models),
which suggests $m = 10$ for non-seasonal data, or $T/5$ if smaller). statsmodels does **not**
adjust by default: `acorr_ljungbox` has `model_df=0`, `test_serial_correlation` has
`df_adjust=False`, and `summary()` reports lag 1 only.[^lb] In one probe, $Q^\ast(10) = 9.97$
gave $p = 0.443$ unadjusted and $0.353$ with one degree of freedom removed.[^probe-lb]

**Jarque–Bera.** With residual skewness $S$ and kurtosis $K$,
$\text{JB} = \frac{T}{6}\left(S^2 + \frac{(K-3)^2}{4}\right) \approx \chi^2_2$ under normality
(Jarque & Bera 1980, 1987).[^jb] With thousands of daily returns it almost always rejects (heavy
tails). That affects the intervals, not the point forecast.

**QQ plot.** Sorted residuals against $N(0,1)$ quantiles. An S-shape with the ends pulling away
from the line means heavier tails than normal.

**ARCH-LM (Engle 1982).** Regress the squared residuals on $q$ of their own lags,
$\hat e_t^2 = a_0 + a_1\hat e_{t-1}^2 + \dots + a_q\hat e_{t-q}^2 + \text{error}$. Under
$H_0: a_1 = \dots = a_q = 0$ (no ARCH effects), $\text{LM} = nR^2 \sim \chi^2_q$, with $R^2$ from
that regression and $n = T - q$ its number of rows (the first $q$ squared residuals are used up
as lags). Engle wrote $TR^2$; the two agree asymptotically, and statsmodels computes
$(n - \text{ddof})R^2$ with `ddof=0` by default, so $(T - q)R^2$. statsmodels' `het_arch` runs exactly this on `resid**2`.[^arch] It squares
whatever it is given without subtracting a mean, so pass it residuals, not raw returns. On one
simulated GARCH(1,1) path (raw returns, which have mean zero by construction), LM(5)
$= 327.9$ ($p \approx 1\times10^{-68}$), while the lag-1 autocorrelation was 0.03 for the
returns and 0.25 for the squared returns. On the residuals of a random walk with drift fitted to
a path with iid returns, LM(5) $= 7.53$ ($p = 0.18$).[^probe-lb]

**Why this motivates the next project.** ARIMA models the conditional *mean* with one fixed
$\sigma^2$, so its intervals are as wide in a quiet summer as in March 2020. For returns the mean
is close to unpredictable but the *variance* is predictable: squared returns are autocorrelated
(volatility clustering, one of Cont's 2001 stylized facts). GARCH (Bollerslev 1986) models that
conditional variance, and option-implied volatility is the market's forward-looking estimate of
it. That is project 1 of this series.

**Assumptions**

- The residuals are one-step errors on the fitting data.

**Where it breaks**

- The diagnostics run on the same data that chose the model, so passing p-values are optimistic.
- Ljung–Box uses the same $r_k$ as the ACF bands, so under volatility clustering it should
  over-reject like Section 5's probe. That is an inference, not a separate measurement.
- Passing every test does not mean beating the random walk. ARIMA(0,1,0) residuals on a price
  usually pass Ljung–Box too.

---

## 8. Forecasting

**Random walk with drift.** From $y_{T+h} = y_T + h\mu + \sum_{j=1}^{h}\varepsilon_{T+j}$,

$$
\hat y_{T+h \mid T} = y_T + h\hat\mu, \qquad
\operatorname{Var}\big(y_{T+h} - \hat y_{T+h \mid T}\big) = h\sigma^2 + h^2\operatorname{Var}(\hat\mu),
$$

where $\hat\mu$ is the mean of the $T - 1$ observed returns, so $\operatorname{Var}(\hat\mu) = \sigma^2/(T-1)$.
Ignoring the estimation term, the forecast standard deviation is $\sigma\sqrt{h}$: **intervals
widen like $\sqrt{h}$**. Including it gives FPP3's drift-method formula
$\sigma\sqrt{h(1 + h/(T-1))}$
([FPP3 §5.5](https://otexts.com/fpp3/toolbox.html#sec-prediction-intervals)). In a statsmodels
ARIMA(0,1,0) probe, interval widths at $h = 1, 4, 9, 16$ were in ratio exactly
$1:2:3:4$.[^probe-fc]

**Why a static ARIMA price forecast goes flat.** With $d = 1$, the forecast return
$\hat w_{T+h \mid T}$ comes from a stationary ARMA, which reverts to its mean $\mu$ geometrically
(at a rate set by the largest *inverse* AR root, the root nearest the unit circle; for an AR(1)
each step multiplies the gap to $\mu$ by $\phi$), and the MA terms drop out for $h > q$. The
price forecast is $y_T$ plus the sum of those return forecasts, so it settles onto a horizontal
line ($\mu = 0$) or a line of slope $\mu$. A fitted ARIMA(1,1,0) with $\hat\phi = 0.294$ gave
return forecasts of $4.42\times10^{-3}$, $1.30\times10^{-3}$, $3.81\times10^{-4}$,
$1.12\times10^{-4}$, $3.28\times10^{-5}$ for $h = 1, \dots, 5$, each $\hat\phi$ times the one
before. By day five the forecast moves about 0.003% a day.[^probe-fc] Over a
226-day test window, a static forecast is a short wiggle and then a straight line. Its interval
still widens like $\sqrt{h}$ eventually, scaled by $|\theta(1)/\phi(1)|$: the width ratios at
$h = 4, 9, 16$ were 2.56, 4.07 and 5.53, approaching $\sqrt{h}/(1 - 0.2935) = 2.83, 4.25, 5.66$.

**Static versus walk-forward.** A **static** forecast fixes one origin $T$ and predicts
$h = 1, \dots, H$. A **walk-forward** (rolling-origin) evaluation forecasts each test day $t$ from
data up to $t - 1$, records the error, and moves on (Tashman 2000;
[FPP3 §5.10](https://otexts.com/fpp3/toolbox.html#sec-tscv)). Walk-forward errors use only
information available at the time and all share one horizon, so they compare directly with the
random walk's. A static forecast's error is dominated by how far the price wandered after $T$.
For a driftless random walk, the expected squared error at horizon $h$ is $h\sigma^2$, so the RMSE
averaged over $h = 1, \dots, H$ is $\sigma\sqrt{(H+1)/2}$: about 0.19 in log price for
$\sigma = 0.018$ and $H = 226$, against 0.018 one step ahead. That factor of ten comes from the
horizon, not from any model.

**Back-transforming a log forecast.** If $y_{T+h} \mid \text{data} \sim N(\hat\mu_h, \hat\sigma_h^2)$,
with forecast mean $\hat\mu_h$ and forecast variance $\hat\sigma_h^2$ on the log scale, then
$P_{T+h} = e^{y_{T+h}}$ is lognormal and

$$
\operatorname{median}(P_{T+h}) = e^{\hat\mu_h}, \qquad \mathbb{E}[P_{T+h}] = e^{\hat\mu_h + \hat\sigma_h^2/2}.
$$

So the course's `np.exp(forecast_mean)` is the **median** price forecast.
[FPP3 §5.6](https://otexts.com/fpp3/toolbox.html#sec-ftransformations) gives the bias-adjusted
mean as $e^{\hat\mu_h}(1 + \hat\sigma_h^2/2)$, a second-order approximation to the exact formula.
A simulation matched the exact median and mean to within 0.00003; FPP3's approximation came
out 0.0010 below the simulated mean.[^probe-fc] With
$\hat\sigma_h^2 \approx h\sigma^2$ and $\sigma = 0.018$, the mean exceeds the median by a factor of
$e^{h\sigma^2/2}$: 0.016% at $h = 1$, but 3.7% at $h = 226$. The gap matters for static multi-step
forecasts and hardly at all one step ahead.

Which is "right" depends on the loss: expected squared error (RMSE) is minimised by the mean,
expected absolute error (MAE) by the median (Gneiting 2011). The interval bounds are fine either
way: $\exp$ is increasing, so it maps quantiles to quantiles, and `np.exp` of the log bounds is a
valid price interval if the log interval was valid.

**Assumptions**

- The fitted model and its parameters hold throughout the forecast period; the innovations are
  Gaussian with constant variance.

**Where it breaks**

- Parameter and model uncertainty are mostly missing from the intervals.
- Volatility clustering makes the intervals too wide in calm spells and too narrow in turbulent
  ones. Heavy tails make the lognormal correction itself uncertain.

---

## 9. Evaluation

For test errors $e_t = y_t - \hat y_t$, $t = 1, \dots, n$, with actual $y_t$ and forecast $\hat y_t$
(prices here):

$$
\text{RMSE} = \sqrt{\frac{1}{n}\sum_{t=1}^{n} e_t^2}, \qquad
\text{MAE} = \frac{1}{n}\sum_{t=1}^{n} |e_t|, \qquad
\text{MAPE} = \frac{100}{n}\sum_{t=1}^{n} \left|\frac{e_t}{y_t}\right| .
$$

RMSE and MAE are in dollars, so they compare models only on the same series and period
(Hyndman & Koehler 2006).

**MAPE's problems.** It is undefined at $y_t = 0$, explodes near zero, and needs a meaningful zero
(Hyndman & Koehler 2006; [FPP3 §5.8](https://otexts.com/fpp3/toolbox.html#sec-accuracy)). It is
also asymmetric, and the sources disagree on the direction. Hyndman & Koehler (2006) say positive
errors are penalised more. Hyndman (2014) later called that backwards: with $e_t = y_t - \hat y_t$,
*negative* errors (over-forecasts) are penalised more, and FPP3 agrees. "Asymmetric" needs
care, because for a fixed actual, errors of equal size score the same: with $y_t = 100$,
forecasts of 110 and 90 both give 10%. The asymmetry shows up in two other places.

- **Swap the two numbers.** Actual 100 with forecast 150 gives 50%; actual 150 with forecast 100
  gives 33.3%. Of the two, the over-forecast scores worse.
- **The range.** With a non-negative forecast, an under-forecast's percentage error is capped at
  100%, while an over-forecast's is unbounded. So a forecaster who minimises expected MAPE
  shades the forecast low. The MAPE-optimal point forecast is the median of the distribution
  whose density is proportional to $f(y)/y$ (Gneiting 2011). Dividing a log-normal density by
  $y$ shifts its log-mean by $-\sigma^2$, so for a log-normal forecast distribution the
  MAPE-optimal point is $e^{\mu - \sigma^2}$, below the median $e^{\mu}$.[^probe-mape]

On prices far from zero, MAPE is in effect an MAE weighted by 1/price, so errors made when the
price was low count more.

**Relative-to-naive measures** answer the question that matters: did the forecast beat "no
change"? **MASE** (Hyndman & Koehler 2006) scales each error by the in-sample MAE of the one-step
naive forecast, using the $T$ training observations:

$$
q_t = \frac{e_t}{\frac{1}{T-1}\sum_{i=2}^{T}|y_i - y_{i-1}|}, \qquad \text{MASE} = \frac{1}{n}\sum_{t=1}^{n}|q_t| .
$$

MASE below 1 beats the average in-sample one-step naive forecast. **Theil's U (U2)** is the
model's RMSE over the random walk's RMSE for one-step forecasts on the same days. Hyndman &
Koehler (2006) note that Theil's (1966) definition is ambiguous (a relative RMSPE also goes by the
name), so state the formula whenever you report it.

**Diebold–Mariano test** (Diebold & Mariano 1995). For errors $e_{1,t}$ and $e_{2,t}$ from two
methods and a loss $L$ (say $L(e) = e^2$), let $d_t = L(e_{1,t}) - L(e_{2,t})$ with mean $\bar d$.
Under $H_0: \mathbb{E}[d_t] = 0$, $\text{DM} = \bar d/\sqrt{\hat V/n}$ is approximately $N(0,1)$,
where $\hat V$ is a long-run variance of $d_t$ allowing autocorrelation up to lag $h - 1$.
Harvey, Leybourne & Newbold (1997) add a small-sample correction with $t_{n-1}$ critical values.
Diebold (2015) stresses that the test compares *forecasts*, not models. The random walk is nested
inside ARIMA, which complicates the theory for population-level model comparisons (Clark &
McCracken 2001; Clark & West 2007); Giacomini & White (2006) give a framework for rolling-window
forecasts.

**The empirical record says the random walk is the bar.**

- **Exchange rates:** Meese & Rogoff (1983) found the random walk forecast as well as structural
  and time-series models at one- to twelve-month horizons, even when the structural models were
  given the realised future values of their inputs.
- **Equity returns:** Welch & Goyal (2008) found that standard predictors of the US equity premium
  failed to beat the historical-mean forecast out of sample, and most did worse. A historical-mean
  return forecast is, in log-price terms, roughly the random walk with drift. Campbell & Thompson
  (2008) disagree in degree: with sign restrictions, many predictors beat the historical mean by a
  small margin they consider economically meaningful.
- **Serial correlation:** weekly portfolio returns reject the random walk (Lo & MacKinlay 1988),
  while linear autocorrelation of daily returns is generally insignificant (Cont 2001).

I found no well-sourced study of ARIMA on AAPL daily prices specifically. The working expectation
is that ARIMA lands within noise of the random walk, and the repo measures that rather than
assuming it.

**Assumptions**

- The test period is representative, and the forecasts are genuinely out of sample.

**Where it breaks**

- A single test window of about 226 days is one draw; another window can reverse a small gap.
- Comparing static multi-step forecasts mostly compares straight lines (Section 8).
- Picking the best of many models on the test set, then reporting its test score, is selection
  bias.

---

## 10. Data-handling facts that bite in practice

Each was checked in the installed source and, where possible, run on simulated data.

1. **yfinance 1.7.0 adjusts by default.** `download()` has `auto_adjust=True`. It scales Open,
   High and Low by Adj Close / Close and renames Adj Close to Close, so **Close is the split- and
   dividend-adjusted close** and no Adj Close column remains. Code that selects `'Adj Close'` fails
   with a `KeyError`.[^yf-adj]
2. **One ticker still gives MultiIndex columns.** `multi_level_index=True` is the default; columns
   are (Price, Ticker), such as `('Close', 'AAPL')`, so `df['Close']` is a one-column DataFrame,
   not a Series. Pass `multi_level_index=False` to flatten a single-ticker download.[^yf-mi]
3. **`end` is exclusive.** `end='2024-01-01'` covers every day up to 31 December 2023. That day
   was a Sunday, so the course's `end='2023-12-31'` returns the same bars (last one Friday
   2023-12-29), as `config.py` notes. Read in the source at milestone 0; measured in milestone 1:
   the snapshots requested with `end='2026-10-01'` on 2026-10-29 end on 2026-09-30, though
   2026-10-01 is a Thursday and not a US market holiday.[^yf-end]
4. **`fillna(method='ffill')` is gone in pandas 3.1.0.** `fillna` accepts only `value`, `axis`,
   `inplace` and `limit`, and the call raises `TypeError` (measured, for Series and DataFrame). Use
   `.ffill()`.[^pd-fillna]
5. **statsmodels `ARIMA` drops the drift when $d \ge 1$.** The default trend is `'c'` for $d = 0$
   and `'n'` otherwise; `'c'` with $d = 1$ raises `ValueError`; use `'t'` for a drift
   (Section 5).[^trend]
6. **pmdarima `auto_arima` defaults to `test='kpss'` and `information_criterion='aic'`.**
   `with_intercept='auto'` only sets the *starting* value: `True` when
   $d + D \in \lbrace 0, 1\rbrace$. The stepwise search then also fits the null model without the
   constant and toggles the constant on the current best order, so the *final* model can lack an
   intercept even with $d = 1$. On the random-walk-with-drift probe it did: `auto_arima` chose
   (0,1,0) without one.[^probe-drift] pmdarima's `test='adf'` is its **own** ADF (constant *and*
   trend, a fixed $k = \lfloor(n-1)^{1/3}\rfloor$ lagged differences), not statsmodels' default
   (constant only, lag chosen by AIC). It matches statsmodels'
   `adfuller(regression='ct', maxlag=k, autolag=None)`: on ADR-0002's 1,800-point training
   series ($k = 12$) both give $\tau = -0.642439$.[^pm]
   Combining items 5 and 6: on a simulated series with a strong drift, `auto_arima` chose (0,1,0)
   *with* an intercept, and refitting that order in statsmodels with defaults produced a flat
   forecast. After 250 steps it sat 0.47 below pmdarima's drifting forecast in log price. In
   dollars, measured against the drifting forecast, the flat one is about 37% lower; measured
   against the flat one, the drifting forecast is about 59% higher. (ADR-0002's "18%" for its own
   example is on the second base.)[^probe-pm]
7. **statsmodels 0.15.0 warns on `adfuller`/`kpss` return types.** Each issues a `FutureWarning`
   unless `result_object=` is passed; the return type changes in 0.16 or after July 2027, whichever
   is later.[^adf]
8. **Ljung–Box defaults** do not adjust degrees of freedom (Section 7).[^lb]

---

## 11. What this repo does differently, and why (preview)

The full "where the sample goes wrong" critique is milestone 5. In short:

- **Order selection uses training data only.** The split comes before any choice of $d$, $p$, $q$
  or trend (milestone 2; [ADR-0002](../adr/0002-order-selection.md)).
- **KPSS runs alongside ADF**, with an explicit rule, and clipped KPSS p-values are reported as
  bounds (milestone 2).
- **The drift is a decision.** The trend term is chosen and recorded, so the statsmodels refit is
  the model that was selected (milestones 2–3).
- **Diagnostics use adjusted degrees of freedom**, plus ARCH-LM to show what ARIMA leaves behind
  (milestone 3).
- **Walk-forward one-step forecasts sit next to a random-walk baseline**, scored with MASE and
  Theil's U as well as RMSE, MAE and MAPE. Adding a Diebold–Mariano test is an open question for
  milestone 4.
- **Two course lines that fail on the pinned stack** (found by the milestone-0 review on
  simulated data, and reproduced for this note; handled in milestone 4, explained in
  milestone 5):[^probe-course]
  - The Module 9 forecast crashes. statsmodels 0.15.0's `get_forecast` raises
    `ValueError: No supported index is available.` for a model fitted on a date index with no
    frequency (`statsmodels/tsa/base/tsa_model.py:437-445`). A trading-day index has none:
    pandas cannot infer one once holidays leave gaps. Fitting on a plain array avoids it.
  - The Module 10 MAPE is `nan`. Under yfinance 1.7.0, `df['Close']` is a one-column DataFrame,
    so the course's MAPE line subtracts a DataFrame from a Series. pandas aligns the Series'
    index with the DataFrame's *columns*, the result is an all-NaN frame, and its mean is `nan`.
    The line is reached only once the forecast crash above is worked around.
- **Median and mean back-transforms are both reported**, labelled (milestone 4).
- **Data provenance:** `auto_adjust`, `multi_level_index` and the exclusive `end` are set
  explicitly, and versions and download time are recorded (milestone 1). Backward adjustment
  rescales earlier prices whenever a later dividend or split occurs, so a re-download can change
  history. That follows from how backward adjustment works; Yahoo's exact method is not verified
  here.

---

## 12. Glossary

- **ACF / PACF**: autocorrelation by lag; partial autocorrelation, net of shorter lags.
- **ADF**: augmented Dickey–Fuller test; null hypothesis = unit root.
- **AIC / AICc / BIC**: penalised-likelihood scores for models fitted to the same data.
- **ARCH effect**: autocorrelation in squared residuals; predictable volatility.
- **Backshift operator $B$**: $Bx_t = x_{t-1}$.
- **Diffuse prior**: an initial state variance so large it says "starting level unknown".
- **Drift**: mean per-period change of an I(1) series; slope of its long-run forecast.
- **I($d$)**: needs $d$ differences to become stationary.
- **Invertible**: an MA model whose shocks are recoverable uniquely from past data.
- **Kalman filter**: recursion giving one-step predictions and their variances in a state-space model.
- **KPSS**: stationarity test; null hypothesis = stationary.
- **Ljung–Box**: portmanteau test for residual autocorrelation up to lag $m$.
- **MASE**: MAE scaled by the in-sample one-step naive MAE.
- **Static forecast**: every horizon from one origin.
- **Theil's U (U2)**: model RMSE over random-walk RMSE, one step ahead.
- **Unit root**: an AR-polynomial root at $z = 1$; shocks never decay.
- **Walk-forward (rolling origin)**: forecast one step ahead from each successive origin.
- **Weak stationarity**: constant mean and variance; autocovariance depends only on the lag.
- **White noise**: zero-mean, constant-variance, serially uncorrelated shocks.

## Verification notes

- **Checked against the primary text:** Fama (1970) pp. 383–388 (scanned copy); Hyndman & Koehler
  (2006), definitions and the Theil's U remark (authors' preprint, pp. 7–12); FPP3 §5.2–5.10 and
  §9.1–9.8 (online, 2026-10-28); every library fact (installed source, plus probes on simulated
  data).
- **Abstract or bibliographic record only:** Welch & Goyal (2008), Campbell & Thompson (2008),
  Lo & MacKinlay (1988) and Diebold (2015), from NBER working-paper abstracts; Meese & Rogoff
  (1983), from a library-catalogue abstract found by search; Tashman (2000), from bibliographic
  record and keywords.
- **Secondary source:** Cont (2001), via Ratliff-Crain et al. (2023); the original is paywalled.
- **From standard references, not re-read for this note:** Said & Dickey's lag-growth result,
  Plosser & Schwert's over-differencing analysis, the Diebold–Mariano and HLN formulas, Gneiting's
  mean/median result and his MAPE-optimal point (checked numerically for the log-normal case),
  the prediction-error decomposition (Harvey; Durbin & Koopman), and Box &
  Jenkins' minus-sign MA convention. Citation metadata (authors, year, journal, volume, pages) was
  checked against Crossref for every DOI listed.
- **Not verified:** Yahoo's adjusted-close methodology; any ARIMA-on-AAPL study.

## References

- Akaike, H. (1974). A new look at the statistical model identification. *IEEE Transactions on Automatic Control*, 19(6), 716–723. https://doi.org/10.1109/TAC.1974.1100705
- Bollerslev, T. (1986). Generalized autoregressive conditional heteroskedasticity. *Journal of Econometrics*, 31(3), 307–327. https://doi.org/10.1016/0304-4076(86)90063-1
- Box, G. E. P., & Jenkins, G. M. (1970). *Time Series Analysis: Forecasting and Control*. Holden-Day. (5th ed. with G. C. Reinsel and G. M. Ljung, Wiley, 2015.)
- Box, G. E. P., & Pierce, D. A. (1970). Distribution of residual autocorrelations in autoregressive-integrated moving average time series models. *Journal of the American Statistical Association*, 65(332), 1509–1526. https://doi.org/10.1080/01621459.1970.10481180
- Campbell, J. Y., & Thompson, S. B. (2008). Predicting excess stock returns out of sample: Can anything beat the historical average? *Review of Financial Studies*, 21(4), 1509–1531. https://doi.org/10.1093/rfs/hhm055
- Clark, T. E., & McCracken, M. W. (2001). Tests of equal forecast accuracy and encompassing for nested models. *Journal of Econometrics*, 105(1), 85–110. https://doi.org/10.1016/S0304-4076(01)00071-9
- Clark, T. E., & West, K. D. (2007). Approximately normal tests for equal predictive accuracy in nested models. *Journal of Econometrics*, 138(1), 291–311. https://doi.org/10.1016/j.jeconom.2006.05.023
- Cont, R. (2001). Empirical properties of asset returns: stylized facts and statistical issues. *Quantitative Finance*, 1(2), 223–236. https://doi.org/10.1080/713665670
- Dickey, D. A., & Fuller, W. A. (1979). Distribution of the estimators for autoregressive time series with a unit root. *Journal of the American Statistical Association*, 74(366a), 427–431. https://doi.org/10.1080/01621459.1979.10482531
- Diebold, F. X. (2015). Comparing predictive accuracy, twenty years later: A personal perspective on the use and abuse of Diebold–Mariano tests. *Journal of Business & Economic Statistics*, 33(1), 1. https://doi.org/10.1080/07350015.2014.983236 (working paper: https://www.nber.org/papers/w18391)
- Diebold, F. X., & Mariano, R. S. (1995). Comparing predictive accuracy. *Journal of Business & Economic Statistics*, 13(3), 253–263. https://doi.org/10.1080/07350015.1995.10524599
- Durbin, J., & Koopman, S. J. (2012). *Time Series Analysis by State Space Methods* (2nd ed.). Oxford University Press.
- Engle, R. F. (1982). Autoregressive conditional heteroscedasticity with estimates of the variance of United Kingdom inflation. *Econometrica*, 50(4), 987–1007. https://doi.org/10.2307/1912773
- Fama, E. F. (1970). Efficient capital markets: A review of theory and empirical work. *Journal of Finance*, 25(2), 383–417. https://doi.org/10.1111/j.1540-6261.1970.tb00518.x
- Giacomini, R., & White, H. (2006). Tests of conditional predictive ability. *Econometrica*, 74(6), 1545–1578. https://doi.org/10.1111/j.1468-0262.2006.00718.x
- Gneiting, T. (2011). Making and evaluating point forecasts. *Journal of the American Statistical Association*, 106(494), 746–762. https://doi.org/10.1198/jasa.2011.r10138
- Harvey, A. C. (1989). *Forecasting, Structural Time Series Models and the Kalman Filter*. Cambridge University Press.
- Harvey, D., Leybourne, S., & Newbold, P. (1997). Testing the equality of prediction mean squared errors. *International Journal of Forecasting*, 13(2), 281–291. https://doi.org/10.1016/S0169-2070(96)00719-4
- Hurvich, C. M., & Tsai, C.-L. (1989). Regression and time series model selection in small samples. *Biometrika*, 76(2), 297–307. https://doi.org/10.1093/biomet/76.2.297
- Hyndman, R. J. (2014, April 16). Errors on percentage errors. *Hyndsight* blog. https://robjhyndman.com/hyndsight/smape/
- Hyndman, R. J., & Athanasopoulos, G. *Forecasting: Principles and Practice* (3rd ed.). OTexts. https://otexts.com/fpp3/ (online; accessed 2026-10-28)
- Hyndman, R. J., & Koehler, A. B. (2006). Another look at measures of forecast accuracy. *International Journal of Forecasting*, 22(4), 679–688. https://doi.org/10.1016/j.ijforecast.2006.03.001 (preprint: https://robjhyndman.com/papers/mase.pdf)
- Jarque, C. M., & Bera, A. K. (1980). Efficient tests for normality, homoscedasticity and serial independence of regression residuals. *Economics Letters*, 6(3), 255–259. https://doi.org/10.1016/0165-1765(80)90024-5
- Jarque, C. M., & Bera, A. K. (1987). A test for normality of observations and regression residuals. *International Statistical Review*, 55(2), 163–172. https://doi.org/10.2307/1403192
- Kwiatkowski, D., Phillips, P. C. B., Schmidt, P., & Shin, Y. (1992). Testing the null hypothesis of stationarity against the alternative of a unit root. *Journal of Econometrics*, 54(1–3), 159–178. https://doi.org/10.1016/0304-4076(92)90104-Y
- Ljung, G. M., & Box, G. E. P. (1978). On a measure of lack of fit in time series models. *Biometrika*, 65(2), 297–303. https://doi.org/10.1093/biomet/65.2.297
- Lo, A. W., & MacKinlay, A. C. (1988). Stock market prices do not follow random walks: Evidence from a simple specification test. *Review of Financial Studies*, 1(1), 41–66. https://doi.org/10.1093/rfs/1.1.41
- MacKinnon, J. G. (1994). Approximate asymptotic distribution functions for unit-root and cointegration tests. *Journal of Business & Economic Statistics*, 12(2), 167–176. https://doi.org/10.1080/07350015.1994.10510005
- MacKinnon, J. G. (2010). Critical values for cointegration tests. Queen's University Economics Working Paper 1227. http://ideas.repec.org/p/qed/wpaper/1227.html
- Meese, R. A., & Rogoff, K. (1983). Empirical exchange rate models of the seventies: Do they fit out of sample? *Journal of International Economics*, 14(1–2), 3–24. https://doi.org/10.1016/0022-1996(83)90017-X
- Plosser, C. I., & Schwert, G. W. (1977). Estimation of a non-invertible moving average process: The case of overdifferencing. *Journal of Econometrics*, 6(2), 199–224. https://doi.org/10.1016/0304-4076(77)90015-X
- Ratliff-Crain, E., Van Oort, C. M., Bagrow, J., Koehler, M. T. K., & Tivnan, B. F. (2023). Revisiting stylized facts for modern stock markets. arXiv:2311.07738. https://arxiv.org/abs/2311.07738
- Said, S. E., & Dickey, D. A. (1984). Testing for unit roots in autoregressive-moving average models of unknown order. *Biometrika*, 71(3), 599–607. https://doi.org/10.1093/biomet/71.3.599
- Schwarz, G. (1978). Estimating the dimension of a model. *Annals of Statistics*, 6(2), 461–464. https://doi.org/10.1214/aos/1176344136
- Schwert, G. W. (1989). Tests for unit roots: A Monte Carlo investigation. *Journal of Business & Economic Statistics*, 7(2), 147–159. https://doi.org/10.1080/07350015.1989.10509723
- Tashman, L. J. (2000). Out-of-sample tests of forecasting accuracy: An analysis and review. *International Journal of Forecasting*, 16(4), 437–450. https://doi.org/10.1016/S0169-2070(00)00065-0
- Theil, H. (1966). *Applied Economic Forecasting*. North-Holland.
- Welch, I., & Goyal, A. (2008). A comprehensive look at the empirical performance of equity premium prediction. *Review of Financial Studies*, 21(4), 1455–1508. https://doi.org/10.1093/rfs/hhm014

---

[^versions]: Paths are relative to `site-packages` of a Python 3.12 venv with yfinance 1.7.0, pandas 3.1.0, statsmodels 0.15.0 (`statsmodels/_version.py:20`), pmdarima 2.1.1 and numpy 2.5.4, matching `pyproject.toml`. Probes ran with `uv run python -I` on simulated data only. The scripts live in a scratch directory and are not part of the repo, but every probe footnote states its seed and enough of the recipe to re-run it. Another seed changes the numbers, not the qualitative results.

[^decomp]: `statsmodels/tsa/seasonal/_seasonal.py:97` (`two_sided=True`), `:209-216` (centred moving-average filter of length `period`+1 for even `period`, applied two-sided), `:187-192` (`ValueError` for any value ≤ 0 with `model="multiplicative"`; reproduced in a probe). AAPL's 2015–2023 log price is positive, so the error does not fire there.

[^probe-drift]: Simulated log-price random walk with drift: `rng = numpy.random.default_rng(0)`, `y = numpy.cumsum(0.0008 + 0.018 * rng.standard_normal(2000))`, so T = 2000, μ = 0.0008, σ = 0.018. statsmodels `ARIMA(y, order=(0,1,0), trend='t')` estimated the drift at 0.000289 (sample mean of the differences: 0.000294). AIC −10384.28 without trend against −10382.82 with `trend='t'`. pmdarima `auto_arima(y, seasonal=False)` on the same path, with its defaults and again with `test='adf'`, chose (0,1,0) without an intercept: its trace shows (0,1,0) fitted first with the constant and then without it, and the version without won.

[^probe-overdiff]: White noise `z = numpy.random.default_rng(20261028).standard_normal(2000)`. `statsmodels.tsa.stattools.acf(numpy.diff(z), nlags=1)[1]` = −0.486. `ARIMA(numpy.diff(z), order=(0,0,1), trend='n')`: MA coefficient −0.995. The variance ratio Var(Δz)/Var(z) was 1.994 (theory: 2).

[^adf]: `statsmodels/tsa/stattools/_stattools.py:233-242` (signature: `regression="c"`, `autolag="AIC"`), `:373-375` (default `maxlag` = ceil(12·(nobs/100)^0.25), capped), `:390` (lagged level as the first regressor), `:407` (lag chosen by `_autolag`), `:436` (statistic = t-value of the lagged level), `:444` (MacKinnon p-value), `:465-475` (`FutureWarning` when `result_object` is None; reproduced). Critical values from `statsmodels/tsa/adfvalues.py:414` (`mackinnoncrit`), asymptotic 1/5/10%: `'n'` −2.566/−1.941/−1.617; `'c'` −3.430/−2.862/−2.567; `'ct'` −3.959/−3.410/−3.127. The KPSS `FutureWarning` is at `:3250-3261` of the same file (reproduced with `kpss(x)` on a simulated random walk).

[^probe-adf]: Same simulated path as the random-walk-with-drift probe (`default_rng(0)`). `adfuller(..., autolag='AIC', result_object=False)`: levels `'c'` τ = −1.468, p = 0.549, 0 lags; levels `'ct'` τ = −1.765, p = 0.721; first difference `'c'` τ = −45.046, p ≈ 0. `kpss(..., regression='c', nlags='auto')`: levels η = 4.361, p = 0.01, `InterpolationWarning` "...The actual p-value is smaller than the p-value returned."; differences η = 0.090, p = 0.1, warning "...greater than...".

[^kpss]: `statsmodels/tsa/stattools/_stattools.py:3051-3055` (signature: `regression="c"`, `nlags="auto"`), `:3176-3187` (detrending; critical values `[0.119, 0.146, 0.176, 0.216]` for `'ct'` and `[0.347, 0.463, 0.574, 0.739]` for `'c'`, at 10/5/2.5/1%), `:3211` (`pvals = [0.10, 0.05, 0.025, 0.01]`), `:3213` (η), `:3217` (`np.interp`, which clips at the table ends), `:3224-3235` (`InterpolationWarning` at either boundary).

[^trend]: `statsmodels/tsa/arima/model.py:61-72` (docstring: default `'c'` without integration, no trend with it), `:156-160` (code: `trend = "c"` if not integrated, else `"n"`), `:178-190` (`ValueError` for trend terms of lower order than d + D, such as a constant with d = 1; reproduced), `:107-121` (regression-with-ARIMA-errors specification), `:147` (`enforce_stationarity=True, enforce_invertibility=True`). Probe: default `ARIMA(order=(0,1,0)).trend == 'n'`, `k_trend == 0`, and the 5-step forecast equalled the last observation at every step; with `trend='t'`, each step added 0.000289.

[^statespace]: `statsmodels/tsa/arima/model.py:26` (`class ARIMA(sarimax.SARIMAX)`), `statsmodels/tsa/statespace/sarimax.py:37` (`class SARIMAX(MLEModel)`), `statsmodels/tsa/statespace/mlemodel.py:93-95` (MLEModel docstring), `model.py:334-335` (`method = "statespace"` when none is given), `sarimax.py:344, 347` (`simple_differencing=False`, `use_exact_diffuse=False`; `ARIMA.__init__` does not override them), `sarimax.py:669-703` (approximate-diffuse initialisation of the differencing states, stationary initialisation of the ARMA states, `loglikelihood_burn`), `mlemodel.py:2783` (`nobs_effective = nobs - loglikelihood_burn`). Probe MRO: ARIMA → SARIMAX → MLEModel → TimeSeriesModel; d = 1, T = 2000: `loglikelihood_burn = 1`, `nobs_effective = 1999`.

[^ic]: `statsmodels/tsa/statespace/mlemodel.py:3083-3101` (aic, aicc and bic use `nobs_effective` and `df_model`), `:2789-2794` (`df_model` = free parameters + exact-diffuse states + concentration flag), `statsmodels/tools/eval_measures.py:415` (AIC = −2llf + 2k), `:445-448` (AICc = −2llf + 2kn/(n−k−1)), `:476` (BIC = −2llf + k·log n).

[^probe-aicd]: ADR-0002's training series: `rng = numpy.random.default_rng(20261028)`, `y = numpy.log(30.0) + numpy.cumsum(0.0008 + 0.017 * rng.standard_normal(2000))`, first 1,800 values. `ARIMA(y, order=(0,1,0), trend='t')` on the levels: llf 4800.5385 over `nobs_effective` = 1,799 (burn 1). `ARIMA(numpy.diff(y), order=(0,0,0), trend='c')` on the differences: llf 4800.5385 over 1,799 (burn 0); the two agree to 4e-8. `ARIMA(y, order=(1,0,0), trend='c')`: llf 4797.2900 over 1,800, φ̂ = 0.99985, and its first `llf_obs` term, log p(y₁) under the stationary prior, is −1.074. AIC: d = 0, −9588.58 (k = 3); d = 1, −9597.08 (k = 2); gap 8.50. With log p(y₁) removed from the d = 0 log-likelihood (at its fitted parameters, not refitted), the d = 0 AIC on y₂…yₙ is −9590.73 and the gap is 6.35. On all 2,000 values the same steps give log p(y₁) = −1.166 and a gap of 9.64 before and 7.31 after.

[^probe-acf]: 1,000 simulated GARCH(1,1) paths, T = 2000, ω = 1e-5, α = 0.08, β = 0.90: one draw `numpy.random.default_rng(7).standard_normal((1000, 2000))`, then εₜ = √hₜ·zₜ and hₜ₊₁ = ω + αε²ₜ + βhₜ. Every path starts at the unconditional variance, h₁ = ω/(1 − α − β) = 5e-4, with no burn-in. r₁ is `acf(path, nlags=1)[1]`. T·Var(r₁) across paths = 1.55; mean over paths of each path's sample E[ε²ₜε²ₜ₋₁]/σ̂⁴, with σ̂² that path's sample variance, = 1.535 (iid value: 1); share of paths with |r₁| > 1.96/√T = 0.121.

[^lb]: `statsmodels/stats/diagnostic.py:596-600` (`acorr_ljungbox(..., model_df=0)`), `:748-753` (Q*, with the p-value from χ² on `lags - model_df` degrees of freedom), `statsmodels/tsa/statespace/mlemodel.py:3661` (`test_serial_correlation(..., df_adjust=False, ...)`), `:3743-3745` (with `df_adjust`, `model_df = df_model - k_diffuse_states - 1`), `:5580` (`summary()` calls it with `lags=[1]`).

[^probe-lb]: Ljung–Box on the residuals of the ARIMA(1,1,0) forecasting probe (its recipe is in the forecasting-probe footnote of Section 8), with the first, burned residual dropped: `acorr_ljungbox(resid[1:], lags=[10], model_df=0)` gave Q = 9.968, p = 0.443; `model_df=1` gave p = 0.353. ARCH-LM, `het_arch(x, nlags=5)`. (a) x is one simulated GARCH(1,1) return path: z = `numpy.random.default_rng(20261028).standard_normal(2000)` drives ω = 1e-5, α = 0.08, β = 0.90 from h₁ = ω/(1 − α − β), with no burn-in, and x is the raw simulated returns, which have mean zero by construction. LM = 327.90, p = 1.0e-68; lag-1 autocorrelation 0.030 for the returns and 0.253 for their squares. (b) x is the residuals of `ARIMA(y, order=(0,1,0), trend='t')` on the drift-probe path, first (burned) residual dropped: LM = 7.53, p = 0.184. On that path's raw returns `numpy.diff(y)`, which still contain the drift, LM = 7.33, p = 0.197.

[^jb]: `statsmodels/stats/stattools.py:131-136` (skewness, kurtosis, and JB = (n/6)(S² + (K−3)²/4)).

[^arch]: `statsmodels/stats/diagnostic.py:936-938` (`het_arch` signature), `:997-999` (returns `acorr_lm(resid**2, ...)`), `:892-893` (`lagmat(..., trim="both")`, after which `nobs` is the T − q rows that remain), `:905` (`lm = (nobs - ddof) * resols.rsquared`). Probe on the residuals of the drift probe (T = 1,999 after the burned residual, q = 5): `het_arch` returned 7.5301, equal to (T − q)R² from refitting that regression by hand; TR² would be 7.5490.

[^probe-fc]: ARIMA(1,1,0): `rng = numpy.random.default_rng(20261028)`, `e = 0.018 * rng.standard_normal(2000)`, w₀ = 0 and wₜ = 0.3·wₜ₋₁ + eₜ, y = `numpy.cumsum(w)`. `ARIMA(y, order=(1,1,0))` (default trend `'n'`) fitted φ̂ = 0.2935. `get_forecast(20)` increments as quoted (sixth step 9.6e-6), each 0.2935 times the one before. `summary_frame` columns: `mean, mean_se, mean_ci_lower, mean_ci_upper`. 95% width ratios at h = 4, 9, 16: 2.559, 4.069, 5.530. Pure random walk: y = `numpy.cumsum(0.018 * numpy.random.default_rng(1).standard_normal(2000))`, `ARIMA(y, order=(0,1,0))`: width ratios 1, 2, 3, 4 at h = 1, 4, 9, 16, and `mean_se` at those horizons 0.01812, 0.03624, 0.05436, 0.07248 against σ√h = 0.018, 0.036, 0.054, 0.072 (σ̂ = 0.01812). Lognormal check: 2,000,000 draws `numpy.exp(numpy.random.default_rng(20261028).normal(0.2, 0.081 ** 0.5, 2_000_000))`, so 0.081 is the variance: median 1.22138 and mean 1.27190, against e^0.2 = 1.22140 and e^(0.2+0.0405) = 1.27188; FPP3's e^0.2·(1 + 0.0405) = 1.27087.

[^yf-adj]: `yfinance/multi.py:56` (`auto_adjust=True` in the signature), `:86-87` (docstring: "Default is True"), `yfinance/scrapers/history.py:594-596` (applies `utils.auto_adjust` when set), `yfinance/utils.py:506-523` (ratio = Adj Close / Close at `:509`; Open/High/Low scaled; Adj Close renamed to Close at `:518-521`). Probe: `yfinance.multi.Ticker` replaced by a fake class returning simulated OHLC with Close = 10.5…14.5 and Adj Close = 10…14. Default download Close = [10, 11, 12, 13, 14], with no 'Adj Close' column; with `auto_adjust=False`, both columns were present. No network was used.

[^yf-mi]: `yfinance/multi.py:59` (`multi_level_index=True`), `:112-113` (docstring), `:213-219` (`pd.concat(..., keys=..., names=['Ticker', 'Price'])`), `:222-224` (levels swapped to (Price, Ticker) for `group_by='column'`), `:226-227` (flattened only if `not multi_level_index and len(tickers) == 1`). Probe with the fake ticker: default columns `[('Close','AAPL'), ('High','AAPL'), ...]` as a `MultiIndex`; `multi_level_index=False` gave `['Close', 'High', 'Low', 'Open', 'Volume']`; `type(df['Close'])` under the default was `DataFrame`. yfinance itself also emits pandas `Pandas4Warning`s about `inplace=` (`utils.py:514, 518`; `multi.py:220, 224`).

[^yf-end]: `yfinance/multi.py:77-80` (docstring: `end` exclusive, with the example `end="2023-01-01"` → last data point 2022-12-31), `yfinance/scrapers/history.py:213-215` (`end` parsed and converted to a timestamp), `yfinance/utils.py:454-471` (`_parse_user_dt`: a date string becomes midnight in the exchange time zone), `yfinance/scrapers/history.py:393-396` (drops a trailing row at or after `end`). Code reading only; not run against the network.

[^pd-fillna]: `pandas/core/generic.py:7230-7237` (`fillna(self, value, *, axis=None, inplace=False, limit=None)`, with no `method`), `:7474-7481` (`ffill(self, *, axis=None, inplace=False, limit=None, limit_area=None)`). Probe: `TypeError: NDFrame.fillna() got an unexpected keyword argument 'method'` for both Series and DataFrame; `pd.Series([1, nan, 3, nan]).ffill()` gave `[1, 1, 3, 3]`.

[^pm]: `pmdarima/arima/auto.py:349` (`information_criterion='aic'`), `:351` (`test='kpss'`), `:353` (`stepwise=True`), `:371` (`with_intercept="auto"`), `:545-553` (d from `ndiffs(dx, test=test, ...)`), `:623-624` (the starting value: `'auto'` becomes `(d + D) in (0, 1)`), `pmdarima/arima/_auto_solvers.py:312-314` (null model refitted without the constant) and `:440-445` (constant toggled on the current best order), `pmdarima/arima/arima.py:488-499` (intercept passed as `trend='c'` to `statsmodels.tsa.statespace.SARIMAX`), `pmdarima/arima/utils.py:128` (`ndiffs(..., test='kpss', ...)`), `pmdarima/arima/stationarity.py:215` (`class ADFTest`), `:284-286` (regressors: constant, lagged level, time trend), `:326-335` (`k = trunc((n-1)^(1/3))`, then `k = int(k) + 1` as the embedding width), `:289` (the lagged differences are `z[:, 1:k]`, so there are k − 1 = ⌊(n−1)^{1/3}⌋ of them). Probe on ADR-0002's training series (`default_rng(20261028)`, `y = log(30) + cumsum(0.0008 + 0.017 z)`, first 1,800 values): pmdarima's regression has 15 regressors (constant, lagged level, trend and 12 lagged differences) and τ = −0.642439; statsmodels `adfuller(y, regression='ct', maxlag=12, autolag=None)` gives −0.642439, and `maxlag=13` gives −0.719864.

[^probe-pm]: Simulated x = `numpy.cumsum(0.002 + 0.01 * numpy.random.default_rng(1).standard_normal(2000))`, T = 2000. `pm.auto_arima(x, test='adf', stepwise=True, seasonal=False)` gave order (0,1,0), `with_intercept=True`, intercept 0.00186 (the sample mean of the differences is 0.001864). 250-step forecast minus the last observation: statsmodels `ARIMA(x, order=(0,1,0))` 0.0; statsmodels `trend='t'` 0.4648; pmdarima 0.4661; true 250μ = 0.5. e^(−0.4661) = 0.627, so the flat forecast is 37% below pmdarima's drifting one in dollars (equivalently, the drifting one is 59% above the flat one).

[^probe-course]: A simulated frame shaped like a yfinance 1.7.0 single-ticker download, built by hand with no network: `default_rng(20261028)`; dates `pandas.bdate_range('2015-01-02', '2023-12-29')` minus five holidays, so 2,341 rows with `index.freq` and `pandas.infer_freq` both None; Close = 30·exp(cumsum(0.0008 + 0.017·z)); columns a MultiIndex (Price, Ticker). Following the course: `df_close = stock_data['Close']` (a one-column DataFrame), `df_log = np.log(df_close)`, a 90/10 split by position (235 test rows), `ARIMA(train_data, order=(0,1,0)).fit()`, which emits a `ValueWarning` that the date index has no frequency. `get_forecast(steps=235)` then raised the `ValueError`. It raised too with `train_data` flattened to a Series, and worked with a numpy array. With a forecast made from the array and labelled either with the test dates or with integers, `forecast_series - test_data_actual` had shape (235, 236) and was all NaN, and the course's MAPE expression returned `nan`. The positional MAPE was 16.80%.

[^probe-mape]: `numpy.random.default_rng(20261028)`, 400,000 draws of Y = exp(N(0, 0.5²)). The average of \|Y − f\|/Y over a grid f = 0.600, 0.601, …, 1.100 was smallest at f = 0.778, against e^(−0.5²) = 0.7788; the median of Y is 1 and its mean e^0.125 = 1.1331. The arithmetic examples: \|100 − 110\|/100 = \|100 − 90\|/100 = 0.1000; \|100 − 150\|/100 = 0.5000; \|150 − 100\|/150 = 0.3333.
