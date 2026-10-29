# The Python → app JSON contract

This document is the single description of every file the Python side writes for the web app.
The *why* behind the overall design is in [ADR-0001](../adr/0001-python-computes-app-visualises.md);
the order-selection rules that the `stationarity` and `aic_grid` artifacts expose are in
[ADR-0002](../adr/0002-order-selection.md).

**Status by artifact:** `meta` (milestone 0), `prices` and `eda` (milestone 1, schema `1.1.0`),
and `stationarity`, `acf_pacf` and `aic_grid` (milestone 2, schema `1.2.0`, extended in `1.3.0`) are implemented, and
their sections describe the shipped fields. Every other section is the
**planned** shape. It is fixed enough to build against, and each milestone may refine it under
the versioning policy below.

---

## 1. Envelope rules (fixed)

Every file is `app/public/data/<artifact>.json` and has exactly these five keys:

```json
{
  "schema_version": "1.3.0",
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
| `source_commit` | string | A git object name, 40 lowercase hex characters (SHA-1) or 64 (SHA-256), optionally followed by `-dirty`; or `uncommitted`. Since milestone 1 it names the last commit that touched anything outside `app/public/data/` (see "Byte-identical re-exports"). |
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
fails a test. That fixture is the guard against the two readers drifting apart. Milestone 1 adds
the same for payloads: `app/src/test/fixtures/payload_cases.json` edits a hand-written base payload
per artifact (`meta.data.json`, `prices.data.json`, `eda.data.json`, and from milestone 2
`stationarity.data.json`, `acf_pacf.data.json` and `aic_grid.data.json`, all made-up values) and
states each verdict: 218 cases, 132 of them for the milestone-2 artifacts.
`tests/test_payload_corpus.py` and `app/src/lib/contract.payloads.corpus.test.ts` run it through both
readers (`validate_meta`/`parseMeta`, `validate_prices`/`parsePrices`, `validate_eda`/`parseEda`,
`validate_stationarity`/`parseStationarity`, `validate_acf_pacf`/`parseAcfPacf`,
`validate_aic_grid`/`parseAicGrid`).

**Byte-identical re-exports.** With `SOURCE_DATE_EPOCH` set, two exports of the same code (and,
from milestone 1, the same raw snapshot) write byte-identical files. That holds because the
dirty check behind `source_commit` leaves out `app/public/data/`, the exporter's own output:
provenance names the *code* that produced a file, so the first export rewriting `meta.json`
does not turn the second export's `source_commit` into `-dirty`. Any other uncommitted change,
untracked files included, still does. For the same reason, `source_commit` is the last commit
that touched anything outside `app/public/data/` (`git log -1 -- ':(top)'
':(exclude)app/public/data'`), not HEAD: after "commit the code, export, commit the JSON", a
re-export at the JSON commit stamps the same code commit and reproduces the committed files byte
for byte. A repository whose commits only ever touched that folder gives `uncommitted`. Known limit: a file marked with
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

Path: milestone 1 added `prices` and `eda` (1.1.0), M2 added `stationarity`, `acf_pacf`
and `aic_grid` (1.2.0), and the milestone-2 fix round added fields inside `data` only (1.3.0: each
grid cell's `start` and `starts_tried`, the multi-start `fit_settings`, the correlograms' outside
flags and counts). M3 adds `fit` and `residuals` (1.4.0), and M4 adds `forecasts` and `metrics`
(1.5.0). The 1.3.0 readers require the new fields: a 1.2.0 `aic_grid` or `acf_pacf` is refused, and
the app ships with its data, so no older file reaches it. `meta.data.artifacts` always lists exactly the artifacts written by that
export, so the app knows which views can be switched on.

### Size budgets

Aim for ≤ 1 MB (1,000,000 bytes) per file before compression (GitHub Pages serves gzip). If a
file passes 2 MB, the fix is a columnar layout for that artifact, which is a major bump.
`tests/test_committed_artifacts.py` fails if any exported file other than `meta.json` passes
1,000,000 bytes, and `tests/test_repo_data.py` fails if any file in `app/public/data/` passes
10,000,000 bytes (the hard limit of the owner's data rule; see `DATA.md`).

Measured on 2026-10-29 on the milestone-2 export (after the review's fix round, schema 1.3.0) of the 13:37 UTC snapshot (`wc -c`, and Python's
`gzip.compress(data, 6)`; GNU `gzip -6` gives slightly different sizes). The export's
`source_commit` ended in `-dirty`; a clean stamp is 6 bytes shorter per file. All six files are
committed since the owner's decision of 2026-10-29 (ADR-0001, `DATA.md`).

| File | Rows | Bytes | Share of 1 MB | gzip level 6 (Python) |
|---|---|---|---|---|
| `meta.json` | n/a | 1,531 | 0.2% | 565 |
| `prices.json` | 2,953 price rows | 456,025 | 45.6% | 67,170 |
| `eda.json` | 2,037 decomposition rows + 2 × 200 KDE points | 529,907 | 53.0% | 101,501 |
| `stationarity.json` | 3 transforms, 12 test results | 6,685 | 0.7% | 1,355 |
| `acf_pacf.json` | 3 × 51 lags | 44,899 | 4.5% | 6,624 |
| `aic_grid.json` | 144 cells with their parameters, 2 pmdarima runs | 153,790 | 15.3% | 27,717 |

`forecasts` (about 2,700 rows) is still an estimate; it is measured when it ships.

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
| `held_artifacts[]` | string[] | added in 1.1.0: the subset of `artifacts` that the export writes but the repository does not commit (git-ignored). `["prices", "eda"]` in milestone 1; **`[]` since the owner's decision of 2026-10-29** (ADR-0001, `DATA.md`): every exported file is committed. The field stays, because removing it would be a major bump. The real-data tests still skip a held file that is absent, with a message that says how to build it; the app no longer has a "not built in this copy" panel (removed in the milestone-2 fix round, as nothing is held), so a missing file is shown as an error like any other. Each entry must be one of `artifacts`, named once, and never `meta` itself (the app learns what is held from meta). Both readers check this (`validate_meta`, `parseMeta`). The app reads a 1.0.x file, which has no such key, as `[]` |

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
| `source.raw_sha256` | string (64 hex) | SHA-256 of the raw snapshot file's bytes; equals `sha256` in its manifest |
| `source.raw_rows` | int | rows in the raw snapshot (one download covers both windows) |
| `source.downloaded_at` | UTC timestamp string | from the snapshot manifest, not the export clock |
| `source.request` | `{start: date, end_exclusive: date, interval: string, auto_adjust: true}` | the yfinance request that made the snapshot (`start`, `end`, `interval`, `auto_adjust` in the manifest's `request`). Added in 1.1.0 with the artifact itself. |
| `fill.method` | string, closed enum | `"ffill"`, done with `.ffill()` (pandas 3.1 removed `fillna(method=...)`) |
| `fill.filled_dates` | date[] | dates whose close was missing in the snapshot and forward-filled, sorted; each is one of `rows[].date`. A fill may carry a close at most 7 calendar days (`prep.MAX_GAP_DAYS`); a longer run of missing closes, or a missing tail, stops the export instead. Usually empty, because yfinance already drops rows whose price and volume columns are all NaN or zero, unless `keepna=True` (`yfinance/scrapers/history.py:621-625`). Empty in the 2026-10-29 snapshots. |
| `splits.train_fraction` | number | `0.9`. The course window's first `int(n × 0.9)` rows are `train` (truncation, as the course does it), the rest `test` |
| `splits.train` / `.test` / `.oos` | `{start: date, end: date, n: int}` | the **actual** first and last trading dates in each segment (inclusive) and the row count. Both readers check them against `rows[]` |
| `rows[]` | see below | sorted by `date` strictly ascending; course window then OOS window; segments in one block each, in the order `train`, `test`, `oos` |

`rows[]`:

| Field | Type | Unit |
|---|---|---|
| `date` | date | |
| `close_usd` | number | $ (adjusted) |
| `log_close` | number | ln($) |
| `segment` | closed enum `"train"`, `"test"`, `"oos"` | |

**Committed** since the owner's decision of 2026-10-29 (ADR-0001, "The owner's decision on the
price files"; `DATA.md`). In milestone 1 it was held: git-ignored and named in
`meta.data.held_artifacts`. Readers: Python's `validate_prices` (`src/arima_forecasting/payloads.py`) and the app's
`parsePrices` (`app/src/lib/contract.payloads.ts`).

---

### 3.3 `eda` [M1]

Descriptive views of the training series. **View:** price explorer side panels (distribution,
decomposition).

| Field | Type | Notes |
|---|---|---|
| `sample` | closed enum `"train"` | |
| `summary.n`, `summary.start`, `summary.end` | int, date, date | the training rows; equal to `prices.splits.train` |
| `summary.close_usd` | `{min, max, mean, median}` | $ |
| `summary.log_return` | `{n, mean, std, skew, excess_kurtosis}` | over `diff1` of `log_close`, so `n = summary.n − 1`; both readers refuse any other value. Estimators: `std` divides by n − 1; `skew` is the adjusted Fisher–Pearson G1 (pandas `skew()`, scipy `skew(bias=False)`); `excess_kurtosis` is the bias-corrected G2 (pandas `kurt()`, scipy `kurtosis(bias=False)`), 0 for a normal |
| `kdes[]` | `{variable, n, bandwidth_method, bandwidth_factor, bandwidth, points[]}` | `variable` is an **open** enum: `"log_close"` and `"log_return"` (shows the fat tails); both are required, others may be added. (The course's own KDE is of the *dollar* close; see the milestone-1 walkthrough.) `bandwidth_method` is `"scott"` (scipy `gaussian_kde` default); `bandwidth_factor` is scipy's `factor` = n^(−1/5); `bandwidth` is the kernel's standard deviation in the variable's unit, factor × the sample sd (ddof 1). `points[]` = `{x, density, normal_density}`, 200 points, `x` strictly ascending in the variable's unit on an even grid from (min − 3 × bandwidth) to (max + 3 × bandwidth). `normal_density` is the normal density with the sample's mean and sd, for comparison. |
| `decomposition.model` | closed enum `"additive"` | applied to `log_close` (see note) |
| `decomposition.period` | int | `252` (trading days per year, approximately) |
| `decomposition.rows[]` | `{date, observed_log, trend_log, seasonal_log, resid_log}` | one per training row, sorted by date. `trend_log` and `resid_log` are **nullable**, and null on exactly the same rows: the first and last `period // 2` = 126 rows, because the centred moving average is undefined there (statsmodels `seasonal_decompose`, default `extrapolate_trend=0`; measured 126 at each end in the shipped file). `validate_eda` checks that exact pattern. |

