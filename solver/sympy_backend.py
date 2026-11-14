"""SymPy 后端:算术、化简、方程、微积分、数论。

所有结果都由符号引擎精确计算,不做概率性猜测。
"""

from __future__ import annotations

import ast
import re

import sympy as sp

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

_ARITH_PREFIXES = [
    r"calculate",
    r"compute",
    r"evaluate",
    r"what is",
    r"what's",
    r"计算",
    r"求值",
    r"算出",
]

_SIMPLIFY_PREFIXES = [r"simplify", r"化简", r"简化"]

_DERIVATIVE_PREFIXES = [
    r"differentiate",
    r"partial\s+derivative\s+of",
    r"partial\s+derivative",
    r"partial",
    r"derivative of",
    r"derivative",
    r"求偏导数",
    r"求偏导",
    r"偏导数",
    r"偏导",
    r"求导数",
    r"求导",
    r"导数",
]

_LIMIT_PREFIXES = [r"limit\s+of", r"求极限", r"极限", r"limit", r"lim"]

_SERIES_PREFIXES = [
    r"taylor\s+series\s+of",
    r"maclaurin\s+series\s+of",
    r"series\s+of",
    r"expand",
    r"求",
    r"将",
    r"泰勒展开",
    r"麦克劳林展开",
    r"级数展开",
    r"展开",
]

_ODE_PREFIXES = [
    r"solve\s+the\s+ode",
    r"solve\s+the\s+differential\s+equation",
    r"dsolve",
    r"求解微分方程",
    r"解微分方程",
    r"微分方程",
    r"solve",
    r"求解",
    r"解",
]

_INTEGRAL_PREFIXES = [
    r"integrate",
    r"integral of",
    r"integral",
    r"求积分",
    r"积分",
]

_EQUATION_PREFIXES = [
    r"solve for",
    r"solve",
    r"解方程组",
    r"解方程",
    r"求解",
]


def _strip_prefixes(text: str, patterns: list[str]) -> str:
    """去掉句首的题型关键词(按给定顺序,长的模式应在前)。"""
    result = text
    for pattern in patterns:
        result = re.sub(
            rf"^\s*(?:{pattern})\s*[:：]?\s*", "", result, flags=re.IGNORECASE
        )
    return result.strip()


def _make_solution(
    problem: str,
    problem_type: str,
    answer: str,
    steps: list[str],
    ok: bool = True,
    error: str | None = None,
) -> Solution:
    return Solution(
        problem=problem,
        problem_type=problem_type,
        backend="sympy",
        ok=ok,
        answer=answer,
        steps=steps,
        error=error,
    )


def _pick_variable(expr: sp.Expr, preferred: str | None = None) -> sp.Symbol:
    """选择求导/积分的自变量:优先题目指定,其次 x,再次第一个自由符号。"""
    if preferred:
        return sp.Symbol(preferred)
    symbols = sorted(expr.free_symbols, key=lambda s: s.name)
    x = sp.Symbol("x")
    if x in symbols:
        return x
    return symbols[0] if symbols else x


# ---------------------------------------------------------------------------
# 算术 / 化简
# ---------------------------------------------------------------------------


def solve_arithmetic(text: str) -> Solution:
    body = _strip_prefixes(text, _ARITH_PREFIXES).strip(" :：,，;；")
    expr = parse_symbolic(body)
    result = sp.simplify(expr)
    solution = _make_solution(
        text,
        "arithmetic",
        str(result),
        [f"解析表达式: {expr}", "使用 SymPy 化简/求值"],
    )
    return attach(solution, verify_identity(expr, result, "算术结果"))


def solve_simplify(text: str) -> Solution:
    body = _strip_prefixes(text, _SIMPLIFY_PREFIXES).strip(" :：,，;；")
    expr = parse_symbolic(body)
    result = run_with_timeout(sp.simplify, expr)
    solution = _make_solution(
        text,
        "simplify",
        str(result),
        [f"解析表达式: {expr}", "使用 SymPy simplify 化简"],
    )
    return attach(solution, verify_identity(expr, result, "化简结果"))


