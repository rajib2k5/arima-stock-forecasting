# Milestone 2 validation summary

Two independent adversarial reviews checked milestone 2 after it was built. Each was a separate
Claude subagent that did not write the work it checked. The coordinator reproduced the most serious
finding before the fix round, and the builder reproduced each item again before fixing it.

| Pass | Record | Outcome |
|---|---|---|
| Adversarial review: code, contract, data hygiene (evidence-gated, single-context fallback) | [`m2-code-review-ledger.md`](m2-code-review-ledger.md) | 18 claims: 4 refuted (1b, 1c, 2c, 4b), 14 accepted, two of them with a note (1e stale wording, 7 a mutant count); 6 further defects no claim covered |
| Adversarial review: statistics, library behaviour and docs (single-context fallback) | [`m2-stats-review-ledger.md`](m2-stats-review-ledger.md) | 16 gated claims: 3c refuted; 3e, 5 and 6 refuted in part; the rest accepted, 7 and 9 except named lines; 6 refuted statements with fixes; 4 defects no claim covered, the first of them the main one (no guard against local optima) |

The ledgers are point-in-time records. Their `file:line` references point at the tree as it was
reviewed, before the fixes. Absolute home paths in them are redacted to `<repo>`, `<scratch>` or `~`.

## What was refuted, and what changed

| # | Finding (ledger) | Reproduced? | Resolution |
|---|---|---|---|
| 1 | **Local optima in the grid**: one start per cell; many `ok` cells sit below a model they nest (stats 3c and "not covered") | Yes. In the first export, 94 pairs of `ok` d = 1 cells at the shipped tolerance of 2e-3 (99 at zero tolerance; the coordinator counted 86 with a rule not recorded), worst 21.83. The new Python reader refuses that file with 293 problems | Each cell fitted from statsmodels' default start, every model one step smaller padded with zeros, and 24 seeded random starts; the highest likelihood kept, an unconverged winner polished once; the cell records `start` and `starts_tried`. Both readers refuse a cell more than 2e-3 below a model it nests (contract 1.3.0). The new export has no such pair |
| 2 | "No other cell within 2" (stats 3c) | Yes, as a consequence of 1 | **The choice changed** (round 1; superseded in round 2, below): ARIMA(2, 1, 4) with a drift, AIC −10440.208, with six others within 2: (4, 1, 3) +0.119, (4, 1, 2) +0.372, (2, 1, 5) +0.607, (3, 1, 5) +0.742, (5, 1, 2) +1.662, (5, 1, 3) +1.864. Followed through the walkthrough, concept note 07, ADR-0002, the README, notebook 02 and the tests |
| 3 | "Flat surface, nine models 33-40 below" (stats 7) | Yes | Rewritten from the new grid: 26 `ok` cells more than 30 below ARIMA(0, 1, 1) with a drift, the chosen one 41.27 below |
| 4 | The half-sample AIC gaps (2.11, 5.33) are optimiser artifacts (stats 3e) | Yes: both fits started from the default, and the 2015-2019 one did not converge | Deleted. Replaced by the per-day log-likelihood split of the chosen model against ARIMA(0, 1, 1) with a drift: 66.5% of the gain from 2020 onwards, 75.3% from 2020-02-15 to 2020-05-31 (72 days) |
| 5 | "±1 holds for converged fits only" (stats 5) | Yes: pmdarima's visited (2, 1, 2) with an intercept converges (41 iterations) at −10402.059, 34.806 above our (2, 1, 2) with a drift | "Holds only when both fits reach the same optimum", with that measurement (ADR-0002, concept note 07) |
| 6 | Over-fitting never stated (stats 6, "not covered") | Yes | Concept note 07, "Over-fitting, stated plainly": near-cancelling roots make AIC's penalty unreliable; a gain this concentrated may not generalise; milestone 4's out-of-sample test decides |
| 7 | Explain-it-back Q7 gave (2, 1, 2)'s ±158.9° as the choice's roots (stats 9) | Yes | Q7 now gives the chosen model's ±156.7° and names (2, 1, 2)'s |
| 8 | The p-value defined loosely (stats R6) | Yes | Concept note 05: the probability, under the null, of a statistic at least as extreme as the one observed |
| 9 | ADF at d = 2 chose lag 26, the maximum ("not covered") | Yes | Noted in the walkthrough with a measurement: with `maxlag` 40 and 60 the lag is 40 and 45, τ moves from −13.98 to −11.49 and −10.93, the verdict does not; the long lag is the over-differencing |
| 10 | The data test read names and disk sizes only (code 1b, 1c) | Yes, all four bypasses, in a scratch clone | `tests/test_repo_data.py` reads HEAD and index blobs (`git cat-file`), flags `*.csv.gz`, `*.parquet` and any file whose first line has the price-table columns. In a scratch clone each bypass passes the first version and fails the new one (below) |
| 11 | NaN and Infinity tokens: Python reads them, `JSON.parse` does not (code 2c) | Yes | `loads_strict` with a `parse_constant` that raises, in `read_artifact` and `compare_exports`; the review's six cases are the corpus's `token_cases`, run by both suites (the app through `loadArtifact`) |
| 12 | The app counted bars past the band itself (code 4b) | Yes | `acf_outside`, `pacf_outside` and the counts exported; both readers check them; the page draws them |
| 13 | Dead held callout and stale wording (code 1e) | Yes | Callout, `looksAbsent` and their tests removed; `useOrderData.ts`, `contract.md` and the `App.test.tsx` test fixed |
| 14 | LICENSE without a data carve-out; z not tied to alpha; a failed cell's cross at the best cell's height; a duplicated `DATA.md` cell (code, not covered) | Yes | One LICENSE line; `Z_FOR_ALPHA` in both readers; failed cells marked below the floor (`FAILED_Y`); the `DATA.md` table fixed |

