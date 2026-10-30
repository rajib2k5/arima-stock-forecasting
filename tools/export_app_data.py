"""Write the JSON files the web app reads, or check that the committed ones are current.

Run:  uv run python tools/export_app_data.py [--out app/public/data]
      uv run python tools/export_app_data.py --check
      uv run python tools/export_app_data.py --only fit,residuals_aic   (for iterating; see below)

It reads the raw snapshot that tools/fetch_prices.py downloaded ($VOL_DATA_DIR/...); it never
downloads anything itself. Without a snapshot it exits 2 and writes nothing.

This is a thin wrapper. The logic lives in the package: export.py builds the payloads, contract.py
wraps them in the envelope, payloads.py checks their shape, provenance.py supplies the commit and
the time, artifacts.py compares two exports. This file only wires them together.

--check rebuilds every artifact in memory, runs the cross-file check below on the rebuild, and
compares `schema_version`, `artifact` and `data` with the files in --out. `generated_at` and
`source_commit` are not compared, because they legitimately differ between the export run and the
check run. It exits 1 on any disagreement, difference, missing file or extra file, and writes nothing.

--only NAMES writes just the named artifacts, and takes the AIC grid from the aic_grid.json already
in --out instead of refitting it (the grid is most of an export's 8 minutes). It is a shortcut for
iterating on the later artifacts; a full export and --check are still what a commit needs, because
only they rebuild the grid from the snapshot.

fit.json, the three residuals_<id>.json files, the seven forecast_<model>_<method>.json files and
evaluation.json must describe the same fits and forecasts, and the forecasts' actuals must be
prices.json's rows (payloads.validate_fit_residuals, validate_forecast_fit, validate_forecast_prices and
validate_forecast_evaluation). Before writing, the tool checks the set the
folder would hold (the files it writes, and the ones --only leaves as they are) and refuses to write
if they disagree, so `--only fit` after a code change fails instead of leaving fit.json beside stale
residual or forecast files; after writing, it reads the whole set back from disk and checks it
again. Both checks run only when the run writes one of the set or the folder already holds one, so
`--only meta` into a folder without them writes meta.json and nothing else is asked of it.
"""

from __future__ import annotations

import os

# Before numpy loads: the milestone-2 grid fits 144 small models, and OpenBLAS's default thread pool
# makes them over four times slower on a many-core machine (352 s against 84 s, measured). The
# results are bit-identical either way. setdefault, so a caller can still choose a value.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from arima_forecasting.artifacts import ArtifactError, compare_exports, read_artifact  # noqa: E402
from arima_forecasting.config import raw_dir  # noqa: E402
from arima_forecasting.contract import dumps, make_envelope, validate_envelope  # noqa: E402
from arima_forecasting.data import SnapshotError, read_snapshot  # noqa: E402
from arima_forecasting.export import ARTIFACTS, build_payloads  # noqa: E402
from arima_forecasting.fitting import GridMismatch  # noqa: E402
from arima_forecasting.payloads import PAYLOAD_VALIDATORS, validate_fit_residuals, validate_forecast_evaluation, validate_forecast_fit, validate_forecast_prices  # noqa: E402
from arima_forecasting.prep import DataQualityError  # noqa: E402
from arima_forecasting.provenance import build_time, source_commit  # noqa: E402
from arima_forecasting.selection import ModelSearchError  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "app" / "public" / "data"