# ---------------------------------------------------------------------------
# 微积分
# ---------------------------------------------------------------------------


def solve_derivative(text: str) -> Solution:
    var_name: str | None = None

    match = re.search(r"with respect to\s+([a-zA-Z]\w*)", text, flags=re.IGNORECASE)
    if match:
        var_name = match.group(1)
        text_wo = re.sub(
            r"with respect to\s+[a-zA-Z]\w*", "", text, flags=re.IGNORECASE
        )
    else:
        text_wo = text

    # 支持 d/dx 写法
    match = re.search(r"\bd\s*/\s*d\s*([a-zA-Z])\b", text_wo)
    if match:
        var_name = var_name or match.group(1)
        text_wo = re.sub(
            r"\bd\s*/\s*d\s*[a-zA-Z]\b", "", text_wo, flags=re.IGNORECASE
        )

    body = _strip_prefixes(text_wo, _DERIVATIVE_PREFIXES).strip(" :：,，;；")
    expr = parse_symbolic(body)
    var = _pick_variable(expr, var_name)

    is_partial = "partial" in text.lower() or "偏导" in text
    result = run_with_timeout(lambda: sp.simplify(sp.diff(expr, var)))
    operation = "求偏导" if is_partial else "求导"
    solution = _make_solution(
        text,
        "derivative",
        str(result),
        [f"解析表达式: {expr}", f"对 {var} {operation}"],
    )
    return attach(solution, verify_derivative(expr, var, result))


def solve_integral(text: str) -> Solution:
    var_name: str | None = None
    match = re.search(r"with respect to\s+([a-zA-Z]\w*)", text, flags=re.IGNORECASE)
    if match:
        var_name = match.group(1)
        body = re.sub(
            r"with respect to\s+[a-zA-Z]\w*", "", text, flags=re.IGNORECASE
        )
    else:
        body = text

    # 定积分: from A to B
    bounds: tuple[str, str] | None = None
    match = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+)$", body, flags=re.IGNORECASE)
    if match:
        bounds = (match.group(1).strip(), match.group(2).strip())
        body = body[: match.start()]

    body = _strip_prefixes(body, _INTEGRAL_PREFIXES).strip(" :：,，;；")
    expr = parse_symbolic(body)
    var = _pick_variable(expr, var_name)

    lower = upper = None
    if bounds is not None:
        lower = parse_symbolic(bounds[0])
        upper = parse_symbolic(bounds[1])
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
    solution = _make_solution(text, "integral", str(result), steps)
    return attach(solution, verify_integral(expr, var, result, lower, upper))


# ---------------------------------------------------------------------------
# 极限
# ---------------------------------------------------------------------------


def _normalize_limit_point(point: str) -> tuple[str, str]:
    """拆分极限点与方向,并把无穷写法统一为 oo。"""
    point = point.strip()
    direction = "+-"
    if len(point) > 1 and point[-1] in "+-" and point[:-1].strip():
        direction = point[-1]
        point = point[:-1].strip()
    point = (
        point.replace("负无穷", "-oo")
        .replace("正无穷", "oo")
        .replace("无穷大", "oo")
        .replace("无穷", "oo")
        .replace("infinity", "oo")
        .replace("inf", "oo")
        .replace("→∞", "oo")
    )
    return point, direction


