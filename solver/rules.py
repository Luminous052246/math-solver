"""把自然语言题目解析成 TaskSpec。

这里只识别题型并提取字段，不计算结果。规则路径和 LLM 路径
随后都把 TaskSpec 交给同一套后端执行。
"""

from __future__ import annotations

import ast
import re

from .taskspec import TaskSpec
from .text import normalize_text

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

_ROUTES = {
    "constraint",
    "ode",
    "limit",
    "series",
    "matrix",
    "derivative",
    "integral",
    "simplify",
    "number_theory",
    "equation",
    "arithmetic",
}


_HINT_CONTINUATIONS = {
    "factor": ("s", "ize", "ization"),
    "eigen": ("value", "values"),
}


def _contains_hint(hint: str, low: str) -> bool:
    """英文关键词按词边界匹配，中文关键词仍按子串匹配。"""
    if not re.search(r"[a-z]", hint):
        return hint in low
    if hint == "lim ":
        return re.search(r"(?<![a-z])lim(?![a-z])", low) is not None
    if hint == "d/d":
        return re.search(r"(?<![a-z])d/d", low) is not None
    if any(character in hint for character in "/'"):
        return re.search(rf"(?<![a-z]){re.escape(hint)}(?![a-z])", low) is not None
    continuations = _HINT_CONTINUATIONS.get(hint, ("s",))
    suffix = "(?:" + "|".join(re.escape(item) for item in continuations) + ")?"
    return re.search(rf"(?<![a-z]){re.escape(hint)}{suffix}(?![a-z])", low) is not None


def _strip_prefixes(text: str, patterns: list[str]) -> str:
    """去掉句首的题型关键词。长的模式应排在前面。"""
    result = text
    for pattern in patterns:
        result = re.sub(
            rf"^\s*(?:{pattern})\s*[:：]?\s*", "", result, flags=re.IGNORECASE
        )
    return result.strip()


def _select_route(low: str) -> tuple[str, str | None]:
    for route, hints in _ROUTE_TABLE:
        for hint in hints:
            if _contains_hint(hint, low):
                return route, hint
    if "=" in low:
        return "equation", "="
    return "arithmetic", None


def route_problem(text: str) -> tuple[str, str | None]:
    """返回题目被分到的题型及命中的关键词。"""
    return _select_route(normalize_text(text).lower())


def parse_problem(text: str) -> TaskSpec:
    """按关键词路由，并把题目解析成 TaskSpec。"""
    normalized = normalize_text(text)
    route, _ = _select_route(normalized.lower())
    return parse_route(route, normalized)


def parse_route(route: str, text: str) -> TaskSpec:
    """按指定题型解析。文本会先做归一化。"""
    if route not in _ROUTES:
        raise ValueError(f"不支持的题型: {route!r}")
    normalized = normalize_text(text)
    parser = _PARSERS[route]
    return parser(normalized)


def _parse_arithmetic(text: str) -> TaskSpec:
    expression = _strip_prefixes(text, _ARITH_PREFIXES).strip(" :：,，;；")
    return TaskSpec.from_dict({"type": "arithmetic", "expression": expression})


def _parse_simplify(text: str) -> TaskSpec:
    expression = _strip_prefixes(text, _SIMPLIFY_PREFIXES).strip(" :：,，;；")
    return TaskSpec.from_dict({"type": "simplify", "expression": expression})


def _parse_derivative(text: str) -> TaskSpec:
    var_name: str | None = None
    match = re.search(r"with respect to\s+([a-zA-Z]\w*)", text, flags=re.IGNORECASE)
    if match:
        var_name = match.group(1)
        text_wo = re.sub(
            r"with respect to\s+[a-zA-Z]\w*", "", text, flags=re.IGNORECASE
        )
    else:
        text_wo = text

    match = re.search(r"\bd\s*/\s*d\s*([a-zA-Z])\b", text_wo)
    if match:
        var_name = var_name or match.group(1)
        text_wo = re.sub(r"\bd\s*/\s*d\s*[a-zA-Z]\b", "", text_wo, flags=re.IGNORECASE)

    expression = _strip_prefixes(text_wo, _DERIVATIVE_PREFIXES).strip(" :：,，;；")
    data: dict = {"type": "derivative", "expression": expression}
    if var_name:
        data["variables"] = [var_name]
    if _contains_hint("partial", text.lower()) or "偏导" in text:
        data["goal"] = "partial"
    return TaskSpec.from_dict(data)


def _parse_integral(text: str) -> TaskSpec:
    var_name: str | None = None
    match = re.search(r"with respect to\s+([a-zA-Z]\w*)", text, flags=re.IGNORECASE)
    if match:
        var_name = match.group(1)
        body = re.sub(
            r"with respect to\s+[a-zA-Z]\w*", "", text, flags=re.IGNORECASE
        )
    else:
        body = text

    bounds = None
    match = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+)$", body, flags=re.IGNORECASE)
    if match:
        bounds = (match.group(1).strip(), match.group(2).strip())
        body = body[: match.start()]

    expression = _strip_prefixes(body, _INTEGRAL_PREFIXES).strip(" :：,，;；")
    data: dict = {"type": "integral", "expression": expression}
    if var_name:
        data["variables"] = [var_name]
    if bounds is not None:
        data["bounds"] = {"lower": bounds[0], "upper": bounds[1]}
    return TaskSpec.from_dict(data)


