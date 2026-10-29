> Point-in-time record of the milestone-2 adversarial review (code), copied unchanged except that
> absolute home paths are redacted to `<repo>`, `<scratch>` or `~`. Its `file:line` references point at the
> tree as reviewed, before the fix round; [`m2-summary.md`](m2-summary.md) says what changed.

# Milestone 2 adversarial ledger (working tree on 16366d1), 2026-10-29

Mode: single-context sequential fallback (EGV Mode 2). Channel A = source/doc reading (repo source, installed
statsmodels 0.15.0 source). Channel B = runtime probes. "Dual-confirmed (fallback mode)" where both agree.
Env pin: `env-pin.txt` (Python 3.12.13, statsmodels 0.15.0, numpy 2.5.4, node 22.23.1, vite 7.3.7, vitest 4.1.11).
Real repo untouched: `git status --short` = 100 lines before and after, 0 staged.

Scratch: `clone/` = 16366d1 + working tree overlaid (`git ls-files -co --exclude-standard`), no `data/`.
`full/arima-stock-forecasting/` = same, run with `VOL_DATA_DIR=<repo>/data`.

| ID | Claim | A (source) | B (probe) | Gate |
|---|---|---|---|---|
| 1a | prices/eda not ignored; raw + cache ignored | `.gitignore:4,17-19` | `git check-ignore --no-index`: all 6 files under data/ ignored by `/data/`; all 6 app JSON not ignored | ACCEPTED |
| 1b | test_repo_data fails on a tracked raw vendor file | name-only rules, `tests/test_repo_data.py:44-52` | clone: force-added `data/.../raw/*.csv` -> 1 failed. **Byte-identical raw CSV as `app/public/data/aapl_daily.csv` (untracked and staged) -> 16 passed. `AAPL_1d_...csv.gz` force-added -> 16 passed. `notebooks/raw_prices.csv` -> 16 passed** | **REJECTED** |
| 1c | test fails on a file >10 MB under app/public/data | `oversized()` stats the working tree, `tests/test_repo_data.py:57-58` | 10,000,001-byte untracked file -> 1 failed. **Staged 10,000,001-byte blob (`git cat-file -s` = 10000001), working copy truncated -> 16 passed** | **REJECTED** (index not checked) |
| 1d | DATA.md sentence + Yahoo terms line | `DATA.md:11,14` | grep -F both strings: found | ACCEPTED |
| 1e | No doc says price files on hold / never committed | historical docs annotated (01-data-and-eda, 00-scaffold:1502-1506) | grep sweep: docs/*.md clean. Residual stale code text: `app/src/data/useOrderData.ts:4` ("hold no vendor values", contradicts DATA.md:15), `docs/architecture/contract.md:230` ("never the series (owner decision)"), `app/src/App.test.tsx:99` test name "in a fresh clone (held files absent)", dead-path UI copy `PriceExplorerView.tsx:60-67` | ACCEPTED for docs; minor stale strings |
| 1f | held_artifacts stays, empty, right semver | removing a field = major; old parseMeta (16366d1 contract.ts:288-300) accepts `[]` | meta.json `held_artifacts: []`; both suites green | ACCEPTED |
| 2a | 1.2.0 is the right bump | diff: only additive (3 new artifacts); existing validators unchanged; 1.1.0 parseMeta accepts any artifact names | old/new payload diff | ACCEPTED |
| 2b | Both readers agree on 218 corpus cases | corpus has 218 (61 aic_grid, 47 stationarity, 24 acf_pacf ...) | fresh clone: pytest 1079 passed, vitest 860 passed (both include the corpus) | ACCEPTED |
| 2c | Edge payloads as JSON text: zero disagreements, no exceptions | Python `json.loads` accepts NaN/Infinity tokens; JS `JSON.parse` does not | 76 edge cases (`probes/gen_cases.py`): 70 agree (incl. 6 constructed exact-tie cases, max-double AIC, 2**53+-1, 401-digit int, duplicate keys, -0, denormal). **6 diverge: every NaN/Infinity token -> TS SyntaxError. 2 are verdict disagreements: NaN under an unknown data key, -Infinity under an unknown cell key -> Python valid, app cannot parse** | **REJECTED** |
| 3 | --check covers the 3 files and fails on stale/malformed | `artifacts.py:115-153` validates committed file + compares data | full tree: rc=0, lists all 6, 59.2 s. Stale aic 1e-9 -> rc=1; malformed generated_at in stationarity -> rc=1; missing acf_pacf -> rc=1; acf alpha +1e-12 -> rc=1 | ACCEPTED |
| 4a | App draws Python's selection (tie-breaking A4/A5 is validation, not choice) | `aicLandscape.ts:62-65` isSelected reads `grid.selection`; `AicLandscapeView.tsx:78` uses `within_2_aic`; tie logic only in reader `contract.order.ts:464-467,828-830` | A4/A5 mutants fail only corpus reader tests | ACCEPTED |
| 4b | App computes no statistic | `correlogram.ts:29` `outside: Math.abs(value) > band`; `StationarityView.tsx:249-250` shows "Past the band: N of M ACF lags and K of L PACF lags" | not in acf_pacf.json (keys: acf, acf_band, lag, pacf, pacf_band) | **REJECTED** (significance count computed in browser) |
| 5 | 3D lazy, failures distinct, both themes, main 226.77 kB | scene markers by status `AicLandscapeScene.tsx:77-115`; colours via `useThemeColors` + MutationObserver `hooks.ts:47-55` | clone build: index 226.77 kB; index.html loads only index chunk; three chunk (1,081.29 kB, named `inter-latin-400-normal-*.js`) imported only by scene chunks. A9 mutant killed. Themes: not rendered in a WebGL browser (not run) | ACCEPTED for size/laziness/markers; theme UNVERIFIED at runtime |
| 6 | Counts | doc 02:436 names the skip | fresh clone (no data): `1079 passed, 1 skipped` (skip = test_config.py:224, checkout name), vitest `860 passed`, 0 skipped. Full tree: `1080 passed`, notebooks in sync rc=0, --check rc=0 | ACCEPTED (note: the 1 skip is the dir name, not data; no pytest test reads the real snapshot) |
| 7 | Mutations reproduce; P15 equivalent | P15 proof: k = p+q+tau+1, tau in {0,1} | P2 8 failed (claimed 8), P11 2 (2), P14 1 (1), P15 0 (0). A4 1 (1), A5 **2 (claimed 3)**, A11 1 (1), A9 1 (1). Brute force: 0 order disagreements over all pairs with tau in {0,1}; 280 if a two-term trend existed | ACCEPTED (A5 count differs) |
| 8 | file:line refs match | `probes/check_refs.py` | 66 refs: 65 resolve in repo, each lands on the named function/line; 1 external (`statsmodels/graphics/tsaplots.py:146`) verified in installed 0.15.0 (`ax.fill_between(... confint[:, 1] - acf_x ...)`) | ACCEPTED |
| 9 | 1 BLAS thread == default | `export_app_data.py:26` setdefault | 5 cells (incl. selected 3,1,5 t): sha256 of results identical at OPENBLAS 1, default (20), 16; aic -10439.169862236184 = committed | ACCEPTED (5 cells, not full grid) |
| 10 | No raw file tracked/staged; all app data < 10 MB | - | real repo: 0 staged, no committable path matches raw/cache/db/csv rules; largest committable file 4,049,379 B (graph.svg), largest data file eda.json 529,907 B; sampled raw Close values not found in any committable file | ACCEPTED |

## Unclaimed defects
- All six committed JSON say `source_commit: 2a52d8d...-dirty`; no test refuses a `-dirty` stamp in committed files. Must re-export after the code commit.
- `LICENSE` (MIT) has no data carve-out; only DATA.md/README say the data is excluded.
- Both readers accept `acf_pacf.z = 1.96` (not tied to alpha 0.05).
- A failed cell's cross sits at y = 0, the height of the best (lowest-AIC) cell; no real cell has failed, so it only appears in tests.
- DATA.md:9 Sources table repeats "Yahoo Finance via yfinance" in both columns.
- `.gitignore` second layer does not match `raw-before-refresh/` (present under data/; covered only by `/data/`).
