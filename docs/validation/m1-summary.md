# Milestone 1 validation summary

Two independent adversarial reviews checked milestone 1 after it was built. Each was a separate
Claude subagent that did not write the work it checked. The orchestrator reproduced a sample of
their refutations before the fix round, and the builder reproduced each item again before fixing
it.

| Pass | Record | Outcome |
|---|---|---|
| Adversarial review: code, contract, data hygiene, with evidence-gated validation (Mode 1 hybrid) | [`m1-code-review-ledger.md`](m1-code-review-ledger.md) | 14 claims: 7 refuted, most of them in part or narrowly (1, 2, 4, 7, 8, 13, 14), 7 survived (3, 5, 6, 9, 10, 11, 12); 8 further defects no claim covered |
| Adversarial review: statistics, library behaviour and docs (Mode 2, single context) | [`m1-stats-review-ledger.md`](m1-stats-review-ledger.md) | 11 claims: 5 refuted (5, 7 minor, 8, 9, 11), 5 survived (1-4, 10), and claim 6 split (6a and 6b survived, 6c unresolved); 6 refuted statements (R1-R6), 8 oversimplifications (O1-O8), 5 further defects (D1-D5) |
| Re-review of the fixed tree (Mode 2, single context) | [`m1-rereview-ledger.md`](m1-rereview-ledger.md) | 17 checks: 13 survived, 4 refuted in part; all four fixed in a second round |
| Owner gate (a decision from the hub, not a review) | ADR-0001, "Open question for the learner" | `prices.json` and `eda.json` moved from "committed by default" to "on hold" |

The ledgers are point-in-time records. Their `file:line` references point at the tree as it was
reviewed, before the fixes. Absolute home paths in them are redacted to `<repo>`, `<scratch>` or
`~`.

## What was refuted, and what changed