## Found while fixing

- A padded start can stop exactly where it began, unconverged; a "converged first" rule then kept a
  worse converged run and left 7 nesting breaks. Fixed by keeping the highest likelihood.
- A converged run can stop short: (0, 1, 1) with a drift converged 1.7e-4 below an unconverged run.
  Fixed by the polish restart and a keep tolerance of 1e-4.
- `random_starts(…, count=RANDOM_STARTS)` read the constant at import, so a sensitivity run that set
  it to 6 silently drew 2 and showed "no change". Fixed (read at call time); the run was repeated.
- A start can end at NaN parameters without an error; numpy then raised outside the run's `try`
  (found by mutant F3). Fixed: a non-finite run is a failure; a test fails on the old code.
- statsmodels' `arroots` divides by a root at zero, which a padded start that never moved has;
  `largest_inverse_root` reads the inverse roots from the polynomial instead.

## Pushback

- **The near-tie list is not settled by better starts.** (Round 2 went further: better search moved the choice too.) The review expected that, with good starts,
  a fixed list of near ties would appear. Measured: with 2, 6, 12 and 24 random starts the chosen cell
  and its AIC never moved, but the other cells within 2 were 3, 5, 4 and 6. The docs call the list a
  lower bound.
- **The review's "no probe beat (3, 5, t)" does not hold.** With random starts, ARIMA(2, 1, 4) with a
  drift reaches −10440.208, below (3, 1, 5) with a drift at −10439.466 (and round 2 found ARIMA(3, 1, 4)
  lower still).
- **Mutant A5 kills 3 tests, not 2.** Re-run on the fix-round tree: the three AIC tie cases fail. The
  review's mutant text was not recorded, so its 2 could not be reproduced.

## Mutants of the new guards

