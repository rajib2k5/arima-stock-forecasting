# Log returns, fat tails and KDE bandwidth

Status: milestone-1 concept note, written 2026-10-29 and corrected after the milestone-1 review.
The AAPL numbers come from the training segment of `app/public/data/prices.json` and `eda.json`, as
exported locally from the 13:37 UTC snapshot (2015-01-02 to 2023-02-03, 2,037 closes, 2,036
returns; these two files are not committed, see ADR-0001). Each was measured on 2026-10-29 with the
command shown in the [milestone walkthrough](../milestones/01-data-and-eda.md#measured-results).

## First principles

A **log return** is the change in the log of the price from one day to the next:
$r_t = \ln P_t - \ln P_{t-1}$. It has two useful properties.

- **It adds up over time.** The log return over a week is the sum of the five daily ones. Simple
  returns multiply instead, which linear models such as ARIMA handle badly.
- **It is close to the simple return for small moves.** $r = \ln(1 + R) \approx R$ when R is small.
  A 1% day is a log return of 0.00995.

A **distribution** says how often each size of move happens. The usual benchmark is the **normal**
(Gaussian) bell curve. It is fixed by two numbers: the mean and the standard deviation (sd).

**Fat tails** means that big moves happen far more often than a normal curve with the same mean and
sd allows. **Excess kurtosis** measures this. It is 0 for a normal distribution and positive for a
fat-tailed one. **Skewness** measures lopsidedness. It is negative when the big moves are mostly
falls.

A **kernel density estimate** (KDE) draws a smooth curve of the distribution from the data. It puts
a small normal bump, the **kernel**, on every observation and adds the bumps up. The **bandwidth** h
is the sd of each bump. A small h gives a spiky curve that follows every quirk of the sample. A large
h gives a smooth curve that can hide the peak and the tails. Choosing h is the whole art.

A KDE describes a sample whose values come from **one fixed distribution**. A daily return is
roughly like that. A price *level* is not: AAPL's log price wandered from 3.0 to 5.2 over the
training years. A KDE of the level mostly shows how many days the price spent at each height. The
course draws a KDE of the dollar close; we draw the log close (for comparison) and the log return
(the series a model works with).

## The maths

**The KDE.** For values $x_1, \dots, x_n$ and bandwidth h,

$$\hat f(x) = \frac{1}{n h} \sum_{i=1}^{n} \varphi\left(\frac{x - x_i}{h}\right), \qquad \varphi(u) = \frac{e^{-u^2/2}}{\sqrt{2\pi}}.$$

**Scott's rule** (scipy's default, and what pandas' `plot(kind='kde')` uses) sets
$h = n^{-1/5} \cdot s$, where s is the sample sd. For our log returns, n = 2,036, so the factor is
$2036^{-0.2} = 0.21789$, and s = 0.018862, so h = 0.0041098 log points.

Two other rules, for comparison, on the same returns:

| Rule | Formula | h |
|---|---|---|
| Scott (used) | $n^{-1/5} s$ | 0.004110 |
| scipy's `'silverman'` | $(3n/4)^{-1/5} s = (4/3)^{1/5} s\, n^{-1/5}$, the bandwidth that is optimal when the data really are normal; Scott's is $(3/4)^{1/5} = 0.944$ times it at any n | 0.004353 |
| Silverman's rule of thumb (textbook) | $0.9 \min(s, \text{IQR}/1.34)\, n^{-1/5}$ | 0.002635 |

The textbook rule is 36% narrower here. It uses the interquartile range (IQR = 0.018008), which the
fat tails do not inflate. The sd is pulled up by the big days, so Scott's rule smooths more.

**The returns, measured.**

| Quantity | Value |
|---|---|
| mean | 0.000902 per day |
| sd (n − 1) | 0.018862 |
| skewness G1 | −0.225 |
| excess kurtosis G2 | 5.20 |
| days beyond 3 sd | 31 of 2,036 = 1.52%; a normal predicts 0.27% (5.5 days) |
| days beyond 4 sd | 11; a normal predicts 0.13 days |
| largest fall | 2020-03-16, −0.1377 (−12.9% simple), 7.35 sd below the mean |
| largest rise | 2020-03-13, +0.1132 (+12.0% simple) |
| third and fourth largest | 2019-01-03, −0.1049; 2020-03-12, −0.1040 |

Under a normal curve, a fall of 7.35 sd or more has probability $1.0 \times 10^{-13}$ on a given day.
The sample of 2,036 days had one. On the 200-point grid the KDE's highest value is 29.44, against
21.15 for the normal curve with the same mean and sd: 1.39 times as tall. (The grid points miss the
true peak slightly; the reviewer measured 29.465 at x = −0.00014.) A fat-tailed distribution is also *peakier*: more quiet
days and more wild days, fewer middling ones.

**The two estimators.** The contract names them because each has rivals.

- G1, the adjusted Fisher–Pearson skewness, is pandas' `skew()` and scipy's `skew(bias=False)`.
  scipy's default `skew()` is the biased g1.
- G2, the bias-corrected excess kurtosis, is pandas' `kurt()` and scipy's `kurtosis(bias=False)`.

On n = 2,036 the bias correction is small. On the hand example in `tests/test_eda.py` (five closes,
four returns) it is large: g2 = −2 but G2 = −6.

## Assumptions

- The returns come from one distribution that does not change over time (they are *identically
  distributed*). A KDE treats every day as a draw from the same curve.
- Scott's and Silverman's rules are *normal-reference* rules: they pick h as if the data were
  normal. The normal-optimal value is scipy's `'silverman'`; Scott's is 0.944 times it. Neither is
  optimal for a fat-tailed sample.
- The grid is wide enough. Ours runs from 3 bandwidths below the smallest value to 3 above the
  largest. Measured with scipy's exact `integrate_box_1d`: the log-return KDE keeps all but
  1.3 × 10⁻⁶ of its mass inside the grid (the trapezoid rule over the 200 points gives 0.99999855),
  and the log-close KDE all but 4.3 × 10⁻⁵, about 32 times as much, because its extremes sit in
  sparse stretches where a whole bump hangs over the edge.

## Where it breaks

- **Volatility clusters.** Calm months and wild months alternate: March 2020 holds two of the three
  largest moves above, and three of the four beyond ±0.1. The returns are not identically
  distributed, so the KDE blends several curves into one. It is a summary of the period, not a
  model of tomorrow.
- **One bandwidth cannot fit both the peak and the tails.** The big days inflate s, so Scott's h is
  wide for the crowded centre: the peak is flattened. In the sparse tails the same h is narrow
  compared with the gaps between the rare big days, so each extreme day stands alone as its own
  bump of height $1/(n h \sqrt{2\pi}) = 0.0477$: the tails are lumpy, under-smoothed. Measured on
  2026-10-29 (scipy's `find_peaks` on the KDE evaluated at 20,001 points): 8 local maxima, the
  peak and 7 tail bumps beyond ±0.05, two of them single days at −0.1377 and +0.1131 with height
  0.0477 each, and two (−0.1045, −0.0828) at about twice that height, as two nearby days give
  (−0.1049 and −0.1040 are the third and fourth largest moves). The textbook rule, built
  on the IQR, is narrower still; an adaptive (variable-bandwidth) KDE is the usual remedy.
- **A KDE of a level shows the path, not a distribution.** Our log-close KDE has three local peaks
  on the 200-point grid, near 3.28, 3.71 and 4.94 in log points: price levels the stock lingered
  at. Another eight years would give a different shape.
- **The kernel leaks past hard limits.** A KDE of a positive quantity puts some mass below zero. Log
  returns have no hard limit, so this does not bite here.
- **The sd is not the risk.** With excess kurtosis 5.2, "three sd" happens 5.6 times as often as the
  normal rule of thumb says.
- **Clustering is a separate fact from fat tails.** Intervals built on one constant error variance
  (as ARIMA's are) are too narrow in storms and too wide in calm spells *because volatility
  clusters*, not because of the kurtosis as such. Milestone 3's ARCH-LM test measures the
  clustering.

## In this project

- `src/arima_forecasting/eda.py:47-52` (`log_returns`) differences the log close.
- `src/arima_forecasting/eda.py:55-83` (`summary`) computes the four moments with the named
  estimators.
- `src/arima_forecasting/eda.py:86-98` (`tail_share`) counts the days beyond k sd and the normal
  share.
- `src/arima_forecasting/eda.py:101-133` (`kde`) runs scipy's `gaussian_kde` with Scott's rule on a
  200-point grid and adds the normal reference curve.
- `app/src/lib/explorer.ts` (`kdePlot`) draws `density` and `normal_density` from the JSON; the app
  computes neither.
