# Milestone 0 code review ledger (adversarial)

Date: 2026-10-28. Reviewer stance: every claim starts REJECTED; it SURVIVES only if a probe
built to break it failed to.

- **Mode:** single-context sequential fallback (one reviewer plays both channels). Probes were
  written into a pre-registered ledger before any docs were fetched. Where both channels agree,
  this ledger says "dual-confirmed (fallback mode)", not "independently proven".
- **Tiers:** Tier 2 (Channel A: primary docs, source or registry; Channel B: runtime probe) for
  C2 (date numerics), C6 (supply chain), C7 (bundle), C11c (yfinance shape) and C12 (Blender
  camera). Tier 1 (runtime only, with a falsifier) for everything else.
- **Environment:** Python 3.12.13 (repo `.venv`), uv 0.11.25, node 22.23.1, npm 10.9.8, git
  2.43.0, aarch64 Linux. Blender: no binary on this machine, and the Blender MCP bridge reported
  "Could not connect to Blender".
- **Where the experiments ran:** every mutation and git experiment ran on scratch copies. The
  real repo was not changed. The only file this review writes in the repo is this one.

---

## C1. `contract.py` enforces contract.md §1, and NaN/±Inf cannot reach a file through the exporter

**Channel B.**

- `validate_envelope` was run on 82 envelopes (see C2). It rejected every input that breaks a
  §1 rule: wrong key set, non-semver, major ≠ 1, a bad artifact name, a non-UTC or impossible
  timestamp (including the leap second `:60`), a bad commit, and `data` that is not an object.
- NaN probe. `tools/export_app_data.py:main` was run with `meta_payload` monkeypatched, writing
  to a temp `--out`:

  | Payload | Result | File written |
  |---|---|---|
  | `nan` | `ValueError: Out of range float values are not JSON compliant` | no |
  | `inf` nested in a list | same `ValueError` | no |
  | `-inf` nested in a dict | same `ValueError` | no |
  | `np.float64('nan')` | same `ValueError` | no |
  | `nan` as a dict key | same `ValueError` | no |
  | `inf` as a dict key | same `ValueError` | no |
  | tuple containing `nan` | same `ValueError` | no |
  | `np.float32('nan')` | `TypeError` | no |
  | `np.array([nan])` | `TypeError` | no |

  Falsifier: `allow_nan=True` is already in the M0 mutation table, and it kills 4 tests.
- Caveats found:
  - `make_envelope` raises `OverflowError`, not the `ValueError` its docstring promises, for an
    aware datetime near `datetime.min` or `datetime.max`. Example: `datetime(1,1,1,0,30,tzinfo=+01:00)`.
  - Nothing cross-checks `artifact == file stem`. The exporter writes the literal `"meta"` twice,
    at `tools/export_app_data.py:37` and `:58`.

**Verdict: SURVIVES.** The literal tokens `NaN` and `Infinity` cannot be written.

---

## C2. The TS parser and the Python validator accept exactly the same envelopes

**Channel B.** One corpus of 82 envelopes was run through
`uv run python … validate_envelope` and `node --experimental-strip-types … parseEnvelope`. The
scripts are in `scratchpad/review-code/c2/`. Result: **14 divergences out of 82.**

| Input | Python | TS |
|---|---|---|
| `generated_at` `0001-01-01T00:00:00Z`, `0050-06-15…`, `0099-12-31T23:59:59Z` | accept | **reject** |
| `artifact` `Meta`, `META`, `1meta`, `_meta`, `meta-2`, `"meta\n"`, `" meta"`, `méta` | reject | **accept** |
| an extra top-level key (`extra`, `__proto__`, `constructor`) | reject | **accept** |
| `2026-02-30…`, `:60`, `24:00`, uppercase hex, short sha, `-DIRTY`, `1.0`, `01.0.0`, `1.0.0-rc.1`, `1.0.0+build`, `data` = `[]` or `null` or a string or a number | reject | reject (agree) |

**Channel A.**

- ECMA-262, MakeFullYear (tc39.es, fetched 2026-10-28): "interpreting any value in the
  inclusive interval from 0 to 99 as a count of years since the start of 1900". So `Date.UTC(1,0,1)`
  is the year 1901, and the year check at `app/src/lib/contract.ts:69` fails.
