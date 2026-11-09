# Milestone 5: pre-registered inference for the forecast comparisons

Written on 2026-11-09, before any block-resampled statistic was computed. This file is frozen: `tools/comparison_inference.py` pins its SHA-256 and refuses to run if the file changes. A change to this plan needs a new file with a new name and a note on why. The old result stays as it is.

## What is already spent

Milestone 4 (commit `2dec79f`) scored both windows once. It ran one Diebold–Mariano test (HLN correction) for each comparison, with no correction for multiple tests:

| Window | Dates | Trading days |
|---|---|---|
| test | 2023-02-06 → 2023-12-29 | 227 |
| oos | 2024-01-02 → 2026-09-30 | 689 |

Their point estimates are known: the RMSE ratios and the DM p-values in `app/public/data/evaluation.json`. **This analysis is therefore not a fresh holdout.**

- The model orders were chosen on the train split only (ADR-0002).
- This analysis changes no model, order, window, forecast or loss. It changes only the inference: block resampling instead of an i.i.d. variance, and one correction over the whole family instead of none.
- A fresh one-shot holdout would be the trading days after 2026-10-01. The frozen snapshot does not hold them. They are the next evidence (live periods), and this analysis does not use them.

## The family (k = 28)

Every comparison of a forecast with the random walk that `evaluation.json` and the README report is in the family. That is 7 forecasts × 2 windows × 2 losses = 28:

- **Forecasts:** aic static, aic walk-forward, aic refit, bic static, bic walk-forward, course static, course walk-forward.
- **Windows:** test, oos.
- **Losses:** squared, absolute.

No other comparison is reported as a test.

## The per-period series

For each comparison and each trading day t in the window:

- **Errors:** e_t = actual log close − forecast log close. The forecast is the point forecast of the log price. These are the errors `evaluation.json` uses (`dm_settings.errors = "log"`).
- **Loss:** L(e) = e² (squared) or |e| (absolute).
- **Loss differential:** d_t = L(e_t, model) − L(e_t, random walk).

The series are read from the exported forecast files in `app/public/data/`.

**Gate before any inference.** The 16 one-step comparisons must reproduce `evaluation.json`'s `dm[].n` exactly and its `dm[].mean_diff` within a relative 1e-12 (absolute 1e-18 near zero). The 12 static comparisons must reproduce the log RMSE and MAE in `metrics[]` to the same tolerance. If the gate fails, nothing below runs.

## The test

- **Null hypothesis:** E[d_t] = 0, two-sided.
- **Block length b, from the measured ACF of d_t in that window:**
  - Compute the sample ACF of d_t: demeaned, biased estimator, lags 1 … L with L = min(⌊n/4⌋, 100). The band is c = 1.96/√n.
  - b is the smallest ℓ ≥ 1 such that |ρ̂(ℓ)|, |ρ̂(ℓ+1)| and |ρ̂(ℓ+2)| are all below c.
  - If no such ℓ ≤ L − 2 exists, then b = L + 1.
- **Block-count floor:** if ⌊n/b⌋ < 8, the comparison is **UNRESOLVED**. It has no p-value and enters the correction with p = 1.
- **Primary statistic:** circular block bootstrap (Politis and Romano, 1992) of the centred series d_t − d̄.
  - Block length b; B = 19,999 replicates.
  - `numpy.random.default_rng(20261109)`, with one generator per comparison in the family order above. The seed is 20261109 + the comparison's index (0–27).
  - The statistic is the mean.
  - p = (1 + #{|d̄*| ≥ |d̄|}) / (B + 1).
- **Secondary, reported but not decisive:** the Newey–West t with a Bartlett kernel and lag b − 1, and a normal two-sided p.
- **Correction:** Holm–Bonferroni over all k = 28 at α = 0.05 (family-wise), applied to the primary p-values. Report both the raw and the Holm-adjusted p.
- **Decision:** reject when the Holm-adjusted p < 0.05. The direction comes from the sign of d̄: positive means the model is worse than the random walk, negative means it is better.
  - Otherwise the result is "no difference detected". This is not "equal". The minimum detectable effect is reported beside it: (1.96 + 0.84) × the standard deviation of the bootstrap means d̄*, which is the smallest |E[d_t]| that a per-test 5% test detects with 80% power at this n before the correction.
  - UNRESOLVED applies when the comparison is below the floor.
- **Sensitivity, reported but not decisive:** the same bootstrap with block 2b, and the same with b = 1 (the i.i.d. case).
- **The primary result is final.** A sensitivity run never replaces it.

## Null controls (they must pass before the results are read)

1. **Identical forecasts.** Set the model's forecast to the random walk's (d ≡ 0). Then p = 1 and nothing is rejected.
2. **Shifted forecast.** Add +0.02 to the aic walk-forward log forecast on the oos window. The comparison is rejected under both losses, with d̄ > 0.
3. **Size.** Run 2,000 simulated series of n = 227, mean 0, under two processes: i.i.d. N(0, 1), and AR(1) with ρ = 0.3. Use the block rule above and B = 999.
   - The rejection rate at 5% must fall in [3%, 8%] for each process.
   - The AR(1) series with b = 1 forced is also reported, to show what an i.i.d. bootstrap does on dependent data.

## Labels

The metric is the log forecast loss on AAPL's adjusted close. It is the project's stated forecast metric, not a trading P&L, and no stake depends on it.

## Outputs

`uv run python tools/comparison_inference.py` writes `docs/validation/m5-comparison-inference.json` and `docs/validation/m5-comparison-inference.md`. For each comparison they contain:

- n, d̄ and b, plus the block count;
- the raw and Holm-adjusted p;
- the Newey–West t and p;
- the sensitivity p-values;
- the minimum detectable effect, and the verdict.

The outputs also carry the null-control results and this file's SHA-256.
