"""题型路由:根据题面特征选择解析方式与求解后端。"""

from __future__ import annotations

from . import sympy_backend, z3_backend
from .text import normalize_text
from .types import Solution

_Z3_HINTS = ("such that", "find integer", "find real", "整数解", "满足约束")
_ODE_HINTS = ("ode", "differential equation", "微分方程", "dy/dx", "dsolve", "y'")
_LIMIT_HINTS = ("limit", "lim ", "极限", "趋于", "tends to")
_SERIES_HINTS = ("series", "taylor", "maclaurin", "泰勒", "麦克劳林", "级数")
_MATRIX_HINTS = (
    "determinant",
    "inverse",
    "eigen",
    "matrix",
    "rank",
    "transpose",
    "行列式",
    "逆矩阵",
    "特征值",
    "矩阵",
    "秩",
    "转置",
)
_DERIVATIVE_HINTS = ("differentiate", "derivative", "partial", "d/d", "求导", "导数", "偏导")
_INTEGRAL_HINTS = ("integrate", "integral", "积分")
_SIMPLIFY_HINTS = ("simplify", "化简", "简化")
_NUMBER_THEORY_HINTS = (
    "gcd",
    "lcm",
    "factor",
    "prime",
    "最大公约数",
    "最小公倍数",
    "质因数",
    "质数",
    "因数分解",
)

# 按优先级排列的路由表,命中第一个即返回。
_ROUTE_TABLE = (
    ("constraint", _Z3_HINTS),
    ("ode", _ODE_HINTS),
    ("limit", _LIMIT_HINTS),
    ("series", _SERIES_HINTS),
    ("matrix", _MATRIX_HINTS),
    ("derivative", _DERIVATIVE_HINTS),
    ("integral", _INTEGRAL_HINTS),
    ("simplify", _SIMPLIFY_HINTS),
    ("number_theory", _NUMBER_THEORY_HINTS),
)

_ROUTE_FUNCS = {
    "constraint": z3_backend.solve,
    "ode": sympy_backend.solve_ode,
    "limit": sympy_backend.solve_limit,
    "series": sympy_backend.solve_series,
    "matrix": sympy_backend.solve_matrix,
    "derivative": sympy_backend.solve_derivative,
    "integral": sympy_backend.solve_integral,
    "simplify": sympy_backend.solve_simplify,
    "number_theory": sympy_backend.solve_number_theory,
    "equation": sympy_backend.solve_equation,
    "arithmetic": sympy_backend.solve_arithmetic,
}


def _select_route(low: str) -> tuple[str, str | None]:
    """返回 (题型, 命中的特征词)。未命中特征词时按是否含等号判断。"""
    for route, hints in _ROUTE_TABLE:
        for hint in hints:
            if hint in low:
                return route, hint
    if "=" in low:
        return "equation", "="
    return "arithmetic", None


def route_problem(text: str) -> tuple[str, str | None]:
    """返回题目被分到的题型及命中的关键词,供界面展示。"""
    normalized = normalize_text(text)
    return _select_route(normalized.lower())


def solve_route(route: str, text: str) -> Solution:
    """按指定题型直接调用后端,跳过关键词路由。

    供结构化任务协议使用:规划器已经确定了题型,只需要执行。
    """
    if route not in _ROUTE_FUNCS:
        raise ValueError(f"不支持的题型: {route!r}")
    return _ROUTE_FUNCS[route](normalize_text(text))


def solve_problem(text: str) -> Solution:
    """求解一道自然语言数学题(纯规则路由,不调用 LLM)。"""
    normalized = normalize_text(text)
    route, _ = _select_route(normalized.lower())

    try:
        return solve_route(route, normalized)
    except Exception as exc:  # 解析或求解失败时返回结构化错误
        return Solution(
            problem=text,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
