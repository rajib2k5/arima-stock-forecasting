> Point-in-time record of the milestone-2 adversarial review (stats), copied unchanged except that
> absolute home paths are redacted to `<repo>`, `<scratch>` or `~`. Its `file:line` references point at the
> tree as reviewed, before the fix round; [`m2-summary.md`](m2-summary.md) says what changed.

# M2 statistics review: ledger

mode: single-context sequential fallback (Mode 2). Results are "dual-confirmed (fallback mode)", not independent.
Env: env-pin.txt (Python 3.12.13, statsmodels 0.15.0, pmdarima 2.1.1, scipy 1.18.1, numpy 2.5.4, pandas 3.1.0).
Pre-registration: claims-ledger.md. Channel A: channel-a.md (committed before any probe output). Channel B: channel-b.md, verbatim p*.out.
Repo files were not modified. The probes used prices.json train rows, not VOL_DATA_DIR.

## Gate per task claim

| # | Gate | Notes |
|---|---|---|
| 1 | ACCEPTED | Train only (export.py:159; n 2037). All 12 ADF/KPSS figures reproduce exactly with plain statsmodels calls at default maxlag. 'ct' agrees. ndiffs gives 1,1,1. The clipping guard matches _stattools.py:3224-3235. "inconclusive" is total and reachable. Nits: d2 ADF picked lag 26 = maxlag (boundary, not mentioned); `tests_conflict` is also true when the fallback d is "inconclusive" (naming) |
| 2 | ACCEPTED | plot defaults (tsaplots.py:156,157,162,318). The band equals what plot_acf/plot_pacf actually pass to fill_between (diff 0.0). The Bartlett and 1/sqrt(n) forms match the source. All values reproduce |
| 3a trend/d | ACCEPTED | arima/model.py:178-190. 'c' at d1 and 't' at d2 refused; 't' at d1 is the drift. d=2 has no admissible drift (quadratic) and the grid documents this |
| 3b k | ACCEPTED | k = len(params) = df_model for all 144 cells. P15 equivalence holds: by reasoning, a smaller p+q never pairs with a larger k when the trend is 0 or 1 term; it was not run as a mutant |
| 3c "no other d=1 cell within 2" | **REJECTED** | It is true of the artifact, false of the models. The grid's 'ok' cells are often not at their MLE: 53 d=1 nesting violations, up to 21.8 llf. With better starts, (5,2,t) +0.498, (2,4,t) +1.676, (4,2,t) +1.785 and (4,5,t) +1.999 are all within 2. At its MLE, (4,5,t) is always within 2, because it nests (3,5,t) with one extra parameter. No probe beat (3,5,t) itself |
| 3d BIC | ACCEPTED | |
| 3e roots ~158 deg | ACCEPTED | nine lowest: AR 156.3-158.9, MA 155.8-160.3 |
| 3e "gain mostly 2020+" | conclusion ACCEPTED, evidence **REJECTED** | The per-observation llf split shows 64-80% of the gain comes from 2020+ (2,2,t: 17.49 of 21.96; 3,5,t: 17.39 of 27.12), and 72-85% from 2020-02-15..05-31 alone. But the docs' half-sample evidence is an optimizer artifact. On the 2020- half, from a better start, (2,1,2)t is -22.98 vs (0,1,1)t (the docs say +5.33). The 2015-2019 fit (2.11) did not converge |
| 3f AIC never across d | ACCEPTED | |
| 4 statuses | ACCEPTED, with a defect | The counts, thresholds, AR/MA split and the d0 "all 30 AR fits" claim reproduce, and 0.99 = pmdarima _auto_solvers.py:42. But "ok" only means "the optimiser said converged": nothing detects a local optimum (see 3c) |
| 5 pmdarima | ACCEPTED (numbers); a derived claim **REJECTED** | All the numbers reproduce; ARIMA and SARIMAX at maxiter 50 agree bit for bit. REJECTED: "The ±1 tolerance of §7 holds for converged fits only" (ADR-0002:389). Same model, both converged: SARIMAX (2,1,2)+c -10402.059 vs ARIMA (2,1,2)t -10436.865, a gap of 34.8, and pmdarima's default run visited exactly that fit |
| 6 honesty | partly **REJECTED** | The tone is candid: BIC disagreement, cancelling roots, 2020. But "over-fitting", "redundant parameters" and "may not generalise" are never stated. The key supporting evidence is wrong (3c, 3e), and the "flat surface" is presented as a property of the data |
| 7 concept maths | ACCEPTED except where listed | k_max 26, the KPSS formula and critical values, half-lives, SE 1.1, Bartlett, 0.04344, the 8-point example (by hand), llf 5229.585, the BIC sums, the power table (re-run) and drift = c/(1-sum phi) (0.0008984 vs 0.0008982) all check out. REJECTED: 07:104-107 ("flat surface", "nine larger models 33-40 below": an optimizer artifact) and 07:114-117 (the half-sample numbers) |
| 8 measured numbers | ACCEPTED for all stats numbers in "Measured results" (more than 40 checked) and the sizes | Timings, determinism and JS chunk sizes were NOT re-run |
| 9 predict/explain | mostly ACCEPTED | Predict Q5 ("how many within 2": the expected answer, 0, depends on the optimizer). Explain Q7 (milestone:483) attributes ±158.9° to "AIC's choice"; those are (2,1,2)n's roots, and (3,1,5)t's are 156.7°/156.6° |
| 10 course | ACCEPTED | Read with zipfile. ADF only, on the whole df_log (course.txt:223,230; split at :283); plot_acf/plot_pacf(df_log_diff, lags=50) (:250-251); auto_arima arguments identical apart from trace (:260-271) |
| 11 oversimplifications | see below | |

