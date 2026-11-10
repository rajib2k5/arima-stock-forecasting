# Milestone 5: addendum to both inference plans (corrections after review)

Written on 2026-11-09, after the v2 analysis ran and an adversarial review of its procedure (validation router row 5, procedure claims only). The two plans, `m5-preregistration.md` (v1) and `m5-preregistration-v2.md` (v2), are frozen and are not edited. This file corrects them. Where it disagrees with them, this file is right.

## 1. A false statement in both plans

**What the plans say.** v1 says it was written "before any block-resampled statistic was computed". v2 says "No p-value, ACF or block length of an unshifted real comparison has been computed".

**Why it is false.** Milestone 4's third review pass (commit `800a0a8`, 2026-10-30) had already published several such statistics on the real out-of-sample loss differentials, in `docs/milestones/04-forecast-and-evaluation.md` (items 14 and 15, and probe 5):

- the Ljung–Box test at lag 10, and the lag-1 autocorrelation of d_t;
- circular block bootstrap p-values with blocks of 5, 10 and 20 days;
- Newey–West p-values at 6 and 9 lags.

`evaluation.json` also holds all 16 DM-HLN p-values. The author of both plans had those results in hand. The two sentences were wrong when they were written, and both are withdrawn.

**What remains true:**

- Neither plan's own family was computed before that plan was frozen. v1's tool stopped at its size control, and its JSON has no comparisons and no runs of the family. v2's plan was hashed at 21:36:59Z, and its first run started at 21:58:37Z.
- The switch from v1 to v2 was triggered by a failed size control on simulated data.
- v2's test and its ν come from a published rule (Lazarus, Lewis, Stock and Watson, 2018). They were not tuned on the real series.
- The outcome is the same one that v1's informal fallback gives. That fallback is DM-HLN with Holm over the 16 one-step comparisons, and it also leaves exactly one rejection, BIC, oos, absolute loss: 16 × 0.00017 = 0.0027, and the next smallest gives 15 × 0.0100 = 0.15.

So the procedure was not blind to the real data. Its choices, and the single surviving result, do not appear to depend on what was seen.

## 2. Limits that the size control did not cover

v2's size control used five simulated null processes. The real out-of-sample loss differentials lie outside all of them. These numbers were re-measured by the orchestrator, with n = 689 for both series:

| Series (oos) | Autocorrelations, lags 1–10, summed | Excess kurtosis | Share of Σ(d − d̄)² in the top 5 days |
|---|---|---|---|
| aic walk-forward, squared loss | −0.467 | 135.3 | 0.67 |
| bic walk-forward, absolute loss (the surviving result) | −0.155 | 6.6 | 0.21 |

**Squared loss.** The squared-loss series are dominated by one burst of five days, and its signs largely cancel at low frequencies. This is why EWC's long-run variance falls far below γ̂0 there (Ω̂/γ̂0 ≈ 0.32 for aic walk-forward), and why its p-values on oos squared loss are much smaller than DM-HLN's. The reviewer built nulls by block resampling (b = 40) from the real series. On those, EWC rejected 12.0% and 13.4% of true nulls for aic walk-forward and aic refit, oos, squared loss. So the raw EWC p-values for the oos squared-loss comparisons are not reliable. None of them survives Holm in any case.

**Absolute loss (the surviving result).** On the same kind of nulls, EWC rejected 5.1% to 6.9%. The reviewer's largest calibrated p for this comparison is 0.0011, which gives 28 × p = 0.031, still below 0.05. Those calibration figures are the reviewer's and were not re-run here.

**The oos one-step comparisons are not independent.** The loss differentials of aic walk-forward and aic refit correlate 0.995 (squared) and 0.989 (absolute). "All eight lean the same way" is therefore not eight pieces of evidence.

## 3. What the write-ups must say

- **The oos window.** No model, order or forecast was chosen on it. The inference method was chosen after milestone 4's results on it were seen. "Never used for any choice" is withdrawn.
- **The surviving result.** One verdict survives correction for all 28 comparisons: BIC's one-step forecast is worse than the random walk on oos, absolute loss. State it with its procedure, its limits (section 2), "not a fresh holdout", and the proxy label: log loss on the adjusted close, not a P&L.
- **The other comparisons.** "No difference detected" after the correction. Raw p-values are not presented as a pattern.
- **Comparisons that are not tests.**
  - The static paths, and the comparison of the AIC model with a random walk that carries its drift, are one path each. They describe what happened. They do not show that two forecasts are equal.
  - The course model's static oos path, which has no drift, has a ratio of 0.9991, just below 1.
- **Coverage.** The 32 Kupiec coverage tests are per test, with no correction. Holm over those 32 keeps 13 of the 20 "too wide" verdicts: 9 on the test window and 4 on oos.
