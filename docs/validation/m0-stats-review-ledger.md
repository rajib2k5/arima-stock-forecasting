# Milestone 0: adversarial review of the statistics and library-behaviour claims

**Reviewer:** adversarial-reviewer session (Opus), 2026-10-28.
**Protocol:** evidence-gated validation, Tier 2 dual channel.
**Mode:** single-context sequential fallback. Every "SURVIVES" below means *dual-confirmed (fallback mode)*, not independently proven. The claims ledger and probe designs were frozen first. The Channel A verdicts were written before any probe ran. One probe check (C1d) had a wrong pass condition and was re-run as a separate, labelled probe.
**Default verdict:** every claim started as "broken".
**Scope:** the statistics and library claims in `docs/concepts/00-background.md`, `docs/adr/0002-order-selection.md`, `docs/architecture/contract.md`, `docs/milestones/00-scaffold.md` (Pitfalls, Predict-first, Results) and `docs/prfaq.md` (the four mistakes). Not in scope: Q3, Q4, Q7 and Q8 of the milestone, which cover git, the bundle and test counts. They were not examined.

**Environment** (taken from `uv run python -I`, aarch64):

- Python 3.12.13, statsmodels 0.15.0, pmdarima 2.1.1, pandas 3.1.0, yfinance 1.7.0, numpy 2.5.4, scipy 1.18.1.
- `SP` below means `.venv/lib/python3.12/site-packages`.
- All data was simulated. No prices were downloaded.
- For yfinance, `YfData.get` and `cache_get` were replaced by a fake. The proxies pointed at `127.0.0.1:9`, so a real request would have failed. All 10 HTTP calls went to the fake. `~/.cache/py-yfinance` was left untouched (mtimes checked before and after).

The probe scripts and their raw outputs are kept outside the repo, in the session scratchpad (`review-stats/probes/p1…p7`). The outputs quoted below are copied from them verbatim.

---

## C1. statsmodels 0.15.0 `ARIMA`

| Sub-claim | Channel A (source) | Channel B (probe output) | Verdict |
|---|---|---|---|
| Default trend is `'n'` when d ≥ 1 (and `'c'` when d = 0) | `SP/statsmodels/tsa/arima/model.py:156-160`; docstring `:68-69` | `trend d=1: n  d=0: c  D=1: n`. The mutant run, with the expectation flipped, FAILs. | **SURVIVES** |
| `trend='c'` with d ≥ 1 raises | `model.py:178-190`: raises when the lowest trend term is below d + D | `('c',d=1)`, `('ct',d=1)` and `('t',d=2)` all raise `ValueError`. `('t',d=1)` constructs. | **SURVIVES**. The rule is broader than stated: `'t'` with d = 2 also raises. |
| `simple_differencing=False` | `model.py:204-211` (not passed), `:229-232` (stripped from the init keys), `sarimax.py:344` (default False) | `simple_differencing attr: False  model nobs: 2000` | **SURVIVES** |
| The likelihood burns the first d observations | `sarimax.py:677-683`: burn = k_states − k_order when stationarity is enforced, otherwise k_states | Burn is 0/1/1/2 for (1,0,0), (0,1,0), (1,1,0), (0,2,1), and `llf == sum(llf_obs[burn:])` exactly (5331.595517 and 5328.296924). With `enforce_stationarity=False` the burn is 2 for (0,1,0) and 3 for (2,1,0). | **SURVIVES**. The first probe asserted `llf_obs[:d] == 0`. That condition was wrong (statsmodels reports the burned terms but leaves them out of `llf`), so that check was invalid and was replaced by the sum check. |
| `trend='t'` with d = 1 is a drift | `model.py:61-72`, `:104-121` (the trend is an exog regressor in levels, `trend_offset=1`) | `params x1 0.000823`. Every forecast increment is 0.000823 (`np.allclose`). | **SURVIVES** |

## C2. The likelihood identity, and why AIC is not compared across d

**Equality.** Channel B, on the training part (`y[:1800]`, seed 20261028):

