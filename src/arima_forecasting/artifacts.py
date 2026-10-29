"""Read exported artifacts back, and compare two exports.

Used by three callers: the export tool's --check mode (are the committed files current?), the
notebooks (which read the committed files, so they run without the raw snapshot), and the tests.
Reading files is the only I/O here; the comparison itself is pure.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from arima_forecasting.contract import validate_envelope
from arima_forecasting.payloads import PAYLOAD_VALIDATORS

# The parts of an envelope a check compares. generated_at and source_commit are left out on
# purpose: they legitimately differ between the export run and the check run (ADR-0001).
COMPARED_KEYS = ("schema_version", "artifact", "data")


class ArtifactError(ValueError):
    """A file is missing, is not JSON, or breaks the contract."""


def _refuse_constant(token: str) -> None:
    raise ValueError(f"{token} is not JSON (the app's JSON.parse refuses it)")


def loads_strict(text: str) -> Any:
    """json.loads as the app's JSON.parse reads a file: NaN, Infinity and -Infinity are refused.

    Python's json.loads accepts those three tokens by default, so without this a file the app
    cannot even parse could pass every Python check (an unknown key is ignored by both readers,
    so a NaN under one was the milestone-2 review's example). Raises ValueError, which includes
    json.JSONDecodeError.
    """
    return json.loads(text, parse_constant=_refuse_constant)


def find_app_data(start: Path | None = None) -> Path:
    """The repo's app/public/data folder, found from `start` (default: the current folder) upward.

    A notebook may run from the repo root or from notebooks/; both find the same folder.
    """
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        candidate = folder / "app" / "public" / "data"
        if candidate.is_dir():
            return candidate
    raise ArtifactError(f"no app/public/data folder in {here} or any folder above it")


def read_artifact(folder: Path, name: str) -> dict[str, Any]:
    """Load `<folder>/<name>.json` and check its envelope and payload, or raise ArtifactError."""
    path = folder / f"{name}.json"
    if not path.is_file():
        raise ArtifactError(f"{path} does not exist")
    try:
        envelope = loads_strict(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ArtifactError(f"{path} is not valid JSON: {error}") from error
    problems = validate_envelope(envelope)
    if not problems and envelope["artifact"] != name:
        problems = [f"artifact is {envelope['artifact']!r}, expected {name!r}"]
    if not problems and name in PAYLOAD_VALIDATORS:
        problems = PAYLOAD_VALIDATORS[name](envelope["data"])
    if problems:
        raise ArtifactError(f"{path}: " + "; ".join(problems))
    return envelope


def table_from_prices(data: Mapping[str, Any]) -> pd.DataFrame:
    """The price table (close_usd, log_close, segment by date) rebuilt from a `prices` payload.

    JSON stores each float with Python's shortest round-trip repr, so these are the very floats
    the export computed, and eda_payload(table_from_prices(prices)) reproduces eda.json exactly.
    """
    rows = data["rows"]
    return pd.DataFrame(
        {
            "close_usd": [row["close_usd"] for row in rows],
            "log_close": [row["log_close"] for row in rows],
            "segment": [row["segment"] for row in rows],
        },
        index=pd.DatetimeIndex([row["date"] for row in rows], name="date"),
    )


def _short(value: object) -> str:
    text = json.dumps(value, sort_keys=True)
    return text if len(text) <= 60 else text[:57] + "..."


def first_difference(old: object, new: object, path: str) -> str | None:
    """Where two JSON values first differ, as 'path: old != new', or None if they are equal.

    Types count: 1 and 1.0 are different JSON (an integer field turning into a float is a change).
    """
    if type(old) is not type(new):
        return f"{path}: {_short(old)} != {_short(new)}"
    if isinstance(old, dict):
        assert isinstance(new, dict)
        for key in sorted(old.keys() | new.keys()):
            if key not in old:
                return f"{path}.{key}: missing in the committed file"
            if key not in new:
                return f"{path}.{key}: no longer produced"
            found = first_difference(old[key], new[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(old, list):
        assert isinstance(new, list)
        for index, (a, b) in enumerate(zip(old, new)):
            found = first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
        if len(old) != len(new):
            return f"{path}: {len(old)} items committed, {len(new)} regenerated"
        return None
    if old != new:
        return f"{path}: {_short(old)} != {_short(new)}"
    return None


def compare_exports(folder: Path, regenerated: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Compare freshly built envelopes with the files in `folder`. Returns one line per problem.

    Checks the set of files too: a stale extra file (an artifact no longer exported) is a problem,
    because the app's real-data test would read it.
    """
    problems: list[str] = []
    on_disk = sorted(path.stem for path in folder.glob("*.json"))
    for extra in sorted(set(on_disk) - set(regenerated)):
        problems.append(f"{extra}: {folder / (extra + '.json')} is not produced by this export")
    for name, envelope in regenerated.items():
        path = folder / f"{name}.json"
        if not path.is_file():
            problems.append(f"{name}: {path} is missing")
            continue
        try:
            committed = loads_strict(path.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append(f"{name}: {path} is not valid JSON ({error})")
            continue
        if not isinstance(committed, dict):
            problems.append(f"{name}: {path} is not a JSON object")
            continue
        # The committed file must also be one the app would accept. generated_at and
        # source_commit are not compared below, but a malformed one (or an extra top-level key)
        # would make the app refuse the file, so the envelope and payload rules are checked here.
        invalid = validate_envelope(committed)
        if not invalid and committed["artifact"] != name:
            invalid = [f"artifact is {committed['artifact']!r}, expected {name!r}"]
        if not invalid and name in PAYLOAD_VALIDATORS:
            invalid = PAYLOAD_VALIDATORS[name](committed["data"])
        problems += [f"{name}: committed file breaks the contract: {problem}" for problem in invalid]
        # Compare like with like: the regenerated envelope as it would read back from disk.
        fresh = json.loads(json.dumps(envelope, sort_keys=True, allow_nan=False))
        for key in COMPARED_KEYS:
            found = first_difference(committed.get(key), fresh[key], key)
            if found:
                problems.append(f"{name}: {found}")
    return problems
