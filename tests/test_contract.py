"""Acceptance tests for contract.py (the Python -> app JSON envelope). Expected values are
literals worked out by hand (arithmetic in comments), never recomputed by the code under test."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import pytest

from arima_forecasting import contract
from arima_forecasting.contract import dumps, make_envelope, validate_envelope

UTC = timezone.utc
SHA = "0123456789abcdef0123456789abcdef01234567"  # 10 + 6 + 10 + 6 + 8 = 40 hex characters
SHA256 = "0123456789abcdef" * 4  # 16 hex characters x 4 = 64: the length in a SHA-256 repository
NOON_UTC = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def good_envelope() -> dict:
    return {
        "schema_version": "1.0.0",
        "artifact": "meta",
        "generated_at": "2026-10-28T12:00:00Z",
        "source_commit": SHA,
        "data": {"ticker": "AAPL"},
    }


# --- 1. make_envelope: happy path --------------------------------------------------------

def test_schema_version_constant():
    # 1.1.0: milestone 1 added the prices and eda artifacts, a minor (additive) change. 1.2.0:
    # milestone 2 added stationarity, acf_pacf and aic_grid, another minor change. 1.3.0: the
    # milestone-2 fix round added fields inside data only (each cell's start and starts_tried, the
    # multi-start fit settings, the outside flags and counts of the correlograms), minor again.
    # 1.4.0: milestone 3 added fit and the three residuals_<id> artifacts, minor.
    assert contract.SCHEMA_VERSION == "1.4.0"


def test_make_envelope_happy_path():
    envelope = make_envelope("meta", {"ticker": "AAPL"}, generated_at=NOON_UTC, source_commit=SHA)
    assert envelope == {
        "schema_version": "1.4.0",
        "artifact": "meta",
        "generated_at": "2026-10-28T12:00:00Z",
        "source_commit": SHA,
        "data": {"ticker": "AAPL"},
    }


def test_make_envelope_output_passes_validate_envelope():
    envelope = make_envelope("meta", {}, generated_at=NOON_UTC, source_commit=SHA + "-dirty")
    assert validate_envelope(envelope) == []


@pytest.mark.parametrize(
    "moment, expected",
    [
        # 12:00 at UTC+05:30 is 12:00 - 5:30 = 06:30 UTC, same day.
        (datetime(2026, 10, 28, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
         "2026-10-28T06:30:00Z"),
        # 23:30 at UTC-05:00 is 23:30 + 5:00 = 28:30 = 04:30 UTC on the NEXT day.
        (datetime(2026, 10, 28, 23, 30, tzinfo=timezone(timedelta(hours=-5))),
         "2026-10-29T04:30:00Z"),
        # 02:15 at UTC+05:30 is 02:15 - 5:30 = -3:15, i.e. 20:45 UTC on the PREVIOUS day.
        (datetime(2026, 10, 28, 2, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))),
         "2026-10-27T20:45:00Z"),
        # 00:00 on 1 January 2027 at UTC+01:00 is 23:00 UTC on 31 December 2026 (year rolls back).
        (datetime(2027, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=1))),
         "2026-12-31T23:00:00Z"),
    ],
)
def test_make_envelope_converts_aware_datetimes_to_utc(moment, expected):
    envelope = make_envelope("meta", {}, generated_at=moment, source_commit="uncommitted")
    assert envelope["generated_at"] == expected


def test_make_envelope_converts_a_named_timezone():
    # 2026-10-28 is before the US clocks go back (2026-11-01), so New York is on daylight time,
    # UTC-04:00. 12:00 + 4:00 = 16:00 UTC.
    moment = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    envelope = make_envelope("meta", {}, generated_at=moment, source_commit="uncommitted")
    assert envelope["generated_at"] == "2026-10-28T16:00:00Z"


def test_make_envelope_drops_microseconds_without_rounding():
    # .999999 s must be cut off, not rounded up to the next second.
    moment = datetime(2026, 10, 28, 12, 0, 0, 999999, tzinfo=UTC)
    envelope = make_envelope("meta", {}, generated_at=moment, source_commit="uncommitted")
    assert envelope["generated_at"] == "2026-10-28T12:00:00Z"


def test_make_envelope_pads_early_years_to_four_digits():
    envelope = make_envelope(
        "meta", {}, generated_at=datetime(5, 1, 2, 3, 4, 5, tzinfo=UTC), source_commit="uncommitted"
    )
    assert envelope["generated_at"] == "0005-01-02T03:04:05Z"


def test_make_envelope_copies_data():
    data = {"a": 1}
    envelope = make_envelope("meta", data, generated_at=NOON_UTC, source_commit="uncommitted")
    data["a"] = 2
    assert envelope["data"] == {"a": 1}


# --- 2. make_envelope: rejections --------------------------------------------------------

def test_make_envelope_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        make_envelope("meta", {}, generated_at=datetime(2026, 10, 28, 12, 0), source_commit=SHA)


class NoOffset(tzinfo):
    """A tzinfo object that is attached to a datetime but knows no offset.

    Python's own documentation calls such a datetime naive: `tzinfo is not None` is true, yet
    `utcoffset()` is None, so converting it to UTC would silently assume the machine's zone.
    """

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return None


def test_make_envelope_rejects_a_tzinfo_that_gives_no_offset():
    moment = datetime(2026, 10, 28, 12, 0, tzinfo=NoOffset())
    # Sanity check: the first half of the awareness test (`tzinfo is None`) cannot catch this.
    assert moment.tzinfo is not None
    assert moment.utcoffset() is None
    with pytest.raises(ValueError, match="timezone-aware"):
        make_envelope("meta", {}, generated_at=moment, source_commit=SHA)


def test_make_envelope_rejects_non_datetime():
    with pytest.raises(ValueError, match="datetime"):
        make_envelope("meta", {}, generated_at="2026-10-28T12:00:00Z", source_commit=SHA)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "artifact",
    ["", "Meta", "1meta", "_meta", "me-ta", "me ta", "meta.json", "meta\n", "méta", "١meta"],
)
def test_make_envelope_rejects_bad_artifact_names(artifact):
    with pytest.raises(ValueError, match="artifact"):
        make_envelope(artifact, {}, generated_at=NOON_UTC, source_commit=SHA)


@pytest.mark.parametrize("artifact", ["meta", "a", "price_history", "oos_forecast_2", "a1"])
def test_make_envelope_accepts_good_artifact_names(artifact):
    assert make_envelope(artifact, {}, generated_at=NOON_UTC, source_commit=SHA)["artifact"] == artifact


@pytest.mark.parametrize(
    "commit",
    [
        "",
        "abc",
        "a" * 39,  # one too short
        "a" * 41,  # one too long
        "a" * 63,  # one short of a SHA-256 id
        "a" * 65,  # one past a SHA-256 id
        "a" * 128,  # two ids in a row
        "A" * 40,  # upper-case hex
        "A" * 64,  # upper-case SHA-256 hex
        "g" * 40,  # not hex
        "a" * 40 + "-DIRTY",
        "a" * 64 + "-DIRTY",
        "a" * 40 + "-dirty-dirty",
        "a" * 40 + "\n",
        "a" * 64 + "\n",
        "a" * 40 + "-dirty\n",
        "Uncommitted",
        "uncommitted-dirty",
        "uncommitted\n",
        None,
    ],
)
def test_make_envelope_rejects_bad_commits(commit):
    with pytest.raises(ValueError, match="source_commit"):
        make_envelope("meta", {}, generated_at=NOON_UTC, source_commit=commit)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "commit",
    [SHA, SHA + "-dirty", "a" * 40, "0" * 40 + "-dirty", "uncommitted", SHA256, SHA256 + "-dirty"],
)
def test_make_envelope_accepts_good_commits(commit):
    assert make_envelope("meta", {}, generated_at=NOON_UTC, source_commit=commit)["source_commit"] == commit


@pytest.mark.parametrize("data", [None, [1, 2], "text", 3])
def test_make_envelope_rejects_non_mapping_data(data):
    with pytest.raises(ValueError, match="data"):
        make_envelope("meta", data, generated_at=NOON_UTC, source_commit=SHA)  # type: ignore[arg-type]


# --- 3. validate_envelope ----------------------------------------------------------------

def test_validate_accepts_a_good_envelope():
    assert validate_envelope(good_envelope()) == []


@pytest.mark.parametrize("obj", [None, [], "meta", 3, [good_envelope()]])
def test_validate_rejects_non_objects(obj):
    problems = validate_envelope(obj)
    assert len(problems) == 1
    assert "JSON object" in problems[0]


@pytest.mark.parametrize("key", ["schema_version", "artifact", "generated_at", "source_commit", "data"])
def test_validate_reports_each_missing_key(key):
    envelope = good_envelope()
    del envelope[key]
    assert validate_envelope(envelope) == [f"missing key: {key}"]


@pytest.mark.parametrize("commit", [SHA256, SHA256 + "-dirty"])
def test_validate_accepts_a_sha256_commit(commit):
    envelope = good_envelope()
    envelope["source_commit"] = commit
    assert validate_envelope(envelope) == []


def test_validate_reports_extra_keys():
    envelope = good_envelope()
    envelope["extra"] = 1
    assert validate_envelope(envelope) == ["unexpected key: extra"]


def test_validate_reports_an_empty_object_as_five_missing_keys():
    assert validate_envelope({}) == [
        "missing key: artifact",
        "missing key: data",
        "missing key: generated_at",
        "missing key: schema_version",
        "missing key: source_commit",
    ]


@pytest.mark.parametrize(
    "field, value",
    [
        ("schema_version", 1),
        ("schema_version", None),
        ("artifact", 7),
        ("generated_at", 1_700_000_000),
        ("source_commit", None),
        ("source_commit", 123),
        ("data", [1, 2]),
        ("data", None),
        ("data", "x"),
    ],
)
def test_validate_catches_wrong_types(field, value):
    envelope = good_envelope()
    envelope[field] = value
    problems = validate_envelope(envelope)
    assert len(problems) == 1
    assert field in problems[0]


@pytest.mark.parametrize(
    "field, value",
    [
        ("schema_version", "1.0"),
        ("schema_version", "v1.0.0"),
        ("schema_version", "1.0.0-beta"),
        ("schema_version", "01.0.0"),
        ("schema_version", ""),
        ("artifact", "Meta"),
        ("artifact", "meta\n"),
        ("artifact", ""),
        ("generated_at", "2026-10-28 12:00:00"),
        ("generated_at", "2026-10-28T12:00:00"),
        ("generated_at", "2026-10-28T12:00:00+00:00"),
        ("generated_at", "2026-10-28T12:00:00.5Z"),
        ("generated_at", "2026-10-28T12:00:00Z\n"),
        ("generated_at", "2026-10-28t12:00:00z"),
        ("generated_at", "2026-13-28T12:00:00Z"),  # there is no month 13
        ("generated_at", "2026-02-30T12:00:00Z"),  # there is no 30 February
        ("generated_at", "2026-10-28T24:00:00Z"),  # there is no hour 24
        ("source_commit", "abc"),
        ("source_commit", "A" * 40),
        ("source_commit", "a" * 63),
        ("source_commit", "a" * 65),
        ("source_commit", "a" * 40 + "-DIRTY"),
        ("source_commit", "a" * 40 + "\n"),
        ("source_commit", "committed"),
    ],
)
def test_validate_catches_bad_formats(field, value):
    envelope = good_envelope()
    envelope[field] = value
    problems = validate_envelope(envelope)
    assert len(problems) == 1
    assert field in problems[0]


def test_validate_returns_all_problems_not_just_the_first():
    envelope = good_envelope()
    envelope["artifact"] = "Bad Name"
    envelope["source_commit"] = "nope"
    envelope["data"] = []
    del envelope["generated_at"]
    envelope["surprise"] = 1
    problems = validate_envelope(envelope)
    # missing generated_at, unexpected surprise, then artifact, source_commit, data
    assert len(problems) == 5
    for needle in ("generated_at", "surprise", "artifact", "source_commit", "data"):
        assert any(needle in problem for problem in problems), needle


@pytest.mark.parametrize("version", ["1.0.0", "1.2.0", "1.0.1", "1.10.3", "1.0.100"])
def test_validate_accepts_any_minor_or_patch_of_major_1(version):
    envelope = good_envelope()
    envelope["schema_version"] = version
    assert validate_envelope(envelope) == []


@pytest.mark.parametrize("version", ["2.0.0", "0.9.0", "0.0.0", "10.0.0", "11.2.3", "100.0.0"])
def test_validate_rejects_other_major_versions(version):
    # "10.0.0" starts with the character "1" but is major 10, so it must be refused too.
    envelope = good_envelope()
    envelope["schema_version"] = version
    problems = validate_envelope(envelope)
    assert len(problems) == 1
    assert "major" in problems[0]


# --- 4. dumps ----------------------------------------------------------------------------

def test_dumps_exact_text():
    # Keys sorted at every level (artifact < data < generated_at < schema_version <
    # source_commit, and a < b inside data), 2-space indent, one list item per line, and
    # exactly one trailing newline.
    envelope = {
        "source_commit": "uncommitted",
        "schema_version": "1.0.0",
        "generated_at": "2026-10-28T12:00:00Z",
        "data": {"b": [1, 2], "a": 1},
        "artifact": "meta",
    }
    assert dumps(envelope) == (
        "{\n"
        '  "artifact": "meta",\n'
        '  "data": {\n'
        '    "a": 1,\n'
        '    "b": [\n'
        "      1,\n"
        "      2\n"
        "    ]\n"
        "  },\n"
        '  "generated_at": "2026-10-28T12:00:00Z",\n'
        '  "schema_version": "1.0.0",\n'
        '  "source_commit": "uncommitted"\n'
        "}\n"
    )


def test_dumps_is_independent_of_insertion_order():
    forward = {"data": {"x": 1, "y": 2}, "artifact": "meta"}
    backward = {"artifact": "meta", "data": {"y": 2, "x": 1}}
    assert dumps(forward) == dumps(backward)


def test_dumps_round_trips_through_json():
    envelope = make_envelope("meta", {"n": 3, "xs": [0.5, -1.25]}, generated_at=NOON_UTC, source_commit=SHA)
    assert json.loads(dumps(envelope)) == envelope


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_dumps_refuses_non_finite_floats(bad):
    # NaN and Infinity are not JSON; the browser's JSON.parse would reject the whole file.
    envelope = make_envelope("meta", {"value": bad}, generated_at=NOON_UTC, source_commit=SHA)
    with pytest.raises(ValueError, match="not JSON compliant"):
        dumps(envelope)


def test_dumps_refuses_non_finite_floats_nested_in_lists():
    envelope = make_envelope(
        "meta", {"series": [1.0, [2.0, float("nan")]]}, generated_at=NOON_UTC, source_commit=SHA
    )
    with pytest.raises(ValueError, match="not JSON compliant"):
        dumps(envelope)


def test_dumps_accepts_large_finite_floats():
    # The guard must reject only non-finite values, not merely big ones.
    envelope = make_envelope("meta", {"big": 1e308}, generated_at=NOON_UTC, source_commit=SHA)
    assert json.loads(dumps(envelope))["data"]["big"] == 1e308


# --- 5. dumps: integers a browser cannot read exactly ------------------------------------

# JavaScript numbers are 64-bit floats, exact for whole numbers up to 2**53 - 1. Typed as literals:
# 2**53 = 9_007_199_254_740_992, so the largest safe integer is one less.
LARGEST_SAFE = 9_007_199_254_740_991
FIRST_UNSAFE = 9_007_199_254_740_992

# Where the integer sits: top of data, inside a list, inside a tuple, deep inside dicts and lists.
PLACEMENTS = {
    "in a dict": (lambda n: {"n": n}, "envelope.data.n"),
    "in a list": (lambda n: {"xs": [1, n]}, "envelope.data.xs[1]"),
    "in a tuple": (lambda n: {"xs": (n,)}, "envelope.data.xs[0]"),
    "nested": (lambda n: {"a": {"b": [{"c": 0}, {"c": n}]}}, "envelope.data.a.b[1].c"),
}


def with_data(data):
    return make_envelope("meta", data, generated_at=NOON_UTC, source_commit=SHA)


@pytest.mark.parametrize("place", PLACEMENTS)
@pytest.mark.parametrize("n", [LARGEST_SAFE, -LARGEST_SAFE, 0, 1, -1])
def test_dumps_accepts_integers_up_to_the_largest_a_browser_reads_exactly(n, place):
    build, _ = PLACEMENTS[place]
    text = dumps(with_data(build(n)))
    assert str(n) in text
    assert json.loads(text)["data"] == json.loads(json.dumps(build(n)))


@pytest.mark.parametrize("place", PLACEMENTS)
@pytest.mark.parametrize("n", [FIRST_UNSAFE, -FIRST_UNSAFE, 10**18, -(10**18), 10**309])
def test_dumps_refuses_integers_a_browser_would_round(n, place):
    # 10**309 is also the case where JavaScript does not merely round but reads Infinity.
    build, path = PLACEMENTS[place]
    with pytest.raises(ValueError, match="JavaScript") as caught:
        dumps(with_data(build(n)))
    assert path in str(caught.value)  # says where the integer is


def test_dumps_names_the_integer_it_refuses():
    with pytest.raises(ValueError, match="9007199254740992"):
        dumps(with_data({"n": FIRST_UNSAFE}))


def test_dumps_does_not_print_a_huge_integer_in_full():
    with pytest.raises(ValueError) as caught:
        dumps(with_data({"n": 10**309}))
    assert len(str(caught.value)) < 200


def test_dumps_ignores_booleans_and_floats_that_equal_large_integers():
    # True is an int in Python but JSON writes it as `true`; a float is a 64-bit float on both
    # sides, so 2.0**60 survives the trip exactly.
    text = dumps(with_data({"flag": True, "big_float": 2.0**60, "small": 3}))
    assert json.loads(text)["data"] == {"flag": True, "big_float": 2.0**60, "small": 3}


def test_dumps_reports_a_circular_reference_as_json_does():
    # The size check walks the structure, so it must come after json has had its look: walking a
    # loop first would end in a RecursionError instead of this ValueError.
    data: dict = {}
    data["me"] = data
    with pytest.raises(ValueError, match="Circular reference"):
        dumps(with_data(data))
