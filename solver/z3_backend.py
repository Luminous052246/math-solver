"""Z3 后端:整数/实数线性约束求解。

支持的题目格式:
    find integers x and y such that x + y = 10 and x - y = 4
    find integers x such that x > 3 and x < 6 and x != 4

Z3 是 SMT 求解器,能给出可满足解、判定无解,并检查解是否唯一。
约束中的表达式用 Python AST 安全解析,不使用 eval。
"""

from __future__ import annotations

import ast
import re

import z3

from .types import Solution
from .verify import Verification, attach

_COMPARATOR_RE = re.compile(r"==|!=|<=|>=|=|<|>")


def _eval_node(node: ast.AST, env: dict):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise ValueError("不支持布尔字面量")
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("不支持的字面量")

    if isinstance(node, ast.Name):
        if node.id not in env:
            raise ValueError(f"使用了未声明的变量: {node.id}")
        return env[node.id]

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        raise ValueError("不支持二元运算符")

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, env)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        raise ValueError("不支持一元运算符")

    raise ValueError("不支持的表达式结构")


def _to_z3(expr: str, env: dict):
    expr = expr.strip()
    if not expr:
        raise ValueError("空表达式")
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree.body, env)


def _parse_constraint(text: str, env: dict):
    match = _COMPARATOR_RE.search(text)
    if not match:
        raise ValueError(f"约束缺少比较符: {text!r}")

    lhs = _to_z3(text[: match.start()], env)
    rhs = _to_z3(text[match.end() :], env)
    op = match.group(0)

    if op in ("=", "=="):
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    if op == "<=":
        return lhs <= rhs
    if op == ">=":
        return lhs >= rhs
    if op == "<":
        return lhs < rhs
    if op == ">":
        return lhs > rhs
    raise ValueError(f"不支持的比较符: {op}")


def solve(text: str) -> Solution:
    match = re.search(
        r"find\s+(integers?|reals?)\s+(.+?)\s+such that\s+(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(
            "约束题格式应为: find integers x and y such that <约束1> and <约束2>"
        )

    domain = match.group(1).lower()
    var_names = [
        name
        for name in re.findall(r"[a-zA-Z]\w*", match.group(2))
        if name.lower() not in {"and", "or"}
    ]
    if not var_names:
        raise ValueError("未找到变量声明")

    use_int = domain.startswith("integer")
    env = {
        name: z3.Int(name) if use_int else z3.Real(name) for name in var_names
    }

    constraints = [
        part.strip()
        for part in re.split(r"\s+and\s+", match.group(3))
        if part.strip()
    ]
    if not constraints:
        raise ValueError("未找到约束条件")

    solver = z3.Solver()
    parsed_constraints = [_parse_constraint(constraint, env) for constraint in constraints]
    for constraint in parsed_constraints:
        solver.add(constraint)

    steps = [
        f"声明变量: {', '.join(var_names)} ({'整数' if use_int else '实数'})"
    ]
    steps.extend(f"约束: {c}" for c in constraints)

    result = solver.check()
    if result == z3.unsat:
        solution = Solution(
            problem=text,
            problem_type="constraint",
            backend="z3",
            ok=True,
            answer="无解",
            steps=steps + ["约束不可满足 (unsat)"],
        )
        return attach(solution, Verification(None, "无解结论未做独立验证"))
    if result == z3.unknown:
        return Solution(
            problem=text,
            problem_type="constraint",
            backend="z3",
            ok=False,
            steps=steps,
            error="Z3 返回 unknown,无法确定解",
        )

    model = solver.model()
    values = [
        (name, model.eval(env[name], model_completion=True))
        for name in var_names
    ]

    # 再加一条"与原解不同"的约束,检查是否还存在其他解
    solver.add(z3.Or([env[name] != value for name, value in values]))
    unique = solver.check() == z3.unsat
    steps.append("解唯一" if unique else "存在多解,以下为其中一个解")

    answer = ", ".join(f"{name} = {value}" for name, value in values)
    solution = Solution(
        problem=text,
        problem_type="constraint",
        backend="z3",
        ok=True,
        answer=answer,
        steps=steps,
    )
    holds = all(
        z3.is_true(model.eval(constraint, model_completion=True))
        for constraint in parsed_constraints
    )
    verification = (
        Verification(True, "模型回代检验通过:所有约束均被满足")
        if holds
        else Verification(False, "模型回代检验失败:存在未满足的约束")
    )
    return attach(solution, verification)
