# ARIMA stock forecasting: the app

A small React app that visualises the results of the Python study in the parent folder. **The app never computes a result.** Python does all the statistics and writes versioned JSON; the app reads that JSON and draws it, plus a few small, unit-tested display transforms in `src/lib/`.

Milestone 0 shipped the shell: an **About** page (the project, the analysis path, study windows and milestones read from `meta.json`), an **Architecture** page (three animated diagrams and a 3D wiring check), the data-contract loader, and light and dark themes. Milestone 1 adds the **Price explorer**, the first page drawn from data: the adjusted close from `prices.json` on a dollar or log axis with the train, test and out-of-sample segments shaded, and panels for the two KDEs and the four decomposition parts from `eda.json`. The page is offered only when `meta.json` lists both files, and its code is a separate chunk, loaded when the page first opens. The two files are not committed (`meta.json` names them in `held_artifacts`), so in a fresh clone the page says that the data is not built in this copy and gives the two commands that build it. The stationarity lab, the AIC landscape, the walk-forward forecast and the residual diagnostics arrive in later milestones.

## Run it

```bash
# 1. download the prices once, then build the JSON, from the repository root. prices.json and
#    eda.json are not committed (owner gate, ADR-0001); without them the Price explorer says so.
uv run python tools/fetch_prices.py
uv run python tools/export_app_data.py

# 2. start the app (from this folder)
npm ci
npm run dev        # development server
npm run verify     # lint + tests with coverage thresholds + production build
npm run preview    # serve the production build locally
```

If `app/public/data/meta.json` is missing or invalid, the About page says so and shows the command above instead of drawing a half-wrong page.

The build uses relative URLs (`base: './'`), so the contents of `dist/` work when served from any sub-path.

## Where the data comes from

```
Yahoo Finance (yfinance) -> raw CSV cache, outside the repo -> src/arima_forecasting (Python)
    -> tools/export_app_data.py -> app/public/data/<artifact>.json -> this app
```

`app/public/data/` is written by `tools/export_app_data.py`. Nothing in this app fetches market data or talks to any third-party service; the only network requests are for its own files, and the 3D labels use a font bundled with the app.

## The JSON contract

Every file `public/data/<artifact>.json` is an envelope:

```json
{
  "schema_version": "1.0.0",
  "artifact": "meta",
  "generated_at": "2026-10-28T12:00:00Z",
  "source_commit": "<40 or 64 lowercase hex> | <the same>-dirty | uncommitted",
  "data": { }
}
```

| Field | Rule |
|---|---|
| `schema_version` | `MAJOR.MINOR.PATCH`. The app accepts any `1.x.y` and refuses every other major version. |
| `artifact` | Matches `^[a-z][a-z0-9_]*$` (the same pattern Python uses), and must equal the name of the file that was requested. |
| `generated_at` | UTC, exactly `YYYY-MM-DDTHH:MM:SSZ`, a real calendar instant: years 0001–9999, no leap second. Checked by plain calendar arithmetic (not `Date.UTC`, which reads years 0–99 as 1900–1999), with the same rules as the Python side. |
| `source_commit` | A git object name of 40 (SHA-1) or 64 (SHA-256) lowercase hex characters, the same plus `-dirty`, or `uncommitted`. |
| `data` | An object. Its shape depends on the artifact. |

The envelope's top level is closed: an unknown top-level key is an error, like a missing or wrongly typed one. Unknown keys *inside `data`* are ignored, so a minor release can add fields without breaking older builds. The parser reports **every** problem it finds, not just the first.

The `meta` artifact's `data` holds `project`, `title`, `ticker`, `windows` (`course` and `oos`, each `{start, end_exclusive}` as `YYYY-MM-DD`, start before end), `milestones` (`id`, `slug`, `title`, `status` of `done`, `current` or `planned`; ids unique; exactly one `current`) and `artifacts` (a list of names). The About page shows the end-exclusive windows as inclusive date ranges.

The code:

- `src/lib/contract.ts` is the pure parser: `parseEnvelope(raw)` and `parseMeta(data)` return `{ok: true, ...}` or `{ok: false, errors: string[]}`. No fetch, no clock, no DOM.
- `src/lib/contract.payloads.ts` holds the milestone-1 payload parsers, `parsePrices` and `parseEda`, in the same style. They sit in their own module because `contract.ts` is bundled into the main chunk and these are needed only by the lazily loaded explorer (measured: the main chunk is 10.27 kB smaller this way).
- `src/data/loadArtifact.ts` is the only I/O: `loadArtifact(name, fetchImpl = fetch)` fetches `${BASE_URL}data/${name}.json` and runs the parser. HTTP errors, network errors, invalid JSON, contract violations and a wrong artifact name all come back as typed values (`src/lib/loadError.ts`).

## Layout

```
src/lib/        pure UI logic (coverage-gated): contract and payload parsers, the SVG plot and
                its helpers, explorer presentation, the view gate, 3D axes geometry,
                capability probes, display transforms, theme, storage, diagrams, shell
src/data/       the artifact loader, the hook that loads meta.json, and the explorer's loader
src/views/      About, Price explorer (lazy), Architecture and the lazily loaded 3D preview
src/test/       test setup and hand-built contract fixtures
```

`src/lib/diagrams.tsx` is an unmodified copy of the author's reusable animated-diagram components (architecture, sequence and activity SVG diagrams). Its test file is adapted: the fixture labels are neutral and the test of the page that used to wrap the diagrams was removed along with that page.

The 3D preview (`src/views/AicAxesScene.tsx`) is loaded with `React.lazy`, so three.js lands in its own chunk and is fetched only when the Architecture page is opened. All of its geometry (axis ends, tick labels, floor lines, camera framing, motion settings) is computed in `src/lib/aicAxes.ts` and unit-tested. Without WebGL2, or if the scene throws, a static description of the same axes is shown instead. With `prefers-reduced-motion: reduce` the scene does not auto-rotate.

## Tests

```bash
npm test           # run once
npm run coverage   # with thresholds on src/lib/**: 85% lines, 85% functions, 75% branches
```

Tests assert behaviour against hand-worked values or hand-built fixtures, not against copies of the code's own output. `src/test/fixtures/envelope_cases.json` is shared with the Python tests: both suites run every case in it, so the two envelope parsers cannot change apart without a test failing. One test file is the exception on purpose: `src/lib/contract.realdata.test.ts` runs the production parsers over the real files in `public/data/`, so a change in the Python exporter that this app cannot read fails here. Thresholds are enforced in `vite.config.ts` and are not to be lowered.

## Dependencies

Every dependency in `package.json` is pinned to an exact version, and `package-lock.json` is committed. The versions in the lock file were chosen to be at least 14 days old on the day the lock was created (2026-10-28), as a small supply-chain precaution. `@fontsource/inter` (SIL Open Font License 1.1) supplies the one font file the 3D labels use, so no font is fetched from a CDN at run time.

`src/data/` (the loader) is committed like any other source, and so is `public/data/meta.json`. The two price files the exporter also writes there, `prices.json` and `eda.json`, are git-ignored by the owner gate (ADR-0001) and built locally. The repository's top-level `.gitignore` keeps raw market data out with the anchored rule `/data/`, which matches only a `data/` folder at the repository root; a bare `data/` would also have matched these two folders. This app's own `.gitignore` has no `data` rule. `tests/test_gitignore.py` (in the repository root) checks all of this with `git check-ignore`.

## Not financial advice

This is an educational study of a statistical method. Nothing here is a recommendation to buy or sell anything.
