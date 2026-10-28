# The Python → app JSON contract

This document is the single description of every file the Python side writes for the web app.
The *why* behind the overall design is in [ADR-0001](../adr/0001-python-computes-app-visualises.md);
the order-selection rules that the `stationarity` and `aic_grid` artifacts expose are in
[ADR-0002](../adr/0002-order-selection.md).

**Status by artifact:** `meta` is implemented (milestone 0). Every other section is the
**planned** shape. It is fixed enough to build against, and each milestone may refine it
under the versioning policy below.

---

## 1. Envelope rules (fixed)

Every file is `app/public/data/<artifact>.json` and has exactly these five keys:

```json
{
  "schema_version": "1.0.0",
  "artifact": "meta",
  "generated_at": "2026-10-28T12:00:00Z",
  "source_commit": "0123456789abcdef0123456789abcdef01234567",
  "data": {}
}
```

| Key | Type | Rule |
|---|---|---|
| `schema_version` | string | Semver `MAJOR.MINOR.PATCH`. One version for the whole contract, shared by every file written in one export. The app accepts any `1.x.y` and refuses every other major. |
| `artifact` | string | Matches `^[a-z][a-z0-9_]*$` on both sides (Python's `validate_envelope` and the app's `parseEnvelope`) and equals the file stem. The app also checks it against the file it asked for. |
| `generated_at` | string | UTC, exactly `YYYY-MM-DDTHH:MM:SSZ`, and a date and time that exist. Both sides apply the same calendar rules: years 0001–9999, real month lengths and leap years, and no leap second (a seconds field of 60 is refused). The app checks them with plain calendar arithmetic, because JavaScript's `Date.UTC` reads years 0–99 as 1900–1999; the shared fixture below checks that the two sides agree. Taken from `SOURCE_DATE_EPOCH` when that is set (see "Byte-identical re-exports" below). |
| `source_commit` | string | A git object name, 40 lowercase hex characters (SHA-1) or 64 (SHA-256), optionally followed by `-dirty`; or `uncommitted`. |
| `data` | object | The payload, described per artifact below. |

**Serialisation** (`arima_forecasting.contract.dumps`): `json.dumps(envelope, sort_keys=True,
indent=2, allow_nan=False)` plus a final newline, UTF-8. Sorted keys and fixed indentation
mean the same data always gives the same bytes, so a git diff shows only real changes.
`dumps` also refuses any integer outside JavaScript's safe-integer range, ±(2^53 − 1) =
±9,007,199,254,740,991. Beyond it `JSON.parse` would silently round the number to the nearest
double, so the app would read a different value from the one Python wrote.

**Closed envelope, open payload.** The envelope's top level is **closed**: both readers
(`validate_envelope` and `parseEnvelope`) reject a missing *or* an unknown top-level key, so
adding an envelope field is a major bump. The `data` payload is **open**: the app's payload
parsers **ignore unknown keys inside `data`**, which is what lets a minor version add fields
without breaking an older app.

**One fixture, two test suites.** `app/src/test/fixtures/envelope_cases.json` is a shared list
of valid and invalid envelopes. The Python suite runs every case through `validate_envelope` and
the app's suite runs every case through `parseEnvelope`, so a rule that changes on one side only
fails a test. That fixture is the guard against the two readers drifting apart.

**Byte-identical re-exports.** With `SOURCE_DATE_EPOCH` set, two exports of the same code (and,
from milestone 1, the same raw snapshot) write byte-identical files. That holds because the
dirty check behind `source_commit` leaves out `app/public/data/`, the exporter's own output:
provenance names the *code* that produced a file, so the first export rewriting `meta.json`
does not turn the second export's `source_commit` into `-dirty`. Any other uncommitted change,
untracked files included, still does. Known limit: a file marked with
`git update-index --assume-unchanged` or `--skip-worktree` is invisible to `git status`, so a
change to it is not reported as dirty.

## 2. Value conventions (apply to every artifact)

