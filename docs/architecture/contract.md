# The Python → app JSON contract

This document is the single description of every file the Python side writes for the web app.
The *why* behind the overall design is in [ADR-0001](../adr/0001-python-computes-app-visualises.md);
the order-selection rules that the `stationarity` and `aic_grid` artifacts expose are in
[ADR-0002](../adr/0002-order-selection.md).

**Status by artifact:** `meta` (milestone 0), `prices` and `eda` (milestone 1, schema `1.1.0`),
`stationarity`, `acf_pacf` and `aic_grid` (milestone 2, schema `1.2.0`, extended in `1.3.0`), and
`fit`, `residuals_aic`, `residuals_bic` and `residuals_course` (milestone 3, schema `1.4.0`), and
the seven `forecast_<model>_<method>` files and `evaluation` (milestone 4, schema `1.5.0`) are
implemented, and their sections describe the shipped fields.

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
| **Bounds** | Every list in `data` is bounded before it is walked, in both readers (`payloads._list`, `Reader.list`): a longer one is one short problem, "`<path>: has N <items>, more than the M a reader takes`", the same words in both, and is not read. Lists of days and points: `MAX_LIST` = 10,000 (no list of trading days can be longer than the download window's 4,291 calendar days; the KDE grids have 200 points). Short lists of names (meta's milestones and artifacts, eda's KDEs, the fit's lag lists): `MAX_NAMES` = 100. A list that enumerates a pinned set takes that set's size (transforms and correlogram series 3, fit models 3, Ljung–Box rows 3, ARCH-LM rows 2); the AIC grid takes its dimensions (p and q axes 6 values each from 0 to 5, specs 3 with d from 0 to 2, trends 3, cells and `within_2_aic` 324, `best_per_d` and `status_counts` 3, a cell's `params` object walked only up to 12 entries) and pmdarima's (2 runs, 72 visited fits each); the fit's lists take its order (parameters 22, roots and pairs 10, burned rows 2); every warning list 100 (`MAX_WARNINGS`); the forecast windows `MAX_ROWS` (§3.9). The shared corpus's `size_cases` put each list one past its bound, at its bound, and (for the grid) at 2,000,000 items, in both readers. **One bound per file, not per list:** a reader reports at most `MAX_PROBLEMS` = 200 problems for a file and then one more, "`data: more than 200 problems; a reader reports the first 200 and stops`" ("`envelope: …`" for the envelope's own problems), and stops reading (`contract.MAX_PROBLEMS` and `more_problems` in Python, `MAX_PROBLEMS` and `moreProblems` in `contract.ts`), so lists inside lists cannot multiply the count (100 KDEs of 10,000 empty points gave 3,000,000 problems before it). The corpus's `cap_cases` hold both readers to the same first 200 problems, word for word, and the same last line. **One quoting function:** a message shows a value read from a file only through `contract.shown` (Python) or `shown` (`contract.ts`): up to 80 characters of a string and its length, a list or object only when it has at most 8 small, flat entries, anything else by its size, and never by walking into a nested value; a key read from a file is quoted the same way (`params['ar.L1']`). A value the reader has already checked to be a date, a finite number or one of a pinned set is written as it is (at most 24 characters, or the pinned text). So a 60 MB string or a 100,000-deep array gives a short problem, quickly, in both readers (Python's `json.loads` stops near 10,000 levels; `read_artifact` and `--check` report such a file as one problem). In Python an integer too big for a double (400 digits; JSON.parse reads it as Infinity) is a problem, never an exception: every conversion of a number from a file to a float catches the overflow (`_finite`, `_Checker.number`), and no `int()` reads a run of digits from a file that could pass the 4,300 digits Python allows. `tests/test_payloads_hostile.py` puts such an integer in every numeric field of every artifact, in turn, and runs the per-file readers, the checks across files and `--check`'s family check on each |

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
flags and counts). M3 added `fit` and one residuals artifact per fitted model, `residuals_aic`,
`residuals_bic` and `residuals_course` (1.4.0). In that export the five earlier data artifacts
changed only their envelopes; `meta.data` lists the four new names and marks milestone 3 current.
M4 added the seven `forecast_<model>_<method>` artifacts and `evaluation` (1.5.0); in that export the
earlier artifacts changed only their envelopes, and `meta.data` lists the eight new names and marks
milestone 4 current. The 1.3.0 readers require the new fields: a 1.2.0 `aic_grid` or `acf_pacf` is refused, and
the app ships with its data, so no older file reaches it. `meta.data.artifacts` always lists exactly the artifacts written by that
export, so the app knows which views can be switched on.

### Size budgets