- Python 3.12 docs: "MINYEAR is 1". So Python accepts years 1 to 99.
- contract.md §1 lists the artifact pattern and says unknown keys are tolerated only "inside
  `data`" (contract.md:40-43). `parseEnvelope` checks only that `artifact` is non-empty
  (`contract.ts:122`), and it ignores unknown top-level keys.

**Mitigation in the app.** `loadArtifact.ts:19,40` re-checks the name pattern and equality with
the requested name, so the artifact rows are masked end to end. The extra-key rows and the
year 1–99 rows are not masked.

**Verdict: REFUTED (dual-confirmed, fallback mode).**

**Fix:** in `parseEnvelope`, reject unknown envelope keys and apply `/^[a-z][a-z0-9_]*$/`. In
`isCalendarDay`, use `Date.UTC` plus `setUTCFullYear(y)`, or check `y >= 1` in Python's
direction. Add the 14 rows above as a shared fixture for both test suites.

---

## C3. `source_commit` reports `-dirty` for any uncommitted change, never raises, and says `uncommitted` only with no commit

**Channel B.** Temp repos, using `GIT_CONFIG_GLOBAL=/dev/null`. Script:
`scratchpad/review-code/c3/probe_prov.py`.

| Case | Result |
|---|---|
| modified, staged-only, untracked, untracked with `status.showUntrackedFiles=no`, deleted, subdir path, detached HEAD (clean and dirty), git not on PATH, nonexistent path, path is a file | PASS |
| `core.quotePath=false` and an untracked file named `b"\xff.txt"` | **RAISED** `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff` (`text=True` at `provenance.py:31`) |
| a non-executable `git` first on PATH | **RAISED** `PermissionError` (only `FileNotFoundError` is caught, at `provenance.py:45`) |
| `update-index --assume-unchanged` or `--skip-worktree`, then modify | bare sha (**not dirty**) |
| a new `.py` file hidden by `.git/info/exclude` | bare sha (**not dirty**) |
| an `--object-format=sha256` repo | a 64-hex string, which `make_envelope` then rejects with `ValueError`, so the export aborts |
| an orphan branch in a repo that has commits | `uncommitted` |

**Verdict: REFUTED.** It raises in two reachable configurations, and it misses changes that git
status hides.

**Fix:** run `git -c core.quotepath=on status --porcelain=v1 -z`, decode with
`errors="surrogateescape"` (or read bytes), catch `OSError`, and accept a 64-hex sha in the
contract or map it.

---

## C4. With `SOURCE_DATE_EPOCH` set, two exporter runs give byte-identical `meta.json`

**Channel B.**

- With `--out` outside the tree, running under `TZ=UTC LANG=C.UTF-8 PYTHONHASHSEED=1` and again
  under `TZ=Asia/Kolkata LANG=de_DE.ISO-8859-1 PYTHONHASHSEED=999`, `cmp` reported identical
  files (sha256 prefix `c95c4c2b98a07116`).
- With the default `--out` (the tracked `app/public/data`) in a committed scratch repo:

  ```
  61c61
  <   "source_commit": "7a8ebded61bfa061d2796be3bb8cf6db16e02457"
  >   "source_commit": "7a8ebded61bfa061d2796be3bb8cf6db16e02457-dirty"
  ```

  Run 1 rewrites a tracked file, so run 2 sees a dirty tree. The milestone doc admits this (Q3),
  but the claim as stated has no qualifier. Today it holds only because the repo has no commit
  yet.

**Verdict: REFUTED for the default invocation once a commit exists.** It SURVIVES for an
out-of-tree `--out`.

**Fix:** state the qualifier, or exclude the output path from the dirty check
(`git status --porcelain -- . ':!app/public/data'`).

---

## C5. `build_notebooks.py` is deterministic; `test_notebooks.py` fails on a stale or missing notebook; the kernel is isolated

**Channel B.**

- Determinism. Built twice with `PYTHONHASHSEED` 1 vs 777, `TZ` UTC vs Pacific/Chatham, and
  `LANG=C`. Both builds were byte-identical, and identical to the committed notebook.
- Stale notebook (one byte appended, scratch copy): `2 failed, 6 passed`, no skips. Missing
  notebook: `5 failed, 3 passed`, no skips.
