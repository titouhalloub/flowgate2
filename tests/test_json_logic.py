"""Tests for the minimal JSON Logic evaluator."""

import pytest

from app.json_logic import evaluate


def test_literal_passthrough():
    assert evaluate(42, {}) == 42
    assert evaluate("hello", {}) == "hello"
    assert evaluate(True, {}) is True
    assert evaluate(None, {}) is None
    assert evaluate([1, 2, 3], {}) == [1, 2, 3]


def test_var_dot_path():
    ctx = {"instrument": {"transaction_type": "loan"}}
    assert evaluate({"var": "instrument.transaction_type"}, ctx) == "loan"


def test_var_list_path():
    ctx = {"instrument": {"type_specific_data": {"rate": 0.06}}}
    assert evaluate(
        {"var": ["instrument", "type_specific_data", "rate"]}, ctx
    ) == 0.06


def test_var_missing_path_returns_none():
    ctx = {"instrument": {}}
    assert evaluate({"var": "instrument.missing"}, ctx) is None
    assert evaluate({"var": "no.such.path"}, ctx) is None


def test_comparison_operators():
    ctx = {"rate": 0.06}
    assert evaluate({"==": [{"var": "rate"}, 0.06]}, ctx) is True
    assert evaluate({"!=": [{"var": "rate"}, 0.06]}, ctx) is False
    assert evaluate({"<": [{"var": "rate"}, 0.10]}, ctx) is True
    assert evaluate({"<=": [{"var": "rate"}, 0.06]}, ctx) is True
    assert evaluate({">": [{"var": "rate"}, 0.10]}, ctx) is False
    assert evaluate({">=": [{"var": "rate"}, 0.06]}, ctx) is True


def test_and_or_not():
    ctx = {"a": True, "b": False}
    assert evaluate({"and": [{"var": "a"}, True]}, ctx) is True
    assert evaluate({"and": [{"var": "a"}, {"var": "b"}]}, ctx) is False
    assert evaluate({"or": [{"var": "a"}, {"var": "b"}]}, ctx) is True
    assert evaluate({"!": {"var": "b"}}, ctx) is True
    assert evaluate({"not": {"var": "a"}}, ctx) is False


def test_in_operator():
    ctx = {"mode": "sukuk"}
    assert evaluate({"in": [{"var": "mode"}, ["sukuk", "murabaha"]]}, ctx) is True
    assert evaluate({"in": [{"var": "mode"}, ["loan", "equity"]]}, ctx) is False


def test_if_two_and_three_args():
    ctx = {"x": 1}
    assert evaluate({"if": [{"==": [{"var": "x"}, 1]}, "yes"]}, ctx) == "yes"
    assert evaluate(
        {"if": [{"==": [{"var": "x"}, 1]}, "yes", "no"]}, ctx
    ) == "yes"
    assert evaluate(
        {"if": [{"==": [{"var": "x"}, 2]}, "yes", "no"]}, ctx
    ) == "no"


def test_empty_operator():
    ctx = {"a": [], "b": [1], "c": "", "d": "x", "e": None}
    assert evaluate({"empty": {"var": "a"}}, ctx) is True
    assert evaluate({"empty": {"var": "b"}}, ctx) is False
    assert evaluate({"empty": {"var": "c"}}, ctx) is True
    assert evaluate({"empty": {"var": "d"}}, ctx) is False
    assert evaluate({"empty": {"var": "e"}}, ctx) is False


def test_truthy_operator():
    ctx = {"a": 0, "b": 1, "c": [], "d": [1], "e": None}
    assert evaluate({"truthy": {"var": "a"}}, ctx) is False
    assert evaluate({"truthy": {"var": "b"}}, ctx) is True
    assert evaluate({"truthy": {"var": "c"}}, ctx) is False
    assert evaluate({"truthy": {"var": "d"}}, ctx) is True
    assert evaluate({"truthy": {"var": "e"}}, ctx) is False


def test_in_range_inclusive():
    ctx = {"rate": 0.06}
    assert evaluate({"in_range": [{"var": "rate"}, 0.0, 0.30]}, ctx) is True
    assert evaluate({"in_range": [0.0, 0.0, 0.30]}, ctx) is True
    assert evaluate({"in_range": [0.30, 0.0, 0.30]}, ctx) is True
    assert evaluate({"in_range": [{"var": "rate"}, 0.10, 0.30]}, ctx) is False
    assert evaluate({"in_range": [None, 0.0, 0.30]}, ctx) is False


def test_nested_expression_interest_sanity():
    """The real-world composite: rate is not None AND in range."""
    ctx = {"instrument": {"type_specific_data": {"interest_rate": 0.06}}}
    expr = {
        "and": [
            {"!": {"empty": [{"var": "instrument.type_specific_data.interest_rate"}]}},
            {"in_range": [
                {"var": "instrument.type_specific_data.interest_rate"},
                0.0, 0.30,
            ]},
        ]
    }
    assert evaluate(expr, ctx) is True

    ctx2 = {"instrument": {"type_specific_data": {"interest_rate": 0.95}}}
    assert evaluate(expr, ctx2) is False


def test_unknown_operator_raises():
    with pytest.raises(ValueError, match="Unknown JSON Logic operator"):
        evaluate({"bogus": [1, 2]}, {})


def test_multi_key_dict_raises():
    with pytest.raises(ValueError, match="exactly one key"):
        evaluate({"var": "x", "also": "y"}, {})
