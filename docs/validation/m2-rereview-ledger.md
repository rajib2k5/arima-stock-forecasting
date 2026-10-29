> Point-in-time record of the milestone-2 re-review of the first fix round, copied unchanged except that
> absolute home paths are redacted to `<repo>`, `<scratch>` or `~`. Its `file:line` references point at the
> tree as reviewed, before the second fix round; [`m2-summary.md`](m2-summary.md) says what changed.

# M2 fix-round re-review ledger (2026-10-29)

Tree: <repo>, uncommitted working tree, HEAD 16366d1. No tracked or
working-tree file was modified (`git status --short` showed 108 lines before and after; aic_grid.json mtime
is 13:31 CDT, from before this review). Env for every Python run: OPENBLAS_NUM_THREADS=1, VOL_DATA_DIR=$PWD/data.
Scratch: this directory.

## 1. (2,1,4,t) at AIC -10440.208 is the lowest-AIC ok cell at d=1: REFUTED

- attack1.py: 22 cells (the 7 near ties, (3,1,4,t), (4,1,4,t), (5,1,4,t), (2,1,3,t), (4,1,5,t), (5,5,t),
  (3,3,t), (5,1,t), (1,5,t), and 6 no-trend cells). Phase A: default start with lbfgs / nm / powell, 80 random
  starts with lbfgs (own seeds, scales 1 and 2), 15 with bfgs. Phase B: every cell's best params moved into
  every other cell (padded or truncated by parameter name), with lbfgs and nm. Phase C: top 5 per cell polished
  with lbfgs, maxiter 200. 2151 + 648 + polish fits. Log: attack1.log.
- Result: (3,1,4,t) reaches llf 5229.1227, AIC -10440.2454. That is 0.037 below the chosen cell, and 1.02 llf
  above the grid's 5228.1042, which is exactly (2,1,4,t)'s llf. Five Nelder-Mead runs from different
  transplanted starts reached the same point.
- Checked with the repo's own code (verify1b.py): `selection.run_start` from the Nelder-Mead endpoints gave
  converged True in 1 iteration (3 of 4 runs), warnflag 0, AR 0.9317, MA 0.8850. Then `selection._cell_from`
  gave status=ok, AIC -10440.2454. So under the repo's own rule the selection would be ARIMA(3,1,4) with a drift.
- The same stall pattern shows elsewhere. 7 cells in aic_grid.json have an llf equal, to 1e-6, to a model one
  step smaller (stuck at the zero-padded start): (1,3,4,n), (1,3,3,t), (1,3,4,t), (1,4,4,t), (1,4,5,t),
  (1,5,5,t), and (0,5,5,c). Every one of these I attacked moved up: (3,3,t) +0.78, (3,4,t) +1.02,
  (4,4,t) +0.08 at ok (+0.51 near unit root), and (5,5,t) +1.02 at ok.
- Smaller gains in other cells (my best ok, against the grid): (4,1,3,t) +0.014, (3,1,5,t) +0.075,
  (5,1,2,t) +0.066, (2,1,5,t) +0.025, (2,1,4,t) +3e-4.

## 2. Within-2 list matches JSON; docs call it a lower bound and claim nothing more: REFUTED in part

- Recomputed from the cells, it matches `selection.within_2_aic` exactly (7 entries, deltas
  0/0.119/0.372/0.607/0.742/1.662/1.864). Payload and docs agree. The 26 / 41.27 / 16 counts in concept
  note 07 also reproduce.
- "Lower bound" appears in concept note 07:242, ADR-0002:442 and the walkthrough:614. The README:7
  and walkthrough:44 and :314 state "six" / "Seven models are within 2" with no qualifier.
- Refuted statement: concept note 07:109-111 says (3,1,4,t) is "just outside", at ΔAIC 2.000000000004, being
  the chosen model "with a third AR coefficient of about zero". In fact it is a separate optimum at ΔAIC −0.037,
  with ar.L3 = −0.40. Against the true best, the near ties found are (2,1,4,t) +0.036, (4,1,3,t) +0.128,
  (4,1,2,t) +0.400, (2,1,5,t) +0.593, (3,1,5,t) +0.629, (5,1,2,t) +1.566, (5,1,3,t) +1.859 and
  (4,1,4,t) +1.994: eight others, not six.

