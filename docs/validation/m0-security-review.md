# Milestone 0 security review (before the first public push)

**Date:** 2026-10-28. **Scope:** the whole working tree before the first commit: 104 files, excluding `.venv/`, `app/node_modules/`, `app/dist/` and `app/coverage/`, but including both lockfiles. **Reviewer:** an independent Claude (Opus) subagent, read-only. The packaged `security-review` command could not run, because it diffs against `origin/HEAD` and the repo had no commits or remote branch yet. So the same checklist was applied to the whole tree by hand.

**Verdict: no exploitable findings, and no real exposure, in any of the 8 categories.**

| # | Category | Result | Evidence |
|---|---|---|---|
| 1 | Secrets and personal data | No findings | No keys, tokens, `.env` files, private keys or credentials. The notebook has no outputs. PNGs have no text chunks. Commit identity is the GitHub no-reply address. `.gitignore` covers `.env*`, `/data/`, `app/dist` and `app/coverage`. No absolute home paths in any committed file. |
| 2 | Command execution | No findings | `provenance.py` passes a list to `subprocess.run`, without `shell=True`. `git status` runs a repo's own `core.fsmonitor` hook, but `git clone` never copies `.git/config`, and the exporter only inspects its own repo. Anyone who controls that `.git` already controls the exporter's code. |
| 3 | File writes | No findings | The three CLI tools write fixed file names, with content the repo generates, to a path their own user chose. There is no privilege boundary. |
| 4 | Notebook execution in tests | No findings | A malicious committed notebook would run during `pytest`, exactly as any malicious test file would. |
| 5 | Web app | No findings | No `dangerouslySetInnerHTML`, `innerHTML`, `eval` or `new Function`. JSON values render as escaped React text. `localStorage` holds only a validated theme name. `index.html` has no inline script. The font is bundled, and only same-origin requests were observed. |
| 6 | Supply chain | No findings | All 372 `package-lock.json` entries come from registry.npmjs.org with sha512 integrity. The only install scripts are esbuild's binary check and the macOS-only fsevents. `uv.lock` uses only pypi.org, and every file is hashed. `npm audit --omit=dev` reports 0. The 3 moderate dev advisories (`@vitest/mocker`) need vitest's browser mode, which this repo does not use. |
| 7 | Blender script | No findings | It never saves a `.blend`, deletes only its own `arima_hero_*` objects, and factory-resets only in background mode. |
| 8 | GitHub | No findings | There is no `.github/` directory, and nothing assumes secrets. |

## Notes, not findings (to handle)

- **Blender exit:** in a windowed Blender, an invalid command-line flag or `--help` makes argparse call `sys.exit`, which bypasses the script's "never exit a windowed Blender" guard. Not verified against a real Blender.
- **Saved notebook outputs:** if someone runs `notebooks/00_project_tour.ipynb` in Jupyter and saves it, cell outputs would record the local data path. The notebook sync test fails in that case, but only if the tests are run before committing.
- **CSV files:** `*.csv` files outside `/data/` are not ignored. That is intended, because `reports/` will hold result tables.

## Addendum: the tree changed after this review

The review covered 104 files as they stood at 09:28. Before the first commit, the review fixes changed 40 of them and added 14, for 118 in total: the graph files, the review ledgers, `reports/README.md`, the shared envelope corpus and its two tests, a Node type shim, and a 3D-label test.

The code changes all **tighten** existing behaviour:
- **Validation:** the TypeScript envelope check is now closed at the top level, uses calendar arithmetic and enforces the artifact-name pattern. `dumps` refuses integers beyond ±(2^53 − 1).
- **`source_commit`:** it no longer raises, it accepts SHA-256 object names, and it excludes `app/public/data/` from the dirty check.
- **Tests:** the notebook kernel's `IPYTHONDIR` is isolated, and a windowed Blender no longer exits on bad arguments.

No full security re-review was run on those changes.

The final verifier pass repeated the hygiene part on all 118 files, binary PNGs included:
- **Home path:** `/home/rajib2k5` appeared once, an absolute interpreter path quoted in `m0-code-review-ledger.md`. It was redacted.
- **Other searches:** there are no hits for a personal email or `/tmp/claude-` scratch paths.
- **Lockfiles:** the lockfile, audit and install-script findings above were re-checked and still hold.

## Not checked

The Blender script inside a real Blender; network requests made from troika's web worker (concluded from reading the code); a live malicious-notebook test, which would have meant editing the repo.