- `lev llf 4798.454852 burn 1 nobs_eff 1799 | dif llf 4798.454852 burn 0 nobs_eff 1799 | gap -4.10e-09`
- At identical parameters the gap is `-3.467e-09`.
- The gap moves with the approximate-diffuse variance: −3.5e-8 at 1e4, −3.5e-9 at 1e6, +1.8e-6 at 1e8 (rounding error dominates at 1e8).
- Falsifier: an ARMA(1,0) **with** a constant on the differences differs by −2.144.
- `SARIMAX(simple_differencing=True)` gives 4798.454852.
- `use_exact_diffuse=True` gives **4797.535914** (`nobs_diffuse 1`, burn 0). That is 0.92 nats lower, which equals −½ log 2π for one diffuse observation.

**Equality verdict: SURVIVES.** Caveat: the identity holds under statsmodels' default convention (approximate diffuse prior plus burn). It does not hold under exact diffuse initialisation.

**Does the conclusion follow, and is it explained correctly?** Channel B on the training part:

- d = 0 (1,0,0)+c: llf = log p(y₁) **−1.074** + conditional 4798.364, with φ̂ = 0.99985.
- AIC with the full likelihood: d0 −9588.58 against d1 −9597.08 (gap 8.50).
- AIC on the common sample y₂…yₙ: d0 −9590.73 against d1 −9597.08 (gap **6.35**).
- The full series reproduces the ADR's −10654.96 and −10664.60 exactly. There, log p(y₁) = −1.166 and the common-sample gap is 7.31.

What this shows:

- The equality by itself does not imply incomparability. The **burn** does: the d = 0 likelihood contains one extra term, log p(y₁), from the stationary prior.
- This difference exists because of the diffuse initialisation.
- The two likelihoods describe the *same* random variables. The Jacobian of differencing is 1, so log p(Δy₂…Δyₙ) = log p(y₂…yₙ | y₁).
- The ADR's formula (`0002-order-selection.md:155-158`) is correct.
- Two things are missing from the docs:
  - Here the "different data" term is worth only about 2 AIC points of the 8.5–9.6.
  - The deeper reason not to choose d by AIC is that the d = 0 and d = 1 comparison sits on the unit-root boundary. There the likelihood ratio follows a Dickey–Fuller distribution, not χ², so AIC's 2k penalty is not calibrated.

| Statement | Verdict |
|---|---|
| ADR §3 formula and table (`0002:144-162`) | **SURVIVES**. Every number reproduces. |
| Background §6, `00-background.md:365-368`: "a density for the log *prices* … for the log *returns*. They describe different random variables … not on a common scale" | **REFUTED**. Conditional on y₁ they are the same variables on the same scale. The difference is one term, −1.07 nats here. |
| Milestone Q6, `00-scaffold.md:1042`: AIC "must never be compared across d" | **REFUTED as worded**. It contradicts the ADR's own rejected alternative (`0002:176-184`), and the common-sample comparison is valid. |

**Fix:** replace "different random variables / not on a common scale" with: "the d = 0 likelihood also scores y₁ under the stationary prior; the d = 1 likelihood conditions on y₁ through the diffuse prior and the burn. Even on a common sample, AIC is not calibrated for the unit-root boundary, so d is chosen by tests."

## C3. The drift-trap numbers (ADR problem 2; milestone Q5)

**Reproduction.** Channel B (p1, p2):

- `last train 4.8874  sm default step1 4.8874 step200 4.8874  sm 't' step200 5.0519  actual y[1999] 5.1442`
- `ADR args, train: best (0, 1, 0) intercept=True aic=-9597.077 step200=5.0529`

**SURVIVES**: every number reproduces to 4 dp.

**Is "the refit drops pmdarima's drift" a correct reading of the course?** **SURVIVES, with a condition.**

- `ARIMA(train_data, order=model_autoARIMA.order)` (`sample.txt:245`) passes only the (p, d, q) tuple. The intercept is never passed on, and the refit's trend is `'n'` (probe p6).
- With the course's *full* argument list, auto_arima still picks (0,1,0) + intercept, on both the training part and the full series (p2).
- The condition: this only matters when pmdarima's selected model actually has an intercept. The stepwise search can turn the intercept off (see C4b).
- New finding (p6): on the pinned stack the course never reaches the flat line. Its `get_forecast` raises (see "Not asked" 1).

**Dollar percentages.** **SURVIVES**, with one inconsistency.

- 0.1655 → e^0.1655 − 1 = 18.0%.
- 226 × 0.0009 → 22.6%.
- 1 − e^(−0.48) = 38.1%.
- The docs mix two bases. "18%" is pmdarima's forecast relative to the flat one. Measured against the drifting forecast, the flat one is 15.3% lower. The background's "38% lower" uses that second base.

