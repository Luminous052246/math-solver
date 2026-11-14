"""题型路由与规则求解。

规则路径先把题目解析成 TaskSpec，再交给与 LLM 相同的执行入口。
"""

from __future__ import annotations

from .engine import execute_spec
from .rules import parse_problem, parse_route, route_problem
from .types import Solution

__all__ = ["route_problem", "solve_problem", "solve_route"]


def solve_route(route: str, text: str) -> Solution:
    """按指定题型解析并执行，跳过关键词路由。"""
    spec = parse_route(route, text)
    return execute_spec(spec, text, planner="rule")


def solve_problem(text: str) -> Solution:
    """求解一道自然语言数学题。不调用 LLM。"""
    try:
        spec = parse_problem(text)
    except Exception as exc:
        return Solution(
            problem=text,
            ok=False,
            planner="rule",
            error=f"{type(exc).__name__}: {exc}",
        )
    return execute_spec(spec, text, planner="rule")
