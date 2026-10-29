# Adjusted prices, snapshots and forward fill

Status: milestone-1 concept note, written 2026-10-29 and corrected after the milestone-1 review.
Every number is measured on the AAPL snapshot downloaded on 2026-10-29 at 13:37 UTC (its SHA-256 is
in your local `data/` manifest), with the command named next to it, or it is marked as illustrative, not measured or
not verified here.

## First principles

A **close** is the price of one share at the end of a trading day.

A **corporate action** changes the share without changing what the company is worth. Two kinds
matter here.

- A **split** turns each share into several. AAPL split 4-for-1 on 2020-08-31. One old share became
  four new ones, so the quoted price fell to about a quarter overnight. Nobody lost money.
- A **cash dividend** pays each holder a small amount of cash. On the *ex-dividend date* the price
  drops by about that amount, because a buyer from that day on no longer gets the payment.

A return computed from raw closes would show a 75% "crash" on the split day. It would also show a
small loss on every ex-dividend date, while the holder actually kept that value as cash.

An **adjusted close** fixes both. Every close *before* an event is multiplied by a factor; the
most recent closes stay as quoted, and older ones shrink. For a split, the return across the event
then equals what a holder earned, exactly. For a dividend it is close but not exact (see the maths
below).

A note on words. People call such a series "backward-adjusted", because the factors are applied to
the past. yfinance also has an option named `back_adjust`, and it means something else: it
"mimics true historical prices" (`yfinance/utils.py:527`). This repo leaves `back_adjust=False` and
uses `auto_adjust=True`, which replaces `Close` with Yahoo's adjusted close and scales Open, High and
Low by the same ratio. No `Adj Close` column is left (`yfinance/utils.py:509-523`).

Because the factors apply to the past, **history can change after the fact**. A new dividend
should multiply every earlier adjusted close by a new factor. That part is Yahoo's behaviour; it is
**not verified here** (there is only indirect support: yfinance's own price-repair code computes a
dividend factor as `1 - div / close_before` and compounds it, `yfinance/scrapers/history.py:1150`).
What *was* measured is stronger, and simpler: two downloads of the same request, made 90 minutes
apart on 2026-10-29, were not byte-identical. The dates and volumes matched exactly, but the four
prices differed on 2,125 of 2,953 rows, by at most 7.3 × 10⁻⁷ of the price. So a download is a
**snapshot**: a file fixed at one moment. We keep its bytes and its SHA-256, a 64-hex-character
fingerprint that changes if any byte changes.

A **missing close** is a row whose close is empty. **Forward filling** replaces it with the last
known close. It uses only the past, so it leaks nothing from the future. pandas spells it `.ffill()`.
The course's `fillna(method='ffill')` no longer exists in pandas 3.1.

## The maths

**A split.** For a k-for-1 split that takes effect on day s, the adjustment divides every close
before s by k. The adjusted log return across the split is

$$r_s = \ln P_s - \ln\left(P_{s-1} / k\right).$$

Without the adjustment the return would carry an extra $\ln(1/k)$. For AAPL's 4-for-1 split that is
$\ln(1/4) = -1.386$, a fake fall of 75%.

Measured on our adjusted series: the log return from 2020-08-28 to 2020-08-31, across the split,
is +0.0333, a 3.3% rise and no jump. (Command: read `rows` of `app/public/data/prices.json` and
difference `ln(close_usd)` at those two dates; run 2026-10-29. The prices themselves are in your
local files only: this repository does not publish them.)

**A dividend.** One common method (CRSP's style, and the one yfinance's repair code uses) multiplies
every close before the ex-date e by

$$f = 1 - \frac{D}{P_{e-1}},$$

where D is the dividend and $P_{e-1}$ the close the day before. *Illustrative numbers, not AAPL
data:* with D = $0.25 and $P_{e-1}$ = $200, f = 0.99875. One such factor is tiny. AAPL pays a
dividend every quarter, so the factors pile up over eleven years. Yahoo's exact method is not
verified here.

The adjusted return across the ex-date is $P_e / (f P_{e-1}) - 1$. The holder's true return is
$(P_e + D) / P_{e-1} - 1$. The two agree only when $P_e = P_{e-1} - D$, that is, when the price
drops by exactly the dividend. *Illustrative:* with D = $0.25 and a close going from $200 to $202,
the adjusted return is 1.12641% and the holder's is 1.12500%.

