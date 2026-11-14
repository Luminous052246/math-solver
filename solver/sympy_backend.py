"""SymPy 后端：按 TaskSpec 字段做精确计算。

本模块不解析自然语言。题面到字段的转换在 rules.py。
"""

from __future__ import annotations

import re

import sympy as sp

from .taskspec import TaskSpec
from .text import parse_symbolic, parse_with_locals
from .timeout import run_with_timeout
from .types import Solution
from .verify import (
    attach,
    verify_derivative,
    verify_equation,
    verify_factorization,
    verify_gcd,
    verify_identity,
    verify_integral,
    verify_lcm,
    verify_limit,
    verify_matrix,
    verify_ode,
    verify_primality,
    verify_series,
    verify_system,
)


def _make_solution(
    problem_type: str,
    answer: str,
    steps: list[str],
    ok: bool = True,
    error: str | None = None,
) -> Solution:
    return Solution(
        problem="",
        problem_type=problem_type,
        backend="sympy",
        ok=ok,
        answer=answer,
        steps=steps,
        error=error,
    )


def _preferred_variable(spec: TaskSpec) -> str | None:
    return spec.variables[0] if spec.variables else None


def _pick_variable(expr: sp.Expr, preferred: str | None = None) -> sp.Symbol:
    """选择自变量：优先任务指定的变量，其次 x，再次第一个自由符号。"""
    if preferred:
        return sp.Symbol(preferred)
    symbols = sorted(expr.free_symbols, key=lambda symbol: symbol.name)
    x = sp.Symbol("x")
    if x in symbols:
        return x
    return symbols[0] if symbols else x


def execute(spec: TaskSpec) -> Solution:
    """执行一个已经校验过的 SymPy 任务。"""
    handler = _HANDLERS.get(spec.type)
    if handler is None:
        raise ValueError(f"SymPy 后端不支持的题型: {spec.type}")
    return handler(spec)


def _arithmetic(spec: TaskSpec) -> Solution:
    expr = parse_symbolic(spec.expression)
    result = sp.simplify(expr)
    solution = _make_solution(
        "arithmetic",
        str(result),
        [f"解析表达式: {expr}", "使用 SymPy 化简/求值"],
    )
    return attach(solution, verify_identity(expr, result, "算术结果"))


def _simplify(spec: TaskSpec) -> Solution:
    expr = parse_symbolic(spec.expression)
    result = run_with_timeout(sp.simplify, expr)
    solution = _make_solution(
        "simplify",
        str(result),
        [f"解析表达式: {expr}", "使用 SymPy simplify 化简"],
    )
    return attach(solution, verify_identity(expr, result, "化简结果"))


def _derivative(spec: TaskSpec) -> Solution:
    expr = parse_symbolic(spec.expression)
    var = _pick_variable(expr, _preferred_variable(spec))
    result = run_with_timeout(lambda: sp.simplify(sp.diff(expr, var)))
    operation = "求偏导" if spec.goal == "partial" else "求导"
    solution = _make_solution(
        "derivative",
        str(result),
        [f"解析表达式: {expr}", f"对 {var} {operation}"],
    )
    return attach(solution, verify_derivative(expr, var, result))


def _integral(spec: TaskSpec) -> Solution:
    expr = parse_symbolic(spec.expression)
    var = _pick_variable(expr, _preferred_variable(spec))
    lower = upper = None
    if spec.bounds is not None:
        lower = parse_symbolic(spec.bounds["lower"])
        upper = parse_symbolic(spec.bounds["upper"])
        result = run_with_timeout(lambda: sp.integrate(expr, (var, lower, upper)))
        steps = [
            f"解析被积函数: {expr}",
            f"计算定积分 ∫[{lower}, {upper}] 关于 {var}",
        ]
    else:
        result = run_with_timeout(lambda: sp.integrate(expr, var))
        steps = [
            f"解析被积函数: {expr}",
            f"计算不定积分,关于 {var}(结果省略常数 C)",
        ]
    result = run_with_timeout(sp.simplify, result)
    solution = _make_solution("integral", str(result), steps)
    return attach(solution, verify_integral(expr, var, result, lower, upper))