## Refuted items with location and a minimal fix

1. milestone 02:255 (Q5), :42-43; ADR-0002:391; concept 07:77-79. "No other cell within 2". Fix: say "no other cell *as fitted* within 2". Better: refit each cell from its best nested sub-model (padded with zeros) plus a few random starts, keep the best converged fit, and re-derive within_2.
2. concept 07:104-107. "Most of the d=1 surface is flat … nine larger models 33-40 below". Fix: state that 29+ larger 'ok' cells sit at local optima; with the starts fixed, about 12 cells are within 4 of the best.
3. milestone 02:273-274, :325-326; concept 07:114-117. "The gain disappears on either half". Fix: delete this. Replace it with the llf_obs split: 64-80% of the gain is from 2020+, 72-85% from 2020-02-15..05-31. Disclose that the 2015-2019 half-sample fit did not converge.
4. ADR-0002:389 (and concept 07:148-149). "±1 holds for converged fits". Fix: "holds only when both fits reach the same optimum; a converged SARIMAX (2,1,2)+c sits 34.8 above our (2,1,2)t".
5. milestone 02:483 Explain Q7. Fix: "(2,1,2)'s roots at ±158.9° (the chosen cell's are at about 156.7°)".
6. concept 05:11-12. "The p-value is that likelihood". Fix: "the probability, under the null, of a statistic at least as extreme as the one observed".

## Not covered by any claim

- **No local-optimum guard.** fit_cell (selection.py:83-149) uses one start, and the readers re-derive status from the convergence flags only. Add a nesting check: llf(bigger) >= llf(nested) - tol, flagged or refit. This is the main defect: the shipped landscape, delta_aic for 29+ cells and within_2 are optimizer artifacts.
- **AIC with near-cancelling roots.** The redundant AR/MA parameters are close to unidentified, which is the regime where AIC's 2k penalty, like the unit-root argument of 07:39-42, is invalid and over-selection is expected. The docs make this argument for d but not for the chosen order.
- d2 ADF lag chosen at the boundary (26 = maxlag): the over-differencing also shows in the test's lag choice.
- The milestone 02:202 list of not-converged cells names 3 of the 4 and does not say that (1,1,0) appears twice (concept 07:97 is correct).
