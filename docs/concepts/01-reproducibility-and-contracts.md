# Reproducibility and contracts, from first principles

This note explains the ideas behind milestone 0: why the repo pins what it pins, why the JSON
files look the way they do, and why a test only counts once it has failed. The code walkthrough
is in [milestone 0](../milestones/00-scaffold.md); the decisions are in
[ADR-0001](../adr/0001-python-computes-app-visualises.md) and the
[contract](../architecture/contract.md). Every number below was measured on 2026-10-28 with the
commands in the milestone's Results section.

---

## 1. Exact pins, ranges and lockfiles

A *dependency specifier* says which versions of a package you accept.

- A **range**, such as `statsmodels>=0.15`, accepts many versions. The installer picks the newest
  one that fits *on the day you install*. Two installs a month apart can get different code.
- An **exact pin**, such as `statsmodels==0.15.0`, accepts one version. This repo pins all 12
  direct Python dependencies (`pyproject.toml:6-15`, `:29-34`) and all 23 direct app dependencies
  (`app/package.json:16-42`).
- A pin covers only the packages you name. Their own dependencies, the *transitive* ones, can
  still float. pandas 3.1.0, for example, depends on numpy, python-dateutil and tzdata
  (`uv.lock:683-690`).
- A **lockfile** records the whole resolved tree: every package, its exact version, where it came
  from, and a hash of each file. uv's documentation describes `uv.lock` as a universal lockfile
  (one file for all platforms and Python versions) that should be committed and that uv, not you,
  edits ([uv docs, "The lockfile"](https://docs.astral.sh/uv/concepts/projects/layout/#the-lockfile)).
  Here `uv.lock` has 84 package entries (one is the project itself) and 467 SHA-256 hashes;
  `app/package-lock.json` has 372 packages, every one with an `integrity` hash.

So the pins state intent in a file a human reviews, and the lockfile reproduces everything
underneath. `tests/test_package.py:53-57` checks that each pin equals the locked version, so the
two cannot drift apart.

**Assumptions**
- The package index keeps serving those exact files, and they still match the recorded hashes.
- Every locked package has a build for your platform (here Linux aarch64).

**Where it breaks**
- Pins freeze bug fixes and security fixes too. Updating becomes a deliberate act.
- Exact pins suit an application. A library that others install should use ranges, or it will
  conflict with its users' pins.
- The interpreter is pinned only to `3.12.*` (`pyproject.toml:5`); the patch version (3.12.13 on
  the build machine) can differ between machines.

---

## 2. Semantic versioning applied to a data contract

[Semantic versioning](https://semver.org/spec/v2.0.0.html) (semver) writes a version as
`MAJOR.MINOR.PATCH`. You bump MAJOR for an incompatible change, MINOR for a backward-compatible
addition, and PATCH for a backward-compatible fix.

For a JSON contract, the "API" is the *shape* that readers rely on. The contract's own table
(`docs/architecture/contract.md:81-85`) applies semver like this:

- **Breaking (major):** removing or renaming a field; changing its type, unit or meaning; making a
  non-nullable field nullable; adding a value to a *closed* enum (one the reader may switch over
  exhaustively); adding, removing or renaming an envelope key.
- **Additive (minor):** a new field in `data`; a new artifact; a new value in an *open* enum.
- **Patch:** no shape change, such as fixing how a value is computed without changing what it means.

Two design choices make this workable. First, the version describes shape, not content:
re-exporting with new data never bumps it (`contract.md:78-79`). Second, units live in field
names (`close_usd`, `log_close`), so a unit change *is* a rename, which is visibly major.

"Adding a field is not breaking" is only true if old readers ignore fields they do not know. That
is the next section. Semver for data is a joint promise of the writer's policy and the reader's
behaviour.

**Assumptions**
- People bump the version correctly; no parser can check intent.
- One version covers every file from one export, so artifacts cannot disagree.

**Where it breaks**
- A meaning change without a shape change (dollars silently becoming log-dollars under the same
  name) passes every parser. Only review catches it
  (`docs/adr/0001-python-computes-app-visualises.md:155`).
- semver's major version 0 means "anything may change", which is why the contract started at
  `1.0.0`. Pre-release tags such as `1.0.0-rc.1` are rejected by both parsers.

---

## 3. A closed envelope, an open payload, and one corpus for two readers

Martin Fowler's [TolerantReader](https://martinfowler.com/bliki/TolerantReader.html) pattern
says: a consumer should read only the parts of a message it needs and ignore the rest, so the
producer can add things without breaking it. This repo applies it to one level of each file and
not to the other.

- **The envelope's top level is closed.** Both readers, Python's `validate_envelope`
  (`src/arima_forecasting/contract.py:119-122`) and the app's `parseEnvelope`
  (`app/src/lib/contract.ts:166-171`), reject a missing *or* an unknown top-level key. The five
  envelope keys are what every artifact shares and what the loader trusts before it reads any
  payload, so a new one is a major bump (`docs/architecture/contract.md:43-47`).
- **The `data` payload is open.** The app's payload parsers build a *new* object from the keys
  they know (`contract.ts:176-179`, `:272`). Unknown keys inside `data` are ignored and not passed
  on, so a minor version can add a field without breaking an older app. Missing or wrongly typed
  known keys are still errors; tolerance is not coercion.

The trade-off, for a field nobody told the reader about:

| | Strict reader (the top level here) | Tolerant reader (`data` here) |
|---|---|---|
| A new optional field | breaks every old app (forces a major bump) | ignored safely (a minor bump) |
| A typo in a field name | caught | silently ignored; the real field reads as "missing" |

The repo takes tolerance only where it buys something: payloads will grow field by field from
milestone 1 on. It gets typo protection back from the strict Python writer and its tests. The
envelope, by contrast, should almost never change, so strictness there costs little and catches
a malformed file before anything else is read.

**One corpus for two readers.** The envelope rules are written twice, in Python and in
TypeScript, and two copies of a rule drift. The code review showed how far: fed the same 82
envelopes, the two readers disagreed on 14 (early-year timestamps, artifact names such as
`Meta`, and extra top-level keys; see milestone 0, pitfalls 10 and 11). Each side's tests were
good tests of their own reader; nothing compared the two. The fix is one shared list of cases,
`app/src/test/fixtures/envelope_cases.json`: 142 envelopes (34 valid, 108 invalid), each with a
name and the verdict both readers must reach. `tests/test_contract_corpus.py` runs every case
through `validate_envelope`, and `app/src/lib/contract.corpus.test.ts` runs the same file
through `parseEnvelope`. A rule changed on one side only now fails that side's tests. Re-run on
the current code, the review's 82 envelopes give 0 disagreements (measured).

**Assumptions**
- Every unknown field inside `data` is truly optional to an old reader.
- Each rule that matters has at least one case in the corpus.

**Where it breaks**
- A new payload field that changes how *other* fields must be read (say, a `units` key) is
  ignored by an old reader, which then misreads the rest. Such a change must be a major bump.
- A reader that passed unknown data through, instead of dropping it, would forward unvalidated
  content to code that trusts it.
- The corpus checks only the cases it lists. A rule both sides get wrong the same way, or an input
  nobody thought to add, passes it. An exhaustive comparison is stronger where the input space is
  small enough. For timestamps it was run once, outside the test suites: over a grid of 1,120,100 timestamp strings (every `YYYY-MM-DDT12:00:00Z` for years 0000–9999, months 00–13 and days 00, 01 and 27–32, plus `2026-10-28` with hours 00, 01, 23, 24, 25 × minutes 00, 01, 59, 60 × seconds 00, 01, 59, 60, 61),
  the old readers disagreed on 6,459, all in the years 0001–0099
  (JavaScript's `Date.UTC` reads years 0–99 as 1900–1999), and the current readers agree on
  every one (measured). Inside the app's suite, "calendar arithmetic" tests compare the new
  calendar with a `Date`-based oracle on every year 0001–9999.

---

## 4. Why JSON has no NaN

Computers store most real numbers as [IEEE 754](https://standards.ieee.org/ieee/754/6210/)
floating point. A binary64 "double" has 1 sign bit, 11 exponent bits and 52 fraction bits. When
all exponent bits are 1, the value is special: a zero fraction means $\pm\infty$, and a non-zero
fraction means **NaN**, "not a number". It is the result of operations such as $0/0$ or
$\infty - \infty$. Python's `float("nan")` is the bit pattern `7ff8000000000000` (measured):
exponent `0x7ff`, top fraction bit set, which marks a "quiet" NaN. NaN is *unordered*: it compares
unequal to everything, itself included, so `nan == nan` is `False` (measured).

[RFC 8259](https://www.rfc-editor.org/rfc/rfc8259) defines JSON numbers by a decimal grammar:
optional minus, digits, optional fraction, optional exponent. Its section 6 says that values this
grammar cannot express, Infinity and NaN among them, are not allowed. JSON is meant to be
language-neutral, and many languages have no literal for them.

Python's `json.dumps` writes `NaN` by default (measured: `'NaN'`). Node's `JSON.parse` rejects
that with a `SyntaxError` for the whole document (measured). In the other direction,
`JSON.stringify({x: NaN, y: Infinity})` silently writes `{"x":null,"y":null}` (measured). Both
directions lose information without the producer noticing. The contract's answer: `allow_nan=False`
on export, and a missing value is an explicit `null` with a sibling field that says why
(`docs/architecture/contract.md:67`).

The same binary64 format sets a second limit. Its 52 fraction bits (53 with the implicit leading
bit) hold every integer exactly only up to $2^{53} - 1 = 9{,}007{,}199{,}254{,}740{,}991$, which
JavaScript calls `Number.MAX_SAFE_INTEGER` (measured). `JSON.parse` turns every number into such a
double, so `JSON.parse("9007199254740993")` gives `9007199254740992`, and the 310-digit `10**309`
that Python writes happily becomes `Infinity` (both measured in Node 22). So `dumps` refuses any
integer beyond ±(2^53 − 1), naming its path, after `json.dumps` has run
(`src/arima_forecasting/contract.py:173-191`, the walk at `:152-170`;
`docs/architecture/contract.md:36-41`). A value that really needs more digits must travel as a
string.

**Assumptions**
- Every producer uses the project's `dumps`, never a bare `json.dumps`.

**Where it breaks**
- `null` alone loses the reason, so the reason must be a separate field.
- The integer check covers integers only. A float such as `1e300` is a valid double and passes;
  floats lose precision in their last digits by design, which is a different problem.

---

## 5. Deterministic outputs

An output is *deterministic* if the same inputs always give the same bytes. Then git diffs show
only real changes, a hash identifies a result, and a verifier can compare two runs.

Sources of accidental difference, and the guard for each:

- **The clock.** The [`SOURCE_DATE_EPOCH` specification](https://reproducible-builds.org/specs/source-date-epoch/)
  says: if this environment variable is set, a build must use it (seconds since 1970-01-01 00:00
  UTC, written like the output of `date +%s`) instead of the current time, and should exit with an
  error if it is malformed. `build_time` does this (`src/arima_forecasting/provenance.py:93-112`).
  Two exports with `SOURCE_DATE_EPOCH=1700000000` were byte-identical; without it, exactly one
  line, `generated_at`, differed (measured). The contract also bans wall-clock values inside
  `data` (`contract.md:74`).
- **The exporter's own output.** In a committed repo, the first export rewrites the tracked
  `meta.json`. If provenance counted that as a change, the second export of the same code would
  stamp `-dirty` and the two files would differ. Section 6 explains the exclusion that prevents
  it; `test_two_exports_with_a_fixed_source_date_epoch_are_byte_identical` checks the result.
- **Random ids.** nbformat gives each new cell a random id; two calls gave `bd6a5883` and
  `6e7f134d` (measured). The builder sets `cell-00`, `cell-01`, ... (`tools/build_notebooks.py:204`).
- **Key order.** `sort_keys=True` makes the bytes independent of dict insertion order
  (`contract.py:189`).
- **Formatting.** Fixed two-space indent and exactly one trailing newline.

**Assumptions**
- Same lockfile, same interpreter, same machine.

**Where it breaks**
- Python's `int()` is looser than the spec. The first version of `build_time` used it and
  accepted `"1_000"`, `" 5 "` and `"-86400"` (measured), so a typo like `1_700000000` would have
  been read as a real time instead of failing. It now accepts ASCII digits only
  (`provenance.py:107`), and a test rejects those three plus `"5\n"`, `"+5"` and `"١٠"`.
- Byte identity has been checked only on one machine. Optimiser results in later milestones may
  differ in the last digits across CPUs or maths libraries; that is untested.

---

## 6. Provenance: commit SHA, dirty trees, and why "uncommitted" exists

*Provenance* answers "which code made this file?". The answer is a git *commit SHA*: a hash of
the commit's content, its parents and its metadata, written as 40 hex characters (SHA-1) or, in a
repository created with `git init --object-format=sha256`, 64. Both lengths are accepted. If you
have the SHA and the data, you can check out that commit and rerun.

That only works if the code that ran **is** the commit. If the working tree had changes (edited,
staged, deleted or new untracked files), the SHA alone cannot reproduce the file, so
`source_commit` appends `-dirty`. Untracked files count, because a new module the exporter imports
changes its output. Not every tool agrees: `git describe --always --dirty` ignored an untracked
file that `source_commit` flagged (measured). And if there is no commit at all, as in this repo
today, there is no SHA to give, so the value is `uncommitted` rather than a fake.

**What "dirty" leaves out, and why.** The exporter writes into the repository, into
`app/public/data/`. Provenance names the *code* that produced a file, and regenerating the output
does not change the code. So the dirty check leaves out exactly that folder, with the pathspec
`-- ':(top)' ':(exclude)app/public/data'` (`src/arima_forecasting/provenance.py:75-83`, reasons in
the comment at `:64-71`). Without it, the first export would modify the tracked `meta.json` and
the second would stamp `-dirty`: provenance would report the exporter's own footprint as a code
change. The other half of the pathspec matters too. `':(top)'` is the whole repository; a bare
`'.'` would limit the check to the folder `source_commit` was asked about, so a call from a
subfolder would miss a change elsewhere. Both halves have tests, and so does the exclusion's width
(`app/public/other.json` still counts).

A file cannot contain the SHA of the commit that contains it: writing the SHA changes the file,
which changes the SHA. So the procedure is two commits: commit the code, export on the clean tree,
commit the JSON (`docs/adr/0001-python-computes-app-visualises.md:157-162`).

**Assumptions**
- The commit is pushed and stays reachable.
- Ignored files do not affect the output.

**Where it breaks**
- Ignored inputs *do* affect output: the raw price file lives outside the repo, and an ignored
  file never makes the tree dirty (`test_gitignored_files_do_not_make_the_tree_dirty`). That is why
  the planned `prices` artifact records the raw snapshot's SHA-256 too.
- A file marked `git update-index --assume-unchanged` or `--skip-worktree` is invisible to
  `git status`, so editing it does not make the tree dirty (`provenance.py:73-74`).
- If the export folder ever held a hand-written file, a change to it would not count either.
  Today it holds only exporter output.
- A rebase or force-push can make the recorded commit disappear.

---

## 7. Why a passing test proves nothing until it has failed

A test that has never failed may be *unable* to fail. It might assert on a copy of the code, on
the wrong value, or on nothing at all.

*Mutation testing* measures this directly. It was introduced by DeMillo, Lipton and Sayward in
"Hints on Test Data Selection: Help for the Practicing Programmer" (IEEE *Computer* 11(4),
1978). You make a *mutant*, a copy of the code with one small deliberate fault, such as `>=`
changed to `>`. If some test fails, the mutant is *killed*. If all tests pass, it *survives*, and
you have found behaviour no test pins. The idea rests on two hypotheses from that paper:
programmers write code that is nearly right (the *competent programmer hypothesis*), and tests
that catch simple faults also catch most complex ones (the *coupling effect*). The *mutation
score* is killed mutants divided by non-equivalent mutants.

Milestone 0 shows the loop working. The **first run** tried 12 mutants. 9 were killed. One was
*equivalent*: adding `^…$` inside a `fullmatch` changes nothing, so it cannot be killed (all 115
contract tests passed). Two survived: deleting `--untracked-files=normal` and ignoring a failing
`git status`, both in `provenance.py`, left all 23 provenance tests passing. Score:
$9 / (12 - 1) \approx 82\%$. A test was then added for each survivor. On the **re-run**, the same 12 mutants gave 11 killed, 1 equivalent and 0
survivors, and 7 new mutants for guards added in the same round were all killed: 18 of 18
non-equivalent mutants killed, a score of 100% on this set.

A score of 100% on your own mutants says less than it seems. The adversarial reviewer wrote six
*new* mutants, and three survived: a `tzinfo` without an offset treated as aware, the year check
of the old `Date.UTC` calendar dropped, and a whitespace-only artifact name accepted. All three are
killed now. The code that fixed the review's findings came with 55 more mutants, of which 53 were
killed and 2 were equivalent. The lesson is the one this section started with: a test suite is
only as good as the faults someone tried, and the person who wrote the code is the worst-placed
to imagine them. The tables and the measured runs are in the
[milestone 0 results](../milestones/00-scaffold.md#results-measured).

*Coverage* would not have found the two survivors. Coverage counts lines that *ran*, and both
lines run in every provenance test that makes a commit. A test with no assertion raises coverage
as much as a good one.

**Assumptions**
- Small syntactic faults stand in for real bugs (the two hypotheses above).

**Where it breaks**
- Equivalent mutants must be recognised by hand.
- Each mutant reruns the tests, so full mutation runs are slow; tools such as mutmut (Python)
  and Stryker (JavaScript) automate and prune them.
- A killed mutant shows only that a test notices *that* change.

---

## 8. Supply-chain hygiene

Every dependency is code you run without reading. A *supply-chain attack* publishes a malicious
release of a real package, or a look-alike name, and waits for installs.

- **Minimum release age.** The app's lock used only versions at least 14 days old on the lock day,
  2026-10-28 (`app/README.md:89`). The bet is that a bad release is usually noticed and pulled
  within that time. Measured: of the 23 direct app dependencies, the youngest was `vite@7.3.7`,
  published 2026-10-06, 21.8 days before. Only direct dependencies were checked, not all 372 lock
  entries.
- **`npm audit`** compares the lock against a public advisory database
  ([npm docs](https://docs.npmjs.com/cli/commands/npm-audit)). `npm audit --omit=dev`, which checks
  only what ships to users, found 0 vulnerabilities. The full `npm audit` found 3 moderate
  advisories, all in the test runner (`vitest`, `@vitest/mocker`, `@vitest/coverage-v8`).
- **Dev versus runtime.** Development dependencies never reach a visitor's browser; they run on
  the developer's machine and in CI. A dev advisory is still real, but its blast radius is your
  machine, not your users.
- **The trade-off, measured.** The fix, vitest 4.1.12, was published 2026-10-15: 12.4 days before
  the lock day. The 14-day rule would have refused it. A minimum age delays good fixes as well as
  bad releases. `npm audit fix --force` would jump past the pinned range, so it should not be run
  blindly.
- **Integrity hashes** stop a tampered file posing as a known version. They do not stop a
  malicious version that was genuinely published.
- **The Python side does not apply the rule yet.** Measured against PyPI's upload times, 17 of
  the 83 package versions in `uv.lock` were less than 14 days old when the lock was written
  (2026-10-28, 12:11 UTC). Two are direct dependencies: `pandas==3.1.0` (6.0 days) and
  `pytest==9.2.0` (0.6 days); the rest are transitive, such as `tzdata==2026.6`, uploaded 0.1 days
  before. uv's `exclude-newer` setting could enforce an age rule, but applying it would move the
  pinned statistics stack, and the concept notes and ADRs cite that stack's behaviour at
  `file:line`, so every such citation would have to be re-checked. That is an owner decision,
  question 5 of the [PR/FAQ owner questions](../prfaq.md#open-questions-for-the-owner-to-settle-at-the-milestone-0-checkpoint).

**Assumptions**
- The advisory database is complete; transitive dependencies are as old as the direct ones (not
  checked).

**Where it breaks**
- An old package can have an undiscovered flaw; age is not safety.
- npm runs dependencies' install scripts by default, so `npm ci` itself executes third-party code.
- The Python side has hashes in `uv.lock` but no minimum-age rule yet (next paragraph).

---

## Sources

- T. Preston-Werner, *Semantic Versioning 2.0.0*. <https://semver.org/spec/v2.0.0.html>
- Reproducible Builds, *SOURCE_DATE_EPOCH specification*. <https://reproducible-builds.org/specs/source-date-epoch/>
- T. Bray (ed.), *RFC 8259: The JavaScript Object Notation (JSON) Data Interchange Format*, 2017, section 6. <https://www.rfc-editor.org/rfc/rfc8259>
- IEEE, *IEEE 754-2019, Standard for Floating-Point Arithmetic*. <https://standards.ieee.org/ieee/754/6210/>
- Astral, *uv documentation: project structure and files, "The lockfile"*. <https://docs.astral.sh/uv/concepts/projects/layout/#the-lockfile>
- M. Fowler, *TolerantReader*, 2011. <https://martinfowler.com/bliki/TolerantReader.html>
- R. A. DeMillo, R. J. Lipton and F. G. Sayward, "Hints on Test Data Selection: Help for the Practicing Programmer", *IEEE Computer* 11(4), 34–41, 1978. doi:10.1109/C-M.1978.218136
- npm, *npm-audit*. <https://docs.npmjs.com/cli/commands/npm-audit>
