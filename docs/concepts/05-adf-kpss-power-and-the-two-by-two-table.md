# 05 · ADF and KPSS: power, the deterministic term and the 2 × 2 table

Background [§3 and §4](00-background.md#3-stationarity-unit-roots-and-differencing) define
stationarity, unit roots and the two tests. This note goes one level deeper. It asks what a test
result can and cannot tell you, measures how often each test is right on simulated data of the
training sample's length, and explains why the project reads the two tests together.

## First principles

A **hypothesis test** starts from a claim, the **null hypothesis**, and asks whether the data are
unlikely under it. The test reduces the data to one number, the **test statistic**. The **p-value**
is the probability, computed as if the null were true, of a statistic at least as extreme as the one
observed. It is not the probability that the null is true. A small p-value is evidence against the
null. A large p-value is not evidence for it: it only says the data did not contradict it.

A test can be wrong in two ways.

- It can reject a true null. This is a **type I error**. Its rate is the **size** of the test. At
  the 5% level the size should be 5%.
- It can fail to reject a false null. Its rate is a **type II error**. One minus that rate is the
  **power** of the test: how often it notices that the null is false.

Power depends on how false the null is. A small departure is hard to see. A big one is easy.

The two unit-root tests have **opposite nulls**.

- **ADF** (augmented Dickey–Fuller): the null is "the series has a unit root". Rejecting it is
  evidence of stationarity.
- **KPSS** (Kwiatkowski, Phillips, Schmidt and Shin): the null is "the series is stationary".
  Rejecting it is evidence of a unit root.

So a test that "does not reject" says something different in each case. ADF not rejecting means
"I cannot rule out a unit root". KPSS not rejecting means "I cannot rule out stationarity".

A **deterministic term** is the part of the test regression that is not random: a constant, or a
constant and a linear trend. It sets what "stationary" means in the alternative. With a constant
(`regression='c'`), the alternative is "stationary around a fixed mean". With a trend (`'ct'`), it
is "stationary around a straight line".

## The maths

**The ADF regression.** For a series $y_t$, ADF fits

$$
\Delta y_t = \alpha + \gamma\, y_{t-1} + \sum_{i=1}^{k} \delta_i\, \Delta y_{t-i} + e_t ,
$$

with a linear trend $\beta t$ added for `'ct'`. Here $\gamma = \phi - 1$, where $\phi$ is the AR(1)
coefficient. The null is $\gamma = 0$. The statistic is $\hat\gamma / \operatorname{se}(\hat\gamma)$.
Under the null it does not follow a t distribution; its critical values come from MacKinnon's
tables. At 5% with a constant the critical value is about −2.86, not −1.645.

The lag count $k$ is chosen by AIC from 0 to

$$
k_{\max} = \left\lceil 12 \left( n / 100 \right)^{1/4} \right\rceil .
$$

For the training sample, $n = 2037$: $(20.37)^{1/4} = 2.1245$, times 12 is 25.49, rounded up to
**26**. The project passes this value explicitly, so the artifact records it
(`stationarity.py:59`). On the training log price AIC chose 9 lags.

**The KPSS statistic.** Regress $y_t$ on a constant (or a constant and a trend). Call the residuals
$\hat u_t$ and their running sums $S_t$. Then

$$
\eta = \frac{1}{n^2 \hat\sigma^2_{\text{LR}}} \sum_{t=1}^{n} S_t^2 ,
$$

where $\hat\sigma^2_{\text{LR}}$ is a long-run variance with an automatically chosen bandwidth. A
wandering series has running sums far from zero, so $\eta$ is large. The 5% critical value is
0.463 with a constant and 0.146 with a trend.

**The clipped p-value.** statsmodels reads the KPSS p-value off a four-row table that covers
0.10, 0.05, 0.025 and 0.01. Outside that range it returns the edge and warns. On the training log
price, $\eta = 6.8235$, far above the 1% value of 0.739, so the p-value came back as 0.01 with the
warning "the actual p-value is smaller". The artifact stores this as `p_value_bound: "smaller"`,
and the app writes "≤ 0.01".

**A worked power measurement.** How often does each test notice a stationary series that is
close to a random walk? We simulated 400 AR(1) paths, $x_t = \phi x_{t-1} + \varepsilon_t$, for each
$\phi$, each of length 2,037 (the training size), and ran both tests with a constant at 5%:

| $\phi$ | Half-life of a shock | ADF rejects (power) | KPSS rejects | Both say "stationary" |
|---|---|---|---|---|
| 1 (random walk) | never decays | 7.0% (the size) | 98.0% | 0.8% |
| 0.999 | 693 days | 9.2% | 99.0% | 0.2% |
| 0.995 | 138 days | 30.8% | 89.5% | 5.8% |
| 0.99 | 69 days | 85.8% | 74.0% | 24.5% |
| 0.98 | 34 days | 100.0% | 53.0% | 47.0% |
| 0.95 | 13.5 days | 100.0% | 21.5% | 78.5% |

The half-life is $\ln 0.5 / \ln \phi$: for $\phi = 0.999$, $-0.6931 / -0.0010005 = 693$ trading days.
The script and its printed output are in the milestone-2 walkthrough, "Measured results".

Three lessons follow from the table.

1. **ADF has almost no power near 1.** A series whose shocks halve in 693 trading days (about
   2.75 years) is stationary, yet ADF rejects only 9.2% of the time, barely above its size of 7%.
2. **KPSS over-rejects for persistent stationary series.** At $\phi = 0.99$ the series is
   stationary, but KPSS rejects 74% of the time. Its null is true; it still says "unit root".
3. **Together they need a clear case.** The "stationary" verdict (ADF rejects, KPSS does not) is
   reached reliably only when shocks die out within a few weeks.

So the tests cannot tell a random walk from a very persistent stationary series with seven to
eight years of daily data. For forecasting a stock price this matters little: over a horizon of
weeks the two models forecast almost the same. It is why "the log price has a unit root" is a
modelling decision supported by evidence, not a proven fact.

**The size row.** ADF rejected 7.0% of true random walks, not 5%. With 400 paths the standard error
of a 5% rate is $\sqrt{0.05 \times 0.95 / 400} = 1.1$ points, so 7.0% is about 1.8 standard errors
high. Lag selection by AIC is a known reason for a slightly oversized ADF in finite samples. We did
not investigate it further.

## The 2 × 2 table

Each test gives "reject" or "do not reject". Read together:

| | KPSS does not reject | KPSS rejects |
|---|---|---|
| **ADF rejects** | **Stationary.** Both point the same way. Do not difference. | **Conflict.** Both reject. A structural break, or a root close to 1, can do this. Investigate. |
| **ADF does not reject** | **Inconclusive.** Neither test can tell. The data are too short or too noisy. | **Unit root.** Both point the same way. Difference and test again. |

The contract's `verdict` field uses exactly these four words (`stationarity.py:127`). The planned
contract had three; "inconclusive" was added when the table was implemented, because the cell
exists and the app must be able to show it.

**The rule for d** (ADR-0002, §2) reads this table at d = 0, 1 and 2, in order. It takes the first d
whose verdict is "stationary". If none is, it takes the first d at which KPSS does not reject, and
sets `tests_conflict` to true so that the app and the write-up say so (`stationarity.py:146`).

**On AAPL's training segment** the table reads:

| Series | ADF τ (p) | KPSS η (p) | Verdict |
|---|---|---|---|
| Log price, d = 0 | −0.407 (0.909) | 6.8235 (≤ 0.01) | Unit root |
| First difference, d = 1 | −13.814 (8.1 × 10⁻²⁶) | 0.0972 (≥ 0.10) | Stationary |
| Second difference, d = 2 | −13.981 (4.2 × 10⁻²⁶) | 0.0185 (≥ 0.10) | Stationary |

So d = 1, with no conflict. pmdarima's own `ndiffs` agrees with each of its three tests (KPSS, ADF
and PP all give 1).

