"""Python's payload readers against the shared corpus app/src/test/fixtures/payload_cases.json.

The app's suite runs the same cases through parseMeta, parsePrices, parseEda, parseStationarity,
parseAcfPacf and parseAicGrid (app/src/lib/contract.payloads.corpus.test.ts). Each case edits a hand-written base payload and
states the verdict both readers must reach, so a rule changed in one language only fails a test.
The review of milestone 1 found 12 disagreements in 34 edge payloads before this corpus existed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from arima_forecasting.artifacts import ArtifactError, compare_exports, read_artifact
from arima_forecasting.contract import SCHEMA_VERSION
from arima_forecasting.payloads import (
    validate_acf_pacf,
    validate_aic_grid,
    validate_eda,
    validate_meta,
    validate_prices,
    validate_stationarity,
)

FIXTURES = Path(__file__).resolve().parent.parent / "app" / "src" / "test" / "fixtures"
CORPUS = json.loads((FIXTURES / "payload_cases.json").read_text(encoding="utf-8"))
VALIDATORS = {
    "meta": validate_meta,
    "prices": validate_prices,
    "eda": validate_eda,
    "stationarity": validate_stationarity,
    "acf_pacf": validate_acf_pacf,
    "aic_grid": validate_aic_grid,
}
BASES = {name: json.loads((FIXTURES / f"{name}.data.json").read_text(encoding="utf-8")) for name in VALIDATORS}


def apply(base: dict, edits: list[dict]) -> dict:
    """A copy of `base` with each edit applied: set the value at a path, or delete it."""
    data = copy.deepcopy(base)
    for edit in edits:
        *parents, last = edit["path"]
        node = data
        for key in parents:
            node = node[key]
        if edit.get("delete"):
            del node[last]
        elif isinstance(node, list) and last == len(node):
            node.append(edit["value"])
        else:
            node[last] = edit["value"]
    return data


def test_the_corpus_is_a_list_of_cases_with_both_verdicts():
    cases = CORPUS["cases"]
    assert len(cases) >= 200
    assert {c["base"] for c in cases} == set(VALIDATORS)
    for base in VALIDATORS:  # every artifact has cases of both verdicts
        assert {c["valid"] for c in cases if c["base"] == base} == {True, False}, base
    assert {c["valid"] for c in cases} == {True, False}
    assert len({c["name"] for c in cases}) == len(cases)


def test_the_corpus_keeps_the_values_only_python_can_see():
    # 4.0 must reach Python as a float and the 401-digit literal as an int, or those cases test nothing.
    values = [e["value"] for c in CORPUS["cases"] for e in c["edits"] if "value" in e]
    assert any(isinstance(v, float) and v == 4.0 for v in values)
    assert any(isinstance(v, int) and v > 10**400 - 1 for v in values)
    assert any(isinstance(v, float) and v == float("inf") for v in values)


@pytest.mark.parametrize("case", CORPUS["cases"], ids=[c["name"] for c in CORPUS["cases"]])
def test_python_agrees_with_the_corpus(case):
    problems = VALIDATORS[case["base"]](apply(BASES[case["base"]], case["edits"]))
    if case["valid"]:
        assert problems == []
    else:
        assert problems, "expected at least one problem"


# --- NaN and Infinity written as JSON tokens -------------------------------------------------------
# JSON has no NaN or Infinity, and the app's JSON.parse refuses the tokens; Python's json.loads reads
# them unless told not to. Each case writes a whole envelope with one bare token in it. Both readers
# must refuse the text at the parsing step (app/src/lib/contract.payloads.corpus.test.ts runs the
# same cases through loadArtifact).

TOKEN_CASES = CORPUS["token_cases"]


def token_text(case: dict) -> str:
    data = copy.deepcopy(BASES[case["base"]])
    *parents, last = case["path"]
    node = data
    for key in parents:
        node = node[key]
    node[last] = "__TOKEN__"
    envelope = {"schema_version": SCHEMA_VERSION, "artifact": case["base"], "generated_at": "2026-10-29T00:00:00Z", "source_commit": "0" * 40, "data": data}
    return json.dumps(envelope).replace('"__TOKEN__"', case["token"])


def test_the_token_cases_hold_bare_tokens_python_would_otherwise_read():
    assert len(TOKEN_CASES) >= 6
    assert {c["token"] for c in TOKEN_CASES} == {"NaN", "Infinity", "-Infinity"}
    for case in TOKEN_CASES:
        text = token_text(case)
        assert f": {case['token']}" in text and f'"{case["token"]}"' not in text
        json.loads(text)  # the default parser accepts it: the case tests something


@pytest.mark.parametrize("case", TOKEN_CASES, ids=[c["name"] for c in TOKEN_CASES])
def test_python_refuses_a_nan_or_infinity_token_when_it_reads_a_file(case, tmp_path):
    name = case["base"]
    (tmp_path / f"{name}.json").write_text(token_text(case), encoding="utf-8")
    with pytest.raises(ArtifactError, match=f"is not valid JSON: {case['token']} is not JSON"):
        read_artifact(tmp_path, name)
    fresh = {"schema_version": SCHEMA_VERSION, "artifact": name, "generated_at": "2026-10-29T00:00:00Z", "source_commit": "0" * 40, "data": BASES[name]}
    problems = compare_exports(tmp_path, {name: fresh})
    assert [p for p in problems if "is not valid JSON" in p and f"{case['token']} is not JSON" in p], problems