## 3. Nesting guard refuses > 2e-3 and accepts 1e-3 in both readers: SURVIVES at the shipped setting; the bound is file-controlled

- c3/make.py edits (3,1,4,t), which nests (2,1,4,t), with llf, aic, aicc, bic and delta_aic kept consistent.
  Python (`validate_envelope` + `PAYLOAD_VALIDATORS['aic_grid']`) and TS (`parseAicGrid` bundled with esbuild
  and run under node 22) gave the same results:
  gap 3e-3 refused, gap 2.5e-3 refused (1 nesting error each), gap 1.9e-3 accepted, gap 1e-3 accepted.
- Hole: the tolerance comes from the file being checked (`fit_settings.nesting_tolerance`; payloads.py:974,
  contract.order.ts:859). The only rule is that it must be > 0. A 21.83 drop with `nesting_tolerance: 100`
  (or 1e300) is accepted by both readers. No test pins 2e-3: grep finds NESTING_TOLERANCE only in
  test_selection.py:242 and :252, which are selection-side. The corpus covers only 0 and missing.

## 4. 66.5% from 2020 onwards, 75.3% from 2020-02-15 to 2020-05-31 (72 days): SURVIVES at the grid's point; the third digit is not robust

- At the grid's exact (2,1,4,t) point (`selection.refit_cell`) and (0,1,1,t) point, `filter().llf_obs`:
  gain 25.636, 2020+ 66.50%, window 75.26%, 72 days (3.53% of 2037). Reproduces.
- Independent fit (c4.py, `loglikeobs`): (2,1,4,t) at llf 5228.1045 (+3e-4) gives 67.05% / 75.70%.
  Near-top optima within 0.002 llf span 66.4-67.1% and 75.2-75.7%. The flat ridge moves the third digit.
- If the selection is the true optimum (3,1,4,t): gain 26.654, 64.2% from 2020 and 77.2% from the window.

## 5. test_repo_data.py fails on a renamed or gzipped raw table: REFUTED (gzip part)

- Scratch clone at clone/ with the working tree rsynced in. Baseline `32 passed`. Script: c5.sh. Each case
  was reverted after its run, and the clone's status was 108 lines afterwards as before.
- Caught (1 failed): raw CSV as app/public/data/x.txt, untracked and staged. Gzip named prices.csv.gz, staged.
- Not caught (32 passed), all staged: gzip as app/public/data/x.txt.gz, gzip as app/public/data/x.gz,
  xz as notebooks/p.csv.xz, a headerless CSV, a tab-separated file, a comment line before the header, Date
  renamed to Timestamp, and UTF-16.
- The causes are the name rule (`RAW_SUFFIXES = (".db", ".csv.gz", ".parquet")`, tests/test_repo_data.py:31)
  and the first-line, comma-only header sniff (:107-110).

## 6. The app no longer computes the outside flag itself: SURVIVES (one wording nit)

- The draw path uses Python's flags: correlogram.ts:30 reads `row.acf_outside` / `row.pacf_outside`,
  CorrelogramPlot.tsx:93 uses `b.outside`, and StationarityView.tsx:249-250 uses `*_outside_count`.
- The only |value| > band comparison in the app is the reader's check of Python's flag
  (contract.order.ts:477-479), which is the design.
- acf_pacf.json: every flag and count equals |value| > band for lags >= 1 on all 3 series (log 50/1,
  diff1 11/7, diff2 15/20).
- Nit: identification.py:18-19 says the app "never compares a value with its band itself". The reader
  does compare, to check the flag.

## 7. Reproducible, byte-identical aic_grid.json: SURVIVES

- I did not run --check, because it compares only schema_version/artifact/data and cannot show byte identity.
  Instead I ran ONE export to scratch with SOURCE_DATE_EPOCH=1793298513 (the committed 2026-10-29T18:28:33Z):
  `uv run python tools/export_app_data.py --out export_out`, exit 0, wall time 4:57.38 (/usr/bin/time).
  This ran alongside my 12-process attack on 20 cores, so it is not comparable to the summary's 3:15.
- `cmp`: all 6 files byte-identical to app/public/data, including aic_grid.json (sha256 94feb1250d22...).
  `compare_exports(app/public/data, <scratch envelopes>)` returned [], which is what --check would print as
  current.