def _normalize_limit_point(point: str) -> tuple[str, str]:
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


def _parse_limit(text: str) -> TaskSpec:
    var_name: str | None = None
    point_str: str | None = None
    body = text

    match = re.search(
        r"\bas\s+([a-zA-Z]\w*)\s*(?:->|tends?\s+to)\s*([^\s,，]+)",
        text,
        flags=re.IGNORECASE,
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
    body = _strip_prefixes(body, _LIMIT_PREFIXES)
    expression = body.replace("的极限", "").strip(" :：,，;；")
    data: dict = {
        "type": "limit",
        "expression": expression,
        "variables": [var_name],
        "point": point_str,
        "direction": direction,
    }
    return TaskSpec.from_dict(data)


def _parse_series(text: str) -> TaskSpec:
    var_name: str | None = None
    center_str = "0"
    body = text

    match = re.search(
        r"(?:around|at)\s+([a-zA-Z]\w*)\s*=\s*([^\s,，]+)", text, flags=re.IGNORECASE
    )
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
    expression = body.strip(" :：,，;；")

    data: dict = {
        "type": "series",
        "expression": expression,
        "center": center_str,
        "order": order,
    }
    if var_name:
        data["variables"] = [var_name]
    return TaskSpec.from_dict(data)


def _parse_ode(text: str) -> TaskSpec:
    body = _strip_prefixes(text, _ODE_PREFIXES).strip(" :：,，;；")
    return TaskSpec.from_dict({"type": "ode", "ode": body})


def _parse_matrix_literal(text: str) -> list[list[float]]:
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
    return data


def _parse_matrix(text: str) -> TaskSpec:
    low = text.lower()
    matrix = _parse_matrix_literal(text)
    if "行列式" in text or _contains_hint("determinant", low) or re.search(r"\bdet\b", low):
        operation = "determinant"
    elif "特征值" in text or _contains_hint("eigen", low):
        operation = "eigenvalues"
    elif "逆矩阵" in text or _contains_hint("inverse", low):
        operation = "inverse"
    elif "转置" in text or _contains_hint("transpose", low):
        operation = "transpose"
    elif "秩" in text or _contains_hint("rank", low):
        operation = "rank"
    else:
        raise ValueError("无法识别矩阵操作,支持:行列式、特征值、逆矩阵、转置、秩")
    return TaskSpec.from_dict(
        {"type": "matrix", "operation": operation, "matrix": matrix}
    )


def _parse_number_theory(text: str) -> TaskSpec:
    low = text.lower()
    numbers = [int(n) for n in re.findall(r"-?\d+", text)]
    if not numbers:
        raise ValueError("未找到整数参数")
    if _contains_hint("gcd", low) or "最大公约数" in low:
        operation = "gcd"
    elif _contains_hint("lcm", low) or "最小公倍数" in low:
        operation = "lcm"
    elif _contains_hint("factor", low) or "质因数" in low or "因数分解" in low:
        operation = "factorization"
    elif _contains_hint("prime", low) or "质数" in low:
        operation = "primality"
    else:
        raise ValueError("无法识别的数论题型")
    return TaskSpec.from_dict(
        {"type": "number_theory", "operation": operation, "numbers": numbers}
    )


def _parse_equation(text: str) -> TaskSpec:
    if re.search(r"<=|>=|!=|<|>", text):
        raise ValueError("不等式题请使用 'find integers ... such that ...' 格式")

    body = text
    target_var: str | None = None
    match = re.search(r"\bfor\s+([a-zA-Z]\w*)\b", body, flags=re.IGNORECASE)
    if match:
        target_var = match.group(1)
        body = body[: match.start()] + body[match.end() :]

    body = _strip_prefixes(body, _EQUATION_PREFIXES).strip(" :：,，;；")
    equations = [part.strip() for part in re.split(r"\s+and\s+|;", body) if part.strip()]
    if not equations:
        raise ValueError("未找到方程")
    data: dict = {"type": "equation", "equations": equations}
    if target_var:
        data["variables"] = [target_var]
    return TaskSpec.from_dict(data)


def _parse_constraint(text: str) -> TaskSpec:
    match = re.search(
        r"find\s+(integers?|reals?)\s+(.+?)\s+such that\s+(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(
            "约束题格式应为: find integers x and y such that <约束1> and <约束2>"
        )
    domain = "integer" if match.group(1).lower().startswith("integer") else "real"
    variables = [
        name
        for name in re.findall(r"[a-zA-Z]\w*", match.group(2))
        if name.lower() not in {"and", "or"}
    ]
    if not variables:
        raise ValueError("未找到变量声明")
    constraints = [
        part.strip() for part in re.split(r"\s+and\s+", match.group(3)) if part.strip()
    ]
    if not constraints:
        raise ValueError("未找到约束条件")
    return TaskSpec.from_dict(
        {
            "type": "constraint",
            "domain": domain,
            "variables": variables,
            "constraints": constraints,
        }
    )


_PARSERS = {
    "arithmetic": _parse_arithmetic,
    "simplify": _parse_simplify,
    "derivative": _parse_derivative,
    "integral": _parse_integral,
    "limit": _parse_limit,
    "series": _parse_series,
    "ode": _parse_ode,
    "matrix": _parse_matrix,
    "number_theory": _parse_number_theory,
    "equation": _parse_equation,
    "constraint": _parse_constraint,
}