## C4. pmdarima 2.1.1

| Sub-claim | Channel A | Channel B | Verdict |
|---|---|---|---|
| `test='kpss'`, `information_criterion='aic'` | `SP/pmdarima/arima/auto.py:349, :351` | `inspect.signature`: `'test': 'kpss', 'information_criterion': 'aic'` | **SURVIVES** |
| `with_intercept='auto'` gives an intercept iff d + D ∈ {0, 1} | `auto.py:623-624` sets the *starting* value. `_auto_solvers.py:312-314` and `:440-445` refit without the constant and toggle it. | Intercept candidates of both kinds `[False, True]` were fitted at d = 0, 1 **and 2** | **REFUTED as a statement about the final model**. It is true only of the starting value. The docs themselves describe it correctly (`00-background.md:613-615`). |
| Failed fits are dropped and warnings hidden | `_auto_solvers.py:507-520` and `:564-566`. Only `LinAlgError` and `ValueError` are caught. The default `error_action='trace'` (`auto.py:362`) warns. | Injected a `ValueError` for (1,1,1). With the default, (1,1,1) was dropped and **`['ModelFitWarning']`** was raised, with a traceback. With `'ignore'`, nothing was raised. `suppress_warnings=True` silenced the in-fit warnings (0 against 3). | **Partly REFUTED**. Failed fits are dropped. Under the defaults they are not hidden: only warnings raised *inside* the fit are suppressed. The course's `error_action='ignore'` is what makes failures silent. Any other exception type aborts the whole search (an `IndexError` did, in p2). ADR §5 (`0002:229-232`) words this correctly. ADR `:268` ("drops failed fits, hides warnings") is loose. |
| Stepwise visits a subset (ADR problem 3: 5 orders including (2,1,2), "with the course's arguments") | The course passes `start_p=1, start_q=1` (`sample.txt:210`). The defaults are 2 and 2 (`auto.py:333-335`). ADR `:45` says "everything else is the library default". | ADR's args on train: **5** orders, including (2,1,2). The course's real args on train: **4** orders, `[(0,1,0),(0,1,1),(1,1,0),(1,1,1)]`, with the same choice and forecast. | **"Subset" SURVIVES. "5 orders with the course's arguments" is REFUTED.** |
| `test='adf'` is pmdarima's own ADF (with a trend term and a fixed lag ⌊(n−1)^{1/3}⌋ + 1) | `stationarity.py:327-332`: `k = trunc(...)`, then `k + 1` is the embed width. The regression takes `z[:,1:k]` (`:290-291`), which is k − 1 lagged differences. | pm statistic `-0.642439`, 15 regressors, which is 12 lagged differences. statsmodels `adfuller(ct)` gives **12 lags → -0.642439** and 13 lags → −0.719864. | **Own ADF with a trend: SURVIVES. "+1" lag: REFUTED.** The lag is ⌊(n−1)^{1/3}⌋. Fix `0002:126` and `00-background.md:615-616`. |

## C5. yfinance 1.7.0 `download`, single ticker, faked HTTP

