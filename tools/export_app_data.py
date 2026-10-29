"""Write the JSON files the web app reads, or check that the committed ones are current.

Run:  uv run python tools/export_app_data.py [--out app/public/data]
      uv run python tools/export_app_data.py --check

It reads the raw snapshot that tools/fetch_prices.py downloaded ($VOL_DATA_DIR/...); it never
downloads anything itself. Without a snapshot it exits 2 and writes nothing.

This is a thin wrapper. The logic lives in the package: export.py builds the payloads, contract.py
wraps them in the envelope, payloads.py checks their shape, provenance.py supplies the commit and
the time, artifacts.py compares two exports. This file only wires them together.

--check rebuilds every artifact in memory and compares `schema_version`, `artifact` and `data`
with the files in --out. `generated_at` and `source_commit` are not compared, because they
legitimately differ between the export run and the check run. It exits 1 on any difference,
missing file or extra file, and writes nothing.
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

from arima_forecasting.artifacts import compare_exports  # noqa: E402
from arima_forecasting.config import raw_dir  # noqa: E402
from arima_forecasting.contract import dumps, make_envelope, validate_envelope  # noqa: E402
from arima_forecasting.data import SnapshotError, read_snapshot  # noqa: E402
from arima_forecasting.export import build_payloads  # noqa: E402
from arima_forecasting.payloads import PAYLOAD_VALIDATORS  # noqa: E402
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
    args = parser.parse_args(argv)

    try:
        snapshot = read_snapshot(raw_dir())
    except (SnapshotError, ValueError) as error:  # ValueError: VOL_DATA_DIR inside the repo
        print(f"error: {error}", file=sys.stderr)
        return EXIT_NO_SNAPSHOT

    # The commit and the time are read once, here, and handed to the pure code.
    generated_at = build_time()
    commit = source_commit(REPO_ROOT)
    try:
        payloads = build_payloads(snapshot)
    except (DataQualityError, ModelSearchError) as error:  # the data cannot give a valid export
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

    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        path = args.out / f"{name}.json"
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path} ({len(text.encode('utf-8')):,} bytes)")
    return 0


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
