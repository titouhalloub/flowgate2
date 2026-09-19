"""A minimal JSON Logic evaluator.

Supports the subset of operators Flowgate's compliance rules need:
variable access, comparison, boolean logic, membership, conditional,
and a small number of named predicates. Deliberately small -- the
full JSON Logic spec has operators (cat, substr, merge, ...) that
are attack surface we do not need.

Expression grammar:
  - A non-dict expression is a literal and is returned unchanged.
  - A dict with exactly one key is an operator invocation. The key
    is the operator name, the value is the argument(s).
  - An operator that takes multiple arguments uses a list.
  - An operator that takes one argument may pass it directly or as
    a single-element list.

Supported operators:
  var         read a path from context; missing paths yield None
  == != < <= > >=   comparison; Python semantics
  and or !    boolean logic; and/or are variadic, ! is unary
  in          membership test: {"in": [needle, haystack]}
  if          ternary: {"if": [cond, then]} or [cond, then, else]
  empty       true if the argument is None, or an empty list, dict, or string
  truthy      Python truthiness of the argument
  in_range    inclusive bounds: {"in_range": [x, lo, hi]}
  meaningful  true when str-normalized value is not "", "false", "0"
"""

from __future__ import annotations

from typing import Any


def _resolve_var(context: Any, path: Any) -> Any:
    """Read a value from context by dot-path or list-path.

    - "instrument.transaction_type" splits on "." and walks the dict.
    - ["instrument", "type_specific_data", "rate"] walks explicitly.
    Missing keys or non-dict intermediates yield None.
    """
    if isinstance(path, str):
        segments = path.split(".")
    elif isinstance(path, list):
        segments = path
    else:
        return None

    current: Any = context
    for segment in segments:
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
        else:
            return None
    return current


def _is_empty(value: Any) -> bool:
    """True for None, empty list, empty dict, or empty string.

    None is treated as empty because the compliance rules use this to
    mean "the field is absent or has no values" -- e.g. no KYC doc
    attached, no underlying asset declared. False for numbers,
    booleans, and non-empty containers.
    """
    if value is None:
        return True
    if isinstance(value, (list, dict, str, tuple)):
        return len(value) == 0
    return False


def evaluate(expression: Any, context: Any) -> Any:
    """Evaluate a JSON Logic expression against a context.

    The context is a plain dict. A missing path returns None; the
    caller decides whether that means 'rule does not fire' or
    'rule fires with the None branch'.
    """
    if not isinstance(expression, dict):
        return expression

    if len(expression) != 1:
        raise ValueError(
            f"JSON Logic expression must have exactly one key; "
            f"got {list(expression.keys())!r}"
        )

    (op, arg), = expression.items()

    if op == "var":
        return _resolve_var(context, arg)

    if op in ("and", "or"):
        args = arg if isinstance(arg, list) else [arg]
        values = [evaluate(a, context) for a in args]
        if op == "and":
            return all(bool(v) for v in values)
        return any(bool(v) for v in values)

    if op in ("!", "not"):
        inner = arg[0] if isinstance(arg, list) and len(arg) == 1 else arg
        return not bool(evaluate(inner, context))

    if op == "if":
        args = arg if isinstance(arg, list) else [arg]
        if len(args) == 2:
            return evaluate(args[1], context) if bool(evaluate(args[0], context)) else None
        if len(args) == 3:
            return evaluate(args[1], context) if bool(evaluate(args[0], context)) else evaluate(args[2], context)
        raise ValueError("if takes 2 or 3 arguments")

    if op in ("==", "!=", "<", "<=", ">", ">="):
        args = arg if isinstance(arg, list) else [arg]
        if len(args) != 2:
            raise ValueError(f"{op} takes exactly 2 arguments")
        left = evaluate(args[0], context)
        right = evaluate(args[1], context)
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        return left >= right

    if op == "in":
        args = arg if isinstance(arg, list) else [arg]
        if len(args) != 2:
            raise ValueError("in takes exactly 2 arguments")
        needle = evaluate(args[0], context)
        haystack = evaluate(args[1], context)
        if haystack is None:
            return False
        return needle in haystack

    if op == "empty":
        inner = arg[0] if isinstance(arg, list) and len(arg) == 1 else arg
        return _is_empty(evaluate(inner, context))

    if op == "truthy":
        inner = arg[0] if isinstance(arg, list) and len(arg) == 1 else arg
        return bool(evaluate(inner, context))

    if op == "in_range":
        args = arg if isinstance(arg, list) else [arg]
        if len(args) != 3:
            raise ValueError("in_range takes exactly 3 arguments")
        value = evaluate(args[0], context)
        low = evaluate(args[1], context)
        high = evaluate(args[2], context)
        if value is None:
            return False
        return low <= value <= high

    if op == "meaningful":
        # True when the value, after string normalization, is not
        # one of "", "false", "0". Matches the gharar check in
        # shariah_no_speculation's callable. The presence of the
        # key is not enough -- a value of "false" or "0" means the
        # flag is off.
        inner = arg[0] if isinstance(arg, list) and len(arg) == 1 else arg
        value = evaluate(inner, context)
        if value is None:
            return False
        return str(value).lower().strip() not in ("", "false", "0")

    raise ValueError(f"Unknown JSON Logic operator: {op!r}")
