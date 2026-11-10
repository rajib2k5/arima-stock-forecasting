# Milestone 5: dual-channel check of the library claims

`route: rows 3 | primary: dual-channel EGV, Mode 1 (two independent subagents) | complement: orchestrator split probes on C5b, C9b and C10 | not-run: adversarial pass (reading cannot settle API behaviour) | stop: met`

The milestone-5 walkthrough and concept note 12 make 32 claims about statsmodels 0.15.0, pmdarima 2.1.1, pandas 3.1.0 and yfinance 1.7.0 (Python 3.12, pinned in `uv.lock`). The claims were frozen in a ledger on 2026-11-09, and then two agents checked them separately:

- **Channel A** read only the documentation and the installed source code, and ran nothing.
- **Channel B** only ran probes, on simulated data. Each probe had a falsifier: a changed input on which the probe must fail.

Neither agent saw the other's results.

## Result

| Gate | Claims |
|---|---|
| Both channels confirm | 27: C1a–d, C2a–b, C3a–c, C4a–d, C5c–d, C6a–b, C7a–c, C8a–c, C9a, C11, C12a–b |
| Both channels refute | 2: C5a, C5b |
| The channels disagreed; settled by a split and a measurement | 3: C9b, C10a, C10b |

**C5a (refuted as worded, now fixed).** The ledger said statsmodels' ARIMA "initialises the state" with an approximate diffuse prior of variance 10⁶. Both channels found that only the level, the differencing state, gets that prior. The ARMA part starts from its stationary distribution. Concept note 12 already said "the level"; its summary line now says it too.

**C5b (refuted, now fixed).** The concept note said the first one-step forecast's variance is 10⁶ + σ². It is 10⁶ + σ²(1 + θ²).

- On the course model's own fit to the 2,037 training days: θ = −0.07881, σ² = 0.00035403, and the first variance is 1,000,000.0003562305. The formula 10⁶ + σ²(1 + θ²) matches it exactly; 10⁶ + σ² is 2.2e-6 short.
- The printed value, 1,000,000.00036, was already right. Only the formula was wrong.

**C10a and C10b (accepted after a split).** Channel B confirmed both on simulated data. Channel A found that statsmodels' forecast equals the textbook form only once the Kalman filter has settled. The split settles each one by a measurement on the course model's own fit:

| Claim | Measured on the course model's fit | Gate |
|---|---|---|
| The forecast mean is flat for every step h ≥ 1 | max \|m_h − m_1\| = 0.0, with both channels confirming | ACCEPTED |
| The mean equals y_T + θ ε̂_T | gap 5.1e-10 | ACCEPTED |
| The variance equals σ²(1 + (h − 1)(1 + θ)²) | relative gap at most 2.4e-7, largest at h = 1 | ACCEPTED, and concept notes 10 and 12 now say it is the settled-filter form |

**C9b (accepted after a live probe).** The claim is that `yfinance.download("AAPL")["Close"]` is a one-column DataFrame labelled with the ticker. Channel A confirmed it from the source. Channel B could not decide, because its sandbox had no network.

- The orchestrator downloaded AAPL for 2026-10-01 to 2026-10-08: `DataFrame (5, 1) ['AAPL']`.
- Falsifier: with `multi_level_index=False`, the same call gives a `Series (5,)` and the probe fails.

## Records

The ledger, both channels' files and the probes are not in the repository. They are in the session scratchpad: `egv5/claims-ledger.md`, `egv5/channel-a.md`, `egv5/channel-b.md`, `egv5/probes/` and `egv5/orch/`.