| Topic | Rule |
|---|---|
| **Missing values** | Explicit JSON `null`. Never `NaN`, `Infinity` or an omitted key (the export raises if a float is non-finite). Every nullable field is marked *nullable* below. Where a reader needs the reason, a sibling field gives it (`status`, `error`, `*_reason`). A key is always present, so the app can tell "no value" apart from "an older schema without this field". |
| **Dates** | `"YYYY-MM-DD"` strings: the exchange's trading date, with no time and no zone. Windows are half-open: `start` is included, `end_exclusive` is not. |
| **Numbers** | JSON numbers (IEEE-754 doubles). Counts and orders are integers. Python does **not** round; the app formats for display. |
| **Units in names** | `_usd`: dollars (adjusted close). `_log` or `log_`: natural log of the dollar price. `diff1`/`diff2`: first/second differences of the log price (daily log returns for `diff1`; unitless "log points"). `_pct`: percent on a 0–100 scale. Fields with no unit suffix are unitless (test statistics, p-values, AIC, densities). Changing a unit therefore means changing a name, which is a major bump. |
| **Row layout** | Arrays of objects ("records"), one object per row, sorted as stated per artifact. Self-describing and diff-friendly; columns cannot fall out of step. The cost is roughly 2–3× the size of a columnar layout; see size budgets. |
| **Enumerations** | Each enum is marked **closed** (the app may switch over it exhaustively; adding a value is a major bump) or **open** (the app must render unknown values generically; adding a value is a minor bump). |
| **Samples** | Any block of estimated numbers says which data it used: `"sample": "train" \| "course" \| "test" \| "oos"` (closed). `train` and `test` are the 90/10 split of the course window by position, `course` is train + test, and `oos` is the frozen out-of-sample window. |
| **Determinism** | No wall-clock values in `data` (no fit timings, no "downloaded 3 minutes ago"). The only clock value in a file is `generated_at`. |

### Versioning policy

`schema_version` describes the **shape** of the files, not their **content**. Re-exporting
with new data or fixed code changes the numbers and `source_commit`, never the version.

| Bump | When | Examples |
|---|---|---|
| **Major** (`2.0.0`): the app refuses | Anything an existing reader could misread | removing or renaming a field; changing a type, unit or meaning; making a non-nullable field nullable; adding a value to a **closed** enum; changing the date format; adding, removing or renaming an envelope key |
| **Minor** (`1.1.0`) | Additions an old reader can safely ignore | a new artifact; a new field in `data`; a new value in an **open** enum; making a nullable field always non-null |
| **Patch** (`1.0.1`) | No shape change | correcting this document; changing how a value is computed *without* changing what it means (a bug fix) |

Planned path: milestone 1 adds `prices` and `eda` (1.1.0), M2 adds `stationarity`, `acf_pacf`
and `aic_grid` (1.2.0), M3 adds `fit` and `residuals` (1.3.0), and M4 adds `forecasts` and
`metrics` (1.4.0). `meta.data.artifacts` always lists exactly the artifacts written by that
export, so the app knows which views can be switched on.

### Size budgets (estimates, to be measured when each artifact first ships)

Aim for ≤ 1 MB per file before compression (GitHub Pages serves gzip). The two largest are
expected to be `prices` (about 2,950 trading days from 2015 to September 2026) and `forecasts`
(about 2,700 rows). If a file passes 2 MB, the fix is a columnar layout for that artifact,
which is a major bump.

## 3. Artifacts by milestone

The rest of this document describes only the `data` object. "View" names the app screen that
reads the artifact.

---

### 3.1 `meta` [M0, implemented]

What the project is and how far it has got. **View:** the app shell (title, ticker, milestone
progress bar), and the gate that switches on views whose artifact exists.

