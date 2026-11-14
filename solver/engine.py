"""执行已经确定的 TaskSpec。

规则解析和 LLM 翻译都停在 TaskSpec。数值结果只从这里进入 SymPy / Z3。
"""

from __future__ import annotations

from . import sympy_backend, z3_backend
from .taskspec import TaskSpec
from .types import Solution


def run_task(spec: TaskSpec) -> Solution:
    """按任务字段调用后端，不再把任务渲染成自然语言后重新解析。"""
    spec.validate()
    if spec.type == "constraint":
        return z3_backend.execute(spec)
    return sympy_backend.execute(spec)


def execute_spec(
    spec: TaskSpec,
    original_problem: str,
    *,
    planner: str = "spec",
) -> Solution:
    """执行结构化任务，并把来源记在结果上。"""
    try:
        solution = run_task(spec)
    except Exception as exc:
        solution = Solution(
            problem=original_problem,
            problem_type=spec.type,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    solution.problem = original_problem
    solution.problem_type = spec.type
    solution.planner = planner
    solution.task = spec.to_dict()
    solution.steps.insert(0, f"执行 {spec.type} 任务")
    return solution