def solve_limit(text: str) -> Solution:
    var_name: str | None = None
    point_str: str | None = None
    body = text

    match = re.search(
        r"\bas\s+([a-zA-Z]\w*)\s*(?:->|tends?\s+to)\s*([^\s,，]+)", text, flags=re.IGNORECASE
    )
    if match:
        var_name, point_str = match.group(1), match.group(2)
        body = text[: match.start()] + text[match.end() :]
    else:
        match = re.search(r"当\s*([a-zA-Z]\w*)\s*趋于\s*([^\s,，]+)\s*时", text)
        if match:
            var_name, point_str = match.group(1), match.group(2)
            body = text[: match.start()] + text[match.end() :]
        else:
            match = re.search(
                r"\blim(?:it)?\s+(?:of\s+)?([a-zA-Z]\w*)\s*->\s*([^\s,，]+)",
                text,
                flags=re.IGNORECASE,
            )
            if match:
                var_name, point_str = match.group(1), match.group(2)
                body = text[match.end() :]

    if var_name is None or point_str is None:
        raise ValueError(
            "极限题格式应为: limit of <表达式> as x -> <值> 或 当 x 趋于 <值> 时 <表达式> 的极限"
        )

    point_str, direction = _normalize_limit_point(point_str)
    point = parse_symbolic(point_str)

    body = _strip_prefixes(body, _LIMIT_PREFIXES)
    body = body.replace("的极限", "").strip(" :：,，;；")
    expr = parse_symbolic(body)
    var = _pick_variable(expr, var_name)

    result = run_with_timeout(sp.limit, expr, var, point, direction)
    solution = _make_solution(
        text,
        "limit",
        str(result),
        [
            f"解析表达式: {expr}",
            f"计算 {var} -> {point_str} 的极限(方向: {direction})",
        ],
    )
    return attach(solution, verify_limit(expr, var, point, direction, result))


# ---------------------------------------------------------------------------
# 级数展开
# ---------------------------------------------------------------------------


def solve_series(text: str) -> Solution:
    var_name: str | None = None
    center_str = "0"
    body = text

    match = re.search(r"(?:around|at)\s+([a-zA-Z]\w*)\s*=\s*([^\s,，]+)", text, flags=re.IGNORECASE)
    if match:
        var_name, center_str = match.group(1), match.group(2)
        body = text[: match.start()] + text[match.end() :]
    else:
        match = re.search(r"在\s*([a-zA-Z]\w*)\s*=\s*([^\s,，]+)\s*处", text)
        if match:
            var_name, center_str = match.group(1), match.group(2)
            body = text[: match.start()] + text[match.end() :]
        else:
            match = re.search(r"(?:around|at)\s+([^\s,，]+)", text, flags=re.IGNORECASE)
            if match:
                center_str = match.group(1)
                body = text[: match.start()] + text[match.end() :]

    match = (
        re.search(r"order\s+(\d+)", text, flags=re.IGNORECASE)
        or re.search(r"到\s*(\d+)\s*阶", text)
        or re.search(r"(\d+)\s*阶", text)
    )
    order = int(match.group(1)) if match else 6

    body = re.sub(r"(?:to\s+)?order\s+\d+", "", body, flags=re.IGNORECASE)
    body = re.sub(r"到\s*\d+\s*阶", "", body)
    body = _strip_prefixes(body, _SERIES_PREFIXES).strip(" :：,，;；")
    for keyword in ("泰勒展开", "麦克劳林展开", "级数展开", "展开"):
        body = re.sub(rf"^\s*{keyword}\s*", "", body)
        body = re.sub(rf"\s*{keyword}\s*$", "", body)
    body = body.strip(" :：,，;；")

    expr = parse_symbolic(body)
    var = _pick_variable(expr, var_name)
    center = parse_symbolic(center_str)

    result = run_with_timeout(sp.series, expr, var, center, order)
    result = sp.simplify(result.removeO())
    solution = _make_solution(
        text,
        "series",
        str(result),
        [
            f"解析函数: {expr}",
            f"在 {var} = {center} 处展开到 {order - 1} 次",
        ],
    )
    return attach(solution, verify_series(expr, var, center, result, order))


# ---------------------------------------------------------------------------
# 常微分方程
# ---------------------------------------------------------------------------


def _parse_ode_side(side: str) -> sp.Expr:
    side = side.replace("ODE2", "Derivative(y(x), x, 2)")
    side = side.replace("ODE1", "Derivative(y(x), x)")
    side = re.sub(r"\by\b(?!\s*\()", "y(x)", side)
    return parse_with_locals(
        side,
        {"y": sp.Function("y"), "x": sp.Symbol("x"), "Derivative": sp.Derivative},
    )


