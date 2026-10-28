# Milestone 0 validation summary

Five independent passes checked milestone 0 before its first commit. Each was a separate Claude subagent that did not write the work it checked.

| Pass | Record | Outcome |
|---|---|---|
| Adversarial review: code, contract, hygiene, with evidence-gated validation | [`m0-code-review-ledger.md`](m0-code-review-ledger.md) | 13 claims: 7 refuted, 6 survived |
| Adversarial review: statistics and library behaviour, with evidence-gated validation, Tier 2 | [`m0-stats-review-ledger.md`](m0-stats-review-ledger.md) | 8 claims refuted, plus 5 findings nobody had asked about |
| Security review before the first public push | [`m0-security-review.md`](m0-security-review.md) | No exploitable findings; addendum for the final tree |
| Verifier: re-measured every number in the docs (first pass) | (scratch only) | 237 rows: 9 disagree, 6 could not be measured |
| Verifier: final pass after both fix rounds | (scratch only) | The 16 refuted items below re-checked: all resolved. About 330 figures re-measured and agreeing. 5 small items, fixed before commit. |

The ledgers are point-in-time records. Their `file:line` references point at the tree as it was reviewed, before the fixes. A reviewer may have been wrong too, so each refutation was reproduced before it was acted on. One claim from the build itself was also refuted: the architect said a malformed `SOURCE_DATE_EPOCH` silently falls back to the current time. It raises `ValueError` (`src/arima_forecasting/provenance.py`), as its docstring says.

## What was refuted, and what changed

| # | Claim as first written | What was wrong | Resolution |
|---|---|---|---|
| 1 | AIC cannot be compared across d because the likelihoods are of "different random variables, not on a common scale". | Differencing is a map with Jacobian 1. The d = 1 likelihood is the conditional density log p(y₂…yₙ \| y₁), and the d = 0 likelihood is the joint density; they differ by log p(y₁). | Rewritten in the background note §6, ADR-0002 §3, the contract and walkthrough Q6. The reason now given: joint versus conditional likelihood, plus the unit-root boundary, where the AIC penalty is not calibrated. That is why d is chosen by ADF and KPSS. |
| 2 | pmdarima `with_intercept='auto'` means an intercept iff d + D ∈ {0, 1}. | It only sets the stepwise starting value; the search toggles the intercept (`_auto_solvers.py:440-445`). | Fixed everywhere it appeared. |
| 3 | pmdarima drops failed fits silently. | Only with `error_action='ignore'`, which the course passes. The default `'trace'` warns with a traceback. | Fixed. |
| 4 | The stepwise search visits 5 of 36 orders with the course's arguments. | With `start_p=1, start_q=1` it makes 5 fits of 4 distinct orders. | Fixed and measured in ADR-0002. |
| 5 | pmdarima's ADF uses ⌊(n−1)^{1/3}⌋ + 1 lags. | It uses ⌊(n−1)^{1/3}⌋, and matches statsmodels `adfuller(regression='ct', maxlag=12, autolag=None)` to 6 decimals. | Fixed. |
| 6 | The pmdarima root filter discards near-unit-root AR models. | When q > 0 the MA check overwrites the AR check (`_auto_solvers.py:37-40`), so AR roots are ignored. | Documented as a pmdarima quirk in ADR-0002. |
| 7 | Fama (1970) allows predictable volatility. | Footnote 5, p. 387, says the order of past returns "is of no consequence". | Corrected. |
| 8 | "Largest AR root". | By the doc's own convention it is the largest *inverse* root. | Corrected. |
| 9 | The −4e-9 log-likelihood gap is "optimiser noise". | The gap is there at identical parameters, and it moves with the diffuse-prior variance. | Explained as the approximate-diffuse-initialisation effect. |
| 10 | Footnote `[^probe-pm]` numbers. | They did not reproduce. | Re-measured with a full recipe. |
| 11 | The TypeScript and Python envelope validators agree. | 14 of 82 envelopes diverged: `Date.UTC` maps years 0–99 to 19xx, TypeScript accepted any artifact name, and TypeScript accepted extra top-level keys. | Closed top level, the same name pattern and calendar arithmetic on both sides. A shared corpus of 142 cases (`app/src/test/fixtures/envelope_cases.json`) is run by both pytest and vitest. Now 0 divergences on the reviewer's 82, and 0 on a 1,120,100-string timestamp grid (the old readers diverged on 6,459). |
| 12 | `source_commit` never raises. | It raised on non-UTF-8 file names (`UnicodeDecodeError`) and on a non-executable `git` (`PermissionError`), and it rejected SHA-256 repos. | `surrogateescape`, `except OSError`, and 40- or 64-hex object names in both languages' contracts. |
| 13 | With `SOURCE_DATE_EPOCH`, two exports are byte-identical. | The first export dirtied the tree, so the second said `-dirty`. | The dirty check excludes `app/public/data/` (`:(top)` plus an exclude pathspec), with an end-to-end byte-identity test. |
| 14 | The tests are mutation-checked. | 3 of the reviewer's 6 new mutants survived. | Tests added; all 3 are now killed. A further 55 mutants: 53 killed, 2 equivalent. |
| 15 | The ERD and `.mmd` files describe the contract. | The ERD's `meta` fields did not exist, and the `.mmd` files were stale against the kit's current commit. | ERD fixed against the real payload; all `.mmd` files regenerated with kit `56aad83` and byte-checked. |
| 16 | The docs are suitable for a public repo. | They presented the unpublished diagram kit as a required tool, and one ledger line held an absolute home path. | Reworded; path redacted. |

**Verifier disagreements**, all fixed:
- a stale line range;
- "0.01%", which is 0.016%;
- a sentence about a deleted file;
- the ERD's nullable marker;
- ARCH-LM inputs that were not stated;
- `mean_se` steps that were mislabelled;
- unseeded probes;
- the README screenshots;
- the empty `reports/` folder;
- two rounding-level figures;
- an ambiguous σ⁴;
- an unstated grid recipe.

## Two course failures found along the way

These were found on simulated data and reproduced on the pinned stack, statsmodels 0.15.0 and yfinance 1.7.0. They are milestone 4 and 5 items, described in the background note §11 and the walkthrough's "What is next":
- **The forecast raises.** The course's `get_forecast` call raises `ValueError: No supported index is available.` on a trading-day index.
- **MAPE comes out NaN.** The course's MAPE line returns `nan`, because a Series minus a one-column DataFrame aligns into an all-NaN frame.

## Gates at commit time

The final verifier pass ran them; `uv run pytest` was re-run by the orchestrator after the last doc edits.
- `uv run pytest -q`: 530 passed.
- `uv run python tools/build_notebooks.py --check`: notebooks are in sync.
- `cd app && npm run verify`: lint clean; 458 tests in 21 files passed. Coverage of `src/lib/**` is 97.99% statements, 95.34% branches, 98.24% functions and 99.46% lines. The main chunk is 224.51 kB, and the lazy three.js chunk is 1,082.42 kB.
