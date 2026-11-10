# Milestone 5: pre-registered inference for the forecast comparisons, version 2

Written on 2026-11-09. It replaces the primary test of `m5-preregistration.md` (v1, SHA-256 `4a7e5090…f275db`) and leaves v1 and its outputs as the record. This file is frozen: `tools/comparison_inference.py` pins its SHA-256 and refuses to run a v2 analysis if the file changes.

## Why there is a version 2

v1's size control failed before any v1 family result was computed:

- **AR(1) with ρ = 0.3, n = 227:** v1's block bootstrap rejected 194 of 2,000 true nulls, 9.70%. The required band was [3%, 8%].
- **Cause:** the block rule picked b = 2 for most of those series. At b = 2 the bootstrap variance of the mean is about 1.29·γ0, against a true long-run variance of 1.857·γ0.

A design phase followed. It used simulated data only, on seeds 20261201 onwards, and computed no real loss differential. It tried three longer blocks, each built from the Politis–White automatic block length (2004, with the 2009 correction) and floored at v1's block:

- C1: max(b_v1, ⌈b_PW⌉)
- C2: max(b_v1, ⌈1.5 b_PW⌉)
- C3: max(b_v1, ⌈2 b_PW⌉)

At n = 227 and AR(1) with ρ = 0.5, all three rejected more than 8% of true nulls: 9.70%, 8.60% and 8.85%. Longer blocks did not fix it (C3 rejected more than C2), so the limit is the plain bootstrap of the mean at this n, not the block length. v1's informal fallback was the DM test with the HLN factor and γ̂0 alone. It rejected 16.4% of true nulls at ρ = 0.3 and 26.0% at ρ = 0.5 (n = 227), so it is not a fallback.

Two facts from real data are already known before this plan:

- the mean loss differentials (milestone 4's `evaluation.json`, reproduced exactly by v1's gate);
- the v1 block lengths of one real series shifted by +0.02 (v1's control 2: b = 6 for squared loss and b = 1 for absolute loss on the aic walk-forward oos window).

No p-value, ACF or block length of an unshifted real comparison has been computed.

## What stays as in v1

- the family and its order (k = 28);
- the windows;
- the losses;
- the per-period series d_t;
- the gate;
- α = 0.05 with Holm–Bonferroni over all 28;
- the decision words (worse, better, no difference detected, UNRESOLVED);
- the minimum detectable effect, reported beside a "no difference detected";
- the proxy label;
- both windows already scored once in milestone 4, so this is a change of inference, not a fresh holdout.

## What changes

### The 12 static comparisons are UNRESOLVED by construction

A static path's errors come from one origin and add up over the horizon. Its d_t is not a stationary series, so no test in this plan applies to it. Each static comparison enters Holm with p = 1. Its RMSE ratio stays in the README as a description of one path, never as a test.

### Primary test for the 16 one-step comparisons: the EWC fixed-smoothing t test

This is the equal-weighted cosine test of Lazarus, Lewis, Stock and Watson (2018, "HAR inference: recommendations for practice"):

- **Degrees of freedom:** ν = ⌊0.4 n^(2/3)⌋. That is 14 for n = 227 and 31 for n = 689.
- **Cosine weights:** for j = 1 … ν, Λ_j = √(2/n) Σ_{t=1..n} cos(π j (t − ½)/n) · d_t.
- **Variance estimate:** Ω̂ = (1/ν) Σ_j Λ_j².
- **Statistic:** t = √n · d̄ / √Ω̂, with a two-sided p from Student's t with ν degrees of freedom.
- **Constant series:** if Ω̂ = 0 and d̄ = 0, then p = 1. If Ω̂ = 0 and d̄ ≠ 0, the comparison is UNRESOLVED.
- **Minimum detectable effect:** (t_{ν, 0.975} + t_{ν, 0.80}) · √(Ω̂/n).

### Secondary results: reported, never decisive

Each is printed beside the measured size of its own test from control 3:

1. **The circular block bootstrap with the block from the measured ACF:** rule C2, b = max(b_v1, ⌈1.5 b_PW⌉), with the floor of 8 blocks.
   - The bootstrap itself is as in v1: B = 19,999, and seed 20261109 + the comparison's index.
   - Politis–White follows the authors' reference code: flat-top window, c = 2, K_n = max(5, ⌈√log10 n⌉), M = 2m̂, the circular-bootstrap constant.
   - For a constant series, b = 1.
2. **milestone 4's DM-HLN p:** copied from `evaluation.json`.

## Null controls (they must pass before any result is read)

1. **Identical forecasts.** d ≡ 0 for all 28. Every primary p equals 1, and nothing is rejected.
2. **Shifted forecast.** Add +0.02 to the aic walk-forward log forecast on the oos window. The primary rejects it under both losses (28 × p < 0.05), with d̄ > 0.
3. **Size.** Use control seeds 20261301 onwards. They are new, and the design phase did not use them.
   - 2,000 reps at n = 227 and at n = 689.
   - Processes: i.i.d. N(0, 1); AR(1) with ρ = 0.3; AR(1) with ρ = 0.5; and the design phase's GARCH(1,1) null loss differential (α = 0.08, β = 0.90, t(4) shocks, daily sd about 0.017, model forecast 0.02·r_{t−1} + 0.0009, centred by its 10⁶-day mean), under both losses.
   - **The primary's rejection rate at 5% must lie in [3%, 8%] in all 10 cells.**
   - The secondary bootstrap's rates (B = 999 here) and DM-HLN's are measured on the same series and reported. They do not gate anything.

If control 3 fails for the primary, no primary p-value is reported for any comparison. All 28 are UNRESOLVED, the reason is stated, and the next evidence is live periods. No version 3 will be written for this milestone.

## Outputs

`uv run python tools/comparison_inference.py --plan v2` writes `docs/validation/m5-comparison-inference-v2.json` and `docs/validation/m5-comparison-inference-v2.md`. They include:

- this file's SHA-256 and v1's;
- the gate and the three controls, with each test's measured size;
- for each of the 28 comparisons:
  - n, d̄ and ν, plus the primary t, p and Holm-adjusted p;
  - the minimum detectable effect;
  - the C2 block, block count and p;
  - the DM-HLN p;
  - the verdict;
- a "Runs" section that lists every run.

A bug fix is allowed and logged. A setting change is not.