| Field | Type | Notes |
|---|---|---|
| `project` | string | `"arima-stock-forecasting"` |
| `title` | string | display title |
| `ticker` | string | `"AAPL"` |
| `windows.course` | `{start: date, end_exclusive: date}` | `2015-01-01` → `2024-01-01` |
| `windows.oos` | `{start: date, end_exclusive: date}` | `2024-01-01` → `2026-10-01` |
| `milestones[]` | `{id: int, slug: string, title: string, status}` | `status` is a **closed** enum: `"done"`, `"current"`, `"planned"`. Exactly one is `"current"`. Sorted by `id`. |
| `artifacts[]` | string[] | slugs written by this export, for example `["meta"]` |

Source of truth: `src/arima_forecasting/export.py` (`meta_payload`) and `config.py` (the windows).

---

### 3.2 `prices` [M1]

The cleaned daily price series that every later step starts from. **View:** price / log-price
explorer (dollar or log axis, segments shaded).

| Field | Type | Notes |
|---|---|---|
| `ticker` | string | |
| `price_basis` | string, closed enum | `"adjusted_close"`: yfinance's `Close` with `auto_adjust=True` (see the ERD) |
| `source.provider` | string | `"yahoo_via_yfinance"` |
| `source.yfinance_version` | string | `"1.7.0"` |
| `source.raw_sha256` | string (64 hex) | SHA-256 of the raw snapshot file; links to its manifest |
| `source.raw_rows` | int | rows in the raw snapshot |
| `source.downloaded_at` | UTC timestamp string | from the snapshot manifest, not the export clock |
| `fill.method` | string | `"ffill"`, done with `.ffill()` (pandas 3.1 removed `fillna(method=...)`) |
| `fill.filled_dates` | date[] | dates whose close was forward-filled; usually empty, because yfinance already drops rows whose price and volume columns are all NaN or zero, unless `keepna=True` (`yfinance/scrapers/history.py:621-624`) |
| `splits.train_fraction` | number | `0.9` |
| `splits.train` / `.test` / `.oos` | `{start: date, end: date, n: int}` | the **actual** first and last trading dates in each segment (inclusive) and the row count |
| `rows[]` | see below | sorted by `date` ascending; course window then OOS window |

`rows[]`:

| Field | Type | Unit |
|---|---|---|
| `date` | date | |
| `close_usd` | number | $ (adjusted) |
| `log_close` | number | ln($) |
| `segment` | closed enum `"train"`, `"test"`, `"oos"` | |

Open question: whether this file is committed at all is the learner's decision; see ADR-0001.

---

### 3.3 `eda` [M1]

