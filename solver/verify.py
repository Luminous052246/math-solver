"""答案独立验证:回代、求导、数值采样与独立消元。

验证与求解分离,尽量不复用求解时的结论:
    - 方程 / 微分方程:把解代回原式,残差应为 0
    - 导数:中心差分与符号求导双重检查
    - 积分:不定积分求导回验,定积分用数值积分交叉验证
    - 极限 / 级数:邻域数值采样
    - 矩阵:独立分数消元、乘法回验、特征方程回验
    - 数论:整除性与乘法复原,不依赖 SymPy

结果三态:
    ok=True  通过
    ok=False 不通过
    ok=None  无法验证(含参数、奇点、超时等)
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

import sympy as sp

from .timeout import run_with_timeout

if TYPE_CHECKING:
    from .types import Solution


@dataclass
class Verification:
    ok: bool | None
    message: str


def attach(solution: "Solution", verification: Verification) -> "Solution":
    """把验证结果挂到求解结果上。"""
    solution.verified = verification.ok
    solution.verification = verification.message
    return solution


# ---------------------------------------------------------------------------
# 基础数值工具
# ---------------------------------------------------------------------------


def _finite(value) -> complex | None:
    try:
        number = complex(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number.real) and math.isfinite(number.imag):
        return number
    return None


def _numeric(expr) -> complex | None:
    try:
        return _finite(sp.N(expr, 30))
    except Exception:
        return None


def _is_close(
    left: complex, right: complex, rel: float = 1e-6, abs_tol: float = 1e-9
) -> bool:
    return abs(left - right) <= max(abs_tol, rel * max(abs(left), abs(right)))


def _zero_numeric(expr: sp.Expr) -> bool | None:
    """随机取点判断表达式是否恒为 0;无法取值时返回 None。"""
    symbols = sorted(expr.free_symbols, key=lambda item: item.name)
    generator = random.Random(20261112)
    checked = 0
    for _ in range(5):
        values = {symbol: generator.uniform(0.43, 2.37) for symbol in symbols}
        number = _numeric(expr.subs(values) if values else expr)
        if number is None:
            continue
        checked += 1
        if abs(number) > 1e-8:
            return False
    return True if checked else None


def _zero(expr: sp.Expr, timeout: float = 8.0) -> bool | None:
    """判断表达式是否恒为 0:先符号化简,再随机数值兜底。"""
    try:
        simplified = run_with_timeout(sp.simplify, expr, timeout=timeout)
    except Exception:
        simplified = None
    if simplified is not None and simplified == 0:
        return True
    return _zero_numeric(expr)


def _identity_verification(residual: sp.Expr, label: str) -> Verification:
    outcome = _zero(residual)
    if outcome is True:
        return Verification(True, f"{label}通过:残差为 0")
    if outcome is False:
        return Verification(False, f"{label}失败:残差不为 0")
    return Verification(None, f"{label}无法完成(含无法数值化的项)")


# ---------------------------------------------------------------------------
# 算术 / 化简 / 求导 / 积分
# ---------------------------------------------------------------------------


def verify_identity(expr: sp.Expr, result: sp.Expr, label: str = "结果") -> Verification:
    return _identity_verification(expr - result, f"{label}回验")


def _finite_difference_check(
    expr: sp.Expr, var: sp.Symbol, result: sp.Expr
) -> tuple[bool | None, str]:
    extra = sorted(
        (expr.free_symbols | result.free_symbols) - {var}, key=lambda item: item.name
    )
    generator = random.Random(4242)
    checked = 0
    for _ in range(4):
        env = {symbol: generator.uniform(0.53, 2.31) for symbol in extra}
        point = generator.uniform(0.61, 1.97)
        step = 1e-5
        f_plus = _numeric(expr.subs(env).subs(var, point + step))
        f_minus = _numeric(expr.subs(env).subs(var, point - step))
        answer = _numeric(result.subs(env).subs(var, point))
        if f_plus is None or f_minus is None or answer is None:
            continue
        numeric = (f_plus - f_minus) / (2 * step)
        if not _is_close(numeric, answer, rel=5e-4, abs_tol=1e-7):
            return (
                False,
                f"在 {var}={point:.3f} 处有限差分 {numeric.real:.6g} "
                f"与答案 {answer.real:.6g} 不符",
            )
        checked += 1
    if checked:
        return True, f"有限差分回验通过:{checked} 个采样点与答案一致"
    return None, "无法取到有效采样点"


def verify_derivative(expr: sp.Expr, var: sp.Symbol, result: sp.Expr) -> Verification:
    status, message = _finite_difference_check(expr, var, result)
    if status is not None:
        return Verification(status, message)
    outcome = _zero(sp.diff(expr, var) - result)
    if outcome is True:
        return Verification(True, "符号回验通过:求导结果与原函数一致")
    if outcome is False:
        return Verification(False, "符号回验失败:求导结果与原函数不一致")
    return Verification(None, message)


def verify_integral(
    integrand: sp.Expr,
    var: sp.Symbol,
    result: sp.Expr,
    lower: sp.Expr | None = None,
    upper: sp.Expr | None = None,
) -> Verification:
    if lower is None or upper is None:
        return _identity_verification(
            sp.diff(result, var) - integrand, "不定积分求导回验"
        )

    try:
        numeric = run_with_timeout(
            lambda: sp.N(sp.Integral(integrand, (var, lower, upper))), timeout=10.0
        )
    except Exception:
        return Verification(None, "数值积分未能完成,无法交叉验证")

    numeric_value = _numeric(numeric)
    answer_value = _numeric(result)
    if numeric_value is None or answer_value is None:
        return Verification(None, "定积分含无法数值化的参数")
    if _is_close(numeric_value, answer_value, rel=1e-5, abs_tol=1e-7):
        return Verification(
            True, f"数值积分回验通过:数值结果 {numeric_value.real:.10g} 与答案一致"
        )
    return Verification(
        False,
        f"数值积分回验失败:数值结果 {numeric_value.real:.10g},"
        f"答案 {answer_value.real:.10g}",
    )


# ---------------------------------------------------------------------------
# 极限 / 级数
# ---------------------------------------------------------------------------


def _limit_side_values(expr: sp.Expr, var: sp.Symbol, point, side: str):
    values = []
    if point in (sp.oo, -sp.oo):
        base = 1.0 if point == sp.oo else -1.0
        for exponent in (2, 3, 4, 5, 6):
            values.append(_numeric(expr.subs(var, base * 10.0**exponent)))
    else:
        center = _numeric(point)
        if center is None or abs(center.imag) > 1e-12:
            return None
        center = center.real
        sign = -1 if side == "-" else 1
        for exponent in (2, 3, 4, 5, 6):
            values.append(_numeric(expr.subs(var, center + sign * 10**-exponent)))
    return values


def _verify_limit_side(
    expr: sp.Expr, var: sp.Symbol, point, side: str, result: sp.Expr
):
    samples = _limit_side_values(expr, var, point, side)
    if samples is None:
        return None
    samples = [value for value in samples if value is not None]
    if len(samples) < 2:
        return None

    last = samples[-1]
    if result in (sp.oo, -sp.oo):
        growing = abs(last) > abs(samples[-2])
        sign_ok = (last.real > 0) == (result == sp.oo)
        return growing and abs(last) > 1e4 and sign_ok

    answer = _numeric(result)
    if answer is None:
        return None
    return _is_close(last, answer, rel=2e-3, abs_tol=1e-6)


def verify_limit(
    expr: sp.Expr, var: sp.Symbol, point, direction: str, result: sp.Expr
) -> Verification:
    sides = ["+", "-"] if direction == "+-" else [direction]
    outcomes = []
    for side in sides:
        outcome = _verify_limit_side(expr, var, point, side, result)
        if outcome is None:
            return Verification(None, "极限无法用邻域采样验证(存在奇点或震荡)")
        outcomes.append(outcome)

    if all(outcomes):
        side_text = "双侧" if len(outcomes) == 2 else f"{sides[0]} 侧"
        return Verification(True, f"邻域采样回验通过:{side_text}采样趋近答案")
    return Verification(False, "邻域采样回验失败:采样值未趋近答案")


def verify_series(
    expr: sp.Expr,
    var: sp.Symbol,
    center: sp.Expr,
    result: sp.Expr,
    order: int,
) -> Verification:
    center_value = _numeric(center)
    if center_value is None or abs(center_value.imag) > 1e-12:
        return Verification(None, "展开中心无法数值化")
    center_value = center_value.real

    checked = 0
    for offset in (1e-2, -1e-2, 5e-2):
        point = center_value + offset
        function_value = _numeric(expr.subs(var, point))
        expansion_value = _numeric(result.subs(var, point))
        if function_value is None or expansion_value is None:
            continue
        tolerance = max(1e-6, 20 * abs(offset) ** max(order, 2))
        if abs(function_value - expansion_value) > tolerance * max(
            abs(function_value), 1.0
        ):
            return Verification(
                False,
                f"邻域采样失败:在 {var}={point:.4g} 处函数值 "
                f"{function_value.real:.8g} 与展开式 {expansion_value.real:.8g} 偏差过大",
            )
        checked += 1

    if checked:
        return Verification(True, f"邻域采样回验通过:{checked} 个点与函数值吻合")
    return Verification(None, "级数展开无法采样验证")


# ---------------------------------------------------------------------------
# 微分方程 / 方程
# ---------------------------------------------------------------------------


def verify_ode(equation: sp.Eq, solution) -> Verification:
    try:
        outcome = run_with_timeout(
            lambda: sp.checkodesol(equation, solution), timeout=12.0
        )
    except Exception:
        outcome = None

    if isinstance(outcome, tuple) and len(outcome) == 2:
        ok, residual = outcome
        if ok:
            return Verification(True, "回代检验通过:解代入微分方程后残差为 0")
        return Verification(False, f"回代检验失败:残差 {residual}")
    return Verification(None, "checkodesol 未能完成回代验证")


def verify_equation(equation: sp.Eq, var: sp.Symbol, roots: list) -> Verification:
    if not roots:
        return Verification(None, "无解结论未做独立验证")

    checked = 0
    for root in roots:
        residual = equation.lhs.subs(var, root) - equation.rhs.subs(var, root)
        outcome = _zero(residual)
        if outcome is False:
            return Verification(False, f"回代失败:{var} = {root} 不满足原方程")
        if outcome is True:
            checked += 1
    if checked == len(roots):
        return Verification(True, f"回代检验通过:{len(roots)} 个解均满足原方程")
    return Verification(None, "部分解含符号参数,未能完全回验")


def verify_system(
    equations: list[sp.Eq], variables: list[sp.Symbol], solution_dicts: list[dict]
) -> Verification:
    if not solution_dicts:
        return Verification(None, "无解结论未做独立验证")

    for mapping in solution_dicts:
        for equation in equations:
            residual = equation.lhs.subs(mapping) - equation.rhs.subs(mapping)
            outcome = _zero(residual)
            if outcome is False:
                return Verification(False, "回代失败:某组解不满足原方程组")
            if outcome is not True:
                return Verification(None, "部分解含符号参数,未能完全回验")
    return Verification(True, "回代检验通过:全部解均满足原方程组")


# ---------------------------------------------------------------------------
# 矩阵
# ---------------------------------------------------------------------------


def _det_fraction(matrix: sp.Matrix) -> Fraction:
    size = matrix.rows
    data = [[Fraction(str(matrix[i, j])) for j in range(size)] for i in range(size)]
    determinant = Fraction(1)
    for column in range(size):
        pivot = next(
            (row for row in range(column, size) if data[row][column] != 0), None
        )
        if pivot is None:
            return Fraction(0)
        if pivot != column:
            data[column], data[pivot] = data[pivot], data[column]
            determinant = -determinant
        determinant *= data[column][column]
        for row in range(column + 1, size):
            factor = data[row][column] / data[column][column]
            for col in range(column, size):
                data[row][col] -= factor * data[column][col]
    return determinant


def _rank_fraction(matrix: sp.Matrix) -> int:
    data = [
        [Fraction(str(matrix[i, j])) for j in range(matrix.cols)]
        for i in range(matrix.rows)
    ]
    rank = 0
    for column in range(matrix.cols):
        pivot = next(
            (row for row in range(rank, matrix.rows) if data[row][column] != 0), None
        )
        if pivot is None:
            continue
        data[rank], data[pivot] = data[pivot], data[rank]
        pivot_value = data[rank][column]
        for col in range(column, matrix.cols):
            data[rank][col] /= pivot_value
        for row in range(matrix.rows):
            if row != rank and data[row][column] != 0:
                factor = data[row][column]
                for col in range(column, matrix.cols):
                    data[row][col] -= factor * data[rank][col]
        rank += 1
        if rank == matrix.rows:
            break
    return rank


def _parse_scalar(text: str):
    try:
        value = sp.sympify(text)
    except Exception:
        return None
    if isinstance(value, (list, tuple, sp.MatrixBase)):
        return None
    return value


def _parse_matrix_answer(text: str):
    try:
        data = sp.sympify(text)
    except Exception:
        return None
    if not isinstance(data, (list, tuple)):
        return None
    try:
        return sp.Matrix(data)
    except Exception:
        return None


def _elementwise_zero(difference: sp.Matrix, tol: float = 1e-9) -> bool:
    for element in difference:
        value = _numeric(element)
        if value is None or abs(value) > tol:
            return False
    return True


def _eigen_check(matrix: sp.Matrix, value) -> bool | None:
    try:
        determinant = sp.simplify(
            (matrix - sp.eye(matrix.rows) * value).det()
        )
    except Exception:
        return None
    if determinant == 0:
        return True
    numeric = _numeric(determinant)
    if numeric is None:
        return None
    scale = max(1.0, float(matrix.norm()) ** matrix.rows)
    return abs(numeric) <= 1e-7 * scale


def verify_matrix(matrix: sp.Matrix, operation: str, answer: str) -> Verification:
    if operation == "determinant":
        try:
            expected = _det_fraction(matrix)
        except Exception:
            return Verification(None, "行列式无法独立消元验证")
        actual = _parse_scalar(answer)
        if actual is None:
            return Verification(None, "行列式答案无法解析")
        difference = _numeric(actual - sp.Rational(expected.numerator, expected.denominator))
        if difference is not None and abs(difference) <= 1e-9 * max(
            1.0, abs(float(expected))
        ):
            return Verification(True, "独立消元回验通过:行列式一致")
        return Verification(False, f"回验失败:独立消元得到 {expected},答案为 {actual}")

    if operation == "eigenvalues":
        values = [_parse_scalar(part.strip()) for part in answer.split(",")]
        if not values or any(value is None for value in values):
            return Verification(None, "特征值答案无法解析")
        if len(values) != matrix.rows:
            return Verification(False, "特征值数量与矩阵阶数不符")
        for value in values:
            outcome = _eigen_check(matrix, value)
            if outcome is False:
                return Verification(False, f"特征值 {value} 不满足特征方程")
            if outcome is None:
                return Verification(None, "特征方程无法完成验证")
        return Verification(
            True, f"特征方程回验通过:{len(values)} 个特征值均满足 det(A-λI)=0"
        )

    if operation == "inverse":
        parsed = _parse_matrix_answer(answer)
        if parsed is None or parsed.shape != matrix.shape:
            return Verification(None, "逆矩阵答案无法解析")
        if not _elementwise_zero(matrix * parsed - sp.eye(matrix.rows)):
            return Verification(False, "乘法回验失败:A×A^-1 不等于单位矩阵")
        return Verification(True, "乘法回验通过:A×A^-1 = I")

    if operation == "transpose":
        parsed = _parse_matrix_answer(answer)
        if parsed is None or parsed.shape != matrix.T.shape:
            return Verification(None, "转置答案无法解析")
        if not _elementwise_zero(parsed - matrix.T):
            return Verification(False, "逐元素回验失败:转置结果不一致")
        return Verification(True, "逐元素回验通过:转置结果一致")

    if operation == "rank":
        try:
            expected = _rank_fraction(matrix)
        except Exception:
            return Verification(None, "秩无法独立消元验证")
        try:
            actual = int(answer)
        except (TypeError, ValueError):
            return Verification(None, "秩答案无法解析")
        if expected != actual:
            return Verification(False, f"回验失败:独立消元得到秩 {expected},答案为 {actual}")
        return Verification(True, f"独立消元回验通过:秩为 {expected}")

    return Verification(None, "该矩阵操作暂无验证规则")


# ---------------------------------------------------------------------------
# 数论
# ---------------------------------------------------------------------------


def _trial_is_prime(number: int) -> bool:
    if number < 2:
        return False
    if number % 2 == 0:
        return number == 2
    limit = math.isqrt(number)
    factor = 3
    while factor <= limit:
        if number % factor == 0:
            return False
        factor += 2
    return True


def verify_gcd(first: int, second: int, answer: str) -> Verification:
    try:
        value = int(answer)
    except (TypeError, ValueError):
        return Verification(None, "gcd 答案无法解析")
    if value <= 0:
        return Verification(False, "回验失败:gcd 必须为正整数")
    if first % value or second % value:
        return Verification(
            False, f"回验失败:{value} 不能同时整除 {first} 与 {second}"
        )
    if math.gcd(first // value, second // value) != 1:
        return Verification(False, f"回验失败:{value} 不是最大公约数")
    return Verification(True, "整除性回验通过:是公约数且两商互质")


def verify_lcm(first: int, second: int, answer: str) -> Verification:
    try:
        value = int(answer)
    except (TypeError, ValueError):
        return Verification(None, "lcm 答案无法解析")
    expected = abs(first * second) // math.gcd(first, second)
    if value != expected:
        return Verification(False, f"回验失败:lcm 应为 {expected},答案为 {value}")
    return Verification(True, "公式回验通过:lcm = |ab| / gcd(a,b)")


def verify_factorization(number: int, answer: str) -> Verification:
    terms = [
        term.strip()
        for term in re.split(r"(?<!\*)\*(?!\*)", answer)
        if term.strip()
    ]
    if not terms:
        return Verification(None, "质因数分解答案无法解析")

    product = 1
    for term in terms:
        match = re.fullmatch(r"(\d+)(?:\s*\*\*\s*(\d+))?", term)
        if not match:
            return Verification(None, f"无法解析质因数项: {term}")
        base = int(match.group(1))
        exponent = int(match.group(2) or 1)
        if not _trial_is_prime(base):
            return Verification(False, f"回验失败:{base} 不是质数")
        product *= base**exponent

    if product != number:
        return Verification(False, f"回验失败:质因数乘积 {product} ≠ {number}")
    return Verification(True, "乘法回验通过:各因子均为质数且乘积等于原数")


def verify_primality(number: int, answer: str) -> Verification:
    if abs(number) > 10**12:
        return Verification(None, "数值过大,未做试除验证")
    expected = _trial_is_prime(abs(number))
    claimed = {"yes": True, "true": True, "no": False, "false": False}.get(
        answer.strip().lower()
    )
    if claimed is None:
        return Verification(None, "质数判断答案无法解析")
    if claimed != expected:
        return Verification(
            False, f"回验失败:{number} {'是' if expected else '不是'}质数"
        )
    return Verification(True, "试除法回验通过")