EXIT_INVALID = 1
EXIT_NO_SNAPSHOT = 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the JSON files the web app reads.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="folder to write into, or to check (default: app/public/data in this repo)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the files in --out differ from a fresh export",
    )
    parser.add_argument(
        "--only",
        type=lambda text: tuple(name for name in text.split(",") if name),
        default=None,
        help="comma-separated artifacts to write; reuses aic_grid.json from --out instead of refitting the grid",
    )
    args = parser.parse_args(argv)
    if args.only is not None:
        unknown = [name for name in args.only if name not in ARTIFACTS]
        if args.check or not args.only or unknown:
            parser.error(f"--only takes artifact names from {', '.join(ARTIFACTS)}, and not with --check; unknown: {unknown}")

    try:
        snapshot = read_snapshot(raw_dir())
    except (SnapshotError, ValueError) as error:  # ValueError: VOL_DATA_DIR inside the repo
        print(f"error: {error}", file=sys.stderr)
        return EXIT_NO_SNAPSHOT

    # The commit and the time are read once, here, and handed to the pure code.
    generated_at = build_time()
    commit = source_commit(REPO_ROOT)
    reused = None
    if args.only is not None and "aic_grid" not in args.only:
        try:
            reused = read_artifact(args.out, "aic_grid")["data"]
        except ArtifactError as error:
            print(f"error: --only needs a valid aic_grid.json in {args.out}: {error}", file=sys.stderr)
            return EXIT_INVALID
    try:
        payloads = build_payloads(snapshot, aic_grid=reused)
    except (DataQualityError, ModelSearchError, GridMismatch) as error:  # the data cannot give a valid export
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID
    envelopes: dict[str, dict[str, Any]] = {
        name: make_envelope(name, payload, generated_at=generated_at, source_commit=commit)
        for name, payload in payloads.items()
    }

    # Check every envelope against the Python copy of the contract before anything is written,
    # so a malformed file is never written and an export never leaves half its files behind. The
    # app has its own TypeScript copy (app/src/lib/contract.ts). Two things keep the copies
    # together: both languages' tests run the one list of envelopes in
    # app/src/test/fixtures/envelope_cases.json, and app/src/lib/contract.realdata.test.ts parses
    # the files written here.
    problems = []
    for name, envelope in envelopes.items():
        problems += [f"{name}: {p}" for p in validate_envelope(envelope)]
        if name in PAYLOAD_VALIDATORS:
            problems += [f"{name}: {p}" for p in PAYLOAD_VALIDATORS[name](envelope["data"])]
    if problems:
        print("refusing to write an invalid envelope:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_INVALID

    # Serialise everything first: if any payload contains NaN, dumps raises here and no file at
    # all is written, half-written or otherwise.
    texts = {name: dumps(envelope) for name, envelope in envelopes.items()}

    if args.check:
        # The fresh export's own family must agree before it is compared: equal to an inconsistent
        # rebuild, the committed files would be inconsistent too.
        mismatch = _family_problems({name: envelopes[name]["data"] for name in CHECKED})
        if mismatch:
            print("the fresh export's fit, residuals, forecast and evaluation files disagree:")
            for problem in mismatch:
                print(f"  - {problem}")
            return EXIT_INVALID
        stale = compare_exports(args.out, envelopes)
        if stale:
            for line in stale:
                print(f"stale: {line}")
            _explain_snapshot_change(args.out, envelopes)
            print("run: uv run python tools/export_app_data.py")
            return EXIT_INVALID
        print(
            f"app data is current: {', '.join(envelopes)} "
            "(schema_version, artifact and data compared; generated_at and source_commit are not)"
        )
        return 0

    writing = [name for name in texts if args.only is None or name in args.only]
    # The cross-file check runs when this run writes a file of the family, or the folder already
    # holds one: `--only meta` into a folder that has none of them writes meta.json as before.
    family = any(name in FAMILY for name in writing) or any((args.out / f"{name}.json").exists() for name in FAMILY)
    if family:
        # The family the folder will hold: the new files, and the old ones --only keeps.
        planned = {name: envelopes[name]["data"] for name in writing if name in CHECKED}
        try:
            planned |= {name: read_artifact(args.out, name)["data"] for name in CHECKED if name not in planned}
        except ArtifactError as error:
            print(f"error: --only {','.join(writing)} keeps a fit, residuals, forecast or evaluation file that is not valid: {error}", file=sys.stderr)
            return EXIT_INVALID
        mismatch = _family_problems(planned)
        if mismatch:
            print("refusing to write: the fit, residuals, forecast and evaluation files would disagree (add them to --only, or run a full export):", file=sys.stderr)
            for problem in mismatch:
                print(f"  - {problem}", file=sys.stderr)
            return EXIT_INVALID

    args.out.mkdir(parents=True, exist_ok=True)
    for name in writing:
        path = args.out / f"{name}.json"
        path.write_text(texts[name], encoding="utf-8")
        print(f"wrote {path} ({len(texts[name].encode('utf-8')):,} bytes)")

    if not family:
        return 0
    # Read the whole set back from disk and check it again.
    try:
        written = {name: read_artifact(args.out, name)["data"] for name in CHECKED}
    except ArtifactError as error:
        print(f"error: after writing, {error}", file=sys.stderr)
        return EXIT_INVALID
    mismatch = _family_problems(written)
    if mismatch:
        print(f"error: after writing, the fit, residuals, forecast and evaluation files in {args.out} disagree:", file=sys.stderr)
        for problem in mismatch:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_INVALID
    return 0


# The files that must agree with each other: the fit, its residual series, the forecasts made from it,
# and the evaluation computed from the forecasts.
FAMILY = tuple(name for name in ARTIFACTS if name in ("fit", "evaluation") or name.startswith(("residuals_", "forecast_")))
# What the check reads: the family, then prices.json, whose rows the forecasts' actuals and origins must be.
# prices.json alone does not start the check (a folder of milestone-1 files has nothing to agree with it).
CHECKED = (*FAMILY, "prices")


def _family_problems(files: dict[str, Any]) -> list[str]:
    residuals = {name: data for name, data in files.items() if name.startswith("residuals_")}
    forecasts = {name: data for name, data in files.items() if name.startswith("forecast_")}
    return (
        validate_fit_residuals(files["fit"], residuals)
        + validate_forecast_fit(files["fit"], residuals, forecasts)
        + validate_forecast_prices(files["prices"], forecasts)
        + validate_forecast_evaluation(files["evaluation"], forecasts)
    )


def _explain_snapshot_change(folder: Path, envelopes: dict[str, dict[str, Any]]) -> None:
    """If the committed prices came from another snapshot, say so: that explains every diff."""
    try:
        committed = json.loads((folder / "prices.json").read_text(encoding="utf-8"))
        old = committed["data"]["source"]["raw_sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        return
    new = envelopes["prices"]["data"]["source"]["raw_sha256"]
    if old != new:
        print(f"note: the committed prices.json was built from snapshot {old[:12]}...; the snapshot on disk is {new[:12]}...")


if __name__ == "__main__":
    sys.exit(main())
