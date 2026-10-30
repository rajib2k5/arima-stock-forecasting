"""Hostile files against the Python readers: a value of any size or depth, a file of any number of
problems, a number too big for a double. Each must give short problems, quickly, and never an
exception (contract.md, "Bounds"). The app's contract.hostile.test.ts makes the same attacks on the
TypeScript readers, and the shared corpus's cap_cases hold both readers to the same capped result.

Every value here is made up: the bases are the hand-written fixtures in app/src/test/fixtures and the
made-up family of tests/test_payloads_forecast.py.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import time
from pathlib import Path

import pytest

from arima_forecasting import payloads
from arima_forecasting.artifacts import ArtifactError, compare_exports, loads_strict, read_artifact
from arima_forecasting.contract import MAX_PROBLEMS, SCHEMA_VERSION, more_problems, shown, validate_envelope
from test_payloads_forecast import EVALUATION, FIT, FORECASTS, RESIDUALS, _prices_of_the_fixtures

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "app" / "src" / "test" / "fixtures"
VALIDATORS = {
    "meta": payloads.validate_meta,
    "prices": payloads.validate_prices,
    "eda": payloads.validate_eda,
    "stationarity": payloads.validate_stationarity,
    "acf_pacf": payloads.validate_acf_pacf,
    "aic_grid": payloads.validate_aic_grid,
    "fit": payloads.validate_fit,
    "residuals_aic": lambda data: payloads.validate_residuals(data, "aic"),
    **{f"forecast_{m}_{meth}": (lambda data, m=m, meth=meth: payloads.validate_forecast(data, m, meth)) for m, meth in payloads.FORECASTS},
    "evaluation": payloads.validate_evaluation,
}
BASES = {name: json.loads((FIXTURES / f"{name}.data.json").read_text(encoding="utf-8")) for name in VALIDATORS}
SHORT = 400  # no problem may be longer than this many characters, whatever the value it quotes


def _family_problems():
    """tools/export_app_data.py's _family_problems: the checks across files that --check runs."""
    spec = importlib.util.spec_from_file_location("export_app_data", REPO / "tools" / "export_app_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module._family_problems


FAMILY_PROBLEMS = _family_problems()


def deep(levels: int) -> list:
    """An array nested `levels` deep, built without recursion."""
    value: list = []
    for _ in range(levels):
        value = [value]
    return value


def nodes(node, prefix=(), depth=0, most=6):
    """Every path down to `most` levels (the first three items of each list), as in the never-raise test."""
    if depth > most:
        return
    items = node.items() if isinstance(node, dict) else enumerate(node[:3]) if isinstance(node, list) else []
    for key, child in items:
        yield (*prefix, key)
        yield from nodes(child, (*prefix, key), depth + 1, most)


def put(base, path, value):
    data = copy.deepcopy(base)
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return data


def assert_short(problems: list[str], what: str) -> None:
    assert problems, what
    assert len(problems) <= MAX_PROBLEMS + 1, what
    long = [p[:120] for p in problems if len(p) > SHORT]
    assert not long, (what, long)


# --- the one quoting function --------------------------------------------------------------------------


def test_shown_quotes_a_value_of_any_size_or_depth_in_a_few_words():
    assert [shown("oos"), shown(4.5), shown(None), shown(True), shown([1, "a", None]), shown({"a": 1})] == ["'oos'", "4.5", "None", "True", "[1, 'a', None]", "{'a': 1}"]
    assert shown("x" * 80) == repr("x" * 80)
    assert shown("x" * 60_000_000) == repr("x" * 80) + "… (60000000 characters)"
    assert shown([0] * 9) == "an array of 9" and shown([[1, 2]]) == "an array of 1"  # nested: not quoted, however small
    assert shown({f"k{i}": i for i in range(9)}) == "an object with 9 keys" and shown({"a": [1]}) == "an object with 1 keys"
    assert shown(2**53 - 1) == "9007199254740991" and shown(10**400) == "an integer of 1329 bits"
    assert shown(deep(100_000)) == "an array of 1"  # repr() would recurse 100,000 times


# --- a value of 60 MB --------------------------------------------------------------------------------------

BIG = "2" * 60_000_000  # 60 MB: a date, a label, a name or a key of that length
STRING_SPOTS = [
    ("prices", ["rows", 0, "date"]),
    ("prices", ["rows", 0, "segment"]),
    ("prices", ["source", "raw_sha256"]),
    ("prices", ["source", "downloaded_at"]),
    ("prices", ["splits", "oos", "start"]),
    ("meta", ["milestones", 0, "status"]),
    ("meta", ["windows", "oos", "end_exclusive"]),
    ("meta", ["held_artifacts"]),
    ("eda", ["summary", "start"]),
    ("aic_grid", ["cells", 0, "start"]),
    ("fit", ["models", 0, "params", 0, "name"]),
    ("fit", ["models", 0, "params", 0, "library_name"]),
    ("forecast_aic_static", ["label"]),
    ("forecast_aic_refit", ["refits", 0, "params", 0, "name"]),
    ("evaluation", ["models", 0, "label"]),
    ("evaluation", ["methods", 0, "label"]),
]


@pytest.mark.parametrize(("name", "path"), STRING_SPOTS, ids=[f"{n} {'.'.join(map(str, p))}" for n, p in STRING_SPOTS])
def test_a_60_mb_string_gives_a_short_message(name, path):
    value = [BIG] if path == ["held_artifacts"] else BIG
    data = put(BASES[name], path, value)
    start = time.perf_counter()
    problems = VALIDATORS[name](data)
    assert time.perf_counter() - start < 1.0
    assert_short(problems, name)
    assert any("(60000000 characters)" in p for p in problems), problems


def test_a_60_mb_key_or_eda_duplicate_gives_a_short_message():
    params = BASES["aic_grid"]["cells"][0]["params"]
    data = put(BASES["aic_grid"], ["cells", 0, "params"], {**{k: v for k, v in list(params.items())[1:]}, BIG: "x"})
    assert_short(payloads.validate_aic_grid(data), "a 60 MB params key")
    kdes = copy.deepcopy(BASES["eda"]["kdes"])
    kdes[0]["variable"] = kdes[1]["variable"] = BIG
    assert_short(payloads.validate_eda(put(BASES["eda"], ["kdes"], kdes)), "two KDEs of one 60 MB variable")


@pytest.mark.parametrize("key", ["schema_version", "artifact", "generated_at", "source_commit"])
def test_a_60_mb_envelope_field_or_key_gives_a_short_message(key):
    envelope = {"schema_version": SCHEMA_VERSION, "artifact": "meta", "generated_at": "2026-10-29T00:00:00Z", "source_commit": "uncommitted", "data": {}}
    assert_short(validate_envelope({**envelope, key: BIG}), key)
    assert_short(validate_envelope({**envelope, BIG: 1}), "a 60 MB unknown key")
    # A major version of 5,000 digits: int() of more than 4,300 digits raised ValueError before.
    assert_short(validate_envelope({**envelope, "schema_version": "1" + "0" * 5000 + ".0.0"}), "a 5,001-digit major")


def test_a_start_label_of_5000_digits_is_a_problem_not_a_crash():
    # int() of more than 4,300 digits raises ValueError; the label's numbers are read without it.
    cells = BASES["aic_grid"]["cells"]
    i = next(i for i, c in enumerate(cells) if c["status"] != "failed" and c["p"] > 0 and c["q"] > 0)
    for label in ("random " + "9" * 5000, "nested (" + "9" * 5000 + ", 1, 0) c", "polished from (1, " + "9" * 5000 + ", 0) c"):
        problems = payloads.validate_aic_grid(put(BASES["aic_grid"], ["cells", i, "start"], label))
        assert_short(problems, label[:20])
        assert any(p.startswith(f"data.cells[{i}].start") for p in problems), problems


# --- one bound on the problems of a file ------------------------------------------------------------------


def test_an_envelope_with_a_million_unknown_keys_stops_at_max_problems():
    envelope = {"schema_version": SCHEMA_VERSION, "artifact": "meta", "generated_at": "2026-10-29T00:00:00Z", "source_commit": "uncommitted", "data": {}}
    envelope.update({f"k{i:07d}": 0 for i in range(1_000_000)})
    start = time.perf_counter()
    problems = validate_envelope(envelope)
    assert time.perf_counter() - start < 2.0
    assert problems == [f"unexpected key: 'k{i:07d}'" for i in range(MAX_PROBLEMS)] + [more_problems("envelope")]
    assert validate_envelope({**{k: v for k, v in envelope.items() if not k.startswith("k")}, "k1": 0}) == ["unexpected key: 'k1'"]


def test_every_validator_stops_at_max_problems():
    # Every list of each base filled with copies of {} (bounded lists at their bound): a validator may
    # stop early, but never past MAX_PROBLEMS and the line that says so.
    for name, base in BASES.items():
        data = copy.deepcopy(base)
        for path in nodes(data):
            node = data
            try:
                for key in path[:-1]:
                    node = node[key]
                if isinstance(node[path[-1]], list) and len(node[path[-1]]) > 1:
                    node[path[-1]] = [{} for _ in node[path[-1]]]
            except (KeyError, IndexError, TypeError):
                continue
        problems = VALIDATORS[name](data)
        assert len(problems) <= MAX_PROBLEMS + 1, name
        assert len(problems) <= MAX_PROBLEMS or problems[-1] == more_problems("data"), name


# --- a 100,000-deep array ------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(BASES))
def test_a_deep_array_anywhere_gives_short_problems_never_a_recursion_error(name):
    # Python's json.loads stops near 10,000 levels; a value built here is 100,000 deep. Every node down
    # to six levels (the first three items of each list), replaced by it in turn.
    value = deep(100_000)
    tried = 0
    for path in nodes(BASES[name]):
        problems = VALIDATORS[name](put(BASES[name], list(path), value))  # must not raise RecursionError
        assert len(problems) <= MAX_PROBLEMS + 1 and not [p for p in problems if len(p) > SHORT], (path, problems[:2])
        tried += 1
    assert tried > 20


def test_a_file_of_a_100000_deep_array_is_one_short_problem(tmp_path):
    text = json.dumps({"schema_version": SCHEMA_VERSION, "artifact": "prices", "generated_at": "2026-10-29T00:00:00Z", "source_commit": "uncommitted", "data": {**BASES["prices"], "rows": "DEEP"}})
    (tmp_path / "prices.json").write_text(text.replace('"DEEP"', "[" * 100_000 + "]" * 100_000), encoding="utf-8")
    with pytest.raises(ValueError, match="nested deeper than this reader follows"):
        loads_strict((tmp_path / "prices.json").read_text(encoding="utf-8"))
    with pytest.raises(ArtifactError) as raised:
        read_artifact(tmp_path, "prices")
    assert len(str(raised.value)) < SHORT
    fresh = {"schema_version": SCHEMA_VERSION, "artifact": "prices", "generated_at": "2026-10-29T00:00:00Z", "source_commit": "uncommitted", "data": BASES["prices"]}
    problems = compare_exports(tmp_path, {"prices": fresh})
    assert len(problems) == 1 and "nested deeper than this reader follows" in problems[0] and len(problems[0]) < SHORT


def test_a_committed_value_as_deep_as_json_loads_goes_compares_in_a_short_line(tmp_path):
    # The deepest array Python's json.loads reads, where the fresh export has rows: one short problem from
    # the payload check and one from the comparison, which quotes it with shown(), not json.dumps.
    levels = 5_000
    text = json.dumps({"schema_version": SCHEMA_VERSION, "artifact": "prices", "generated_at": "2026-10-29T00:00:00Z", "source_commit": "uncommitted", "data": {**BASES["prices"], "rows": "DEEP"}})
    (tmp_path / "prices.json").write_text(text.replace('"DEEP"', "[" * levels + "]" * levels), encoding="utf-8")
    fresh = {"schema_version": SCHEMA_VERSION, "artifact": "prices", "generated_at": "2026-10-29T00:00:00Z", "source_commit": "uncommitted", "data": BASES["prices"]}
    problems = compare_exports(tmp_path, {"prices": fresh})
    assert problems and not [p for p in problems if len(p) > SHORT], problems
    assert "prices: data.rows[0]: an array of 1 != {'close_usd': 24.0, 'date': '2015-01-02', 'log_close': 3.1781, 'segment': 'train'}" in problems


# --- a number too big for a double -----------------------------------------------------------------------------


def numeric_paths(node, prefix=()):
    """The path of every number (not bool) in a payload."""
    if isinstance(node, dict):
        for key, child in node.items():
            yield from numeric_paths(child, (*prefix, key))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from numeric_paths(child, (*prefix, index))
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield prefix


def fields(base):
    """One path per numeric field: each field's first occurrence and one from the middle of its list."""
    by_field: dict[tuple, list[tuple]] = {}
    for path in numeric_paths(base):
        by_field.setdefault(tuple("*" if isinstance(k, int) else k for k in path), []).append(path)
    return [p for paths in by_field.values() for p in dict.fromkeys((paths[0], paths[len(paths) // 2]))]


HUGE = (10**400, -(10**400))  # 400 digits: JSON.parse reads Infinity; float() raises OverflowError


def _path_of(problem: str) -> str:
    """A problem's path with a quoted key written plainly (data.cells[0].params['const'] -> ...params.const)."""
    return re.sub(r"\['([^']*)'\]", r".\1", problem.split(": ")[0])


@pytest.mark.parametrize("name", list(BASES))
def test_a_400_digit_integer_in_any_numeric_field_is_a_problem_not_a_crash(name):
    tried = 0
    for path in fields(BASES[name]):
        for value in HUGE:
            problems = VALIDATORS[name](put(BASES[name], list(path), value))  # must not raise
            at = "data" + "".join(f"[{k}]" if isinstance(k, int) else f".{k}" for k in path)
            if "settings" in path:
                # pmdarima's arguments as recorded (aic_grid's runs, fit's course_track): an open object both
                # readers take as it is and never read as numbers, so a huge one there is not refused.
                assert not [p for p in problems if _path_of(p).startswith(at)], (at, problems[:3])
                continue
            assert any(_path_of(p).startswith(at) or at.startswith(_path_of(p)) for p in problems), (at, problems[:3])
            assert not [p for p in problems if len(p) > SHORT], (at, problems[:2])
            tried += 1
    assert tried >= 2


FAMILY = {"fit": FIT, **RESIDUALS, **FORECASTS, "evaluation": EVALUATION, "prices": _prices_of_the_fixtures()}


def test_the_made_up_family_is_consistent_across_files():
    # Otherwise the checks across files below would stop before the arithmetic a huge number could break.
    assert payloads.validate_forecast_fit(FIT, RESIDUALS, FORECASTS) == []
    assert payloads.validate_forecast_prices(FAMILY["prices"], FORECASTS) == []
    assert payloads.validate_forecast_evaluation(EVALUATION, FORECASTS) == []


@pytest.mark.parametrize("name", [n for n in FAMILY if n.startswith(("fit", "residuals_", "forecast_aic", "evaluation", "prices"))])
def test_a_400_digit_integer_never_makes_the_checks_across_files_raise(name):
    # In each numeric field of each file of the family in turn: the cross-file checks and the family
    # check --check runs (_family_problems) report or pass, never raise.
    tried = 0
    for path in fields(FAMILY[name]):
        for value in HUGE:
            files = {**FAMILY, name: put(FAMILY[name], list(path), value)}
            residuals = {k: v for k, v in files.items() if k.startswith("residuals_")}
            forecasts = {k: v for k, v in files.items() if k.startswith("forecast_")}
            payloads.validate_forecast_fit(files["fit"], residuals, forecasts)
            payloads.validate_forecast_prices(files["prices"], forecasts)
            payloads.validate_forecast_evaluation(files["evaluation"], forecasts)
            payloads.validate_fit_residuals(BASES["fit"], {"residuals_aic": files.get("residuals_aic", BASES["residuals_aic"])})
            FAMILY_PROBLEMS(files)
            tried += 1
    assert tried >= 2


def test_a_400_digit_sigma2_in_the_fit_is_a_problem_not_a_crash():
    # The review's case: _sigma2 called math.isfinite on the int, which raised OverflowError from
    # validate_forecast_fit and from the family check --check runs.
    fit = copy.deepcopy(FIT)
    fit["models"][1]["params"][-1]["value"] = 10**400
    assert payloads.validate_forecast_fit(fit, RESIDUALS, FORECASTS) == []  # bic's rows are then tied to nothing
    FAMILY_PROBLEMS({**FAMILY, "fit": fit})
    real_fit = put(BASES["fit"], ["models", 1, "params", -1, "value"], 10**400)
    assert any(p.startswith("data.models[1].params[") and "an integer of 1329 bits" in p for p in payloads.validate_fit(real_fit))
    acf = put(BASES["acf_pacf"], ["series", 0, "rows", 3, "acf"], 10**400)
    assert payloads.validate_acf_pacf(acf)  # _finite raised OverflowError here
