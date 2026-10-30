"""The repository's data rule (DATA.md; the owner's decision of 2026-10-29).

The exported JSON in app/public/data/ is committed, prices.json and eda.json included, so a fresh
clone runs the whole app. Bulk raw vendor files stay out. This test fails when either rule breaks:

- a raw vendor file is committed (HEAD), staged (the index), or would be staged by `git add -A`:
  anything under the top-level data/, anything in a folder named raw/ or cache/, a snapshot CSV or
  manifest named like `AAPL_1d_2015-01-01_2026-10-01.csv`, a `*.db` file (yfinance's caches), a
  `*.csv.gz` or `*.parquet` file anywhere, any compressed or archived file (gzip, xz, bzip2, zip,
  recognised by its first bytes, whatever it is called) that holds a price table, and any file that is
  a price table, whatever it is called and wherever it is;
- a file under app/public/data/ is over 10 MB in HEAD, in the index, or in the working tree.

The committed and staged versions are read from git's own blobs (`git cat-file`), not from the
disk, so a big or raw file that is staged and then truncated or deleted on disk is still found.
"Would be staged" (`git ls-files --others --exclude-standard`) catches a mistake before the
commit.

A price table is recognised by its header row: the first line that is not blank or a `#` comment,
split on a comma, a tab or a semicolon, whose first column is Date, Datetime or Timestamp and whose
columns include Open, High, Low, Close and Volume (any case, quotes allowed). The text is decoded as
UTF-16 when it starts with a UTF-16 byte-order mark, otherwise as UTF-8. Compressed files are opened
first (nested up to three levels; every member of a zip). Where it stops: a table with no header
row, with other column names or another delimiter, or inside another container (an Excel file, a
parquet file under another name, a tar) is not recognised by content; only the name and place rules
then apply. The real-data scanner (tools/licensing/scan_real_rows.py) is no longer a gate; it stays as
an optional tool.
"""

from __future__ import annotations

import bz2
import gzip
import io
import lzma
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

import pytest

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = "app/public/data/"
MAX_DATA_FILE_BYTES = 10_000_000  # 10 MB, the same decimal units as contract.md's 1 MB budget
RAW_SUFFIXES = (".db", ".csv.gz", ".parquet")
PRICE_COLUMNS = {"open", "high", "low", "close", "volume"}
DATE_COLUMNS = {"date", "datetime", "timestamp"}
DELIMITERS = (",", "\t", ";")

# data.snapshot_paths names a snapshot <TICKER>_<interval>_<start>_<end>.csv and .manifest.json.
SNAPSHOT = re.compile(r"[A-Z][A-Z0-9.^=-]*_[0-9]+[a-z]+_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}-[0-9]{2}-[0-9]{2}\.(csv|manifest\.json)")


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, input=stdin, capture_output=True)


def committable(repo: Path) -> list[str]:
    """Every path git tracks, plus every untracked path `git add -A` would stage."""
    out = _git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    out.check_returncode()
    return sorted({name.decode() for name in out.stdout.split(b"\0") if name})


def _blob_ids(repo: Path) -> dict[tuple[str, str], str]:
    """(path, "HEAD" or "index") -> blob id, for every file committed in HEAD or staged."""
    ids: dict[tuple[str, str], str] = {}
    head = _git(repo, "ls-tree", "-r", "-z", "HEAD")  # fails before the first commit: nothing committed
    if head.returncode == 0:
        for entry in filter(None, head.stdout.split(b"\0")):
            meta, path = entry.split(b"\t", 1)
            _, kind, sha = meta.split()
            if kind == b"blob":
                ids[(path.decode(), "HEAD")] = sha.decode()
    index = _git(repo, "ls-files", "--stage", "-z")
    index.check_returncode()
    for entry in filter(None, index.stdout.split(b"\0")):
        meta, path = entry.split(b"\t", 1)
        mode, sha, _ = meta.split()
        if mode != b"160000":  # a submodule is a commit, not a blob
            ids[(path.decode(), "index")] = sha.decode()
    return ids


def _read_blobs(repo: Path, shas: set[str]) -> dict[str, bytes]:
    """The content of each blob, from one `git cat-file --batch`."""
    order = sorted(shas)
    out = _git(repo, "cat-file", "--batch", stdin="".join(f"{sha}\n" for sha in order).encode())
    out.check_returncode()
    blobs, at = {}, 0
    for sha in order:
        header_end = out.stdout.index(b"\n", at)
        _, _, size = out.stdout[at:header_end].split()
        start = header_end + 1
        blobs[sha] = out.stdout[start : start + int(size)]
        at = start + int(size) + 1
    return blobs


def versions(repo: Path) -> list[tuple[str, str, bytes]]:
    """(path, where, content) for every version the rule covers: the committed blob ("HEAD"), the
    staged blob ("index"), and the working copy ("disk") of every committable path."""
    ids = _blob_ids(repo)
    blobs = _read_blobs(repo, set(ids.values()))
    found = [(path, where, blobs[sha]) for (path, where), sha in ids.items()]
    for path in committable(repo):
        if (repo / path).is_file():
            found.append((path, "disk", (repo / path).read_bytes()))
    return sorted(found)