Aim for ≤ 1 MB (1,000,000 bytes) per file before compression (GitHub Pages serves gzip). If a
file passes 2 MB, the fix is a columnar layout for that artifact, which is a major bump.
`tests/test_committed_artifacts.py` fails if any exported file other than `meta.json` passes
1,000,000 bytes, and `tests/test_repo_data.py` fails if any file in `app/public/data/` passes
10,000,000 bytes (the hard limit of the owner's data rule; see `DATA.md`).

Measured on 2026-10-29 on the milestone-3 fix-round export (schema 1.4.0) of the 13:37 UTC snapshot (file
sizes in bytes, the same as `wc -c`, and Python's `gzip.compress(data, 6)`; GNU `gzip -6` gives
slightly different sizes; the script is `m3_probe.py` in the milestone-3 walkthrough). The export's
`source_commit` ended in `-dirty`; a clean stamp is 6 bytes shorter per file. All ten files are
committed since the owner's decision of 2026-10-29 (ADR-0001, `DATA.md`). Shares are rounded to one
decimal.

| File | Rows | Bytes | Share of 1 MB | gzip level 6 (Python) |
|---|---|---|---|---|
| `meta.json` | n/a | 1,613 | 0.2% | 585 |
| `prices.json` | 2,953 price rows | 456,025 | 45.6% | 67,176 |
| `eda.json` | 2,037 decomposition rows + 2 × 200 KDE points | 529,907 | 53.0% | 101,505 |
| `stationarity.json` | 3 transforms, 12 test results | 6,685 | 0.7% | 1,356 |
| `acf_pacf.json` | 3 × 51 lags | 44,899 | 4.5% | 6,626 |
| `aic_grid.json` | 144 cells with their parameters, 2 pmdarima runs | 153,790 | 15.4% | 27,719 |
| `fit.json` | 3 models (9, 5 and 2 parameters) with roots and tests | 18,464 | 1.8% | 4,464 |
| `residuals_aic.json` | 2,036 residual rows, 2 × 50 ACF rows, 2,036 QQ points | 483,331 | 48.3% | 93,437 |
| `residuals_bic.json` | the same | 483,320 | 48.3% | 93,397 |
| `residuals_course.json` | the same | 483,398 | 48.3% | 93,578 |
| `forecast_aic_static.json` | 916 forecast rows (227 test, 689 oos), 15 numbers each | 652,916 | 65.3% | 142,160 |
| `forecast_aic_walk_forward.json` | the same | 654,568 | 65.5% | 138,653 |
| `forecast_aic_refit.json` | the same, and 43 refits | 700,824 | 70.1% | 145,013 |
| `forecast_bic_static.json` | 916 forecast rows | 653,233 | 65.3% | 135,141 |
| `forecast_bic_walk_forward.json` | the same | 654,114 | 65.4% | 135,918 |
| `forecast_course_static.json` | the same | 653,590 | 65.4% | 123,794 |
| `forecast_course_walk_forward.json` | the same | 654,966 | 65.5% | 135,783 |
| `evaluation.json` | 4 random-walk, 14 metric, 16 DM and 56 coverage rows | 44,965 | 4.5% | 7,077 |

The three residual series in one file would be 1,450,049 bytes, past the budget; that is why they
are three artifacts (§3.8). On the milestone-2 export (schema 1.3.0) the first six files had the
same byte counts except `meta.json` (1,531), and `aic_grid.json`'s share was listed as 15.3%, a
truncation of 15.38%.

The eight milestone-4 rows were measured the same way on the milestone-4 export (schema 1.5.0, the
same snapshot, `source_commit` ending in `-dirty`), where `meta.json` is 1,856 bytes (631 gzipped).
A model's static and walk-forward paths in one file would be about 1.3 MB, past the budget: that is
why the forecasts are one file per model and method (§3.9).

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
| `windows.oos` | `{start: date, end_exclusive: date}` | `2024-01-01` → `2026-10-01`, pinned in both readers (`config.OOS_WINDOW`; `payloads.OOS_START` and `OOS_END_EXCLUSIVE`, `OOS_WINDOW` in `contract.ts`; added in the milestone-4 third review pass): any other window is refused. The course window is not pinned |
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
| `splits.train_fraction` | number | must be `0.9` (`config.TRAIN_FRACTION`), pinned in both readers (`TRAIN_FRACTION`). The course window's first `int(n × 0.9)` rows are `train` (truncation, as the course does it), the rest `test`: both readers count the rows' segments and refuse any other split (`prep.train_size`, applied with the pinned fraction, never the file's), so a boundary moved by one row with the split counts rewritten to match is refused |
| `splits.train` / `.test` / `.oos` | `{start: date, end: date, n: int}` | the **actual** first and last trading dates in each segment (inclusive) and the row count. Both readers check them against `rows[]`, and against the pinned out-of-sample window (§3.1): the oos segment lies inside it, and train and test end before it starts. The oos rows must also cover the window as the producer's own check does (`prep.check_coverage` with `prep.MAX_GAP_DAYS` = 7; `OOS_MAX_GAP_DAYS` in both readers): the first at most 7 calendar days after 2024-01-01, the last at most 7 before 2026-10-01 (exclusive), and no two consecutive ones more than 7 apart, so rows dropped at either end or inside are refused. (The first and last trading days, 2024-01-02 and 2026-09-30, are not pinned: the synthetic snapshot the tests export trades every weekday, so its oos rows start on 2024-01-01.) |
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
`fit_settings.nesting_tolerance` states another value is refused. The milestone-2 review found 94 such pairs among the `ok` cells of d = 1 in the 1.2.0
file (99 at zero tolerance; the largest shortfall 21.83).

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

### 3.7 `fit` [M3, implemented]

Three models fitted on the training split, each with its parameter inference, inverse roots and
residual tests, and the course's recipe with its two problems measured. Built by
`src/arima_forecasting/fitting.py` and `src/arima_forecasting/diagnostics.py`. **View:** the "Fit and
diagnostics" page (model picker, parameter table, unit circle, test table). Committed: estimates and
test statistics. One value is about a price: the burned residual (`diagnostics.burned[].resid`) is
about the first log price, 3.185 on AAPL, and it is exported so the page can show what the course's
plots include. The only dates are those of the burned residuals.

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `n_train` | int ≥ 2 | |
| `primary` | `"aic"` | a one-value enum: the AIC choice is the primary model (owner's default, LEARNING_LOG); both readers refuse any other id |
| `fit_settings` | `{library, version, model: "ARIMA", method: "statespace", optimizer, maxiter, cov_type: "opg", enforce_stationarity, enforce_invertibility, concentrate_scale}` | the settings of the two grid refits; `cov_type` is statsmodels' default (outer product of gradients). The course model uses `ARIMA(train, order).fit()` defaults, which are the same here except `maxiter` (statsmodels' 50) |
| `z95` | number | 1.959963984540054, the literal both readers hold |
| `cancel_distance` | number, must be 0.1 | the near-cancelling rule's threshold (below), `fitting.CANCEL_DISTANCE` |
| `llf_tolerance` | number, must be 1e-6 | how close a grid refit's llf must be to the grid's, `fitting.LLF_TOLERANCE` |
| `diagnostic_settings` | `{alpha, series, ljung_box_lags[], ljung_box_model_df, arch_lm_lags[], arch_lm_ddof, nlags}` | `alpha` must be 0.05, `ljung_box_lags` [5, 10, 20], `arch_lm_lags` [5, 10], `arch_lm_ddof` 0 and `nlags` 50: each pinned in both readers (`ALPHA`, `LJUNG_BOX_LAGS`, `ARCH_LM_LAGS`, `ARCH_LM_DDOF`, `NLAGS`; a test ties the Python ones to `diagnostics.py`) and never taken from the file, because the lags decide which rows exist and so which verdict is reached, and any other stated value is refused; `series` and `ljung_box_model_df` in words; `arch_lm_ddof` 0, `het_arch`'s default (its docstring suggests p + q for ARMA residuals; ddof scales only the statistic, and the verdicts here do not change, milestone-3 walkthrough) |
| `models[]` | see below | exactly three, ids `"aic"`, `"bic"`, `"course"` in that order |
| `course_track` | see below | |
| `clustering_prediction` | `{model_id, confirmed, arch_lm_rejections, acf_squared_outside_count, acf_squared_expected_by_chance}` | concept note 07's prediction, tested on the primary model: `confirmed` is true exactly when its ARCH verdict is `"found"`; `arch_lm_rejections` counts its ARCH-LM p-values below alpha; the count of squared-residual ACF bars past their band, beside alpha × nlags, the number expected by chance |

`models[]`:

| Field | Type | Notes |
|---|---|---|
| `id` | closed enum `"aic"`, `"bic"`, `"course"` | `aic`: ADR-0002's choice; `bic`: the lowest-BIC ok cell of the same d (`aic_grid.selection.bic_choice`); `course`: the course's refit |
| `label`, `source` | string | for display: the model's name, and where it came from in words |
| `order` | `[p, d, q]` ints | p and q from 0 to 10, d from 0 to 2 (`MAX_PQ`, `MAX_D`; the grid's p and q stop at 5). Both readers check the bound before they build anything from the order, so a stated order of 10⁸ or 2³² gives one short problem, not a list of that many parameter names |
| `trend` | closed enum `"n"`, `"c"`, `"t"` | as in `aic_grid`; the course refit's is statsmodels' default for its d: `"c"` at d = 0, `"n"` at d ≥ 1 (both readers) |
| `nobs`, `nobs_effective`, `loglikelihood_burn` | int | `nobs` = `n_train`; `nobs_effective` = `nobs` − `loglikelihood_burn`; `loglikelihood_burn` from 0 to 2 (it is d for these models) |
| `params[]` | `{name, library_name, value, std_err, z, p_value, ci_low, ci_high}` | one row per parameter, in statsmodels' order: the trend term (`"const"` or `"drift"`), `ar.L1`… , `ma.L1`… , `sigma2`. `library_name` is statsmodels' label (the drift is `"x1"` in 0.15.0). `z` = value / std_err; `p_value` = 2(1 − Φ(\|z\|)), the probability under the null (coefficient 0) of a z at least as far from 0 as the one observed; `ci_*` = value ± z95 × std_err. The five inference fields are **nullable**, all together (a singular covariance). **`sigma2`'s `z` and `p_value` are always null**, with its `std_err` and interval kept: its null value 0 is on the boundary of the parameter space (a variance cannot be negative), where z is not normal, so the z-test does not apply (it would also underflow to p = 0.0 here). `sigma2` > 0. Drift and constant in log points per day, `sigma2` in log points squared |
| `information` | `{llf, aic, aicc, bic, hqic}` | statsmodels' values, with k the number of `params` and n = `nobs_effective` (statsmodels passes `nobs_effective`): aic = −2 llf + 2k, bic = −2 llf + k ln n, aicc = −2 llf + 2kn / (n − k − 1), which statsmodels sets to +∞ when n − k − 1 ≤ 0 (no file can hold that) |
| `grid_llf`, `llf_gap` | number, **nullable** | the grid cell's llf, and llf − grid_llf, whose absolute value must be ≤ `llf_tolerance`; null exactly for `course` |
| `converged`, `iterations`, `warnflag` | bool, int, int | the optimiser's `mle_retvals` |
| `warnings[]` | `{category, message}[]` | every warning raised by the fit |
| `inv_roots_ar[]`, `inv_roots_ma[]` | `{re, im, modulus}[]` | exactly p (or q) inverse roots, largest modulus first. A list of another length is one problem, and Python's pairing check is not run on it; nor on a list of more than `MAX_PQ` roots when the order itself is out of bounds (the check's matching doubles its work with each MA root) |
| `cancelling_pairs[]` | `{ar, ma, distance}[]` | indices into the two root lists, listed by AR index; each index at most once. The rule: among the AR–MA pairs whose distance in the complex plane is ≤ `cancel_distance`, a one-to-one matching with as many pairs as possible, and among those the least total distance (a maximum matching). Closest first is not the rule: AR {0.5, 0.6} and MA {0.51, 0.41} give one pair that way and two by the rule |
| `diagnostics` | see below | |

`models[].diagnostics` (computed on the standardised one-step forecast errors after the burn-in):

| Field | Type | Notes |
|---|---|---|
| `n` | int | `nobs` − `burn_excluded` |
| `burn_excluded` | int, 0 to 2 | = `loglikelihood_burn`: statsmodels drops max(`loglikelihood_burn`, `nobs_diffuse`) itself (`statsmodels/tsa/statespace/mlemodel.py:5345`), d for these models |
| `burned[]` | `{date, resid, resid_std}` | the dropped residuals, one per burned observation, to show what the course's plots include; `resid` in log points |
| `max_abs_resid_after_burn` | number ≥ 0 | the largest \|resid\| that remains, for comparison |
| `ljung_box[]` | `{lag, model_df, df, statistic, p_value, applied}` | one per `ljung_box_lags`; `model_df` = p + q; `applied` exactly when lag > model_df; `df` = lag − model_df and `p_value` are **nullable**, null exactly when not applied; `statistic` ≥ 0, never below the previous row's (Q(h) = n(n + 2) Σ r_k² / (n − k) over k ≤ h is a running sum of terms ≥ 0), and `p_value` = the chi-squared tail of `statistic` on `df` |
| `jarque_bera` | `{statistic, p_value, skew, kurtosis}` | Pearson kurtosis (a normal has 3), at least 1 + skew² (true of every sample); `statistic` = n / 6 (skew² + (kurtosis − 3)² / 4) with n = `diagnostics.n` (statsmodels' `jarque_bera`, to 1e-9 relative), and `p_value` = its chi-squared tail on 2 df |
| `arch_lm[]` | `{lags, statistic, p_value}` | one per `arch_lm_lags`; Engle's LM statistic (n − m − ddof) R², with m = `lags` and n − m the rows of its regression, so from 0 to n − m − ddof (R² ≤ 1), and `p_value` its chi-squared tail on `lags` df (`het_arch`: ddof does not change the df) |
| `verdicts` | `{serial_correlation, normality, arch}` | closed enums: `"found"`, `"not_found"`, `"not_tested"` (no applied Ljung–Box row); `"rejected"`, `"not_rejected"`; `"found"`, `"not_found"`. A verdict is the rejection at `alpha` of any row of its test, **unadjusted** for testing several lags (so a family of three lags rejects more often than alpha). The app keys fixed text by these |
| `acf_outside_count`, `acf_squared_outside_count` | int | equal to the counts in that model's `residuals_<id>` file |

`course_track`:

| Field | Type | Notes |
|---|---|---|
| `settings` | object | the course's `auto_arima` arguments, as passed |
| `pmdarima_version` | string | |
| `n_course`, `n_train`, `test_rows_seen` | int | the full 2015–2023 series the course searches, the training split, and the difference: test rows the search saw |
| `full_series` | `{order, with_intercept, trend, aic, nobs, params[], warnings[]}` | `auto_arima` on the full series; `trend` is our code for its model (**nullable**, as in `aic_grid.pmdarima_check`); `params[]` = `{name, value}` in pmdarima's names; `nobs` = `n_course`. Its `order` is the course model's order |
| `train_only` | `{order, with_intercept, trend}`, **nullable** | the same arguments on the training split alone (`aic_grid.pmdarima_check`, run `"course"`); null if that run is missing |
| `same_order` | bool, **nullable** | the two searches chose the same order and intercept; null exactly when `train_only` is |
| `refit_trend` | closed enum | the course model's trend |
| `drift_dropped` | `{selected_trend, refit_trend, aic_without_drift, aic_with_drift, aic_gap, drift, drift_std_err, drift_p_value}` | the course order refitted with a drift (grid settings) beside the course's refit without one: `selected_trend` = `full_series.trend` (the search's choice; both nullable); `aic_gap` = without − with; `drift_std_err` and `drift_p_value` **nullable**, null together, `drift_std_err` > 0, and `drift_p_value` = 2(1 − Φ(\|drift / drift_std_err\|)) |

Readers: Python's `validate_fit` and the app's `parseFit`.

**What each reader checks (1.4.0).** The app's parsers check shapes, types, closed enums, nulls,
bounds, array lengths and integer bookkeeping (the ids and their order, `primary` = `"aic"`, the
order bounds (p, q ≤ 10, d ≤ 2) and the burn bound (≤ 2) before anything is built from them,
`cancel_distance` = 0.1 and `llf_tolerance` = 1e-6, each pinned in the reader (`CANCEL_DISTANCE`,
`LLF_TOLERANCE`) and never taken from the file, as `NESTING_TOLERANCE` is, and likewise the
`diagnostic_settings` (alpha 0.05, the Ljung–Box and ARCH-LM lags, ddof 0, nlags 50), all compared
exactly, so a value 1e-12 away is another value,
parameter names for the order and trend, `sigma2`'s null z and p-value, the drift's error and
p-value null together and the error positive, `selected_trend` = `full_series.trend`, the course
model's trend = statsmodels' default for its d, root and pair counts and indices, lag lists, the burn
and `n` arithmetic, `applied` against lag and model_df, counts of flagged rows,
`clustering_prediction.confirmed` against the primary model's ARCH verdict, which is an enum). They
never recompute a statistic or compare one with a threshold (ADR-0001). Python's validators also
check those, and: z and the p-value from the estimate and standard error, the interval, aic, bic
and aicc from llf, k and `nobs_effective`, each Ljung–Box, Jarque–Bera and ARCH-LM p-value from its
statistic and df (chi-squared tails in closed form, to `P_REL` = 1e-9 relative, or within
`P_FLOOR` = 1e-300; a p-value of exactly 0.0 only where the tail at its statistic and df is below
`P_FLOOR`, so a 0 beside a moderate statistic is refused; the tail is computed only for a pinned lag
with the df that lag gives, so a row off the pins is a problem and its p-value is not tied; a statistic
of 0 or 5e-324 has a tail of 1), each statistic ≥ 0, the Jarque–Bera
statistic from n, skew and kurtosis (the p-value tie alone sees nothing past a statistic of about
1382, where every tail on 2 df is below `P_FLOOR`), the kurtosis ≥ 1 + skew², each Ljung–Box Q ≥
the one before it, each ARCH-LM statistic ≤ n − lags − ddof, `sigma2` > 0, the
drift's p-value from drift / its error, the root moduli and their order, the cancelling rule (the
number of pairs and their total distance against a maximum matching, the listing order), the llf gap
(llf − grid_llf, and against its tolerance), `drift_dropped.aic_gap`, each verdict and
`arch_lm_rejections` against the p-values, alpha × nlags, each band (z / √n), every ACF `outside`
flag against its band, and the order of the QQ columns. Those Python-only rules are tested in
`tests/test_payloads_fit.py`, not in the shared corpus, whose cases both readers must decide alike.

**Across files.** `fit` and the three `residuals_<id>` files must describe the same fits:
`payloads.validate_fit_residuals` checks that each model's file exists and holds its id, `n`,
`burn_excluded` (so `n` + `burn_excluded` = `nobs`), the fit's `nlags` and its two outside counts.
`tools/export_app_data.py` runs it on the set the folder would hold before writing (so `--only fit`
after a code change refuses to write beside stale residual files) and again on the files read back
after writing.

---

### 3.8 `residuals_aic`, `residuals_bic`, `residuals_course` [M3, implemented]

The residual plot series of one model each (the file name says which). One file per model because
the three models' series are 1,450,049 bytes together (measured), over the 1 MB budget; the app fetches only
the model it shows. **View:** the "Fit and diagnostics" page (standardised residuals over time,
residual ACF and squared-residual ACF, QQ plot).

| Field | Type | Notes |
|---|---|---|
| `sample` | `"train"` | |
| `model_id` | closed enum | the file's model: `residuals_aic` holds `"aic"`, and so on |
| `n`, `burn_excluded` | int; `burn_excluded` 0 to 2 | as in that model's `fit` diagnostics (checked across the two files by `validate_fit_residuals`, above) |
| `z` | number | 1.959963984540054 |
| `nlags` | int ≥ 1 | 50 |
| `rows[]` | `{date, resid_std}` | the standardised residuals after the burn-in, one per training date from the (burn + 1)-th; dates strictly ascending; exactly `n` rows |
| `acf`, `acf_squared` | `{band, outside_count, rows[]}` | the ACF of `resid_std` and of its square at lags 1…nlags; `band` = z / √n (the white-noise band, constant across lags); `rows[]` = `{lag, acf, outside}`, `outside` exactly when \|acf\| > band (decided in Python); `outside_count` = the flagged rows |
| `qq[]` | `{theoretical, t_theoretical, sample}` | every standardised residual (`sample`, sorted ascending) against the normal quantile at its plotting position (scipy's `probplot`) and the quantile of the fitted Student-t at the same position; exactly `n` points, each column non-decreasing |
| `t_fit` | `{df, loc, scale}` | the Student-t fitted by maximum likelihood (`scipy.stats.t.fit`); `df` and `scale` > 0 |

Readers: Python's `validate_residuals(data, model_id)` and the app's `parseResiduals(data, modelId)`.

---

### 3.9 `forecast_<model>_<method>` [M4, implemented]

One forecast path per model and method, on both windows. Seven files: `forecast_aic_static`,
`forecast_aic_walk_forward`, `forecast_aic_refit`, `forecast_bic_static`, `forecast_bic_walk_forward`,
`forecast_course_static`, `forecast_course_walk_forward` (`forecasting.FORECASTS`). One file per
(model, method) because a model's paths together pass the 1 MB budget (two methods with the
Student-t bands are about 1.3 MB) and the page shows one at a time; each file is about 0.65 MB.
Built by `src/arima_forecasting/forecasting.py`. **View:** the "Forecast and evaluation" page (fan
chart, walk-forward animation); it fetches only the file of the model and method on show.

| Field | Type | Notes |
|---|---|---|
| `model_id` | closed enum `"aic"`, `"bic"`, `"course"` | the file's model; both readers refuse another (the parser is called with the id and method the file name gives) |
| `label` | string | the model's display name (`fit.models[].label`), pinned per model id in both readers (`MODEL_LABELS`, `fitting.LABELS`): `"AIC choice (ADR-0002)"`, `"BIC choice"`, `"Course refit"` |
| `method` | closed enum `"static"`, `"walk_forward"`, `"refit"` | the file's method; `"refit"` exists for `"aic"` only (`REFIT_MODELS`) |
| `kind` | closed enum `"multi_step"`, `"one_step"` | `"multi_step"` exactly for `"static"` |
| `order`, `trend` | `[p, d, q]`, closed enum `"n"`, `"c"`, `"t"` | as in `fit` (p, q ≤ 10, d ≤ 2, checked before use); equal to that model's (across files) |
| `parameters` | closed enum `"train"`, `"expanding_refit"` | where the parameters come from: the training fit (`static`, `walk_forward`) or the refits below (`refit`) |
| `refit_every` | int, **nullable** | 21 for `refit` (`REFIT_EVERY`, pinned in both readers), null otherwise |
| `t_df` | number > 2 | the degrees of freedom of the model's residual t fit, `residuals_<id>.t_fit.df` exactly (across files). A t on 2 or fewer has no finite variance, so it cannot be scaled to the forecast's |
| `intervals` | `{levels, normal_z, t_quantile, t_scale, t_multiplier}` | `levels` must be `[0.8, 0.95]` and `normal_z` `[1.2815515655446004, 1.959963984540054]` (scipy's `norm.ppf(0.9)` and `norm.ppf(0.975)`), both pinned in both readers (`LEVELS`, `NORMAL_Z`) and compared exactly; `t_quantile[i]` the Student-t quantile at (1 + level) / 2 on `t_df`; `t_scale` = √((t_df − 2) / t_df), the scale that gives the t a variance of 1; `t_multiplier[i]` = `t_quantile[i]` × `t_scale`. Two numbers each |
| `windows[]` | see below | exactly two, ids `"test"` then `"oos"` |
| `refits` | array, **nullable** | null except for `refit`; see below |

`windows[]`:

| Field | Type | Notes |
|---|---|---|
| `id` | closed enum `"test"`, `"oos"` | |
| `start`, `end` | date | the first and last forecast date, both inclusive; the test window ends before the oos window starts |
| `n` | int, 1 to 10,000 | rows; both readers check the bound (`MAX_ROWS`) before they read a row |
| `origin` | `{date, log_close, close_usd}` | the last day before the window, `date` < `start`: where the static path starts and the random walk's first forecast. The static oos path starts from the last test day with the Kalman state filtered through the test window at the training parameters |
| `rows[]` | see below | exactly `n`, dates strictly ascending, the first `start` and the last `end` |

`rows[]` (every value a finite number; log values in natural-log points, `_usd` in dollars):

| Field | Notes |
|---|---|
| `date` | the day forecast |
| `actual_log`, `actual_usd` | the observed log close and close (`prices`) |
| `mean_log`, `sd_log` | the model's forecast mean and standard deviation of the log price: from the origin (`static`, step = row index + 1), or from the day before with every earlier observation (`walk_forward`, `refit`). `sd_log` > 0; on a static path it does not fall from one row to the next (an h-step forecast variance is a running sum of non-negative terms). It is the variance given the parameters; their estimation error is not in it |
| `median_usd` | exp(`mean_log`): the median of the implied log-normal price, which is what the course reports as "the forecast" |
| `mean_usd` | exp(`mean_log` + `sd_log`² / 2): its mean |
| `lower_80_usd`, `upper_80_usd`, `lower_95_usd`, `upper_95_usd` | exp(`mean_log` ∓ `normal_z[i]` × `sd_log`): the normal intervals (statsmodels' and the course's) |
| `t_lower_80_usd`, `t_upper_80_usd`, `t_lower_95_usd`, `t_upper_95_usd` | exp(`mean_log` ∓ `t_multiplier[i]` × `sd_log`): the variance-matched Student-t intervals |

`refits[]` (only for `refit`): one entry per re-estimation, in order. The forecasts of the first
`refit_every` rows of the test and oos rows taken together use the training parameters; entry k
(from 0) serves the next `refit_every` rows. So there are ⌈(n_test + n_oos) / 21⌉ − 1 entries.

| Field | Type | Notes |
|---|---|---|
| `start_date` | date | the first forecast date its parameters serve: the date of row 21 (k + 1) of the test rows followed by the oos rows |
| `n_obs` | int | the observations it was fitted on, every day before `start_date`: 21 more than the entry before it; the first is `fit.n_train` + 21 (across files) |
| `params[]` | `{name, value}` | named as in `fit` for the order and trend (the trend term, `ar.L1`…, `ma.L1`…, `sigma2`); `sigma2` > 0 |
| `llf` | number | |
| `converged`, `iterations` | bool, int | the optimiser's `mle_retvals` |
| `warnings[]` | `{category, message}[]` | every warning raised by the fit; at most `MAX_WARNINGS` = 100 (both readers, checked before the list is walked; the same bound applies to `fit`'s warning lists) |

Readers: Python's `validate_forecast(data, model_id, method)` and the app's
`parseForecast(data, modelId, method)`.

---

### 3.10 `evaluation` [M4, implemented]

Every forecast scored against the random walk: metrics, Diebold–Mariano tests and interval
coverage, with the verdicts the app keys its text by. Built by `src/arima_forecasting/evaluation.py`
from the forecast payloads' rows, so every number in it can be recomputed from those files.
**View:** the "Forecast and evaluation" page (metrics table, DM result, coverage table).

No timings: the contract keeps wall-clock values out of `data` (§2, "Determinism"), so the times of
the walk-forward and the refit are measured in the milestone-4 walkthrough instead.

| Field | Type | Notes |
|---|---|---|
| `alpha` | number, must be 0.05 | pinned in both readers (`ALPHA`) |
| `interval_levels` | must be `[0.8, 0.95]` | pinned (`LEVELS`) |
| `refit_every` | must be 21 | pinned (`REFIT_EVERY`) |
| `headline_usd` | closed enum `"median"` | the dollar point the headline metric uses: the median, exp(μ), as the course does; the mean's metrics are beside it |
| `dm_settings` | `{horizon, errors, losses, correction, alternative, baseline, same_tolerance}` | must be `1`, `"log"`, `["squared", "absolute"]`, `"harvey_leybourne_newbold"`, `"two_sided"`, `"random_walk"`, `1e-9`; pinned in both readers and compared exactly. `same_tolerance` (log points, `evaluation.SAME_TOLERANCE`): one-step forecasts within it of the random walk's on every day are the random walk's (below) |
| `windows[]` | `{id, start, end, n, origin_date}` | exactly `"test"` then `"oos"`; `n` 1 to 10,000 (bounded first); equal to every forecast file's windows (across files) |
| `models[]` | `{id, label, methods, t_df}` | exactly `"aic"`, `"bic"`, `"course"`; `label`, the Model picker's text, pinned per id in both readers as the method labels are (`MODEL_LABELS`, the forecast files' labels); `methods` the model's methods in file order (`["static", "walk_forward", "refit"]` for aic, `["static", "walk_forward"]` otherwise); `t_df` > 2, equal to its forecast files' (across files) |
| `methods[]` | `{id, kind, label}` | exactly `"static"` (`"multi_step"`), `"walk_forward"` and `"refit"` (`"one_step"`). `label`, the Method picker's text, is pinned per id in both readers (`evaluation.METHOD_LABELS`): `"Static multi-step (the course's)"`, `"Walk-forward one-step"`, `"Walk-forward one-step, refit every 21 days"` |
| `random_walk[]` | `{kind, window, n, log: {rmse, mae}, usd: {rmse, mae, mape_pct}}` | the baseline on each window, static (`"multi_step"`: the origin's value every day) and one step (`"one_step"`: yesterday's value): four rows, multi_step test, multi_step oos, one_step test, one_step oos. It has no variance, so its median and mean are the price itself |
| `metrics[]` | see below | one row per forecast file and window, in `FORECASTS` order, test before oos: 14 rows |
| `dm[]` | see below | one row per one-step forecast file, window and loss (squared, then absolute): 16 rows |
| `coverage[]` | see below | one row per forecast file, window, distribution (normal, then t) and level (0.8, then 0.95): 56 rows |

`metrics[]`:

| Field | Type | Notes |
|---|---|---|
| `model_id`, `method`, `window` | closed enums | |
| `n` | int | the window's `n` |
| `log` | `{rmse, mae}` | in log points, of `actual_log` − `mean_log` |
| `usd_median`, `usd_mean` | `{rmse, mae, mape_pct}` | in dollars, of `actual_usd` − `median_usd` and − `mean_usd`; MAPE = 100 × mean(\|error\| / \|actual\|) |
| `ratio_to_rw` | `{log: {rmse, mae}, usd_median: {rmse, mae, mape_pct}, usd_mean: {…}}` | each metric divided by the random walk's of the same kind and window (`usd` for both dollar blocks): below 1 the model is closer on that metric |
| `back_transform` | `{max_pct, mean_pct}` | 100 × (`mean_usd` / `median_usd` − 1) = 100 × (exp(`sd_log`² / 2) − 1), its largest and mean value over the rows: how far the course's "forecast" (the median) sits below the mean |

`dm[]` (Diebold–Mariano with the Harvey–Leybourne–Newbold correction; evaluation.py's docstring
gives the sources):

| Field | Type | Notes |
|---|---|---|
| `model_id`, `method`, `window` | closed enums | one-step methods only |
| `loss` | closed enum `"squared"`, `"absolute"` | of the log errors |
| `n` | int | the window's `n`; at least 2 |
| `max_forecast_gap` | number ≥ 0 | the largest \|model forecast − random-walk forecast\| over the window, in log points |
| `mean_diff` | number | the mean of d_t = loss(model error) − loss(random-walk error): negative when the model's loss is lower |
| `var_diff` | number | γ₀, the variance of d_t with divisor n (the long-run variance for h = 1); > 0, or ≥ 0 where the verdict is `"same_as_rw"` |
| `statistic` | number, **nullable** | DM = `mean_diff` / √(`var_diff` / n) |
| `hln_factor` | number | √((n + 1 − 2h + h(h − 1) / n) / n) with h = 1, so √((n − 1) / n) |
| `statistic_hln` | number, **nullable** | `statistic` × `hln_factor` |
| `df` | int | n − 1 |
| `p_value` | number in [0, 1], **nullable** | 2 × P(T > \|`statistic_hln`\|) for a Student T on `df` |
| `verdict` | closed enum `"beats_rw"`, `"no_difference"`, `"worse_than_rw"`, `"same_as_rw"` | `"same_as_rw"` exactly when `max_forecast_gap` ≤ `same_tolerance`: the forecasts are the random walk's (an ARIMA(0, 1, 0) without a drift is the random walk), the differential is 0 or rounding noise, and `statistic`, `statistic_hln` and `p_value` are null (only there). Otherwise `"beats_rw"` when `p_value` < `alpha` and `mean_diff` < 0, `"worse_than_rw"` when `p_value` < `alpha` and `mean_diff` > 0, else `"no_difference"`. The app keys fixed text by it |

`coverage[]`:

| Field | Type | Notes |
|---|---|---|
| `model_id`, `method`, `window` | closed enums | |
| `distribution` | closed enum `"normal"`, `"t"` | |
| `level` | number | the pinned level at that position, 0.8 or 0.95 |
| `n`, `inside` | int | the window's `n`; the days with `mean_log` − m × `sd_log` ≤ `actual_log` ≤ `mean_log` + m × `sd_log`, m the file's multiplier for that distribution and level (0 to n) |
| `rate` | number | `inside` / `n` |
| `lr`, `p_value` | number, **nullable** | Kupiec's unconditional-coverage LR statistic and its χ²(1) tail; null exactly for `multi_step` (a static path's days are not independent) |
| `verdict` | closed enum `"too_narrow"`, `"consistent"`, `"too_wide"`, `"not_tested"` | `"not_tested"` exactly for `multi_step`; otherwise `"consistent"` when `p_value` ≥ `alpha`, else `"too_narrow"` (rate below the level) or `"too_wide"` |

Readers: Python's `validate_evaluation` and the app's `parseEvaluation`.

**What each reader checks (1.5.0).** Both readers check shapes, types, closed enums, nulls (all the
nullable fields above null exactly where stated), the pinned settings (`LEVELS`, `NORMAL_Z`,
`REFIT_EVERY`, `ALPHA`, the DM settings), the window, model, method and row sets and their order, the
bounds (order, `n` ≤ `MAX_ROWS` before any row is read, `t_df` > 2, `sd_log` > 0, p-values in
[0, 1], `inside` from 0 to n, `max_forecast_gap` ≥ 0, `var_diff` > 0 (≥ 0 for `"same_as_rw"`), `n` ≥ 2
for a DM row) and the integer and date
bookkeeping (each row count equal to its window's `n`, dates ascending, the first and last equal to
`start` and `end`, the origin before the window, the refit count, each refit's `n_obs` 21 above the
one before, its `start_date` the date of its row, its parameter names, `df` = n − 1, `kind` and
`parameters` from the method, the verdicts that are fixed by the method: `"not_tested"` exactly for
`multi_step`; the DM nulls exactly for `"same_as_rw"`). They never recompute a number from others or compare one with `alpha` (ADR-0001).
Python's validators also check: in each forecast file, every dollar value from `mean_log` and
`sd_log` (median, mean and the eight bounds) and `actual_usd` from `actual_log`, to `_REL` = 1e-9
relative; a static path's `sd_log` never falling; `t_scale` from `t_df`, `t_multiplier` = quantile ×
scale, and each `t_quantile` by evaluating the t's CDF at it (a regularised incomplete beta function,
no scipy) and comparing with (1 + level) / 2 to 1e-10, or, from `t_df` = 10⁴ on (`T_ASYMPTOTIC_DF`;
a near-normal residual series gives such a df), against the Cornish–Fisher expansion in 1 / df
(Abramowitz and Stegun 26.7.5) to 1e-12 relative; `sigma2` > 0 in each refit. In `evaluation`:
each ratio = its metric / the random walk's, exactly (the same division of the same doubles); every
RMSE ≥ its MAE ≥ 0 and MAPE ≥ 0; `back_transform.max_pct` ≥ `mean_pct` ≥ 0; each DM statistic from
`mean_diff`, `var_diff` and n, the HLN factor from n, `statistic_hln` = statistic × factor, the p-value
from `statistic_hln` and `df` (the t tail by the incomplete beta function, to `P_REL` = 1e-9 relative
or within `P_FLOOR` = 1e-300; the t's incomplete beta function takes 0, a subnormal and a huge
statistic, Python only), the verdict from the p-value, `alpha` and the
sign of `mean_diff`, and `"same_as_rw"` exactly when `max_forecast_gap` ≤ `same_tolerance`;
each coverage `rate` = `inside` / `n` exactly, `lr` from n, `inside` and the level (Kupiec), its
p-value from `lr` (χ² on 1 df) and the verdict from the p-value, `alpha`, rate and level. Those rules
are tested in `tests/test_payloads_forecast.py`.