- Isolation. The kernelspec does pin `sys.executable`: the probe kernel reported
  `<repo>/.venv/bin/python` (absolute home path redacted before the first public commit). But the kernel still loads the
  user's IPython profile. With `IPYTHONDIR` pointing at a startup file that puts a decoy source
  tree first on `sys.path`, `test_notebook_runs_without_errors` and
  `test_project_tour_prints_the_values_it_explains` printed `2 passed`, while the kernel imported
  `…/c5/fake/src/arima_forecasting/__init__.py` with `TICKER = DECOY`.

**Verdict: SURVIVES as worded,** because the interpreter is fixed. The broader "isolated" goal
leaks (finding F3).

---

## C6. Pins and supply chain

**Channel B.**

- All 12 direct Python deps are `==` and equal `uv.lock`. All 23 app deps are exact. `npm audit
  --omit=dev` printed `found 0 vulnerabilities`. `npm ci --dry-run` exited 0.
- Lockfile: 371 unique name@version entries, all resolved from `registry.npmjs.org`, all with an
  `integrity` value.

**Channel A.** `npm view <pkg>@<v> time[<v>]` was run for all 371. The newest is `vite@7.3.7` at
2026-10-06T05:11Z, so 0 entries are newer than 2026-10-14. Falsifier: `vitest@4.1.12`
(2026-10-15T14:51Z) would have been flagged.

**Gap:** `[build-system] requires = ["uv_build>=0.11.25,<0.12"]` is a range, and it is not in
`uv.lock`.

**Verdict: SURVIVES** (dual-confirmed, fallback mode), with that minor gap. See F1 for the
Python age problem.

---

## C7. three.js, fiber and drei sit in a lazy chunk; the built app makes no off-origin requests

**Channel B.**

- Clean `vite build` to scratch. It produced the same hashes as the committed `dist`.
- Marker counts:

  | Marker | `index` chunk | `AicAxesScene` chunk |
  |---|---|---|
  | `WebGLRenderer` | 0 | 39 |
  | `troika` | 0 | 35 |
  | `__THREE__` | 0 | 2 |

- The only `import(` in the index chunk is `./AicAxesScene-CBjjtPUx.js`.
- Served on 127.0.0.1 and watched in the server log: `#/about` requested no scene chunk.
  `#/architecture` requested the scene chunk, then the woff from the same origin. All requests
  were same-origin.

**Channel A.** The scene chunk contains
`https://cdn.jsdelivr.net/gh/lojjic/unicode-font-resolver@v1.0.1/packages/data`. troika 0.52.5
(`FontResolver.js:159-218`) fetches from it for any character the supplied font lacks. fontTools
shows the Inter-latin woff covers every current label character, but not `φ θ Δ σ ≤`.

**Verdict: SURVIVES for today's labels.** The comment at `AicAxesScene.tsx:8`, "never fetch a
font from a third-party CDN", is false for any future Greek or math label (F4).

---

## C8. Hygiene of the public tree

- **Secrets:** none found. 104 to-be-committed files were scanned for AKIA, ghp_, sk-, private
  keys, and `token=` patterns. PNGs have no tEXt or iTXt chunks.
- **Email:** the only addresses are `t@example.com` and `test@example.com`. `git config --local
  user.email` is `20094874+rajib2k5@users.noreply.github.com`.
- **Outline copying:** 8-word shingles against `sample.txt` gave one shared shingle, the course
  title, which appears as attribution (`README.md:70`, `AboutView.tsx:10`). 12-word shingles: 0.
  6-grams in code: only that title.
- **Private or suite references: REFUTED.** `docs/architecture/README.md:25,29` makes
  `vol-diagram-kit` the required rebuild tool. That repo has no git remote, and
  `api.github.com/repos/rajib2k5/vol-diagram-kit` returns 404. The "vol" project suite is also
  named in `config.py:18-21`, ADR-0001:116-117 and `README.md:45` (`$VOL_DATA_DIR`,
  `~/data/vol-projects`).

**Fix:** vendor the kit or publish it, and rename the variable and default to project-neutral
names.

---

## C9. Tests are mutation-checked

**Channel B.** New mutants (not in the M0 table) were run on a scratch copy against the full
pytest suite (excluding `test_gitignore`) or the full vitest suite. Every file was restored and
the sha256 verified.

