"""文本归一化与表达式解析。

自然语言题目先做轻量归一化(替换 Unicode 数学符号),再用 SymPy 的
parse_expr 解析成符号表达式。为降低注入风险,表达式只允许数学字符。
"""

from __future__ import annotations

import re

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

# 标准转换 + 隐式乘法(2x -> 2*x) + 幂运算符(^ -> **)
_TRANSFORMS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

_LOCAL_DICT = {
    name: getattr(sp, name)
    for name in (
        "Abs",
        "E",
        "acos",
        "asin",
        "atan",
        "cos",
        "exp",
        "log",
        "pi",
        "sin",
        "sqrt",
        "tan",
    )
}
# 小写 e 按数学惯例视为自然常数,避免 e**x 被当成普通符号积分
_LOCAL_DICT["e"] = sp.E
# 无穷记号,供极限与级数使用
_LOCAL_DICT.update({"oo": sp.oo, "inf": sp.oo, "infinity": sp.oo})

_ALLOWED_RE = re.compile(r"^[0-9a-zA-Z_+\-*/().,%\s]*$")
_BANNED_TOKENS = ("__", "import", "eval", "exec", "lambda", "open(", "os.", "sys.")


def normalize_text(text: str) -> str:
    """统一数学符号,便于解析。"""
    text = text.strip()

    # 根号需要先处理,否则 "√x" 会变成 "sqrtx"
    text = re.sub(r"√\s*\(([^)]*)\)", r"sqrt(\1)", text)
    text = re.sub(r"√\s*([0-9]+(?:\.[0-9]+)?|[a-zA-Z])", r"sqrt(\1)", text)

    replacements = [
        ("×", "*"),
        ("·", "*"),
        ("÷", "/"),
        ("−", "-"),
        ("–", "-"),
        ("—", "-"),
        ("²", "**2"),
        ("³", "**3"),
        ("（", "("),
        ("）", ")"),
        ("，", ","),
        ("；", ";"),
        ("＝", "="),
        ("＋", "+"),
        ("－", "-"),
        ("＊", "*"),
        ("／", "/"),
        ("∞", "oo"),
        ("→", "->"),
        ("′", "'"),
        ("’", "'"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)

    # 幂运算符统一为 **
    text = text.replace("＾", "**").replace("^", "**")
    text = re.sub(r"\bln\b", "log", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sanitize_expression(expr: str) -> str:
    """限制表达式字符集,阻止明显的代码注入片段。"""
    if not _ALLOWED_RE.match(expr):
        raise ValueError(f"表达式包含不允许的字符: {expr!r}")
    lowered = expr.lower()
    for bad in _BANNED_TOKENS:
        if bad in lowered:
            raise ValueError(f"表达式包含禁止的片段: {bad!r}")
    return expr


def parse_with_locals(expr: str, extra_locals: dict) -> sp.Expr:
    """在默认符号表之外附加自定义符号后解析表达式(用于 ODE 等)。"""
    sanitize_expression(expr)
    local = dict(_LOCAL_DICT)
    local.update(extra_locals)
    return parse_expr(
        expr,
        transformations=_TRANSFORMS,
        local_dict=local,
        evaluate=True,
    )


def parse_symbolic(expr: str) -> sp.Expr:
    """把数学表达式字符串解析为 SymPy 对象。"""
    return parse_with_locals(expr, {})
