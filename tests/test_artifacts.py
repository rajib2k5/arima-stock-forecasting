"""Tests for artifacts.py: reading an artifact back and finding where two exports differ."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arima_forecasting.artifacts import ArtifactError, compare_exports, first_difference, read_artifact

# An artifact name with no payload validator, so only the envelope rules apply to it.
GOOD = {
    "schema_version": "1.1.0",
    "artifact": "notes",
    "generated_at": "2026-10-29T12:00:00Z",
    "source_commit": "uncommitted",
    "data": {"x": 1},
}
FIXTURES = Path(__file__).resolve().parent.parent / "app" / "src" / "test" / "fixtures"


@pytest.mark.parametrize(
    "old, new, expected",
    [
        ({"a": 1}, {"a": 1}, None),
        ({"a": 1}, {"a": 2}, "d.a: 1 != 2"),
        ({"a": 1}, {"a": 1.0}, "d.a: 1 != 1.0"),  # an int turning into a float is a change in JSON
        ({"a": 1}, {}, "d['a']: no longer produced"),  # a key of the committed file is quoted (contract.shown)
        ({}, {"a": 1}, "d.a: missing in the committed file"),
        ({"r": [1, 2]}, {"r": [1, 2, 3]}, "d.r: 2 items committed, 3 regenerated"),
        ({"r": [1, {"b": None}]}, {"r": [1, {"b": 0.5}]}, "d.r[1].b: None != 0.5"),
        ({"s": "x" * 81}, {"s": "y"}, "d.s: '" + "x" * 80 + "'… (81 characters) != 'y'"),
        ({"s": [[[]]] * 9}, {"s": "y"}, "d.s: an array of 9 != 'y'"),
    ],
)
def test_first_difference_names_the_path_of_the_first_change(old, new, expected):
    assert first_difference(old, new, "d") == expected


def test_compare_exports_compares_data_but_not_time_or_commit(tmp_path):
    (tmp_path / "notes.json").write_text(json.dumps({**GOOD, "generated_at": "1970-01-01T00:00:00Z", "source_commit": "a" * 40}))
    assert compare_exports(tmp_path, {"notes": GOOD}) == []
    assert compare_exports(tmp_path, {"notes": {**GOOD, "data": {"x": 2}}}) == ["notes: data.x: 1 != 2"]


def test_read_artifact_returns_a_valid_envelope(tmp_path):
    (tmp_path / "notes.json").write_text(json.dumps(GOOD))
    assert read_artifact(tmp_path, "notes") == GOOD


@pytest.mark.parametrize(
    "name, text, message",
    [
        ("notes", None, "does not exist"),
        ("notes", "{oops", "not valid JSON"),
        ("notes", json.dumps({**GOOD, "schema_version": "2.0.0"}), "has a major version other than 1"),
        ("notes", json.dumps({**GOOD, "artifact": "prices"}), "artifact is 'prices', expected 'notes'"),
        ("prices", json.dumps({**GOOD, "artifact": "prices"}), "data.ticker: missing"),
        ("meta", json.dumps({**GOOD, "artifact": "meta"}), "data.project: missing"),
    ],
)
def test_read_artifact_refuses_missing_broken_or_invalid_files(tmp_path, name, text, message):
    if text is not None:
        (tmp_path / f"{name}.json").write_text(text)
    with pytest.raises(ArtifactError, match=message):
        read_artifact(tmp_path, name)


def test_find_app_data_walks_up_from_a_subfolder(tmp_path):
    from arima_forecasting.artifacts import find_app_data

    (tmp_path / "app" / "public" / "data").mkdir(parents=True)
    (tmp_path / "notebooks").mkdir()
    assert find_app_data(tmp_path / "notebooks") == (tmp_path / "app" / "public" / "data").resolve()
    assert find_app_data(tmp_path) == (tmp_path / "app" / "public" / "data").resolve()
    (tmp_path / "elsewhere").mkdir()
    lonely = tmp_path / "elsewhere"
    # tmp_path itself holds app/public/data, so search from a sibling tree that has none above it
    # except tmp_path: that one is found too, which is the point of walking upward.
    assert find_app_data(lonely) == (tmp_path / "app" / "public" / "data").resolve()


def test_find_app_data_says_so_when_there_is_none(tmp_path):
    from arima_forecasting.artifacts import find_app_data

    with pytest.raises(ArtifactError, match="no app/public/data"):
        find_app_data(tmp_path)


@pytest.mark.parametrize("held", [5, ["nope"], [1], ["prices", "prices"], ["meta"]], ids=["5", "unlisted", "number", "twice", "meta"])
def test_read_artifact_refuses_a_meta_whose_held_artifacts_the_app_would_refuse(tmp_path, held):
    # Found by the milestone-1 re-review: read_artifact accepted these while parseMeta refused them.
    data = json.loads((FIXTURES / "meta.data.json").read_text())
    (tmp_path / "meta.json").write_text(json.dumps({**GOOD, "artifact": "meta", "data": {**data, "held_artifacts": held}}))
    with pytest.raises(ArtifactError, match="held_artifacts"):
        read_artifact(tmp_path, "meta")
    (tmp_path / "meta.json").write_text(json.dumps({**GOOD, "artifact": "meta", "data": data}))
    assert read_artifact(tmp_path, "meta")["data"] == data  # sanity: the base itself is accepted
