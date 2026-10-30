"""The contract between the Python side and the web app: one JSON "envelope" around every file.

Python writes JSON files, the browser reads them. Both sides must agree on the outer shape, so
the app can check what it received before it draws a single chart:

    {"schema_version": "1.0.0", "artifact": "meta", "generated_at": "2026-10-28T12:00:00Z",
     "source_commit": "<sha>|<sha>-dirty|uncommitted", "data": {...}}

`<sha>` is 40 lowercase hex characters (a SHA-1 repository) or 64 (a SHA-256 repository).

The envelope's top level is closed: exactly these five keys, and an unknown key is an error, on
this side and in the app (app/src/lib/contract.ts). Adding an envelope field is therefore a major
version bump. The `data` object is open: its own fields may grow in a minor release.
app/src/test/fixtures/envelope_cases.json is one list of envelopes with their expected verdicts;
tests/test_contract_corpus.py and the app's tests both run it, so the two copies of these rules
cannot drift apart unnoticed.

Everything here is pure: no files, no clock, no git. The caller passes the time and the commit.
"""

from __future__ import annotations

import heapq
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

# Semver. A major bump (2.0.0) means a breaking change the app must refuse. Minor and patch
# bumps (1.1.0, 1.0.1) only add things, so an app that understands 1.x can still read them.
SCHEMA_VERSION = "1.5.0"
SUPPORTED_MAJOR = 1

ENVELOPE_KEYS = frozenset({"schema_version", "artifact", "generated_at", "source_commit", "data"})

# We match with fullmatch(), never with "^...$" and match(). In Python, "$" also matches just
# before a trailing newline, so "meta\n" would slip through a "^...$" pattern. [0-9] is spelled
# out because "\d" also accepts digits from other scripts.
_ARTIFACT = re.compile(r"[a-z][a-z0-9_]*")
_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})(-dirty)?")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
UNCOMMITTED = "uncommitted"

# JavaScript numbers are 64-bit floats, which hold a whole number exactly only up to 2**53 - 1.
# JSON.parse rounds a bigger integer to the nearest float (and 10**309 becomes Infinity).
MAX_SAFE_INTEGER = 2**53 - 1

# A reader reports at most MAX_PROBLEMS problems per file, then one more that says it stopped
# (more_problems), and stops reading: the bound is on the file, not on each list, so lists inside
# lists cannot multiply it (100 KDEs of 10,000 empty points made 3,000,000 problems before it). The
# app's contract.ts holds the same number and the same words (contract.md, "Bounds").
MAX_PROBLEMS = 200

# A message quotes a value read from a file only through shown(), in both readers: a string up to
# SHOWN_CHARS characters, a list or an object only when it has at most SHOWN_ITEMS small, flat
# entries, and anything else by its size alone. shown() never walks into a nested value, so a value
# of any length or depth (a 50 MB string, a 100,000-deep array) gives a short message, quickly.
SHOWN_CHARS = 80
SHOWN_ITEMS = 8


def more_problems(root: str) -> str:
    """The problem that ends a list cut at MAX_PROBLEMS (the same words as the app's)."""
    return f"{root}: more than {MAX_PROBLEMS} problems; a reader reports the first {MAX_PROBLEMS} and stops"