def solve_ode(text: str) -> Solution:
    body = _strip_prefixes(text, _ODE_PREFIXES).strip(" :：,，;；")
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
        text,
        "ode",
        f"{ode_solution.lhs} = {ode_solution.rhs}",
        [f"解析方程: {equation}", f"微分方程阶数: {order}", "使用 SymPy dsolve 求解"],
    )
    return attach(solution, verify_ode(equation, ode_solution))


# ---------------------------------------------------------------------------
# 矩阵运算
# ---------------------------------------------------------------------------


def _parse_matrix_literal(text: str) -> sp.Matrix:
    match = re.search(r"\[\s*\[.*\]\s*\]", text, flags=re.DOTALL)
    if not match:
        raise ValueError("未找到矩阵,格式如 [[1, 2], [3, 4]]")
    try:
        data = ast.literal_eval(match.group(0))
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"矩阵字面量无法解析: {exc}") from exc

    if (
        not isinstance(data, list)
        or not data
        or not all(isinstance(row, list) and row for row in data)
        or any(len(row) != len(data[0]) for row in data)
        or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for row in data
            for value in row
        )
    ):
        raise ValueError("矩阵必须是矩形数值列表,格式如 [[1, 2], [3, 4]]")
    return sp.Matrix(data)


def solve_matrix(text: str) -> Solution:
    low = text.lower()
    matrix = _parse_matrix_literal(text)
    dimensions = f"{matrix.rows}×{matrix.cols}"

    if "行列式" in text or "determinant" in low or re.search(r"\bdet\b", low):
        answer = str(matrix.det())
        operation = "计算行列式"
        operation_key = "determinant"
    elif "特征值" in text or "eigen" in low:
        values = []
        for value, multiplicity in matrix.eigenvals().items():
            values.extend([value] * multiplicity)
        values.sort(key=sp.default_sort_key)
        answer = ", ".join(str(value) for value in values)
        operation = "计算特征值"
        operation_key = "eigenvalues"
    elif "逆矩阵" in text or "inverse" in low:
        if matrix.det() == 0:
            raise ValueError("矩阵不可逆(行列式为 0)")
        answer = str(matrix.inv().tolist())
        operation = "求逆矩阵"
        operation_key = "inverse"
    elif "转置" in text or "transpose" in low:
        answer = str(matrix.T.tolist())
        operation = "求转置"
        operation_key = "transpose"
    elif "秩" in text or re.search(r"\brank\b", low):
        answer = str(matrix.rank())
        operation = "计算秩"
        operation_key = "rank"
    else:
        raise ValueError("无法识别矩阵操作,支持:行列式、特征值、逆矩阵、转置、秩")

    solution = _make_solution(
        text,
        "matrix",
        answer,
        [f"解析矩阵({dimensions}): {matrix.tolist()}", operation],
    )
    return attach(solution, verify_matrix(matrix, operation_key, answer))


# ---------------------------------------------------------------------------
# 数论
# ---------------------------------------------------------------------------


def solve_number_theory(text: str) -> Solution:
    low = text.lower()
    numbers = [int(n) for n in re.findall(r"-?\d+", text)]
    if not numbers:
        raise ValueError("未找到整数参数")

    if "gcd" in low or "最大公约数" in low:
        if len(numbers) < 2:
            raise ValueError("gcd 需要两个整数")
        value = sp.gcd(numbers[0], numbers[1])
        solution = _make_solution(
            text,
            "number_theory",
            str(value),
            [f"计算 gcd({numbers[0]}, {numbers[1]})"],
        )
        return attach(
            solution, verify_gcd(numbers[0], numbers[1], str(value))
        )

    if "lcm" in low or "最小公倍数" in low:
        if len(numbers) < 2:
            raise ValueError("lcm 需要两个整数")
        value = sp.lcm(numbers[0], numbers[1])
        solution = _make_solution(
            text,
            "number_theory",
            str(value),
            [f"计算 lcm({numbers[0]}, {numbers[1]})"],
        )
        return attach(
            solution, verify_lcm(numbers[0], numbers[1], str(value))
        )

    if "factor" in low or "质因数" in low or "因数分解" in low:
        n = numbers[0]
        factors = sp.factorint(n)
        parts = [
            f"{prime}**{exp}" if exp > 1 else str(prime)
            for prime, exp in sorted(factors.items())
        ]
        answer = " * ".join(parts) if parts else "1"
        solution = _make_solution(
            text,
            "number_theory",
            answer,
            [f"对 {n} 做质因数分解"],
        )
        return attach(solution, verify_factorization(n, answer))

    if "prime" in low or "质数" in low:
        n = numbers[0]
        answer = "yes" if sp.isprime(n) else "no"
        solution = _make_solution(
            text,
            "number_theory",
            answer,
            [f"判断 {n} 是否为质数"],
        )
        return attach(solution, verify_primality(n, answer))

    raise ValueError("无法识别的数论题型")