| Sub-claim | Channel A | Channel B | Verdict |
|---|---|---|---|
| `auto_adjust=True`: Close is the adjusted close and there is no Adj Close | `multi.py:56`; `utils.py:506-523` | Close `[10.0 … 14.0]` (the fake's adjclose), `'Adj Close' present: False`. Falsifier with `auto_adjust=False`: both columns present. | **SURVIVES**. Caveat: on failure, `utils.empty_df()` (`utils.py:269-276`) **does** contain `('Adj Close', T)`. |
| `multi_level_index=True`; `(Price, Ticker)`; `df['Close']` is a DataFrame | `multi.py:59, 216, 222-227` | `names ['Price', 'Ticker'] \| type(df['Close']): DataFrame`. With `multi_level_index=False` it is a Series. | **SURVIVES** |
| tz-naive index | `multi.py:143-144`, `:209-212` | `index tz: None` | **SURVIVES** |
| `end` is exclusive | `multi.py:77-80`; `history.py:213-215`, `:393-396` | `period2` was 2024-01-09 00:00 −05:00 and the last row 2024-01-08. One trailing bar was dropped. With **two** bars at or after `end`, 2024-01-09 **was kept**. | **SURVIVES on the client side.** It relies on Yahoo honouring `period2`, because yfinance trims only one row. |
| An error returns an empty frame and does not raise | `multi.py:298-302` | `returned DataFrame shape (0, 6) empty True` and the log line "possibly delisted", for a simulated `ConnectionError` | **SURVIVES** |

## C6. pandas 3.1.0 `fillna(method='ffill')`

- Channel A: `SP/pandas/core/generic.py:7230-7237` has no `method` keyword.
- Channel B: `TypeError: NDFrame.fillna() got an unexpected keyword argument 'method'` for a Series, a DataFrame, and the course's DataFrame call with `inplace=True`. The falsifier `fillna(value=0)` works.

**SURVIVES.**

## C7. statsmodels tests

- **`kpss` clipping.** Channel A: `_stattools.py:3211-3235`. Channel B: a random walk gives p 0.01 with "smaller". White noise gives p 0.1 with "greater". The falsifier AR(0.99) gives p 0.0354 with no warning. **SURVIVES.**
- **`acorr_ljungbox` default `model_df=0`.** Channel A: `diagnostic.py:600`, `:750-753`. Channel B: p 0.7534 equals `chi2.sf(Q,10)`. **SURVIVES.**
- **FutureWarning without `result_object`.** Channel A: `_stattools.py:465-475` and `:3250-3261`, removal "0.16.0 or after July 2027". Channel B: `adfuller()` and `kpss()` raise `FutureWarning`; `result_object=False` raises nothing. **SURVIVES. It is real in 0.15.0.** The list is incomplete: `het_arch` (`diagnostic.py:920-928`) also warns (measured), and so does `acf` when given exactly one of `qstat`/`alpha` (`:1037-1051`). Milestone 3 uses `het_arch`.

## C8. Maths in `00-background.md`

| Item | Evidence | Verdict |
|---|---|---|
| Lognormal median e^μ and mean e^{μ+σ²/2}; FPP3's approximation | 2e6 draws: median 1.22138 against 1.22140, mean 1.27190 against 1.27188. FPP3 §5.6 text was fetched and confirms both. | SURVIVES |
| Random walk with drift: mean y_T + hμ̂, variance hσ² + h²σ²/(T−1), and FPP3's √(h(1+h/(T−1))) | Monte Carlo variance 2.4982e-2 against the formula's 2.5025e-2. FPP3 table fetched. | SURVIVES |
| Intervals widen like √h | se(h)/se(1) at h = 1, 4, 16, 64, 256: d = 0 → 1.05 (flat); d = 1 → 2.61, 5.68, 11.57, 23.26 (≈ √h/(1−φ)); d = 2 → about h^{1.5} | SURVIVES. The text scopes √h to the random walk and to d = 1 "eventually", which is correct. It is not true for ARIMA in general. |
| "Reverts … at the rate of the largest AR root" (`:461`) | The doc puts roots outside the unit circle. The root is 3.19, and the decay is 1/root = φ = 0.313. | **REFUTED (wording)**. Should read "the largest *inverse* AR root (the root nearest the unit circle)". |
| ADF regression, null and critical values | `mackinnoncrit`: n −2.566/−1.941/−1.617; c −3.43/−2.862/−2.567; ct −3.959/−3.41/−3.127 | SURVIVES. Minor: γ = φ − 1 is the AR(1) case. In general γ = −φ(1). |
| KPSS null and η | `_stattools.py:3213-3216` (η = ΣS²/T² ÷ long-run variance) | SURVIVES. The symbol r_t means both log return (Notation) and the KPSS random-walk part. |
| Over-differencing: MA(1) with θ = −1 | acf lag-1 −0.493, variance ratio 1.980, MA fit −1.000 | SURVIVES |
| Constant against drift in backshift form | FPP3 §9.5 fetched; `sarimax.py:234-235`; `model.py:104-121` | SURVIVES |
| AR(2) triangle; |θ| < 1 | standard; matches FPP3 | SURVIVES |
| AIC, AICc, BIC; the AICc identity | `eval_measures.py:415, 445-448, 476`. The two AICc forms agree numerically (−9593.98663). | SURVIVES |
| Ljung–Box Q* with m − p − q degrees of freedom | 400 AR(1) residual series: mean Q(10) 9.13. Rejection at 5% is 0.043 with 10 degrees of freedom and 0.065 with 9. | SURVIVES |
| ARCH-LM "TR²" | statsmodels 8.6907 equals (T−q)R² = 8.6907, against TR² = 8.7344 | Minor: T is the auxiliary-regression sample, T − q |
| MAPE, MASE and Theil's U formulas | H&K preprint pp. 7–11 fetched | SURVIVES |
| MAPE asymmetry "reason" (`:536-538`) | Fixed actual 100: forecasts 110 and 90 both give 0.10. The swap gives 0.333 against 0.500. Hyndman (2014) cites Goodwin & Lawton (1999): for a fixed actual, MAPE is symmetric. | **Incomplete**. Equal-size errors at a fixed actual are penalised equally. The asymmetry is in the swap, or in the bounded range that biases MAPE-optimal forecasts low. |
| Diebold–Mariano, HLN, nested-model caveats | consistent with the cited works (formulas not re-derived) | SURVIVES (weak) |

## C9. Literature

- **Fama (1970)**, JSTOR scan:
  - p.383 (three test forms), p.384 (tests "depend to some extent on its validity as well as on the efficiency"), p.386 (submartingale, and fn 4 "random walk with drift"), p.387 ("says much more", "superfluous") and p.388 ("obviously an extreme null hypothesis"): all **confirmed**.
  - **fn 5 is misread** (`00-background.md:90-92`). Fn 5 says that under the random walk model past returns help assess the *stationary* distribution, but "the sequence (or the order) of the past returns is of no consequence". That rules out predictable volatility. It does not license it. **REFUTED (citation).**
- **Meese & Rogoff (1983)**: the primary PDF's abstract matches. **SURVIVES.**
- **MAPE direction.** H&K 2006 p.9 says "heavier penalty on positive errors". Hyndman (2014) says "we got it the wrong way around". FPP3 §5.8 says "negative errors". **SURVIVES**, with the explanation caveat under C8.
- **Tashman (2000)**: bibliographic record, plus secondary fragments on rolling origins. **SURVIVES (weak; content not seen at primary).**
- **Dickey & Fuller (1979), Said & Dickey (1984)**: abstracts match. The k³/n → 0 growth rate is not in the abstract.
- **Kwiatkowski et al. (1992), Engle (1982)**: bibliographic records match. Content not re-read. **SURVIVES (bibliographic).**
- **DOIs**: 12/12 resolve on Crossref with matching authors, year, journal, volume, issue and pages. The 12 are Fama, Meese–Rogoff, Tashman, Dickey–Fuller, Said–Dickey, KPSS, Engle, Hyndman–Koehler, Diebold–Mariano, Ljung–Box, Plosser–Schwert and Diebold 2015.

## C10. Predict-first answers

- **Q1, Q2**: re-run, outputs identical. **SURVIVE.**
- **Q5**: numbers and explanation **SURVIVE**.
- **Q6**: the numbers survive. Two explanations do not:
  - "−4.1e-9 … optimiser noise" (`00-scaffold.md:1038`) is **REFUTED**. At identical parameters the gap is −3.47e-9 and it scales with the approximate-diffuse variance, so the optimiser accounts for about 0.6e-9 of it.
  - "must never be compared" is refuted under C2.
- **Q3, Q4, Q7, Q8**: not examined (out of scope).

## C11. The PR/FAQ's four mistakes against `sample.txt`

1. **Order chosen on the full series.** `auto_arima(df_log…)` (`:210`) runs before the split (`:230-231`). **Present.**
2. **One static forecast over the whole test period.** `get_forecast(steps=len(test_data))` (`:274-275`). **Present.** On the pinned stack it raises (see "Not asked" 1).
3. **Dollar errors with no baseline** (`:299-308`). **Present.** The course also reports MAPE in %, and under yfinance 1.7.0 that MAPE line returns `nan` (see "Not asked" 2).
4. **`np.exp` of the mean gives the median.** `np.exp(predicted_mean)` (`:276-279`). **Present. SURVIVES**, conditional on a Gaussian predictive distribution with plug-in parameters. For the course's (0,1,0) no-trend refit, the mean is y_T exactly, so exp(y_T) is exactly the model's median and the mean is P_T·e^{hσ̂²/2}. Two caveats on the PR/FAQ wording (`prfaq.md:19`):
   - The course never says "expected". It *scores* with RMSE, which the mean minimises.
   - "exp of an average log is not the average" explains why the forecast is *not the mean*. It does not explain why it *is the median*, which needs symmetry on the log scale.

---

## Not asked about, found anyway

1. **The course's Module 9 crashes on the pinned stack.**
   - statsmodels 0.15.0 raises `ValueError: No supported index is available.` from `get_forecast` when the model was fitted on a DatetimeIndex with no frequency (`SP/statsmodels/tsa/base/tsa_model.py:437-445`).
   - A trading-day index always has no frequency, because of holidays.
   - Measured in p6 on a simulated 2,336-row trading-day frame with yfinance-shaped columns.
   - No milestone-0 document records this. Milestone 4 must forecast with numpy input or a supported index.
2. **The course's MAPE line returns `nan` under yfinance 1.7.0.** `forecast_series - test_data_actual` subtracts a one-column DataFrame from a Series, and pandas aligns the Series index against the DataFrame's columns. The result is a 235×236 all-NaN frame (p6b). The positional MAPE would have been 14.06%.
3. **pmdarima's root test ignores AR roots whenever q + Q > 0.** `_auto_solvers.py:37-40` overwrites the AR maximum with the MA one. A fake ARMA(1,1) with an AR inverse root of 0.999 kept IC 10.0; the AR(1) version got inf. So ADR `:226` ("an inverse AR or MA root … pmdarima's threshold") and `:257` overstate what pmdarima discards.
4. **ADR §7's "0.48 gap … slightly different points" (`0002:261`; also `contract.md:264`).** pmdarima stopped at φ = 0.818, θ = −0.828. statsmodels stopped at φ = 0.004, θ = 0.004. These are opposite ends of a near-cancelling ridge, not nearby points.
5. **Background footnote `[^probe-pm]` (`00-background.md:777`) does not reproduce from its stated recipe.** The footnote gives intercept 0.00193, 0.4822 and 0.4834. The recipe gives 0.00186, 0.4648 and 0.4661, so 37% rather than 38%. Three seed variants also failed. The `[^probe-drift]`, `[^probe-adf]` and `[^probe-acf]` footnotes do reproduce exactly.
6. **`contract.md:321`, "about 0.01%" for the one-day mean/median gap.** It is 0.016% at σ = 0.018.

## Summary

| ID | Claim | Verdict |
|---|---|---|
| C1a–e | statsmodels ARIMA defaults, burn, drift | SURVIVES (C1b broader than stated) |
| C2 equality | levels llf = differences llf | SURVIVES (holds only under the approximate-diffuse convention) |
| C2 reason | "different random variables / not on a common scale"; "must never" | **REFUTED** |
| C3 | 4.8874 / 5.0529 / 5.1442; refit drops the drift; dollar % | SURVIVES (the bases are mixed) |
| C4a | kpss, aic defaults | SURVIVES |
| C4b | intercept iff d + D ∈ {0, 1} | **REFUTED** for the final model (true only of the starting value) |
| C4c | failures dropped and warnings hidden | **Partly REFUTED** (ModelFitWarning by default) |
| C4d | 5 orders with the course's arguments | **REFUTED** (4 orders; course start_p = start_q = 1) |
| C4e | pmdarima ADF lag ⌊(n−1)^{1/3}⌋ + 1 | **REFUTED** (the lag is ⌊(n−1)^{1/3}⌋) |
| C5a–e | yfinance defaults and shapes | SURVIVES (caveats on `end` and on the failure frame) |
| C6 | `fillna(method=)` raises `TypeError` | SURVIVES |
| C7a–c | KPSS clipping, Ljung–Box `model_df`, FutureWarning | SURVIVES (FutureWarning list incomplete) |
| C8 | maths | SURVIVES except the "largest AR root" wording; the MAPE reason is incomplete |
| C9 | literature and DOIs | SURVIVES except the **Fama fn 5 misreading** |
| C10 | Q5, Q6 | Q5 SURVIVES; the Q6 "optimiser noise" explanation is **REFUTED** |
| C11 | four mistakes present | SURVIVES. The PR/FAQ misses that Module 9 crashes and that the MAPE is `nan` on the pinned stack. |
