"""答案等价比较,用于评测。

数学答案的表示形式多样(x = 2 vs x = 2.0、2*x + 1 vs 1 + 2*x),
这里按语义比较而非字符串比较。
"""

from __future__ import annotations

import re

import sympy as sp

from .text import parse_symbolic

# 变量名后允许函数写法,如 y(x) = C1 + x**2(ODE 解)
_ASSIGN_RE = re.compile(
    r"([a-zA-Z]\w*)(?:\s*\(\s*[a-zA-Z]\w*\s*\))?\s*=\s*([^,=]+)"
)


def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip("。.;；")
    return text.strip()


def answers_equivalent(expected: str, actual: str) -> bool:
    expected = _clean(expected)
    actual = _clean(actual)
    if not actual:
        return False
    if expected == actual:
        return True

    expected_bool = _as_bool(expected)
    actual_bool = _as_bool(actual)
    if expected_bool is not None:
        return expected_bool == actual_bool

    if "=" in expected or "=" in actual:
        return _compare_assignments(expected, actual)

    if _is_set(expected) or _is_set(actual):
        return _compare_sets(expected, actual)

    return _symbolic_equal(expected, actual)


def _as_bool(text: str):
    return {"yes": True, "true": True, "no": False, "false": False}.get(text.lower())


def _symbolic_equal(left: str, right: str) -> bool:
    try:
        left_expr = parse_symbolic(left)
        right_expr = parse_symbolic(right)
    except Exception:
        return False

    try:
        if sp.simplify(left_expr - right_expr) == 0:
            return True
    except Exception:
        pass

    try:
        return abs(complex(sp.N(left_expr - right_expr))) < 1e-9
    except Exception:
        return False


def _parse_assignments(text: str) -> dict[str, list[str]] | None:
    assignments: dict[str, list[str]] = {}
    for group in re.split(r"\s+or\s+", text):
        matches = _ASSIGN_RE.findall(group)
        if not matches:
            return None
        for name, value in matches:
            assignments.setdefault(name, []).append(value.strip())
    return assignments


def _compare_assignments(expected: str, actual: str) -> bool:
    expected_map = _parse_assignments(expected)
    actual_map = _parse_assignments(actual)
    if expected_map is None or actual_map is None:
        return False
    if set(expected_map) != set(actual_map):
        return False
    return all(
        _multiset_equal(expected_map[name], actual_map[name])
        for name in expected_map
    )


def _multiset_equal(left: list[str], right: list[str]) -> bool:
    if len(left) != len(right):
        return False
    remaining = list(right)
    for value in left:
        for index, candidate in enumerate(remaining):
            if _symbolic_equal(value, candidate):
                remaining.pop(index)
                break
        else:
            return False
    return True


def _is_set(text: str) -> bool:
    return text.startswith("{") and text.endswith("}")


def _parse_set(text: str) -> list[str] | None:
    if not _is_set(text):
        return None
    inner = text[1:-1].strip()
    if not inner:
        return []
    return [item.strip() for item in inner.split(",")]


def _compare_sets(expected: str, actual: str) -> bool:
    expected_set = _parse_set(expected)
    actual_set = _parse_set(actual)
    if expected_set is None or actual_set is None:
        return False
    return _multiset_equal(expected_set, actual_set)