**The second difference also passes.** Both tests call it stationary. That is expected: if the first
difference is stationary, so is its difference. Over-differencing does not show up as a failed
unit-root test. It shows up in the ACF (a lag-1 autocorrelation near −0.5) and as an MA root near the
unit circle (concept note 06 and the AIC landscape). This is why the rule takes the **smallest** d
that passes.

## The deterministic term

A log price that rose for eight years is not stationary around a fixed mean. So with `'c'`, ADF
compares a random walk with an alternative that cannot fit the data. That makes it easy for ADF not
to reject, for the wrong reason. The fairer rival to a random walk with drift is "stationary around a
straight line", which is `'ct'`.

The project runs both. The rule reads `'c'`, the statsmodels default and the course's call. The
`'ct'` run is reported next to it, in `with_trend`, to check that the verdict does not depend on
this choice. On the training log price it does not: with a trend, ADF gives p = 0.394 (still no
rejection) and KPSS gives η = 0.7538 against a 1% critical value of 0.216 (still a rejection). The
verdict stays "unit root".

The price of `'ct'` is power. Its critical values are more negative (−3.41 at 5% against −2.86), so
ADF needs stronger evidence to reject.

## Assumptions

- The errors are weakly dependent, so the lag augmentation (ADF) and the long-run variance (KPSS)
  can absorb their autocorrelation.
- One regime holds over the whole sample: no break in the level or the trend.
- The deterministic term matches the series under each hypothesis.
- The variance is roughly constant. Daily returns break this one (volatility clustering), which
  mostly affects the size of the tests, not their direction here.

## Where it breaks

- **Near 1, neither test is reliable.** See the power table: ADF misses persistent stationary series
  and KPSS flags them. A "unit root" verdict is a statement about the data you have.
- **Structural breaks** mimic unit roots. A one-off level shift makes a stationary series look
  integrated to ADF, and a break can make KPSS reject. The March 2020 crash is inside the training
  segment; we did not test for a break.
- **Multiple testing.** Two tests at three values of d is six tests. The 5% level is per test, not
  for the whole decision.
- **Course practice.** The course runs ADF alone, on the whole series (train and test). That uses
  test data to choose d, and it ignores what KPSS adds. Here both tests use the training rows only.

## In this project

- `src/arima_forecasting/stationarity.py:69` runs ADF with the lag range passed explicitly.
- `src/arima_forecasting/stationarity.py:101` runs KPSS and checks that its reading of a clipped
  p-value matches statsmodels' warning word for word, or stops.
- `src/arima_forecasting/stationarity.py:127` is the 2 × 2 table, and `:146` the rule for d.
- `src/arima_forecasting/stationarity.py:158` asks pmdarima's `ndiffs` for its answer, as a
  cross-check that can be "unavailable" without breaking the export.
- The app's Stationarity page draws the table from `stationarity.json`
  (`app/src/views/StationarityView.tsx`).