**What the adjustment does to old levels.** The adjusted close of 2015-01-02 is in your local
snapshot (see your local `data/` manifest for which one). The raw close that day, before the split
and the dividends, was not downloaded, so the size of the cumulative adjustment is **not
measured** in this repo.

**Forward fill.** If $P_t$ is missing and $P_{t-1}$ is known, ffill sets $P_t = P_{t-1}$. The log
return on day t is then exactly 0, and day t+1 carries the whole two-day move.

Measured on our snapshot: 0 missing closes, so `fill.filled_dates` is empty. Across all 2,953 rows
the gaps between consecutive trading days were 1 day 2,311 times, 2 days 28 times, 3 days (a
weekend) 530 times and 4 days (a long weekend) 83 times. Nothing was longer. (Command: the
gap-count snippet in the [milestone walkthrough](../milestones/01-data-and-eda.md#measured-results);
run 2026-10-29.)

## Assumptions

- Yahoo records each split and dividend correctly and on the right date.
- An adjusted series is right for *returns*. Its old *levels* are not prices anyone paid.
- Missing closes are rare and short, so a filled day's zero return barely matters. The code
  enforces "short": a fill may carry a close at most 7 calendar days.
- One snapshot is downloaded once and never edited. The SHA-256 check enforces the second half.

## Where it breaks

- **Old levels are not real prices.** A 2015 adjusted close is smaller than what a share cost then.
  Any number tied to a level (a dollar RMSE, a price threshold) depends on the download date.
- **Later dividends reach into the training levels.** Every dividend paid after the training
  segment ends (2023-02-03), up to the download, scales *all* training closes by one common factor.
  Returns are untouched by a common factor, so the log-return summary and KDE, the seasonal part and
  the residual do not move. The levels do: `summary.close_usd`, where the log-close KDE sits, the
  observed and trend levels of the decomposition, and the course-comparison factors. This is a mild
  leak of post-training information into training *levels*. Its size is **not measured** here (the
  unadjusted closes were not downloaded).
- **A refresh changes the numbers.** Even two same-day downloads differed in the seventh
  significant digit (measured above), and a new dividend should re-scale every earlier close.
  That is why the snapshot is kept, its SHA-256 is written into `prices.json`, and
  `tools/fetch_prices.py` reuses the file unless told `--refresh`.
- **A long run of missing closes becomes a flat line.** Forward filling ten missing days would
  invent ten zero returns and a jump on the eleventh, and the variance would look smaller than it
  was. `check_coverage` cannot see this, because it looks only at which *rows* exist, and these
  rows exist with an empty close. So `clean_close` refuses any filled row that lies more than 7
  calendar days after the last real close. That also stops a missing tail (the last weeks empty)
  from becoming a flat end. Shorter runs are filled and listed in `fill.filled_dates`.
- **The first row cannot be filled.** There is nothing before it. `clean_close` stops with an error
  instead of leaving a NaN.
- **ffill only fills rows that exist.** If Yahoo drops a whole day, there is no empty row to fill.
  `check_coverage` refuses a hole of more than 7 calendar days between two rows, but a single
  missing day inside a normal week would look like a holiday. That limit is accepted, not guarded.
- **`auto_adjust=False` changes meaning quietly.** Then an `Adj Close` column appears and `Close` is
  no longer the adjusted close. (That the remaining `Close` is split-adjusted but not
  dividend-adjusted is Yahoo's convention; it is **not verified here**.) `normalize_download`
  refuses the `Adj Close` column, because the contract promises `price_basis: "adjusted_close"`.

## In this project

- `src/arima_forecasting/data.py:53-73` is the explicit download request, all 19 arguments of
  `yfinance.download` with `auto_adjust=True` among them, and it is written into the manifest.
- `src/arima_forecasting/data.py:120-185` (`normalize_download`) refuses `Adj Close`, an empty frame
  and a second ticker, and flattens the `(Price, Ticker)` columns.
- `src/arima_forecasting/data.py:188-202` writes and reads the snapshot bytes; `:259-305`
  (`read_snapshot`) refuses a damaged or wrongly typed manifest, a manifest made with another
  request, and a file whose SHA-256 no longer matches.
- `src/arima_forecasting/prep.py:40-74` (`clean_close`) forward-fills with `.ffill()`, refuses a
  fill that carries a close more than 7 days, and records the filled dates; `:84-103`
  (`check_coverage`) refuses truncated or holed data.
- `src/arima_forecasting/export.py:82-101` copies the snapshot's SHA-256, row count and download
  time into `prices.source`.