def _limit(spec: TaskSpec) -> Solution:
    expr = parse_symbolic(spec.expression)
    var = _pick_variable(expr, _preferred_variable(spec))
    point = parse_symbolic(spec.point)
    result = run_with_timeout(sp.limit, expr, var, point, spec.direction)
    solution = _make_solution(
        "limit",
        str(result),
        [
            f"解析表达式: {expr}",
            f"计算 {var} -> {spec.point} 的极限(方向: {spec.direction})",
        ],
    )
    return attach(solution, verify_limit(expr, var, point, spec.direction, result))


def _series(spec: TaskSpec) -> Solution:
    expr = parse_symbolic(spec.expression)
    var = _pick_variable(expr, _preferred_variable(spec))
    center = parse_symbolic(spec.center)
    result = run_with_timeout(sp.series, expr, var, center, spec.order)
    result = sp.simplify(result.removeO())
    solution = _make_solution(
        "series",
        str(result),
        [
            f"解析函数: {expr}",
            f"在 {var} = {center} 处展开到 {spec.order - 1} 次",
        ],
    )
    return attach(solution, verify_series(expr, var, center, result, spec.order))


def _parse_ode_side(side: str) -> sp.Expr:
    side = side.replace("ODE2", "Derivative(y(x), x, 2)")
    side = side.replace("ODE1", "Derivative(y(x), x)")
    side = re.sub(r"\by\b(?!\s*\()", "y(x)", side)
    return parse_with_locals(
        side,
        {"y": sp.Function("y"), "x": sp.Symbol("x"), "Derivative": sp.Derivative},
    )


def _ode(spec: TaskSpec) -> Solution:
    body = spec.ode
    body = re.sub(r"d\s*y\s*/\s*d\s*x", "ODE1", body, flags=re.IGNORECASE)
    body = body.replace("==", "=")
    body = re.sub(r"y\s*''", "ODE2", body)
    body = re.sub(r"y\s*'", "ODE1", body)
    if body.count("=") != 1:
        raise ValueError("微分方程格式应为: y' = f(x, y) 或 y'' + a*y' + b*y = 0")
    lhs_str, rhs_str = body.split("=")
    lhs = _parse_ode_side(lhs_str.strip())
    rhs = _parse_ode_side(rhs_str.strip())
    equation = sp.Eq(lhs, rhs)

    ode_solution = run_with_timeout(sp.dsolve, equation)
    if isinstance(ode_solution, list):
        ode_solution = ode_solution[0]

    order = sp.ode_order(equation, sp.Function("y")(sp.Symbol("x")))
    solution = _make_solution(
        "ode",
        f"{ode_solution.lhs} = {ode_solution.rhs}",
        [f"解析方程: {equation}", f"微分方程阶数: {order}", "使用 SymPy dsolve 求解"],
    )
    return attach(solution, verify_ode(equation, ode_solution))


def _matrix(spec: TaskSpec) -> Solution:
    if not spec.matrix:
        raise ValueError("矩阵必须是矩形数值列表,格式如 [[1, 2], [3, 4]]")
    matrix = sp.Matrix(spec.matrix)
    dimensions = f"{matrix.rows}×{matrix.cols}"
    operation_key = spec.operation
    if operation_key == "determinant":
        answer = str(matrix.det())
        operation = "计算行列式"
    elif operation_key == "eigenvalues":
        values = []
        for value, multiplicity in matrix.eigenvals().items():
            values.extend([value] * multiplicity)
        values.sort(key=sp.default_sort_key)
        answer = ", ".join(str(value) for value in values)
        operation = "计算特征值"
    elif operation_key == "inverse":
        if matrix.det() == 0:
            raise ValueError("矩阵不可逆(行列式为 0)")
        answer = str(matrix.inv().tolist())
        operation = "求逆矩阵"
    elif operation_key == "transpose":
        answer = str(matrix.T.tolist())
        operation = "求转置"
    elif operation_key == "rank":
        answer = str(matrix.rank())
        operation = "计算秩"
    else:
        raise ValueError("无法识别矩阵操作,支持:行列式、特征值、逆矩阵、转置、秩")

    solution = _make_solution(
        "matrix",
        answer,
        [f"解析矩阵({dimensions}): {matrix.tolist()}", operation],
    )
    return attach(solution, verify_matrix(matrix, operation_key, answer))


