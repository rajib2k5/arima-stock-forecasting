"""Look for real Yahoo rows copied into the repository. Local only.

    uv run python tools/licensing/scan_real_rows.py            # data root from $VOL_DATA_DIR
    uv run python tools/licensing/scan_real_rows.py --root DIR

Adapted from implied-vol-forecasting's tools/licensing/scan_real_rows.py. It reads every raw
snapshot under ``ROOT/arima-stock-forecasting/raw*/*.csv`` and every text file git would commit
(``git ls-files -co --exclude-standard``). A repository line is flagged when:

1. it is at least 12 characters long (after stripping) and appears verbatim in a raw file;
2. it contains a whole raw data row (a raw line with a digit, at least 12 characters);
3. it holds a number with 2 or more decimals and 3 or more significant digits (or an integer of 6
   or more digits, like a volume) that equals, rounded to the number's own decimals, a raw value of
   a date named near it: on the same line within ``NEAR_CHARS`` characters, or on a line up to
   ``NEAR_LINES`` lines away;
4. it holds an integer of 6 or more digits equal to the size of a raw file, or their total;
5. it holds a 64-hex string equal to a raw snapshot's SHA-256.

Rules 1 to 3 find copied prices. Rules 4 and 5 find provenance (a size, a hash), which is not
price data; they are reported with their rule number so the two kinds can be told apart.

It prints only ``file:line`` and the rule number, never the text that matched. Exit 0 clean,
1 something flagged by rules 1 to 3, 2 no raw data to compare with. It is not a test: a fresh clone
has no raw data. Run it before every commit that touches data, docs or fixtures.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from arima_forecasting import config

MIN_LINE = 12
NEAR_CHARS = 120  # rule 3, same line: a one-line JSON file names many dates far from any value
NEAR_LINES = 3  # rule 3, other lines: a dict or a table row spread over a few lines
_US_DATE = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_BIG_INT = re.compile(r"(?<![\w.,])\d{1,3}(?:[,_ ]\d{3})+(?![\w.,]?\d)|(?<![\w.,])\d{6,}(?![\w.])")
_SHA = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])")
_RAW_ALPHABET = re.compile(r"[0-9A-Za-z/.,:^\- ]+")


def _dates_in(text: str) -> list[tuple[int, int, date]]:
    """``(start, end, date)`` for every M/D/Y or ISO date token in ``text`` that is a real calendar date."""
    found = []
    for pattern, order in ((_US_DATE, (2, 0, 1)), (_ISO_DATE, (0, 1, 2))):
        for match in pattern.finditer(text):
            parts = [int(g) for g in match.groups()]
            try:
                found.append((match.start(), match.end(), date(parts[order[0]], parts[order[1]], parts[order[2]])))
            except ValueError:
                continue
    return found


def _significant_digits(token: str) -> int:
    digits = token.lstrip("-").replace(".", "").lstrip("0")
    return len(digits)


class RawIndex:
    """What rules 1 to 5 compare against, built from the raw snapshots."""

    def __init__(self, root: Path):
        self.files = sorted((root / config.PROJECT_SLUG).glob("raw*/*.csv"))
        self.texts: list[str] = []
        self.rows_by_prefix: dict[str, list[str]] = defaultdict(list)
        self.values_by_date: dict[date, set[float]] = defaultdict(set)
        self.sizes: set[int] = set()
        self.shas: set[str] = set()
        for path in self.files:
            blob = path.read_bytes()
            text = blob.decode("utf-8", errors="replace")
            self.texts.append(text)
            self.sizes.add(len(blob))
            self.shas.add(hashlib.sha256(blob).hexdigest())
            for line in text.splitlines():
                line = line.strip()
                dates = _dates_in(line)
                if not dates or dates[0][0] != 0:
                    continue  # a header, or not a data row
                day = dates[0][2]
                if len(line) >= MIN_LINE:
                    self.rows_by_prefix[line[: dates[0][1]]].append(line)
                for token in line[dates[0][1] :].split(","):
                    try:
                        value = float(token)
                    except ValueError:
                        continue
                    if math.isfinite(value):
                        self.values_by_date[day].add(value)
        self.sizes.add(sum(path.stat().st_size for path in self.files))
        self.joined = "\n".join(self.texts)

    def dated_value(self, line: str, nearby: list[date]) -> bool:
        """Rule 3 for one line: a number equal to a raw value of a date on this line or nearby."""
        dates = _dates_in(line)
        for match in _NUMBER.finditer(line):
            token = match.group()
            decimals = len(token.split(".")[1]) if "." in token else 0
            if any(s <= match.start() < e for s, e, _ in dates):
                continue  # part of a date
            if not ((decimals >= 2 and _significant_digits(token) >= 3) or (decimals == 0 and len(token.lstrip("-")) >= 6)):
                continue  # one decimal matches a real value of some date by chance far too often
            days = [d for s, e, d in dates if min(abs(match.start() - e), abs(s - match.end())) <= NEAR_CHARS] + nearby
            number = float(token)
            for day in days:
                if any(round(v, decimals) == number for v in self.values_by_date.get(day, ())):
                    return True
        return False

    def hits(self, line: str) -> int:
        """The first of rules 1, 2, 4 and 5 that flags the line, or 0 (rule 3: ``dated_value``)."""
        stripped = line.strip()
        # Rule 1: the whole line is in a raw file. Raw files hold only this alphabet, so anything
        # else cannot match and the expensive search is skipped.
        if len(stripped) >= MIN_LINE and _RAW_ALPHABET.fullmatch(stripped) and stripped in self.joined:
            return 1
        dates = _dates_in(line)
        for start, end, day in dates:
            # Rule 2: a whole raw row starts at this date.
            for row in self.rows_by_prefix.get(line[start:end], ()):
                if line.startswith(row, start):
                    return 2
        # Rule 4: a raw file size, or a total of them.
        for match in _BIG_INT.finditer(line):
            if int(re.sub(r"[,_ ]", "", match.group())) in self.sizes:
                return 4
        # Rule 5: a raw snapshot's hash.
        return 5 if any(token in self.shas for token in _SHA.findall(line)) else 0


def repo_text_files(repo: Path) -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=repo, capture_output=True, check=True
    ).stdout.split(b"\0")
    return [repo / name.decode() for name in listed if name and (repo / name.decode()).is_file()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, help="the data root (default: ROOT from VOL_DATA_DIR)")
    args = parser.parse_args(argv)
    root = (args.root or config.data_root()).expanduser()
    index = RawIndex(root)
    if not index.files:
        print(f"error: no raw snapshots under {root / config.PROJECT_SLUG}; nothing to compare with", file=sys.stderr)
        return 2
    repo = config.REPO_ROOT
    flagged = 0
    provenance = 0
    scanned = 0
    for path in repo_text_files(repo):
        blob = path.read_bytes()
        if b"\0" in blob[:8192]:
            continue  # binary
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        lines = text.splitlines()
        # Dates per line, for rule 3's neighbourhood; very long lines (minified JSON) lend none.
        line_dates = [[d for _, _, d in _dates_in(line)] if len(line) <= 300 else [] for line in lines]
        for i, line in enumerate(lines):
            nearby = [d for j in range(max(0, i - NEAR_LINES), min(len(lines), i + NEAR_LINES + 1)) if j != i for d in line_dates[j]]
            rule = index.hits(line) or (3 if index.dated_value(line, nearby) else 0)
            if rule:
                print(f"{path.relative_to(repo)}:{i + 1} rule {rule}")
                if rule in (4, 5):
                    provenance += 1
                else:
                    flagged += 1
    note = f"; {provenance} provenance line(s) (rules 4-5)" if provenance else ""
    if flagged:
        print(f"{flagged} price line(s) flagged in {scanned} text file(s) against {len(index.files)} raw snapshot(s){note}")
        return 1
    print(f"clean: 0 price lines flagged in {scanned} text file(s) against {len(index.files)} raw snapshot(s){note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
