# Classical decomposition, and why additive on logs

Status: milestone-1 concept note, written 2026-10-29 and corrected after the milestone-1 review.
The AAPL numbers come from the training segment (2015-01-02 to 2023-02-03, 2,037 trading days) of
the 13:37 UTC snapshot and were measured on 2026-10-29 with the commands shown in the
[milestone walkthrough](../milestones/01-data-and-eda.md#measured-results).

## First principles

A **decomposition** splits a series into three parts:

- the **trend**, the slow movement;
- the **seasonal** part, a pattern that repeats every **period** (here 252 trading days, about one
  year);
- the **residual**, whatever is left.

The **classical** method, which statsmodels' `seasonal_decompose` implements, works in three steps.

1. **Trend.** Take a *centred moving average* over one period. Each day's trend averages 253 days:
   the 126 before it, itself and the 126 after it, with the two end days at half weight (the maths
   below says why). Because the window is centred, it needs 126 days on *each side*. So the first
   126 and the last 126 days get no trend at all.
2. **Seasonal.** Remove the trend. Then, for each position in the period (day 1 of the "year", day
   2, and so on), average the detrended values at that position across all the years. Centre the
   result and repeat it over the whole series. On our training rows, 2,037 − 252 = 1,785 detrended
   values remain, 7.08 periods: 231 of the 252 positions average 7 values and 21 average 8.
3. **Residual.** What remains after removing trend and seasonal. It is missing wherever the trend
   is missing.

There are two ways to combine the parts.

- **Additive:** $Y = T + S + R$. The seasonal swing is a fixed number of units, whatever the level.
- **Multiplicative:** $Y = T \times S \times R$. The seasonal swing is a fixed *percentage* of the
  level. S hovers around 1.

Prices compound, so a multiplicative model suits *dollar* prices: a 2% seasonal effect is $2 on a
$100 stock and $4 on a $200 one. Taking logs turns products into sums:
$\ln(T \cdot S \cdot R) = \ln T + \ln S + \ln R$. So the **additive model on the log price is the
multiplicative model on the dollar price**. The two are one model written two ways.

The course runs a **multiplicative** decomposition **on the log price**. That reads the log as a
product: $\ln P = T \times S \times R$. Its seasonal factor multiplies the *log level*. So a 1%
change in the factor means about 0.03 log points when $\ln P$ is near 3 and about 0.05 when it is
near 5. That has no economic meaning. It is a double transform: the log already made the structure
additive.

## The maths

**The centred moving average for an even period.** With period m = 252 (even), "centred" needs a
small trick. statsmodels uses a 2×m average: weights $1/(2m)$ on the two end days and $1/m$ on the
251 days between them, 253 days in all. Day t's trend is

$$T_t = \frac{1}{2m} y_{t-126} + \frac{1}{m} \sum_{j=-125}^{125} y_{t+j} + \frac{1}{2m} y_{t+126}.$$

That is why exactly $m/2 = 126$ values are missing at each end (statsmodels' default
`extrapolate_trend=0` leaves them missing).

**Measured on the training log price** (`eda.course_comparison`, run 2026-10-29):

| Quantity | Value |
|---|---|
| rows / periods | 2,037 rows, 2,037 / 252 = 8.08 periods |
| trend undefined | first 126 and last 126 rows |
| additive seasonal part, min / max | −0.0552 / +0.0576 log points (range 0.1128) |
| additive seasonal part, sd | 0.0271 log points |
| residual, sd | 0.0763 log points |
| course's multiplicative factors, min / max | 0.98741 / 1.01330 |
| trends of the two versions, largest difference | 0 (the same moving average) |
| seasonal effects on one scale, largest gap: $\max \lvert T(S_\text{mult} - 1) - S_\text{add}\rvert$ | 0.0161 log points |
| $\max \lvert e^{T_{\log}} / T_{\$} - 1\rvert$, our trend against a multiplicative decomposition of the dollar close | 3.03%, on 2020-08-19 |
| $\max \lvert e^{S_{\log}} / S_{\$} - 1\rvert$, the same for the seasonal parts | 0.73% |

The level-based rows (the factors and the 0.0161 gap) depend on dividends paid after the training
segment, because back adjustment scales all training closes by one common factor (concept note
02). The trend-free rows do not. The size of that effect is not measured.

Read the last three rows carefully.

- The course's version and ours share the trend exactly. They differ in the seasonal part by up to
  0.0161 log points, about 1.6%. Small, because the log level moves only from about 3.0 to 5.2
  over the training years. The difference is not the point. The meaning is.
- "Additive on logs equals multiplicative on dollars" is true **as a model**. It is not exactly true
  **as an estimate**. Our trend is a weighted moving average of logs, so $e^T$ is a weighted
  *geometric* mean of prices. The dollar decomposition's trend is the weighted *arithmetic* mean.
  A geometric mean is never larger than an arithmetic one (measured: the ratio is at most 0.998
  everywhere), and for small spreads $\ln(\text{AM}/\text{GM})$ is about half the weighted
  variance of $\ln P$ inside the 253-day window. On 2020-08-19, where the gap peaks at 3.03%, that
  half-variance is 0.0323 against a log gap of 0.0308. **The variance there is mostly drift, not
  noise**: a straight line fitted to the window's log prices (slope 0.0033 a day, the 2020 run-up)
  holds 88% of it, and that straight line alone, with no volatility at all, gives a 2.80% gap. The
  seasonal parts differ too, by up to 0.73%.

## Assumptions

- There is a pattern that repeats exactly every 252 rows.
- The trend is smooth enough for a one-year moving average to capture.
- The seasonal pattern is the same in every year.
- For the multiplicative form, every value is positive. (Log prices from 3.0 to 5.2 are, so the
  course's call does not fail. It only means something odd.)

## Where it breaks

- **A stock has little true seasonality.** If a yearly pattern were reliable, traders would buy
  ahead of it and erase it. The "seasonal" part is the average detrended value at each position
  across only seven or eight years (7.08 periods of detrended data), so it is mostly noise. Its sd (0.0271) is about a third of the
  residual's (0.0763).
- **252 is not the true period.** Calendar years held 250 to 253 trading days (2023 had 250, 2020
  had 253; counted from `prices.json`). Position 1 of each "year" therefore drifts away from the
  first trading day of January. In the training years the drift stays within 2 trading days, and
  it keeps growing on a longer sample.
- **The trend uses the future.** The centred average at day t uses 126 later days. That is fine
  for describing the past. It is useless for forecasting, and it is one more reason the
  decomposition runs on the training segment only.
- **The ends are missing.** The last 126 training days, half a year, have no trend. A plot that
  joined the line across the gap would invent values; the app breaks the line there instead.
- **Shocks bleed into the seasonal part.** March 2020 falls at one position of one year. With only
  seven or eight values to average at each position, that one shock moves the seasonal estimate
  there.

## In this project

- `src/arima_forecasting/eda.py:136-148` (`decompose`) calls `seasonal_decompose` on a plain array
  with an explicit period, because a trading-day index has no frequency.
- `src/arima_forecasting/eda.py:155-170` (`decomposition`) writes the rows, with `null` where the
  trend and residual are undefined.
- `src/arima_forecasting/eda.py:173-210` (`course_comparison`) measures the course's
  multiplicative-on-logs version against ours, and our trend against the dollar decomposition.
- `src/arima_forecasting/payloads.py` checks that the trend is null on exactly the first and last
  `period // 2` rows and nowhere else.
- `app/src/lib/plot.ts` (`gapPath`) breaks the line at each null instead of joining across it.