| # | Finding (ledger) | Reproduced? | Resolution |
|---|---|---|---|
| 1 | A raw snapshot can be staged when `VOL_DATA_DIR` points elsewhere in the repo (code 1) | Yes, by reading `config.data_root` and the ignore rules | `data_root` refuses any folder inside the repo other than `<repo>/data`; `.gitignore` ignores `**/arima-stock-forecasting/raw/` and `cache/` at any depth. `*.csv` stays allowed for `reports/`. |
| 2 | 17 of yfinance's 19 `download` parameters were passed (code 2) | Yes: `inspect.signature` | `period` and `session` passed as `None` (what yfinance's sentinels resolve to when `start` and `end` are given); a test pins the key set to the signature. |
| 3 | A truncated manifest crashes; an edited manifest `request` is reused (code 3) | Yes | `read_snapshot` turns bad JSON and missing keys into `SnapshotError` (exit 2), and refuses a manifest whose `request` differs from `DOWNLOAD_REQUEST`. The real snapshot was refused for that reason and downloaded again (see "Data"). |
| 4 | Long runs of missing closes, and a missing tail, are filled into flat lines (code 4, stats R1) | Yes, with a 25-NaN run and a 15-NaN tail | `clean_close` refuses a filled row more than 7 calendar days after the last real close. Concept note 02 now describes the real guard. |
| 5 | `--check` passes a committed envelope the app would refuse (code 6) | Yes | `compare_exports` validates each committed envelope and payload too. |
| 6 | The Python and TypeScript payload readers disagree on 12 of 34 edge payloads; Python raises `OverflowError` on `1e400` (code 7, 8) | Yes, on the corpus built for the fix | A shared corpus, `app/src/test/fixtures/payload_cases.json` (62 cases), run by both suites. Integral floats count as integers, integers beyond ±(2^53 − 1) and numbers too big for a double are refused, "blank" is one explicit class, the exact 126-row null pattern and `log_return.n = summary.n − 1` are enforced on both sides. |
| 7 | The TypeScript integer minimum is untested; mutant OA4 survived (code 10) | Yes | Corpus and unit cases for each minimum; OA4 (B1 below) is killed. |
| 8 | Provenance has no fixed point: a re-export at the JSON commit rewrites `source_commit` (code 12) | Yes, with a new end-to-end test that failed on the old code | `source_commit` is the last commit that touched anything outside `app/public/data`; `test_the_json_commit_reexports_byte_identically` passes. |
| 9 | Off-by-one `file:line` references; "17 keys" (code 13) | Yes | All references re-verified by script on the final tree. |
| 10 | The deletions removed the owner gate (code 14) | Yes | The gate is restored in ADR-0001 and the PR/FAQ, with both files on hold. |
| 11 | "The three largest training moves all fell in March 2020" (stats R2) | Yes: 2019-01-03 is third | "Two of the three largest, and three of the four beyond ±0.1". |
| 12 | The 3.03% trend gap "grows with volatility" (stats 5, R3) | Yes, re-measured: a zero-volatility straight line gives 2.80% | Rewritten: the gap is about half the weighted variance of ln P inside one window, which in 2020 was mostly drift. |
| 13 | "The tails are smeared" (stats R4) | Yes: an isolated bump per extreme day | Rewritten: one bandwidth over-smooths the peak and under-smooths the sparse tails. |
| 14 | The notebook test does not pin the tail share or the comparison numbers; a vacuous `>= 0.0` assertion; 4 surviving mutants (stats R5, D3) | Yes | Hand-worked tests of `course_comparison` (a level plus a pure seasonal pattern, with the trend, factors, gaps and dollar ratios worked out by hand) and of `tail_share` (a sample that separates `ddof=1` from `ddof=0` and k from 0.8k); the notebook test checks every printed comparison and tail line. |
| 15 | The split is in course module 7, not 2-4 (stats R6) | Yes, from the course text read with stdlib `zipfile` | Walkthrough and notebook say "modules 2-4, plus module 7's split". |
| 16 | Oversimplifications O1-O8 (stats) | Yes | Scott's rule is 0.944 times the normal-reference (`'silverman'`) bandwidth; the trend's end weights are halves; "seven or eight years"; the dividend-adjusted return is approximate; the `back_adjust` naming clash is explained; background §10 item 3 (2023-12-31 was a Sunday); the 0.73% seasonal gap is stated; ARCH-LM tests clustering, not kurtosis. |
| 17 | Defects D1, D2, D4, D5 (stats) | Yes | Later dividends scale the training levels (stated, size not measured); 4.3e-5 of the log-close KDE's mass falls outside the grid (measured); KDE peaks are grid maxima; the gzip command is named. Claim 6c ("Close is only split-adjusted" when `auto_adjust` is off; "each dividend restates history") is marked "not verified here", with the indirect source. |

**Rejected or narrowed:** none of the review's refutations was rejected. One was narrowed in the
fix: the code review's probe of "four trading days absent, a 7-day gap" was accepted by the
coverage check, and still is, because 7 days is the stated limit (`MAX_GAP_DAYS`), and one missing
day inside a normal week remains a documented, unguarded limit.

## The owner gate

`prices.json` and `eda.json` are git-ignored since 2026-10-29. `eda.json` is held because its
decomposition rows carry `observed_log`, and `trend + seasonal + resid` adds back up to it. The
committed `meta.json` lists all three artifacts and names the two held ones in a new 1.1.0 field,
`held_artifacts`. On a fresh clone the app offers the price explorer and says its data is not built
in this copy; the pytest and vitest tests that need a held file skip with that message; a listed
file that is missing and not held still fails.

## Data

The request change (finding 2) made `read_snapshot` refuse the first snapshot (12:07:20 UTC). It
was downloaded again at 13:37:24 UTC (both SHA-256s are in the local `data/` manifests, not in this
repository). The two
same-day downloads were not byte-identical: same dates and volumes, but the prices differed on
2,125 of 2,953 rows by at most 7.3 × 10⁻⁷ of the price. Every number in the milestone-1 docs was
re-measured on the second snapshot; most did not move in their printed digits.

## Mutants of the new guards