def _number_theory(spec: TaskSpec) -> Solution:
    numbers = spec.numbers
    operation = spec.operation
    if operation == "gcd":
        value = sp.gcd(numbers[0], numbers[1])
        solution = _make_solution(
            "number_theory",
            str(value),
            [f"计算 gcd({numbers[0]}, {numbers[1]})"],
        )
        return attach(solution, verify_gcd(numbers[0], numbers[1], str(value)))
    if operation == "lcm":
        value = sp.lcm(numbers[0], numbers[1])
        solution = _make_solution(
            "number_theory",
            str(value),
            [f"计算 lcm({numbers[0]}, {numbers[1]})"],
        )
        return attach(solution, verify_lcm(numbers[0], numbers[1], str(value)))
    if operation == "factorization":
        number = numbers[0]
        factors = sp.factorint(number)
        parts = [
            f"{prime}**{exp}" if exp > 1 else str(prime)
            for prime, exp in sorted(factors.items())
        ]
        answer = " * ".join(parts) if parts else "1"
        solution = _make_solution(
            "number_theory",
            answer,
            [f"对 {number} 做质因数分解"],
        )
        return attach(solution, verify_factorization(number, answer))
    if operation == "primality":
        number = numbers[0]
        answer = "yes" if sp.isprime(number) else "no"
        solution = _make_solution(
            "number_theory",
            answer,
            [f"判断 {number} 是否为质数"],
        )
        return attach(solution, verify_primality(number, answer))
    raise ValueError("无法识别的数论题型")


def _format_single_variable(var: sp.Symbol, solutions: list) -> str:
    if not solutions:
        return "无解"
    ordered = sorted(solutions, key=sp.default_sort_key)
    return " or ".join(f"{var} = {solution}" for solution in ordered)


def _equation(spec: TaskSpec) -> Solution:
    equations = []
    symbols_seen: set[sp.Symbol] = set()
    for equation_str in spec.equations:
        if equation_str.count("=") != 1:
            raise ValueError(f"无法解析方程: {equation_str!r}")
        lhs_str, rhs_str = equation_str.split("=")
        lhs = parse_symbolic(lhs_str.strip())
        rhs = parse_symbolic(rhs_str.strip())
        equations.append(sp.Eq(lhs, rhs))
        symbols_seen |= lhs.free_symbols | rhs.free_symbols

    if spec.variables:
        variables = [sp.Symbol(name) for name in spec.variables]
    else:
        variables = sorted(symbols_seen, key=lambda symbol: symbol.name)

    if not variables:
        raise ValueError("方程中没有未知数")

    steps = [f"解析方程: {', '.join(str(equation) for equation in equations)}"]
    steps.append(f"未知数: {', '.join(str(variable) for variable in variables)}")

    if len(equations) == 1 and len(variables) == 1:
        solutions = run_with_timeout(sp.solve, equations[0], variables[0])
        answer = _format_single_variable(variables[0], solutions)
        steps.append("使用 SymPy solve 求解单个方程")
        solution = _make_solution("equation", answer, steps)
        return attach(solution, verify_equation(equations[0], variables[0], solutions))

    if len(equations) == 1 and not spec.variables and len(variables) > 1:
        raise ValueError("方程含多个未知数,请用 'for <变量>' 指定求解目标")

    solution_dicts = run_with_timeout(sp.solve, equations, variables, dict=True)
    if not solution_dicts:
        answer = "无解"
    else:
        formatted = []
        for solution_dict in solution_dicts:
            parts = [f"{var} = {solution_dict.get(var, var)}" for var in variables]
            formatted.append(", ".join(parts))
        answer = " or ".join(formatted)

    steps.append("使用 SymPy solve 求解方程组")
    solution = _make_solution("equation", answer, steps)
    return attach(solution, verify_system(equations, variables, solution_dicts))


_HANDLERS = {
    "arithmetic": _arithmetic,
    "simplify": _simplify,
    "derivative": _derivative,
    "integral": _integral,
    "limit": _limit,
    "series": _series,
    "ode": _ode,
    "matrix": _matrix,
    "number_theory": _number_theory,
    "equation": _equation,
}