Descriptive views of the training series. **View:** price explorer side panels (distribution,
decomposition).

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `summary.n`, `summary.start`, `summary.end` | int, date, date | |
| `summary.close_usd` | `{min, max, mean, median}` | $ |
| `summary.log_return` | `{mean, std, skew, excess_kurtosis}` | over `diff1` of `log_close` |
| `kdes[]` | `{variable, bandwidth_method, bandwidth, points[]}` | `variable` is an **open** enum: `"log_close"` (the course's KDE) and `"log_return"` (shows the fat tails). `points[]` = `{x, density}`, 200 points; `x` is in the variable's unit. |
| `decomposition.model` | closed enum `"additive"` | applied to `log_close` (see note) |
| `decomposition.period` | int | `252` (trading days per year, approximately) |
| `decomposition.rows[]` | `{date, observed_log, trend_log, seasonal_log, resid_log}` | `trend_log` and `resid_log` are **nullable**: `null` for the first and last `period // 2` = 126 rows, because the centred moving average is undefined there (statsmodels `seasonal_decompose`, default `extrapolate_trend=0`; measured 126 NaN at each end with `period=252`). |

**Note on the course's decomposition.** The course calls
`seasonal_decompose(log_series, model='multiplicative', period=252)`. Taking logs already turns
a multiplicative structure into an additive one, so "multiplicative on logs" multiplies
components that are already logs. We use `additive` on `log_close`, which is equivalent to
`multiplicative` on the dollar price. The write-up shows both and explains the difference.

---

### 3.4 `stationarity` [M2]

The evidence for d. **View:** stationarity lab (toggle d = 0, 1, 2; see the series, its rolling
mean and standard deviation, and the ADF/KPSS table).

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `alpha` | number | `0.05` |
| `transforms[]` | see below | one per d, sorted by `d` |
| `decision.d_selected` | int | by the rule in ADR-0002 §2 |
| `decision.rule` | string | the rule in words, shown in the app |
| `decision.tests_conflict` | bool | true when no d satisfied both tests |
| `decision.pmdarima_ndiffs` | `{status, reason, kpss, adf, pp}` | `status` closed enum `"ok"`/`"unavailable"`; `reason` **nullable** string; `kpss`/`adf`/`pp` **nullable** ints (null when unavailable) |

`transforms[]`:

| Field | Type | Notes |
|---|---|---|
| `id` | closed enum `"log"`, `"diff1"`, `"diff2"` | |
| `d` | int | 0, 1, 2 |
| `n` | int | observations after differencing (n_train − d) |
| `adf` | `{statistic, p_value, used_lag, nobs, critical_values: {"1%","5%","10%"}, regression: "c", autolag: "AIC", reject_unit_root: bool}` | statsmodels `adfuller` |
| `kpss` | `{statistic, p_value, p_value_bound, nlags, critical_values: {"10%","5%","2.5%","1%"}, regression: "c", reject_stationarity: bool}` | `p_value_bound` is **nullable**, closed enum `"smaller"` (the true p is below the reported 0.01) or `"greater"` (the true p is above the reported 0.10), mirroring the wording of statsmodels' `InterpolationWarning`; `null` when the p-value was interpolated inside the table. statsmodels clips KPSS p-values to [0.01, 0.10] (`statsmodels/tsa/stattools/_stattools.py:3205-3235`). |
| `verdict` | closed enum `"stationary"`, `"unit_root"`, `"conflict"` | |
| `rows[]` | `{date, value, roll12_mean, roll12_std, roll252_mean, roll252_std}` | `value` is in this transform's unit (`log` → ln $, `diff1`/`diff2` → log points). Rolling fields are **nullable**: `null` until the window is full (the first 11 or 251 rows). Window 12 is the course's; 252 (one trading year) is added because 12 days is very short for daily data. |

---

### 3.5 `acf_pacf` [M2]

Autocorrelations used to *identify* candidate orders. **View:** stationarity lab, ACF/PACF
panel for the selected d.

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `nlags` | int | `50` (the course's value) |
| `alpha` | number | `0.05` |
| `acf_settings` | `{fft: true, adjusted: false}` | statsmodels defaults |
| `pacf_method` | string | `"ywadjusted"` (statsmodels default) |
| `series[]` | `{transform, n, rows[]}` | `transform` uses the same closed enum as `stationarity`; sorted by d |
| `series[].rows[]` | `{lag, acf, pacf, acf_band, pacf_band}` | `lag` 0…50. `*_band` is the half-width of the 95% band **around zero**, as `plot_acf` draws it (`confint − value`, `statsmodels/graphics/tsaplots.py:146`). `acf_band` widens with lag (Bartlett's formula); `pacf_band` is constant, 1.96/√n. At lag 0 both values are 1 and both bands are 0. |

---

### 3.6 `aic_grid` [M2]

Every (d, p, q, trend) fit on the training split, plus the selection and the pmdarima
cross-check. **View:** 3D AIC landscape (one surface per d and trend; **one d at a time**, never
two d on a shared AIC axis, because d is chosen by the unit-root tests and AIC is compared only
within one d; ADR-0002 §3 gives the reason).

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `n_train` | int | |
| `criterion` | `"aic"` | |
| `grid.p`, `grid.q` | int[] | `[0,1,2,3,4,5]` |
| `grid.specs[]` | `{d, trends[]}` | `[{d:0, trends:["c"]}, {d:1, trends:["n","t"]}, {d:2, trends:["n"]}]` |
| `fit_settings` | `{library: "statsmodels", version, method: "statespace", optimizer: "lbfgs", maxiter, enforce_stationarity: true, enforce_invertibility: true, simple_differencing: false, near_unit_root_threshold: 0.99}` | identical for every cell |
| `cells[]` | see below | sorted by `d`, `trend`, `p`, `q` |
| `selection` | see below | |
| `pmdarima_check` | see below | always present |

`cells[]` (144 rows):

| Field | Type | Notes |
|---|---|---|
| `d`, `p`, `q` | int | |
| `trend` | closed enum `"n"`, `"c"`, `"t"` | statsmodels `ARIMA` trend codes; `"t"` with d = 1 is a drift |
| `status` | closed enum `"ok"`, `"not_converged"`, `"near_unit_root"`, `"failed"` | only `"ok"` is eligible for selection |
| `aic`, `aicc`, `bic`, `llf` | number, **nullable** | `null` only when `status == "failed"` |
| `delta_aic` | number, **nullable** | `aic` minus the lowest eligible AIC **within the same d**; `null` if `aic` is null or the d has no eligible cell |
| `k_params` | int | estimated parameters, including `sigma2` |
| `nobs_effective` | int, **nullable** | n_train − d; `null` when failed |
| `converged` | bool, **nullable** | `mle_retvals["converged"]`; `null` when failed |
| `max_inv_root_ar`, `max_inv_root_ma` | number, **nullable** | largest modulus of the inverse roots; `null` when p (or q) is 0 or the fit failed |
| `warnings[]` | `{category, message}[]` | every warning raised during the fit, in order; empty if none |
| `error` | string, **nullable** | exception text when `failed`, otherwise `null` |

`selection`:

| Field | Type | Notes |
|---|---|---|
| `d_selected` | int | must equal `stationarity.decision.d_selected` (a test checks this) |
| `order` | `[p, d, q]` ints | |
| `trend` | closed enum, as above | |
| `aic` | number | |
| `rule` | string | for example "lowest AIC among status=ok cells with d = 1; ties: fewer parameters, then smaller p+q" |
| `within_2_aic[]` | `{p, q, trend, aic, delta_aic}` | near-ties within the selected d, sorted by AIC |
| `best_per_d[]` | `{d, p, q, trend, aic}`, **nullable** entries | for display only; the app must label these "AIC is not used to choose d" |

`pmdarima_check`:

| Field | Type | Notes |
|---|---|---|
| `status` | closed enum `"ok"`, `"unavailable"` | |
| `reason` | string, **nullable** | import or runtime error when unavailable |
| `version` | string, **nullable** | |
| `runs[]` | `{label, settings, order, with_intercept, aic, visited[]}` | `label` open enum: `"course"` (`test="adf"`), `"defaults"` (`test="kpss"`). `settings` echoes every argument passed. `visited[]` = `{order: [p,d,q], with_intercept: bool, aic}`, the fits the stepwise search kept: pmdarima's `return_valid_fits=True` leaves out failed fits and fits whose AIC its root test set to infinity (`pmdarima/arima/_auto_solvers.py:42-43, 564-566`). Empty array when unavailable. |
| `agreement` | `{d: bool, order: bool, aic_gap_same_order}`, **nullable** | `aic_gap_same_order` = pmdarima's AIC minus our AIC for pmdarima's chosen order with the matching trend; expected within ±1. It is not always near 0: on a near-cancelling ARMA(1,1) the two optimisers can stop at opposite ends of a flat ridge (ADR-0002 §7: φ ≈ 0.818 against φ ≈ 0.004, an AIC gap of 0.48) |

---

### 3.7 `fit` [M3]

The selected model fitted on the training split, and the course's refit for comparison.
**View:** residual diagnostics header (parameter table) and the forecast view legend.

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `models[]` | see below | open enum by `id`: `"selected"`, `"course_refit"` |

`models[]`:

| Field | Type | Notes |
|---|---|---|
| `id` | open enum | `"selected"` = ADR-0002's choice; `"course_refit"` = the course's order (from `auto_arima` on the full series) refitted with statsmodels' default trend, kept to show the dropped drift |
| `order` | `[p, d, q]` | |
| `trend` | closed enum `"n"`, `"c"`, `"t"` | |
| `nobs`, `nobs_effective`, `loglikelihood_burn` | int | |
| `params[]` | `{name, library_name, value, std_err, z, p_value, ci_low, ci_high}` | `name` is normalised (`"const"`, `"drift"`, `"ar.L1"`, `"ma.L1"`, `"sigma2"`); `library_name` is statsmodels' own label (its drift appears as `"x1"` in 0.15.0). `std_err`, `z`, `p_value`, `ci_low`, `ci_high` are **nullable** (null if the covariance matrix is singular). Values for `drift`/`const` are in log points per day; `sigma2` in log points squared. |
| `information` | `{llf, aic, aicc, bic, hqic}` | |
| `converged` | bool | |
| `warnings[]` | `{category, message}[]` | |
| `inv_roots_ar[]`, `inv_roots_ma[]` | `{re, im, modulus}[]` | empty when p (or q) is 0 |

---

### 3.8 `residuals` [M3]

Is the selected model's error white noise? **View:** residual diagnostics (time plot, KDE vs
normal, QQ, residual ACF, test table).

| Field | Type | Notes |
|---|---|---|
| `model_id` | `"selected"` | refers to `fit.models[].id` |
| `burn_excluded` | int | the first `max(loglikelihood_burn, nobs_diffuse)` residuals are dropped, as statsmodels' own `plot_diagnostics` does (`statsmodels/tsa/statespace/mlemodel.py:5344-5345`); the burned residual is huge and meaningless |
| `rows[]` | `{date, resid, resid_std}` | `resid` in log points; `resid_std` = standardised forecast error. Sorted by date. |
| `kde.points[]` | `{x, density, normal_density}` | over `resid_std`; `normal_density` is the N(0,1) reference |
| `qq[]` | `{theoretical, sample}` | every standardised residual, sorted; `theoretical` = normal quantiles |
| `acf.rows[]` | `{lag, acf, band}` | lags 1…50, band as in `acf_pacf` |
| `tests.ljung_box[]` | `{lag, statistic, p_value, model_df}` | lags 10 and 20; `model_df = p + q` |
| `tests.jarque_bera` | `{statistic, p_value, skew, kurtosis}` | |
| `tests.arch_lm` | `{lags, statistic, p_value}` | volatility clustering: why ARIMA intervals are too narrow in calm periods and too wide in stormy ones |

---

### 3.9 `forecasts` [M4]

Every forecast, as rows keyed by method, segment and date. **View:** animated walk-forward
forecast fan vs actuals; static-forecast panel.

| Field | Type | Notes |
|---|---|---|
| `interval_level` | number | `0.95` |
| `point_forecast` | closed enum `"median"` | `mean_usd = exp(mean_log)`, which is the **median** of the implied log-normal price, not its mean. The mean would be `exp(mean_log + var/2)`. The ratio is `exp(var/2)`: with a daily σ of 0.018, about 0.016% one day ahead and about 3.7% at the end of a 226-day static horizon (var ≈ hσ²). |
| `methods[]` | see below | |
| `segments[]` | see below | |
| `rows[]` | see below | sorted by `method`, `segment`, `date` |

`methods[]`:

| Field | Type | Notes |
|---|---|---|
| `id` | **open** enum | `"static"`, `"walk_forward"`, `"random_walk"`; a later milestone may add `"course"` (the course-faithful pipeline) |
| `label` | string | display name |
| `kind` | closed enum `"multi_step"`, `"one_step"` | |
| `model_id` | string, **nullable** | `fit.models[].id`; `null` for `random_walk` |
| `description` | string | for example "one-step-ahead, parameters frozen at the fit, filter updated with each actual (`ARIMAResults.apply`/`append(refit=False)`)" |

`segments[]` (proposed; to be confirmed in M4):

| `id` | `fit_sample` | `origin_date` | Meaning |
|---|---|---|---|
| `"test"` | `"train"` | last train date | the course's evaluation: model fitted on train, forecasts over the last 10% |
| `"oos"` | `"course"` | last course date | the true out-of-sample check: the **same order and trend** (no re-selection) refitted on the whole course window, forecasts over 2024-01-01 → 2026-09-30 |

`rows[]`:

| Field | Type | Unit / notes |
|---|---|---|
| `method` | string (from `methods[].id`) | |
| `segment` | closed enum `"test"`, `"oos"` | |
| `date` | date | the date being forecast |
| `step` | int | steps ahead of the origin: 1…h for `multi_step`, always 1 for `one_step` |
| `actual_log`, `actual_usd` | number | ln $, $ (from `prices`) |
| `mean_log` | number | ln $ |
| `lower_log`, `upper_log` | number, **nullable** | ln $. `null` for `random_walk` (it has no fitted variance in v1) |
| `mean_usd` | number | $, = exp(`mean_log`) |
| `lower_usd`, `upper_usd` | number, **nullable** | $, = exp of the log bounds (exp is monotonic, so the bounds map exactly) |

---

### 3.10 `metrics` [M4]

Forecast accuracy per method and segment. **View:** metrics table beside the forecast views.

| Field | Type | Notes |
|---|---|---|
| `rows[]` | see below | sorted by `segment`, `method` |

| Field | Type | Unit / notes |
|---|---|---|
| `method`, `segment` | as in `forecasts` | |
| `n` | int | rows scored |
| `rmse_usd`, `mae_usd` | number | $ (the course's metrics, on back-transformed median forecasts) |
| `mape_pct` | number | percent, 0–100 |
| `rmse_log`, `mae_log` | number | log points: scale-free, comparable between `test` and `oos` |
| `rmse_ratio_to_random_walk` | number, **nullable** | `rmse_usd / rmse_usd(random_walk)` in the same segment and of the same `kind`; < 1 beats the baseline; `null` for `random_walk` itself |
| `dm_vs_random_walk` | `{statistic, p_value, loss: "squared_error_usd", horizon}`, **nullable** | Diebold–Mariano test against the random walk; `null` for `random_walk` itself |

## 4. Who checks what

| Check | Where | Catches |
|---|---|---|
| Envelope valid before writing | `export_app_data.py` → `contract.validate_envelope` | malformed envelope |
| Both readers agree on every envelope | pytest and vitest each run `app/src/test/fixtures/envelope_cases.json` (§1) | a rule changed in `contract.py` or `contract.ts` but not in the other |
| No NaN/Infinity, no unsafe integers | `contract.dumps` (`allow_nan=False`, plus the ±(2^53 − 1) integer check) | failed calculations leaking into JSON; integers the browser would round |
| Payload shape per artifact | a validator per artifact in the package (from M1), run by pytest on the exporter's output | Python-side shape drift |
| App parses the **real** committed files | vitest, `app/src/lib/contract.realdata.test.ts`: every file in `app/public/data/` through the production `parseEnvelope`, its `artifact` equal to the file stem, its payload through that artifact's parser (`parseMeta` for `meta`; an artifact with no registered parser fails), and the set of files equal to `meta.data.artifacts` | Python changed, app not updated |
| Committed files are current | export check mode: regenerate, compare `schema_version`, `artifact`, `data` | code changed, nobody re-exported |
| Cross-artifact consistency | pytest: `aic_grid.selection.d_selected == stationarity.decision.d_selected`; `forecasts` dates ⊂ `prices` dates; every `methods[].model_id` exists in `fit` | artifacts disagreeing with each other |