Readers: Python's `validate_eda` (`src/arima_forecasting/payloads.py`) and the app's `parseEda`
(`app/src/lib/contract.payloads.ts`).

**Note on the course's decomposition.** The course calls
`seasonal_decompose(log_series, model='multiplicative', period=252)`. Taking logs already turns
a multiplicative structure into an additive one, so "multiplicative on logs" multiplies
components that are already logs. We use `additive` on `log_close`. As a *model* that is the
multiplicative model of the dollar price. As an *estimate* it is close but not identical: the
trend of the logs, exponentiated, is a weighted geometric moving average of prices, while a
multiplicative decomposition of dollars uses the arithmetic one. The gap is about half the weighted
variance of ln P inside one 253-day window, which in the 2020 run-up was mostly drift (measured on
the training rows: at most 3.03% in the trend and 0.73% in the seasonal part).
The milestone-1 walkthrough and [concept note 04](../concepts/04-classical-decomposition-additive-on-logs.md)
show both versions with measured differences.

---

### 3.4 `stationarity` [M2, implemented]

The evidence for d. **View:** the Stationarity page (the test table, the 2 × 2 reading and the
decision). Committed, like every exported file (`DATA.md`); it holds test statistics, not series values.

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `n_train` | int | training rows (the length of the d = 0 series) |
| `alpha` | number | `0.05`; a test rejects when its p-value is below it |
| `transforms[]` | see below | one per d, sorted by `d` strictly ascending |
| `decision.d_selected` | int | by the rule in ADR-0002 §2; both readers re-apply the rule to `transforms` and refuse any other value |
| `decision.rule` | string | the rule in words, shown in the app |
| `decision.tests_conflict` | bool | true when no d is "stationary", so the KPSS fallback chose d |
| `decision.pmdarima_ndiffs` | `{status, reason, version, alpha, max_d, kpss, adf, pp, agrees}` | `status` closed enum `"ok"`/`"unavailable"`. When ok: `reason` null, `version` a string, `kpss`/`adf`/`pp` ints in 0…`max_d`, `agrees` true exactly when all three equal `d_selected`. When unavailable: `reason` a string, `version` nullable, the four values null |

