"""Write the JSON files the web app reads.

Run:  uv run python tools/export_app_data.py [--out app/public/data]

This is a thin wrapper. The logic lives in the package: export.py builds the payload, contract.py
wraps it in the envelope, provenance.py supplies the commit and the time. This file only wires
them together and writes the result.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from arima_forecasting.contract import dumps, make_envelope, validate_envelope
from arima_forecasting.export import meta_payload
from arima_forecasting.provenance import build_time, source_commit

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "app" / "public" / "data"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the JSON files the web app reads.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="folder to write into (default: app/public/data in this repo)",
    )
    args = parser.parse_args(argv)

    # The commit and the time are read once, here, and handed to the pure code.
    envelope = make_envelope(
        "meta",
        meta_payload(),
        generated_at=build_time(),
        source_commit=source_commit(REPO_ROOT),
    )

    # make_envelope already checks its inputs; this checks the finished envelope against the
    # Python copy of the contract rules, so a malformed file is never written. The app has its
    # own TypeScript copy (app/src/lib/contract.ts). Two things keep the copies together: both
    # languages' tests run the one list of envelopes in app/src/test/fixtures/envelope_cases.json,
    # and app/src/lib/contract.realdata.test.ts parses the files written here.
    problems = validate_envelope(envelope)
    if problems:
        print("refusing to write an invalid envelope:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    # Serialise first: if the data contains NaN, dumps raises here and no half-written file
    # is left behind.
    text = dumps(envelope)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "meta.json"
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