def _small(value: object) -> bool:
    return (
        value is None
        or isinstance(value, (bool, float))
        or (isinstance(value, int) and abs(value) <= MAX_SAFE_INTEGER)
        or (isinstance(value, str) and len(value) <= SHOWN_CHARS // 2)
    )


def shown(value: object) -> str:
    """A value from a file as a message quotes it: short whatever its size, and never recursive."""
    if isinstance(value, str):
        if len(value) <= SHOWN_CHARS:
            return repr(value)
        return f"{value[:SHOWN_CHARS]!r}… ({len(value)} characters)"
    if value is None or isinstance(value, (bool, float)):
        return repr(value)
    if isinstance(value, int):
        if abs(value) <= MAX_SAFE_INTEGER:
            return repr(value)
        # str() of an int of more than 4,300 digits raises (json.loads refuses one too); bits never do.
        return f"an integer of {value.bit_length()} bits"
    if isinstance(value, list):
        if len(value) <= SHOWN_ITEMS and all(_small(item) for item in value):
            return repr(value)
        return f"an array of {len(value)}"
    if isinstance(value, dict):
        if len(value) <= SHOWN_ITEMS and all(isinstance(k, str) and len(k) <= SHOWN_CHARS // 2 and _small(v) for k, v in value.items()):
            return repr(value)
        return f"an object with {len(value)} keys"
    return type(value).__name__


def _is_artifact(value: object) -> bool:
    return isinstance(value, str) and _ARTIFACT.fullmatch(value) is not None


def _is_commit(value: object) -> bool:
    return isinstance(value, str) and (value == UNCOMMITTED or _COMMIT.fullmatch(value) is not None)


def _is_timestamp(value: object) -> bool:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        return False
    # The pattern only checks the shape; strptime also rejects dates that do not exist (month 13).
    try:
        datetime.strptime(value, _TIMESTAMP_FORMAT)
    except ValueError:
        return False
    return True


def make_envelope(
    artifact: str,
    data: Mapping[str, Any],
    *,
    generated_at: datetime,
    source_commit: str,
) -> dict[str, Any]:
    """Wrap `data` in the envelope, or raise ValueError saying what is wrong with the inputs."""
    if not _is_artifact(artifact):
        raise ValueError(f"artifact {artifact!r} must match [a-z][a-z0-9_]*")
    if not isinstance(data, Mapping):
        raise ValueError(f"data must be a mapping, got {type(data).__name__}")
    if not isinstance(generated_at, datetime):
        raise ValueError(f"generated_at must be a datetime, got {type(generated_at).__name__}")
    # A naive datetime has no zone, so it could mean any hour of the day. We refuse to guess.
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware (it has no tzinfo)")
    if not _is_commit(source_commit):
        raise ValueError(
            f"source_commit {source_commit!r} must be 40 or 64 lowercase hex characters, "
            f"optionally followed by '-dirty', or 'uncommitted'"
        )

    # Always store UTC so the same instant gives the same text on every machine. timespec
    # "seconds" drops the microseconds (it truncates; it does not round up).
    utc = generated_at.astimezone(timezone.utc)
    stamp = utc.isoformat(timespec="seconds").removesuffix("+00:00") + "Z"

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": artifact,
        "generated_at": stamp,
        "source_commit": source_commit,
        "data": dict(data),
    }


def validate_envelope(obj: object) -> list[str]:
    """Return every problem found in `obj`. An empty list means the envelope is valid.

    tools/export_app_data.py runs this on the finished envelope before it writes anything, and
    the tests use it to check what the tool wrote. (The app does not call it; it has its own
    TypeScript parser in app/src/lib/contract.ts.) It collects all problems instead of stopping
    at the first one: you see the whole list of things to fix in one run.
    """
    if not isinstance(obj, dict):
        return [f"envelope must be a JSON object, got {type(obj).__name__}"]

    problems: list[str] = []
    for key in sorted(ENVELOPE_KEYS - obj.keys()):
        problems.append(f"missing key: {key}")
    # Only the first MAX_PROBLEMS + 1 unexpected keys, in order, are ever formatted: a file may have a
    # million, and the list is cut at MAX_PROBLEMS below.
    for key in heapq.nsmallest(MAX_PROBLEMS + 1, obj.keys() - ENVELOPE_KEYS, key=str):
        problems.append(f"unexpected key: {shown(key)}")

    if "schema_version" in obj:
        version = obj["schema_version"]
        match = _SEMVER.fullmatch(version) if isinstance(version, str) else None
        if match is None:
            problems.append(f"schema_version {shown(version)} must be a semver string like '1.0.0'")
        elif match.group(1) != str(SUPPORTED_MAJOR):
            # Compare the whole major: "10.0.0" starts with "1" but is a different major. The pattern
            # allows no leading zero, so the text comparison is exact, and int() is never asked to
            # read a major of more than 4,300 digits (it raises).
            problems.append(
                f"schema_version {shown(version)} has a major version other than {SUPPORTED_MAJOR}; "
                f"this code understands major {SUPPORTED_MAJOR} only"
            )
    if "artifact" in obj and not _is_artifact(obj["artifact"]):
        problems.append(f"artifact {shown(obj['artifact'])} must be a string matching [a-z][a-z0-9_]*")
    if "generated_at" in obj and not _is_timestamp(obj["generated_at"]):
        problems.append(
            f"generated_at {shown(obj['generated_at'])} must be a real UTC time written "
            f"YYYY-MM-DDTHH:MM:SSZ"
        )
    if "source_commit" in obj and not _is_commit(obj["source_commit"]):
        problems.append(
            f"source_commit {shown(obj['source_commit'])} must be 40 or 64 lowercase hex characters, "
            f"optionally followed by '-dirty', or 'uncommitted'"
        )
    if "data" in obj and not isinstance(obj["data"], dict):
        problems.append(f"data must be a JSON object, got {type(obj['data']).__name__}")
    return problems if len(problems) <= MAX_PROBLEMS else [*problems[:MAX_PROBLEMS], more_problems("envelope")]


def _check_safe_integers(value: object, path: str) -> None:
    """Raise ValueError at the first int the browser could not read back exactly."""
    if isinstance(value, bool):  # True and False are ints in Python, but JSON writes them as words
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            digits = str(value)
            shown = digits if len(digits) <= 24 else digits[:20] + "..."
            raise ValueError(
                f"{path}: integer {shown} is outside +-(2**53 - 1) = +-{MAX_SAFE_INTEGER}, so "
                f"JavaScript would read it inexactly; write it as a string instead"
            )
    elif isinstance(value, dict):
        # Keys are not checked: JSON keys are text, and text survives exactly.
        for key, item in value.items():
            _check_safe_integers(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_safe_integers(item, f"{path}[{index}]")


def dumps(envelope: Mapping[str, Any]) -> str:
    """Serialise to the exact text we write to disk: sorted keys, 2-space indent, final newline.

    `allow_nan=False` is deliberate. Python would happily write NaN or Infinity, but those are
    not valid JSON, and the browser's JSON.parse rejects the entire file when it meets one. A
    float('nan') (a failed calculation, say) must stop the export here with an error, not turn
    into a file that breaks the page.

    `sort_keys=True` makes the output independent of dict insertion order, so the same data
    always produces the same bytes and a git diff shows only real changes.

    An integer outside +-(2**53 - 1) raises ValueError too: Python writes it exactly, but the
    browser would round it to the nearest 64-bit float without telling anyone. The file is
    serialised first, so a NaN or a circular reference is reported by json itself before we
    walk the structure.
    """
    text = json.dumps(envelope, sort_keys=True, indent=2, allow_nan=False) + "\n"
    _check_safe_integers(envelope, "envelope")
    return text