def raw_vendor_files(paths: list[str]) -> list[str]:
    """The paths that are raw vendor files by name or place, under the rule above."""
    found = []
    for path in paths:
        parts = PurePosixPath(path).parts
        name = parts[-1]
        if parts[0] == "data" or "raw" in parts[:-1] or "cache" in parts[:-1] or SNAPSHOT.fullmatch(name) or name.endswith(RAW_SUFFIXES):
            found.append(path)
    return found


def opened(content: bytes, depth: int = 3) -> list[bytes]:
    """The content, or what a compressed or archived file holds, by its first bytes: gzip, xz, bzip2
    or zip (each member), opened up to `depth` levels. A file that will not open is kept as it is."""
    if depth == 0:
        return [content]
    try:
        if content[:2] == b"\x1f\x8b":
            return opened(gzip.decompress(content), depth - 1)
        if content[:6] == b"\xfd7zXZ\x00":
            return opened(lzma.decompress(content), depth - 1)
        if content[:3] == b"BZh":
            return opened(bz2.decompress(content), depth - 1)
        if content[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                return [part for name in archive.namelist() for part in opened(archive.read(name), depth - 1)]
    except (OSError, EOFError, lzma.LZMAError, zipfile.BadZipFile, ValueError):
        pass
    return [content]


def is_price_table(content: bytes) -> bool:
    """True when the text has a price table's header row (see the module docstring)."""
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = content.decode("utf-16", errors="replace")
    else:
        text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for delimiter in DELIMITERS:
            columns = [column.strip().strip('"').strip("'").lower() for column in line.split(delimiter)]
            if columns[0] in DATE_COLUMNS and PRICE_COLUMNS <= set(columns):
                return True
        return False  # only the first such line is a header
    return False


def price_tables(found: list[tuple[str, str, bytes]]) -> list[tuple[str, str]]:
    return sorted({(path, where) for path, where, content in found if any(is_price_table(part) for part in opened(content))})


def oversized(found: list[tuple[str, str, bytes]]) -> list[tuple[str, str, int]]:
    """The versions of data files over the size limit: (path, where, size in bytes)."""
    return sorted((path, where, len(content)) for path, where, content in found if path.startswith(DATA_DIR) and len(content) > MAX_DATA_FILE_BYTES)


def test_git_tracks_no_raw_vendor_file():
    paths = sorted({path for path, _, _ in versions(REPO)})
    assert raw_vendor_files(paths) == []


def test_no_tracked_or_stageable_file_is_a_price_table():
    assert price_tables(versions(REPO)) == []


def test_no_committed_data_file_is_over_10_mb():
    assert oversized(versions(REPO)) == []


def test_the_exported_data_files_are_committed_not_ignored():
    # The other half of the rule: a fresh clone must get every exported file.
    paths = committable(REPO)
    from arima_forecasting.export import ARTIFACTS

    for name in ARTIFACTS:
        assert f"{DATA_DIR}{name}.json" in paths, name


@pytest.mark.parametrize(
    "path",
    [
        "data/arima-stock-forecasting/raw/AAPL_1d_2015-01-01_2026-10-01.csv",
        "data/anything.txt",
        "raw/AAPL_1d_2015-01-01_2026-10-01.manifest.json",
        "snapshots/arima-stock-forecasting/cache/cookies.db",
        "docs/AAPL_1d_2015-01-01_2026-10-01.csv",
        "notes/tkr-tz.db",
        "deep/folder/raw/x.json",
        "app/public/data/AAPL_1d_2015-01-01_2026-10-01.csv.gz",
        "notebooks/prices.csv.gz",
        "reports/prices.parquet",
    ],
)
def test_each_kind_of_raw_vendor_file_is_caught(path):
    assert raw_vendor_files([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        "app/public/data/prices.json",
        "app/src/data/loadArtifact.ts",  # the app's loader folder is called data too
        "reports/metrics.csv",  # result tables are allowed
        "docs/architecture/out/.diagram-kit-manifest.json",
        "src/arima_forecasting/data.py",
    ],
)
def test_ordinary_files_are_not_caught(path):
    assert raw_vendor_files([path]) == []


@pytest.mark.parametrize(
    "first_line, caught",
    [
        (b"Date,Open,High,Low,Close,Volume\n", True),
        (b"\xef\xbb\xbfDate,Open,High,Low,Close,Volume\r\n", True),  # a byte-order mark and CRLF
        (b"date,open,high,low,close,adj close,volume\n", True),  # yfinance with auto_adjust=False
        (b'"Date","Close","High","Low","Open","Volume"\n', True),  # quoted, another column order
        (b"Date\tOpen\tHigh\tLow\tClose\tVolume\n", True),  # tab-separated
        (b"Date;Open;High;Low;Close;Volume\n", True),  # semicolons
        (b"# AAPL daily, from somewhere\n\nDate,Open,High,Low,Close,Volume\n", True),  # a comment first
        (b"Timestamp,Open,High,Low,Close,Volume\n", True),
        ("Date,Open,High,Low,Close,Volume\n".encode("utf-16"), True),  # UTF-16 with its byte-order mark
        (b"Date,Close\n", False),
        (b"date,log_close,segment\n", False),
        (b"Close,Date,Open,High,Low,Volume\n", False),  # the date is not the first column
        (b"", False),
    ],
)
def test_a_price_table_is_recognised_by_its_header(first_line, caught):
    assert is_price_table(first_line + b"2001-02-03,1,2,0.5,1.5,100\n") is caught


def test_a_headerless_table_is_not_recognised_which_the_docstring_says():
    assert not is_price_table(b"2001-02-03,1.0,2.0,0.5,1.5,100\n2001-02-04,1.1,2.1,0.6,1.6,90\n")


@pytest.mark.parametrize("pack", ["gzip", "xz", "bz2", "zip", "gzip in zip"])
def test_a_compressed_price_table_is_opened_whatever_its_name(pack):
    table = b"Date,Open,High,Low,Close,Volume\n2001-02-03,1.0,2.0,0.5,1.5,100\n"
    def zipped(data: bytes) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("notes.txt", b"nothing here")
            archive.writestr("inner.bin", data)
        return buffer.getvalue()
    packed = {"gzip": gzip.compress, "xz": lzma.compress, "bz2": bz2.compress, "zip": zipped, "gzip in zip": lambda b: zipped(gzip.compress(b))}[pack](table)
    assert not is_price_table(packed)
    assert price_tables([("app/public/data/x.bin", "index", packed)]) == [("app/public/data/x.bin", "index")]


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


# Made-up rows: the header of a raw snapshot, and values that are not anyone's prices.
FAKE_RAW = b"Date,Open,High,Low,Close,Volume\n2001-02-03,1.0,2.0,0.5,1.5,100\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    git(tmp_path, "init", "-q", str(repo))
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    (repo / ".gitignore").write_text("/data/\n")
    (repo / "README.md").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    return repo


def test_the_check_sees_a_force_added_raw_file_and_an_unstaged_big_data_file(repo):
    # A raw snapshot that .gitignore ignores, added with --force, is tracked; a big new data file
    # is not staged yet but would be. Both must be found.
    raw = repo / "data" / "arima-stock-forecasting" / "raw" / "AAPL_1d_2015-01-01_2026-10-01.csv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(FAKE_RAW)
    assert raw_vendor_files(committable(repo)) == []  # ignored and untracked: not committable
    git(repo, "add", "-f", str(raw.relative_to(repo)))
    assert raw_vendor_files(committable(repo)) == ["data/arima-stock-forecasting/raw/AAPL_1d_2015-01-01_2026-10-01.csv"]
    big = repo / "app" / "public" / "data" / "huge.json"
    big.parent.mkdir(parents=True)
    with big.open("wb") as handle:
        handle.truncate(MAX_DATA_FILE_BYTES + 1)
    assert oversized(versions(repo)) == [("app/public/data/huge.json", "disk", MAX_DATA_FILE_BYTES + 1)]


# The four ways past the first version of this test that the milestone-2 review found.


@pytest.mark.parametrize("stage", [False, True])
def test_a_raw_csv_renamed_into_the_data_folder_is_caught_by_its_header(repo, stage):
    path = repo / "app" / "public" / "data" / "aapl_daily.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(FAKE_RAW)
    if stage:
        git(repo, "add", "app/public/data/aapl_daily.csv")
    assert raw_vendor_files(committable(repo)) == []  # its name and folder look harmless
    expected = [("app/public/data/aapl_daily.csv", "disk")] + ([("app/public/data/aapl_daily.csv", "index")] if stage else [])
    assert price_tables(versions(repo)) == expected


def test_a_compressed_snapshot_is_caught_by_its_name(repo):
    path = repo / "AAPL_1d_2015-01-01_2026-10-01.csv.gz"
    path.write_bytes(b"\x1f\x8b not really gzip")
    git(repo, "add", "-f", path.name)
    assert raw_vendor_files(committable(repo)) == ["AAPL_1d_2015-01-01_2026-10-01.csv.gz"]


def test_a_raw_csv_in_another_folder_is_caught_by_its_header(repo):
    path = repo / "notebooks" / "raw_prices.csv"
    path.parent.mkdir()
    path.write_bytes(FAKE_RAW)
    git(repo, "add", "notebooks/raw_prices.csv")
    git(repo, "commit", "-q", "-m", "oops")
    path.unlink()  # gone from the disk, still in HEAD and the index
    assert price_tables(versions(repo)) == [("notebooks/raw_prices.csv", "HEAD"), ("notebooks/raw_prices.csv", "index")]


def test_a_big_staged_blob_is_measured_from_git_not_from_the_disk(repo):
    path = repo / "app" / "public" / "data" / "big.json"
    path.parent.mkdir(parents=True)
    with path.open("wb") as handle:
        handle.truncate(MAX_DATA_FILE_BYTES + 1)
    git(repo, "add", "app/public/data/big.json")
    path.write_bytes(b"{}")  # the working copy is small again; the staged blob is not
    assert oversized(versions(repo)) == [("app/public/data/big.json", "index", MAX_DATA_FILE_BYTES + 1)]