**Across files.** `payloads.validate_forecast_fit(fit, residuals, forecasts)`: each forecast file's
order, trend and label equal its model's in `fit`, its `t_df` equals `residuals_<id>.t_fit.df`, a
refit file's first `n_obs` is `fit.n_train` + 21, and each one-step row's `sd_log`² is the `sigma2`
of the parameters it was made with (`fit`'s for a walk-forward file and the refit's first 21 rows,
that refit's own after) to `SIGMA2_REL` = 1e-4 relative: statsmodels' steady-state switch leaves the
one-step variance a constant fraction above `sigma2`, at most 2.67e-5 on AAPL (measured; the
reason is in `payloads.py`), so a rescaled `sd_log` cannot pass with the evaluation rebuilt from it.
The refit file's first block, whose origin is the end of training, has no `refits` entry: its
parameters are the training fit's, so its rows are tied to `fit.json`'s aic `sigma2` (`refits[0]` is
fitted 21 days later, on `n_train` + 21 observations, and serves the second block). Each later block
is tied only to its own refit's `sigma2`: a refit's `sigma2` and its block's `sd_log` rescaled
together (the re-review's `refit_consistent.py`: every refit's `sigma2` × 2.25 with the rows after
the first 21 at `sd_log` × 1.5, the dollars and the evaluation rebuilt) pass every reader in both
languages. `--check` catches it (it refits every block from the snapshot and compares the files), and
so does `tests/test_committed_artifacts.py`, which refits two sampled blocks from the parameters before them.
`payloads.validate_forecast_prices(prices, forecasts)`: each window's rows are that segment's rows of
`prices` (date, log close and close, exactly), its origin is the row before, its start, end and n
are the segment's, and its start, end, n and origin date are `prices.splits` (its segment's, and the
end of the segment before). `payloads.validate_forecast_evaluation(evaluation, forecasts)`: every forecast file
describes the same days and actuals as the first (ids, bounds, origins, dates and actuals, exactly),
the windows, `t_df` and each model's label agree, forecasts made from the same state with the same
parameters are the same numbers (each static path's first day and the refit's first 21 days equal
the walk-forward's `mean_log` and `sd_log`, to `_REL`), and
every metric, every random-walk metric, each DM `mean_diff`, `var_diff` and `max_forecast_gap`, each
coverage `inside` and each `back_transform` is recomputed from the forecast rows (to `_REL`, relative
with no absolute floor; `mean_diff` at the scale of its terms; counts and the gap exactly). A number
that cannot be recomputed (an overflow, a zero actual under MAPE) is reported as a problem, never
raised; a file that is not valid on its own (`validate_forecast`, `validate_evaluation`) is named
once and left out of these checks, so a malformed file cannot make them raise. Every Python tolerance check refuses a value that is not finite on either side: a recomputed
exp that overflowed to inf matches nothing (the review fix round found that `inf <= rel * inf` had
let a row with `mean_log` 710 pass).

**What no reader catches: a look-ahead.** A hand-edited forecast file whose `mean_log` is the day's
own actual, its dollars, its intervals and the evaluation rebuilt from it, passes every reader, in
both languages: a forecast that equals what happened is a valid number, and no reader can tell when
it was made. `--check` catches it (it rebuilds every forecast from the snapshot and compares the
files), and so do the tests: `tests/test_committed_artifacts.py` rebuilds the static and
walk-forward files and samples the refit, and `tests/test_forecasting.py` changes every observation
from day t on and requires every forecast of day t or earlier unchanged.
`tools/export_app_data.py` runs all three, with `prices.json`, on the set the folder would hold
before writing and on the files read back after, as it does for `fit` and the residual files.
`tests/test_committed_artifacts.py` rebuilds the static and walk-forward files from `prices.json`,
`fit.json` and the residual files (filters only, a second or two), refits two sampled blocks of the
refit file from the parameters before them, and rebuilds `evaluation.json` from the forecast files.

## 4. Who checks what

| Check | Where | Catches |
|---|---|---|
| Envelope valid before writing | `export_app_data.py` → `contract.validate_envelope` | malformed envelope |
| Both readers agree on every envelope | pytest and vitest each run `app/src/test/fixtures/envelope_cases.json` (§1) | a rule changed in `contract.py` or `contract.ts` but not in the other |
| No NaN/Infinity, no unsafe integers | `contract.dumps` (`allow_nan=False`, plus the ±(2^53 − 1) integer check) | failed calculations leaking into JSON; integers the browser would round |
| Payload shape per artifact | `src/arima_forecasting/payloads.py` (`validate_meta`, `validate_prices`, `validate_eda`, `validate_stationarity`, `validate_acf_pacf`, `validate_aic_grid`, `validate_fit`, `validate_residuals` once per model id, `validate_forecast` once per forecast file and `validate_evaluation`; for `fit` and the residuals also the statistical rules listed under §3.7, tested in `tests/test_payloads_fit.py`, and for the milestone-4 files those under §3.10, tested in `tests/test_payloads_forecast.py`), run by the exporter on every payload before writing, by `read_artifact` and `--check`, and by pytest | Python-side shape drift |
| `fit` against the residual files, the forecasts against both, `evaluation` against the forecasts | `payloads.validate_fit_residuals`, `validate_forecast_fit` and `validate_forecast_evaluation`, run by `export_app_data.py` on the set it will leave in `--out` before writing (`--only` included) and on the files read back after writing (§3.7 and §3.10, "Across files") | a file rebuilt alone that contradicts the others |
| Both readers agree on every payload | pytest and vitest each run `app/src/test/fixtures/payload_cases.json` (§1): integral floats such as `4.0` count as integers (JavaScript cannot tell them apart), integers beyond ±(2^53 − 1) and numbers too big for a double are refused, and "blank" is one explicit whitespace class on both sides | a payload rule changed in `payloads.py` or `contract.payloads.ts` but not in the other |
| App parses the **real** files | vitest, `app/src/lib/contract.realdata.test.ts`: every file in `app/public/data/` through the production `parseEnvelope`, its `artifact` equal to the file stem, its payload through that artifact's parser (`parseMeta`, `parsePrices`, `parseEda`, `parseStationarity`, `parseAcfPacf`, `parseAicGrid`, `parseFit`, `parseResiduals` with the model id the file name gives, `parseForecast` with the model and method the file name gives, and `parseEvaluation`; an artifact with no registered parser fails), and the set of files equal to `meta.data.artifacts` less the held ones that are absent (each such file gets a skipped test that says why) | Python changed, app not updated |
| Files are current | `tools/export_app_data.py --check`: regenerate from the raw snapshot, run the cross-file checks on the rebuild (since the milestone-4 third review pass), compare `schema_version`, `artifact`, `data`, and the set of files, and refuse a file the app would refuse (its envelope and payload are validated too); exit 1 on a difference, 2 without a snapshot. It reruns the whole export, the 144-cell grid fitted from several starts included, so it takes about as long as an export: 8 to 10 minutes (on 2026-10-29, on a machine loaded by other jobs, milestone 2's export took 491 s and milestone 3's 582 s; `--check`'s own time is in the milestone-3 walkthrough's gate results). Without the snapshot, `tests/test_committed_artifacts.py` checks every step after it: `meta.json` = `meta_payload()`; `prices.json` and `eda.json`, where present, equal what the current code builds from `prices.json`'s own closes; where `prices.json` is present, `stationarity.json` and `acf_pacf.json` equal a fresh computation and a sample of grid cells refits exactly; `fit.json` and the three `residuals_<id>.json` files equal what the current code builds from `prices.json`'s rows and `aic_grid.json`'s recorded estimates (about a second); and in every copy the committed selection and d follow from the committed cells and tests | code changed, nobody re-exported |
| Cross-artifact consistency | pytest (`tests/test_committed_artifacts.py`, in every copy): `aic_grid.selection.d_selected == stationarity.decision.d_selected`, and the three milestone-2 files describe the same training rows. Milestone 3: `fit`'s `aic` and `bic` models have the order and trend of `aic_grid`'s choice and BIC choice; `fit.n_train` equals `aic_grid.n_train` and the training count in `prices`; `course_track.train_only` equals `aic_grid`'s `"course"` pmdarima run; each `residuals_<id>` file holds its model's id, `n` and `burn_excluded`, its rows' dates are the training dates after the burn-in, the burned rows' dates are the ones before it, and its two outside counts equal that model's counts in `fit`. Milestone 4: every forecast file's windows, dates, actuals and origins are `prices`' test and oos rows and the day before each; each file's order, trend, label and `t_df` agree with `fit` and `residuals_<id>` (`validate_forecast_fit`); `evaluation` follows from the forecast rows (`validate_forecast_evaluation`) | artifacts disagreeing with each other |