One mutant per new guard, each on a scratch copy (Python: the full suite minus the diagram and
Blender tests, unchanged copy `698 passed`; app: `npx vitest run`, unchanged copy
`Tests 629 passed (629)`). All 13 Python mutants (Q1-Q13) and all 7 app mutants (B1-B7) were
killed. B1 is the review's surviving OA4. The stats review's four survivors (MA-MD: two in
`course_comparison`, two in `tail_share`) were re-run on the final tree and are killed by the new
hand-worked tests in `tests/test_eda.py`. The walkthrough lists each mutant and the tests that
killed it ([Mutation testing](../milestones/01-data-and-eda.md#mutation-testing)).

## The re-review, and the second fix round

A third pass re-reviewed the fixed tree ([`m1-rereview-ledger.md`](m1-rereview-ledger.md)): 17 checks,
13 survived, 4 refuted in part (1c, 5, 6, 7c). All four were reproduced and fixed:

| Finding | Fix |
|---|---|
| `VOL_DATA_DIR` set to the repo's parent put raw data in `<repo>/raw`, where git could stage it (claim 5) | `data_root` checks `realpath(<root>/arima-stock-forecasting)`: refused if it is the repo or inside it anywhere but `<repo>/data`. `.gitignore` adds `/raw/` and `/cache/`. Mutant R1 (the old check) fails the new parent-of-repo and symlink tests. |
| Python did not validate `meta`: `held_artifacts` of `5`, `["nope"]`, `[1]` passed `read_artifact` (claim 1c) | `validate_meta` mirrors `parseMeta` and is registered; held names must be listed, unique and not `meta`, on both sides; 24 meta cases joined the shared corpus (86 cases). Mutants R2, R3, C1, C2 are killed. Stale wording fixed in `app/README.md` and ADR-0001. |
| A manifest whose `request` is `null`, `"1d"` or `[]` crashed with a traceback (claim 6) | `read_snapshot` checks the types of `request`, `rows` and `sha256` and raises `SnapshotError` (exit 2). Mutant R4 fails 9 tests. |
| The milestone-0 walkthrough still described the `rev-parse HEAD` rule (claim 7c) | A note in its provenance section points to the milestone-1 rule. |

**No real vendor values in a commit (hub rule).** `tools/licensing/scan_real_rows.py` compares
every committable text file with the local raw snapshots. It first flagged 9 price lines and 4
provenance lines (a raw file size, the snapshot hash) in two tests, concept note 02, the walkthrough
and this folder's stats ledger. Tests now use made-up values; the docs use derived statistics or
"see your local `data/` manifest"; the ledgers mark redacted prices and hashes. Final output:
`clean: 0 price lines flagged in 195 text file(s) against 2 raw snapshot(s)`, with no provenance
note.

## Gates at the end of the second fix round

Run on 2026-10-29 on two trees: the working tree (snapshot and held files built locally) and a
fresh `git clone` with the working tree copied over it minus every ignored file.

- `uv run pytest -q`: full tree `839 passed`; fresh clone `829 passed, 10 skipped` (9 name a held
  file and the two build commands; 1 is the parent-of-repo test, skipped because the clone's folder
  has another name).
- `uv run python tools/build_notebooks.py --check`: `notebooks are in sync` on both.
- `cd app && npm run verify`: lint clean on both; full tree `Tests 658 passed (658)` in 30 files;
  fresh clone `Tests 656 passed | 2 skipped (658)`. Coverage of `src/lib/**`: 97.23% statements,
  93.52% branches, 99.02% functions, 99.36% lines. Main chunk 225.63 kB (milestone 0: 224.51 kB).
- `uv run python tools/export_app_data.py --check`: full tree `app data is current: meta, prices,
  eda` (exit 0); fresh clone, no snapshot: exit 2 with the "no complete snapshot" message.
- `tools/licensing/scan_real_rows.py`: `clean: 0 price lines flagged …` (exit 0).
- The diagram specs did not change in either fix round; the mermaid render gate passed before them.