`transforms[]`:

| Field | Type | Notes |
|---|---|---|
| `id` | closed enum `"log"`, `"diff1"`, `"diff2"` | |
| `d` | int | 0, 1, 2, matching `id` |
| `n` | int | `n_train − d` |
| `adf` | `{statistic, p_value, used_lag, maxlag, nobs, critical_values: {"1%","5%","10%"}, regression: "c", autolag: "AIC", reject_unit_root}` | statsmodels `adfuller` with `maxlag` = ⌈12 (n/100)^¼⌉ passed explicitly (statsmodels' own default rule); `used_lag` ≤ `maxlag`; `reject_unit_root` = `p_value < alpha` |
| `kpss` | `{statistic, p_value, p_value_bound, nlags, nlags_method: "auto", critical_values: {"10%","5%","2.5%","1%"}, regression: "c", reject_stationarity}` | `p_value` lies in [0.01, 0.10] because statsmodels clips it to its table (`statsmodels/tsa/stattools/_stattools.py:3224-3235`). `p_value_bound` is **nullable**, closed enum: `"smaller"` exactly when `p_value` is 0.01 (the true p is 0.01 or less), `"greater"` exactly when it is 0.10, `null` otherwise. The exporter stops if this reading disagrees with statsmodels' `InterpolationWarning` |
| `verdict` | closed enum `"stationary"`, `"unit_root"`, `"conflict"`, `"inconclusive"` | the 2 × 2 table of concept note 05, from `reject_unit_root` and `reject_stationarity`; both readers check it. `"inconclusive"` (neither test rejects) was added when the planned three-value enum met the fourth cell of the table |
| `with_trend` | `{adf, kpss, verdict}` | the same two tests with `regression: "ct"` (a constant and a linear trend). Reported to show whether the verdict depends on the deterministic term; **the rule never reads it** |

**Changed from the plan:** the planned `rows[]` (the series, with 12- and 252-day rolling means and
standard deviations) is not in the artifact. For the three transforms it would add 1,680,767 bytes
(measured, written as the exporter writes), past the 1 MB budget for one file, and the d = 0 series
is already in `prices.json`. The Stationarity page shows the tests and the correlograms, which need
no series; a later minor version can add `rows[]` if a view needs it.

Readers: Python's `validate_stationarity` (`src/arima_forecasting/payloads.py`) and the app's
`parseStationarity` (`app/src/lib/contract.order.ts`).

---

### 3.5 `acf_pacf` [M2, implemented]

Autocorrelations used to *identify* candidate orders. **View:** the Stationarity page, ACF and PACF
panels for one d at a time (the chosen d first). Committed: correlations only.

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `nlags` | int | `50` (the course's value) |
| `alpha` | number | `0.05` |
| `z` | number | the two-sided normal quantile for `alpha`, 1.959963984540054. Tied to `alpha` by a table both readers hold (`Z_FOR_ALPHA` in `payloads.py` and `contract.order.ts`): the pair must be one of its rows, exactly, and its only row is (0.05, 1.959963984540054). A new alpha needs a row in both readers |
| `acf_settings` | `{fft: false, adjusted: false, bartlett_confint: true}` | `plot_acf`'s own defaults, which the course's picture uses (the `acf` function itself defaults to `fft: true`; the two agree to about 1e-16) |
| `pacf_method` | string | `"ywm"`, `plot_pacf`'s default (the `pacf` function itself defaults to `"ywadjusted"`, which can leave [−1, 1]) |
| `series[]` | `{transform, d, n, acf_outside_count, pacf_outside_count, rows[]}` | `transform` uses the same closed enum as `stationarity`, `d` matches it; sorted by d; `n` = observations of that series. The two counts (added in 1.3.0) are the number of rows flagged outside, lags 1 to `nlags`; both readers recount them |
| `series[].rows[]` | `{lag, acf, pacf, acf_band, pacf_band, acf_outside, pacf_outside}` | exactly `nlags + 1` rows, `lag` 0…`nlags` in order. `acf` and `pacf` lie in [−1, 1] and are 1 at lag 0. `*_band` is the half-width of the 95% band **around zero**, as `plot_acf` draws it (upper limit minus value, `statsmodels/graphics/tsaplots.py:146`): 0 at lag 0 and positive after. `acf_band` is Bartlett's formula, z √((1 + 2 Σⱼ₍<ₖ₎ rⱼ²) / n), so it widens with the lag; `pacf_band` is z / √n at every lag. `*_outside` (added in 1.3.0) is Python's verdict that the bar reaches past its band: \|value\| > band, strictly, and never at lag 0. Both readers refuse a flag that disagrees with its value and band; the app draws the flag and never compares a value with its band itself |

Readers: Python's `validate_acf_pacf` and the app's `parseAcfPacf`.

---

### 3.6 `aic_grid` [M2, implemented]

Every (d, p, q, trend) fit on the training split, the selection and the pmdarima cross-check.
**View:** the AIC landscape page (one surface per d, never two d on a shared AIC axis, because d is
chosen by the unit-root tests and AIC is compared only within one d; ADR-0002 §3). Committed:
AIC values and fit diagnostics, never a price.

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `n_train` | int | |
| `criterion` | `"aic"` | |
| `grid.p`, `grid.q` | int[] | `[0,1,2,3,4,5]`, strictly ascending |
| `grid.specs[]` | `{d, trends[]}` | `[{d:0, trends:["c"]}, {d:1, trends:["n","t"]}, {d:2, trends:["n"]}]`; sorted by d, trends in alphabetical order |
| `fit_settings` | `{library: "statsmodels", version, model: "ARIMA", method: "statespace", optimizer: "lbfgs", maxiter: 200, enforce_stationarity: true, enforce_invertibility: true, concentrate_scale: false, simple_differencing: false, near_unit_root_threshold: 0.99, starts, random_starts, start_seed, keep_tolerance, nesting_tolerance}` | identical for every cell; a test checks each value against what statsmodels used. The last five (added in 1.3.0) describe the several starts of each cell (ADR-0002, "Revised in the milestone-2 fix round"): `starts` in words; `random_starts` and `start_seed` (ints ≥ 0); `keep_tolerance` (≥ 0), within which a converged run is kept over a higher unconverged one; `nesting_tolerance`, which must be 2e-3, the bound the readers apply |
| `cells[]` | see below | exactly one per (d, trend, p, q) of the grid (144), sorted by d, then trend, then p, then q |
| `selection` | see below | |
| `pmdarima_check` | see below | always present |

`cells[]`:

| Field | Type | Notes |
|---|---|---|
| `d`, `p`, `q` | int | |
| `trend` | closed enum `"n"`, `"c"`, `"t"` | statsmodels `ARIMA` trend codes; `"t"` with d = 1 is a drift |
| `status` | closed enum `"ok"`, `"not_converged"`, `"near_unit_root"`, `"failed"` | only `"ok"` is eligible. Precedence: failed (the fit raised), then not_converged (`converged` false), then near_unit_root (an inverse root modulus above the threshold), then ok. Both readers recompute it from the fields below |
| `reason` | string, **nullable** | `null` exactly when `ok`; otherwise why, in words (the warnflag, the root moduli, or "the fit raised an error") |
| `k_params` | int | p + q + (1 if trend is not `"n"`) + 1 for `sigma2`; known even for a failed fit |
| `aic`, `aicc`, `bic`, `llf` | number, **nullable** | `null` exactly when `failed` |
| `delta_aic` | number, **nullable** | `aic` minus the lowest `aic` among `ok` cells of the **same d**; `null` if `aic` is null or the d has no ok cell. Both readers recompute every value exactly (double subtraction is the same in both languages) |
| `nobs_effective` | int, **nullable** | `n_train − d`; `null` when failed |
| `converged` | bool, **nullable** | `mle_retvals["converged"]`; `null` when failed |
| `iterations`, `warnflag` | int, **nullable** | L-BFGS's iteration count and scipy's `warnflag` (0 converged, 1 a limit reached, 2 stopped for another reason); `null` when failed |
| `max_inv_root_ar`, `max_inv_root_ma` | number, **nullable** | largest modulus of the inverse roots; `null` exactly when p (or q) is 0 or the fit failed |
| `warnings[]` | `{category, message}[]` | every warning raised while building the model and during the kept run, in order; empty if none |
| `error` | string, **nullable** | `"<ExceptionType>: <message>"` when `failed`, otherwise `null` |
| `start` | string, **nullable** | added in 1.3.0: the start the kept run came from: `"default"` (statsmodels' own), `"random <k>"` (the k-th seeded random start, k ≤ `random_starts`, only when p and q are both ≥ 1), or `"nested (p, d, q) <trend>"` (a model of the grid one step smaller: the next smaller p, the next smaller q, or no trend, its estimates padded with zeros), optionally with `", perturbed +"` or `", perturbed -"` (the new AR or MA coefficients set to small seeded values of that sign; not on the trend step); each optionally followed by `", polished"` (that run did not converge and was restarted once from its own estimates). Or `"polished from (p, d, q) <trend>"`: won in the polish stage, from that cell's estimates (same d, any cell of the grid, the cell itself included), by Nelder-Mead then L-BFGS. `null` exactly when `failed`. Both readers check the grammar, that a nested start is one step smaller, and that a polish-stage source is a cell of the same d |
| `params` | object, **nullable** | added in 1.3.0: the kept run's estimates by statsmodels' parameter name, exactly `k_params` finite numbers; `null` exactly when `failed`. A cell won in the polish stage cannot be replayed from its label alone; its likelihood is checked at these values |
| `starts_tried` | int ≥ 1 | added in 1.3.0: how many runs the cell made, the polish included |

**The nesting rule** (both readers, 1.3.0). A cell *nests* another when it has the same d, no fewer
AR and MA lags, and the same trend or a trend where the other has none: setting its extra
coefficients to zero gives the smaller model exactly. So its maximised log-likelihood cannot be
lower. Both readers refuse a file in which any fitted cell's `llf` is below that of a cell it nests
by more than 2e-3, whatever the two cells' statuses: a lower value is a local optimum. The bound is
pinned in each reader (`NESTING_TOLERANCE`), not read from the file, and a file whose
`fit_settings.nesting_tolerance` states another value is refused. The milestone-2 review found 86 such pairs among the `ok` cells of d = 1 in the 1.2.0
file.

`selection` (both readers re-derive each part from `cells` and refuse a mismatch):

| Field | Type | Notes |
|---|---|---|
| `d_selected` | int | one of the grid's d; equal to `stationarity.decision.d_selected` (a test checks this) |
| `order` | `[p, d, q]` ints | the lowest-AIC ok cell of `d_selected`; ties: fewer parameters, then smaller p + q, then smaller p, then the trend code |
| `trend` | closed enum, as above | |
| `aic`, `bic`, `k_params` | number, number, int | the chosen cell's |
| `rule` | string | the rule in words |
| `within_2_aic[]` | `{p, q, trend, aic, delta_aic}` | every ok cell of `d_selected` with `delta_aic` ≤ 2, the chosen one included, in rank order |
| `bic_choice` | `{p, q, trend, aic, bic}` | the ok cell of `d_selected` with the lowest BIC (same tie rule), for the write-up |
| `best_per_d[]` | `{d, cell: {p, q, trend, aic} \| null}` | one per grid d in order; `cell` is **nullable** (no ok cell). For display only: the app labels it "AIC is not used to choose d" |
| `status_counts[]` | `{d, ok, not_converged, near_unit_root, failed}` | one per grid d in order |

`pmdarima_check`:

| Field | Type | Notes |
|---|---|---|
| `status` | closed enum `"ok"`, `"unavailable"` | |
| `reason` | string, **nullable** | null when ok; the import or runtime error when unavailable |
| `version` | string, **nullable** | |
| `runs[]` | see below | non-empty when ok, empty when unavailable |

`runs[]`: `{label, settings, order, with_intercept, trend, aic, converged, iterations, visited[], warnings[], agreement}`.
`label` is an **open** enum: `"course"` (the course's arguments, `test="adf"`, start (1, 1)) and
`"defaults"` (pmdarima's defaults plus `seasonal=False`). `settings` echoes every argument passed,
`return_valid_fits: true` included (the course's `trace=True` only prints and is not passed). `trend`
is our code for pmdarima's model, **nullable**: `"n"` without an intercept, `"c"` with one at d = 0, `"t"`
with one at d = 1, `null` at d = 2 (no matching cell). `converged` and `iterations` describe the chosen
model's fit. `visited[]` = `{order, with_intercept, aic}`, the fits the stepwise search kept, best
first: `return_valid_fits=True` leaves out failed fits and fits whose AIC its root test set to
infinity (`pmdarima/arima/_auto_solvers.py:42-43, 564-566`); the first entry is the chosen model.
`agreement` = `{d, order, trend, same_order_status, aic_gap_same_order}`: three booleans comparing
the run with `selection`, the status of our cell with the same (p, d, q, trend) (**nullable**), and
pmdarima's AIC minus that cell's (**nullable**). The gap is not always near 0. On AAPL the default run's
(2, 1, 2) fit stopped at pmdarima's `maxiter=50` without converging, and the gap is +7.56 (milestone-2
walkthrough).

Readers: Python's `validate_aic_grid` and the app's `parseAicGrid`.

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
| Payload shape per artifact | `src/arima_forecasting/payloads.py` (`validate_meta`, `validate_prices`, `validate_eda`, `validate_stationarity`, `validate_acf_pacf`, `validate_aic_grid`), run by the exporter on every payload before writing, by `read_artifact` and `--check`, and by pytest | Python-side shape drift |
| Both readers agree on every payload | pytest and vitest each run `app/src/test/fixtures/payload_cases.json` (§1): integral floats such as `4.0` count as integers (JavaScript cannot tell them apart), integers beyond ±(2^53 − 1) and numbers too big for a double are refused, and "blank" is one explicit whitespace class on both sides | a payload rule changed in `payloads.py` or `contract.payloads.ts` but not in the other |
| App parses the **real** files | vitest, `app/src/lib/contract.realdata.test.ts`: every file in `app/public/data/` through the production `parseEnvelope`, its `artifact` equal to the file stem, its payload through that artifact's parser (`parseMeta`, `parsePrices`, `parseEda`, `parseStationarity`, `parseAcfPacf`, `parseAicGrid`; an artifact with no registered parser fails), and the set of files equal to `meta.data.artifacts` less the held ones that are absent (each such file gets a skipped test that says why) | Python changed, app not updated |
| Files are current | `tools/export_app_data.py --check`: regenerate from the raw snapshot, compare `schema_version`, `artifact`, `data`, and the set of files, and refuse a file the app would refuse (its envelope and payload are validated too); exit 1 on a difference, 2 without a snapshot. It refits all 144 grid cells, so it takes about a minute (59.2 s measured on 2026-10-29). Without the snapshot, `tests/test_committed_artifacts.py` checks every step after it: `meta.json` = `meta_payload()`; `prices.json` and `eda.json`, where present, equal what the current code builds from `prices.json`'s own closes; where `prices.json` is present, `stationarity.json` and `acf_pacf.json` equal a fresh computation and a sample of grid cells refits exactly; and in every copy the committed selection and d follow from the committed cells and tests | code changed, nobody re-exported |
| Cross-artifact consistency | pytest (`tests/test_committed_artifacts.py`, in every copy): `aic_grid.selection.d_selected == stationarity.decision.d_selected`, and the three milestone-2 files describe the same training rows; planned: `forecasts` dates ⊂ `prices` dates, every `methods[].model_id` exists in `fit` | artifacts disagreeing with each other |