# ---------------------------------------------------------------------------
# 方程与方程组
# ---------------------------------------------------------------------------


def _format_single_variable(var: sp.Symbol, solutions: list) -> str:
    if not solutions:
        return "无解"
    ordered = sorted(solutions, key=sp.default_sort_key)
    return " or ".join(f"{var} = {solution}" for solution in ordered)


def solve_equation(text: str) -> Solution:
    if re.search(r"<=|>=|!=|<|>", text):
        raise ValueError("不等式题请使用 'find integers ... such that ...' 格式")

    body = text
    target_var: str | None = None
    match = re.search(r"\bfor\s+([a-zA-Z]\w*)\b", body, flags=re.IGNORECASE)
    if match:
        target_var = match.group(1)
        body = body[: match.start()] + body[match.end() :]

    body = _strip_prefixes(body, _EQUATION_PREFIXES).strip(" :：,，;；")
    equation_strings = [
        part.strip() for part in re.split(r"\s+and\s+|;", body) if part.strip()
    ]
    if not equation_strings:
        raise ValueError("未找到方程")

    equations = []
    symbols_seen: set[sp.Symbol] = set()
    for equation_str in equation_strings:
        if equation_str.count("=") != 1:
            raise ValueError(f"无法解析方程: {equation_str!r}")
        lhs_str, rhs_str = equation_str.split("=")
        lhs = parse_symbolic(lhs_str.strip())
        rhs = parse_symbolic(rhs_str.strip())
        equations.append(sp.Eq(lhs, rhs))
        symbols_seen |= lhs.free_symbols | rhs.free_symbols

    if target_var:
        variables = [sp.Symbol(target_var)]
    else:
        variables = sorted(symbols_seen, key=lambda s: s.name)

    if not variables:
        raise ValueError("方程中没有未知数")

    steps = [f"解析方程: {', '.join(str(eq) for eq in equations)}"]
    steps.append(f"未知数: {', '.join(str(v) for v in variables)}")

    if len(equations) == 1 and len(variables) == 1:
        solutions = run_with_timeout(sp.solve, equations[0], variables[0])
        answer = _format_single_variable(variables[0], solutions)
        steps.append("使用 SymPy solve 求解单个方程")
        solution = _make_solution(text, "equation", answer, steps)
        return attach(
            solution, verify_equation(equations[0], variables[0], solutions)
        )

    if len(equations) == 1 and target_var is None and len(variables) > 1:
        raise ValueError("方程含多个未知数,请用 'for <变量>' 指定求解目标")

    solution_dicts = run_with_timeout(sp.solve, equations, variables, dict=True)
    if not solution_dicts:
        answer = "无解"
    else:
        formatted = []
        for solution_dict in solution_dicts:
            parts = [
                f"{var} = {solution_dict.get(var, var)}" for var in variables
            ]
            formatted.append(", ".join(parts))
        answer = " or ".join(formatted)

    steps.append("使用 SymPy solve 求解方程组")
    solution = _make_solution(text, "equation", answer, steps)
    return attach(solution, verify_system(equations, variables, solution_dicts))