| ID | Mutant | Result |
|---|---|---|
| S1 | `contract.py:116` `!=` → `>` (accept major 0) | KILLED (2) |
| S2 | `contract.py:72` drop `or generated_at.utcoffset() is None` | **SURVIVED** (300 passed) |
| S3 | `contract.py:50-54` drop the strptime check | KILLED (3) |
| S4 (extra) | accept `UNCOMMITTED` | KILLED (1) |
| A1 | `contract.ts:82` `sec <= 60` | KILLED (1) |
| A2 | `contract.ts:69` drop the year equality | **SURVIVED** (266 passed) |
| A3 | `contract.ts:232` `a.trim() === ''` → `a === ''` | **SURVIVED** (266 passed) |
| A4 (extra) | `contract.ts:160` `>=` → `>` | KILLED (1) |

S5, `except FileNotFoundError` → `except OSError`, survived as expected: it is the fix, not a
defect.

**Verdict: REFUTED.** 3 of the 6 required mutants survive. A2 is the line that causes the C2 year
divergence, and no test pins its behaviour.

---

## C10. Every `file:line` reference and quoted excerpt in the two docs is accurate

**Channel B.**

- Script `c10/refs.py`: 166 refs resolved, 166 in range. Script `c10/blocks.py` and `after.py`:
  20 excerpts are byte-exact substrings of their files.
- Hand-checked: 21 sampled refs, plus all short-form refs at 00-scaffold.md:169-170, 392-396,
  406-409, 436-439 and 489-491, and concepts:19 and 94.
- **Defect 1.** `docs/milestones/00-scaffold.md:365` says "(lines 52-57)". The excerpt is at
  `tools/export_app_data.py:54-59`.
- **Defect 2.** `00-scaffold.md:482` cites `contract.md:40-43` for "the app's reader ignores
  [unexpected envelope keys]". contract.md:40-43 says the reader ignores unknown keys **inside
  `data`**.

**Verdict: REFUTED (2 defects).**

**Fix:** change the annotation to 54-59, and either fix the parser (C2) or document top-level
tolerance in contract.md.

---

## C11. Diagram specs validate, the committed `.mmd` files are kit output, and the diagrams are true

**Channel B.**

- The kit's validator accepts all 5 specs. Falsifier: adding `colour: red` produced
  "unknown key".
- A rebuild with the kit at HEAD `56aad83` ("Fix review defects: Mermaid escaping…", committed
  2026-10-28 09:12 -0500, during this review) **differs in 4 of 5 files**: architecture 30 lines,
  data_flow 26, process 20, contract_sequence 2. Only `erd.mmd` matches. The differences are only
  edge-label quoting and `:` → `#58;`.
- A rebuild with the kit at `34d1966` is identical in all 5 files. The README copies of the
  Mermaid blocks equal the committed `.mmd` files.

**Truth checks.**

- The yfinance columns (Date index, then Close, High, Low, Open, Volume as int64, MultiIndex
  `(Price, Ticker)`, no Adj Close) match the source. See `multi.py:213-224`, `utils.py:506-523`
  and `history.py:595-611`. This is Channel A only: a faked-HTTP runtime probe was not run, so
  this point is UNVERIFIABLE on Channel B.
- `erd.yaml` entity `meta` lists `course_start` and `oos_end_exclusive`. Neither field exists:
  the payload is `windows.course.{start,end_exclusive}` and `windows.oos.{…}`. The ERD omits
  `artifacts[]`, and `meta_milestone` omits `title`.

**Verdict: REFUTED.** The committed files are stale against the current kit, and the ERD
misnames the only implemented artifact's fields.

**Fix:** regenerate with kit 56aad83, and make the meta entity mirror `meta_payload`.

---

## C12. The camera framing in `layout.py` is correct for Blender

**Channel A.**

- Blender 5.2 LTS manual: "Auto: Calculates a square sensor size based on the larger of the
  Resolution dimensions."
- Blender source, `camera.cc:328-346,508-510` (main branch): AUTO maps to HOR when width ≥ height,
  and the sensor spans that side.
- `rna_camera.cc:47-59`: `angle` is computed against `sensor_x` in AUTO.
- So the angle applies to the longer side.

**Channel B.** This is a Blender-convention pinhole model (Euler XYZ, camera looking down local
−Z), with `aim_euler` and `camera_for` taken from the repo. Real Blender was unavailable.

- As shipped (1600×1000, FOV 35°, margin 1.1): worst |ndc| = 0.700 at 1600×1000, 0.857 at
  1000×1600, 0.665 at 4000×1000. Aim error 8.5e-7°.
