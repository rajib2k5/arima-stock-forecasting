"""Download the daily AAPL prices once, into the raw data folder, with a manifest beside them.

Run:  uv run python tools/fetch_prices.py            # reuse the snapshot if it is there
      uv run python tools/fetch_prices.py --refresh  # download again and replace it

The folder is $VOL_DATA_DIR/arima-stock-forecasting/raw/ (default ~/data/vol-projects/...). It is
outside git: raw market data is never committed. This is the only tool that uses the network.
tools/export_app_data.py reads the snapshot this tool writes and never downloads anything.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime, timezone

from arima_forecasting.config import cache_dir, raw_dir
from arima_forecasting.data import DownloadError, SnapshotError, acquire, snapshot_paths, yfinance_download


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the price snapshot once.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="download again and replace the snapshot (the old one is kept if the download fails)",
    )
    args = parser.parse_args(argv)

    import yfinance  # only for its version string; the download itself goes through acquire

    try:
        folder, cache = raw_dir(), cache_dir()
    except ValueError as error:  # VOL_DATA_DIR points inside the repo, outside its data/ folder
        print(f"error: {error}", file=sys.stderr)
        return 1
    try:
        snapshot, reused = acquire(
            folder,
            download=yfinance_download(cache),
            now=lambda: datetime.now(timezone.utc),
            yfinance_version=yfinance.__version__,
            refresh=args.refresh,
        )
    except (DownloadError, SnapshotError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    manifest = snapshot.manifest
    csv_path, manifest_path = snapshot_paths(folder)
    print(("reused " if reused else "downloaded ") + str(csv_path))
    print(f"manifest       {manifest_path}")
    print(f"rows           {manifest['rows']}  ({manifest['first_date']} to {manifest['last_date']})")
    print(f"sha256         {manifest['sha256']}")
    print(f"downloaded_at  {manifest['downloaded_at']}  (yfinance {manifest['yfinance_version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