Python (a copy of the fixed tree; unchanged copy `421 passed` on the suites each mutant ran): F1-F12,
all killed, F9 (a bar on its band counted as outside) only after two tests were added. App (unchanged
copy `Tests 921 passed (921)`): G1-G6, all killed; A5 re-run: 3 fail. The walkthrough lists each
mutant and the tests that killed it ([Mutation testing](../milestones/02-stationarity-and-identification.md#mutation-testing)).

The data test's bypasses, in a scratch clone of the fixed tree (the first version of the test, then
the new one):

| Bypass | First version | New version |
|---|---|---|
| none | 16 passed | 32 passed |
| the raw CSV copied to `app/public/data/aapl_daily.csv`, untracked | 16 passed | 1 failed (`test_no_tracked_or_stageable_file_is_a_price_table`) |
| the same file, staged | 16 passed | 1 failed (the same) |
| `AAPL_1d_2015-01-01_2026-10-01.csv.gz`, force-added | 16 passed | 1 failed (`test_git_tracks_no_raw_vendor_file`) |
| `notebooks/raw_prices.csv`, untracked | 16 passed | 1 failed (price table) |
| the same file, staged | 16 passed | 1 failed (price table) |
| a staged 10,000,001-byte blob, working copy truncated to 0 | 16 passed | 1 failed (`test_no_committed_data_file_is_over_10_mb`) |

## Round 2: the re-review of the fix round

A focused re-review attacked the first fix round
([`m2-rereview-ledger.md`](m2-rereview-ledger.md)); the coordinator reproduced its main finding with
plain statsmodels. Each refuted claim from round 1, and what changed:

| Round-1 claim | Re-review | Resolution |
|---|---|---|
| ARIMA(2, 1, 4) with a drift, AIC −10440.208, is the lowest-AIC `ok` cell at d = 1 | **Refuted**: (3, 1, 4) with a drift reaches −10440.245 (llf 5229.1227), 0.037 lower, `ok` under the repo's own rule | Reproduced. Perturbed padded starts and a polish stage (Nelder-Mead then L-BFGS from every polished cell's estimates, for the cells within 4 AIC of the best of each d and every cell tied with a model it nests), then a nesting repair. **The choice is now ARIMA(3, 1, 4) with a drift, AIC −10440.245** |
| "More starts never moved the choice" | **Refuted** by the row above: it held only for the repo's L-BFGS search | Removed everywhere; the docs say the choice is the best the documented search found and that gaps of a few hundredths mean nothing |
| "Six others within 2" (README, walkthrough) | **Refuted in part**: unqualified, and the true list was longer | Now "the search found seven others within 2, a lower bound": (2, 1, 4) +0.036, (4, 1, 3) +0.128, (4, 1, 2) +0.400, (2, 1, 5) +0.593, (3, 1, 5) +0.629, (5, 1, 2) +1.567, (5, 1, 3) +1.859 |
| Concept note 07: (3, 1, 4) "just outside", at ΔAIC 2.000000000004, the chosen model with a zero third AR coefficient | **Refuted**: a separate optimum, with ar.L3 = −0.40 | Deleted; (3, 1, 4) is the choice |
| No cell is stuck at a nested model's optimum (implied by the nesting rule) | **Refuted**: 7 cells' llf equalled, to 1e-6, a model one step smaller, marked converged | Reproduced on the round-1 file. None now (`test_no_committed_cell_sits_at_the_optimum_of_a_model_it_nests`; `test_no_cell_is_left_at_the_optimum_of_a_model_it_nests` on a simulated walk) |
| The nesting guard refuses a drop above 2e-3 | **Survives** at the shipped setting, but the bound came from the file: `nesting_tolerance: 100` let a 21.8 drop through | Both readers pin 2e-3 and refuse any other stated value; two corpus cases |
| 66.5% / 75.3% of the gain from 2020 / spring 2020 | **Survives** at the grid's point; the third digit moves about half a point between optima within 0.002 llf | Quoted at the grid's recorded parameters (now in the file, `params`) and rounded: about two thirds (64.2%) and about three quarters (77.2%) for the new choice |
| `tests/test_repo_data.py` catches a renamed or compressed raw table | **Refuted**: gzip under other names, xz, tab or semicolon delimiters, a comment line, Timestamp, UTF-16 all passed | Compressed files opened by their first bytes (gzip, xz, bzip2, zip), any of three delimiters, comment lines skipped, UTF-16 by its byte-order mark, Date, Datetime or Timestamp first. Each case proved in a scratch clone (below); a headerless table is still not caught, and the docstring says so |
| The app never compares a value with its band | **Survives**, with a wording nit | `identification.py` now says the reader compares only to check Python's flag |
| The export is reproducible | **Survives** (byte-identical in the re-review) | Unchanged |

**Pushback in round 2:** none of substance. The re-review also listed (4, 1, 4) with a drift within 2
(+1.994, `ok`); in this export its highest-likelihood run (+1.806) did not converge, so the rule
excludes it.

**Checked by the orchestrator after round 2** (the re-review's saved runs against the new grid): no
run beats the selected cell. Seven cells have a better run in the re-review's search than in the grid
(by 0.02 to 1.00 in log-likelihood). One of them matters for the near ties: (4, 1, 4) with a drift
reached +1.139 with a converged run, inside 2. The list in the docs is therefore a lower bound, as
they say; the choice is unaffected.

The data test, round 2, in a scratch clone (the first fix round's test, then the new one; every case
staged, then undone):

| Case | Round 1 | Round 2 |
|---|---|---|
| none | 32 passed | 44 passed |
| gzip as `x.txt.gz`, as `x.gz`; xz as `p.csv.xz`; bzip2 as `p.bin`; a zip as `z.dat` | 32 passed each | 1 failed each |
| tab- and semicolon-separated; a comment line first; Date renamed Timestamp; UTF-16 | 32 passed each | 1 failed each |
| a headerless table (the documented limit) | 32 passed | 44 passed |

## Gates at the end of the second fix round

Run on 2026-10-29 on two trees: the working tree (snapshot under `data/`) and a fresh `git clone`
with the working tree copied over it minus every ignored file. The walkthrough's
[Gate results](../milestones/02-stationarity-and-identification.md#gate-results) give the commands.

- `uv run pytest -q`: full tree `1214 passed in 168.59s`; fresh clone `1213 passed, 1 skipped` (the
  checkout-name test).
- `uv run python tools/build_notebooks.py --check`: `notebooks are in sync` on both.
- `cd app && npm run verify`: lint clean; `Tests 936 passed (936)` on both; coverage of `src/lib/**`
  96.58% statements, 91.86% branches, 99.15% functions, 99.21% lines; main chunk 226.66 kB.
- `VOL_DATA_DIR=$PWD/data uv run python tools/export_app_data.py --check`: `app data is current: …`,
  exit 0, 6 min 22.8 s; the export itself 6 min 50.2 s (3,890 runs; load average about 20 from other
  jobs; the first export took 1 min). Fresh clone: exit 2, no snapshot.
- Every `file:line` in the milestone-2 docs was checked with a script against the final files (0
  problems; the contract's four library paths point into site-packages).
- The diagram specs did not change in either fix round.

Each export's `source_commit` ends in `-dirty`, because the code is not committed yet; the files need
one more export after the code commit.
