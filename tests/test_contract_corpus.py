"""The Python half of the drift guard between the two copies of the envelope rules.

The rules live twice: here in contract.py, and in app/src/lib/contract.ts. This file and
app/src/lib/contract.corpus.test.ts both run every case in ONE shared list,
app/src/test/fixtures/envelope_cases.json, and assert its `valid` flag. If either side changes a
rule without the other, one of the two suites fails on the case where they now disagree.

The `valid` flags were written by hand from the contract, not produced by either implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arima_forecasting.contract import validate_envelope

CORPUS = Path(__file__).resolve().parent.parent / "app" / "src" / "test" / "fixtures" / "envelope_cases.json"
CASES = json.loads(CORPUS.read_text(encoding="utf-8"))


def test_the_corpus_is_a_real_list_of_cases():
    # A parametrized test over an empty list is skipped, not failed, so an emptied or truncated
    # corpus would pass silently without these checks.
    assert isinstance(CASES, list)
    assert len(CASES) >= 100
    for case in CASES:
        assert set(case) == {"name", "envelope", "valid"}, case
        assert isinstance(case["name"], str) and case["name"]
        assert isinstance(case["valid"], bool)
    names = [case["name"] for case in CASES]
    assert len(names) == len(set(names)), "case names must be unique"
    assert any(case["valid"] for case in CASES)
    assert any(not case["valid"] for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_validate_envelope_agrees_with_the_corpus(case):
    problems = validate_envelope(case["envelope"])
    assert (problems == []) is case["valid"], problems
