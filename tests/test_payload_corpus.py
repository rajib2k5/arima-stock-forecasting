"""Python's payload readers against the shared corpus app/src/test/fixtures/payload_cases.json.

The app's suite runs the same cases through parseMeta, parsePrices and parseEda
(app/src/lib/contract.payloads.corpus.test.ts). Each case edits a hand-written base payload and
states the verdict both readers must reach, so a rule changed in one language only fails a test.
The review of milestone 1 found 12 disagreements in 34 edge payloads before this corpus existed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from arima_forecasting.payloads import validate_eda, validate_meta, validate_prices

FIXTURES = Path(__file__).resolve().parent.parent / "app" / "src" / "test" / "fixtures"
CORPUS = json.loads((FIXTURES / "payload_cases.json").read_text(encoding="utf-8"))
BASES = {name: json.loads((FIXTURES / f"{name}.data.json").read_text(encoding="utf-8")) for name in ("meta", "prices", "eda")}
VALIDATORS = {"meta": validate_meta, "prices": validate_prices, "eda": validate_eda}


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
    assert len(cases) >= 80
    assert {c["base"] for c in cases} == {"meta", "prices", "eda"}
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