- Falsifier: passing the wide angle with margin 1.0 gave 1.32, which is out of frame.
- 2000 random directions at margin exactly `1/cos(narrow/2)`: worst 0.9999, so the stated bound
  is tight. Labels protrude 0.005 units past the box, well inside the margin.

**Verdict: SURVIVES** (Channel A confirmed; Channel B is a model, not Blender itself).

---

## C13. `/data/` ignores root data only, and `test_gitignore.py` catches a regression after the first commit

**Channel B.** A committed scratch repo of the public tree (105 files). Baseline: 4 passed.

| Mutation | Result |
|---|---|
| `data/` | 4 failed |
| `**/data/` | 4 failed |
| rule deleted | 1 failed |
| `*.json` added | 1 failed |
| `/app/public/` added | 1 failed |
| `data` added to `app/.gitignore` | 3 failed |

The tests use `--no-index`, so the files being tracked does not hide a bad rule. Ignored paths
today are `.venv`, caches, `app/dist`, `app/coverage`, `node_modules` and `graphify-out`. None is
needed by the app.

**Minor.** The docstring at `tests/test_gitignore.py:26` says a personal excludes file "cannot
change the answer". `$XDG_CONFIG_HOME/git/ignore` still applies under `GIT_CONFIG_GLOBAL=/dev/null`:
1 test failed, a spurious failure rather than a false pass.

**Verdict: SURVIVES.**

---

## Findings nobody asked about

- **F1. Python supply-chain age.** `uv.lock` pins 17 packages uploaded after 2026-10-14. Among
  them are the direct deps `pytest==9.2.0` (PyPI 2026-10-27T21:30Z, 1 day old) and
  `pandas==3.1.0` (2026-10-22, 6 days), plus `tzdata 2026.6`, uploaded today at 09:57Z. The
  concepts doc (line 282) admits there is no age rule; for a public repo, add
  `exclude-newer` to the uv settings.
- **F2.** A Python int above about 1.8e308 is written as a valid JSON number, and `JSON.parse`
  turns it into `Infinity` (probe: `{"x": 10**309}` → `data.x = Infinity`). The writer does not
  enforce the "IEEE-754 doubles" rule in contract.md §2.
- **F3.** The notebook kernel inherits `IPYTHONDIR` startup files (see C5). Set `IPYTHONDIR` and
  `JUPYTER_CONFIG_DIR` to tmp in the `kernel_name` fixture.
- **F4.** The jsDelivr fallback URL ships in the 3D chunk (see C7). Pass `unicodeFontsURL` as a
  local path, or assert in a test that labels stay inside the font's cmap.
- **F5.** The notebook and `README.md:65` list a `reports/` folder that will not exist in the
  public tree (it is an empty, untracked directory).
- **F6.** While this review ran, other processes wrote `docs/architecture/graph/` (about 6 MB:
  graph.html, graph.json, graph.svg) and `docs/validation/m0-stats-review-ledger.md` into the
  repo. The ledger mentions a "session scratchpad". Decide whether these belong in the public
  first commit.

## Summary

| ID | Claim | Verdict |
|---|---|---|
| C1 | Python enforces §1; no NaN/Inf written | SURVIVES |
| C2 | TS and Python agree on every input | **REFUTED** (14/82 divergences) |
| C3 | `source_commit` is always correct and never raises | **REFUTED** |
| C4 | SDE gives byte-identical re-exports | **REFUTED** (default `--out` after the first commit) |
| C5 | Notebook determinism, fail-not-skip, isolated kernel | SURVIVES (isolation leak F3) |
| C6 | Pins, 14-day npm age, audit | SURVIVES (build-system range; F1) |
| C7 | Lazy 3D chunk; no off-origin requests | SURVIVES today (latent CDN URL, F4) |
| C8 | No secrets, private refs or email; no copying | **REFUTED** (private kit and suite refs only) |
| C9 | Mutation-checked | **REFUTED** (3 of 6 new mutants survive) |
| C10 | All refs and excerpts accurate | **REFUTED** (2 defects of 166 refs and 20 excerpts) |
| C11 | Specs valid; `.mmd` = kit output; diagrams true | **REFUTED** (4 of 5 stale vs kit HEAD; ERD meta fields wrong) |
| C12 | Blender framing correct | SURVIVES |
| C13 | `/data/` rule and its test | SURVIVES |
