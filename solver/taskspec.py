"""结构化任务协议。

Agent 的每个前端(规则解析、LLM 规划、外部调用方)都输出同一份
:class:`TaskSpec`,再由确定性后端执行。LLM 只负责"翻译"题目,
不负责计算;所有数值结果仍由 SymPy / Z3 产生。

协议字段按题型裁剪,未使用的字段可以为空。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .text import normalize_text, parse_symbolic

SUPPORTED_TYPES = (
    "arithmetic",
    "simplify",
    "equation",
    "derivative",
    "integral",
    "limit",
    "series",
    "ode",
    "matrix",
    "number_theory",
    "constraint",
)

_EXPRESSION_TYPES = {"arithmetic", "simplify", "derivative", "integral", "limit", "series"}
_MATRIX_OPS = {"determinant", "eigenvalues", "inverse", "transpose", "rank"}
_MATRIX_OP_ALIASES = {
    "det": "determinant",
    "determinant": "determinant",
    "eigen": "eigenvalues",
    "eigenvalue": "eigenvalues",
    "eigenvalues": "eigenvalues",
    "inv": "inverse",
    "inverse": "inverse",
    "transpose": "transpose",
    "trans": "transpose",
    "rank": "rank",
}
_NUMBER_OPS = {"factorization", "gcd", "lcm", "primality"}
_NUMBER_OP_ALIASES = {
    "factor": "factorization",
    "factorization": "factorization",
    "factorize": "factorization",
    "prime_factorization": "factorization",
    "gcd": "gcd",
    "lcm": "lcm",
    "prime": "primality",
    "primality": "primality",
    "isprime": "primality",
}
_VAR_RE = re.compile(r"^[A-Za-z]\w*$")


class SpecError(ValueError):
    """任务描述不符合协议。"""


def _extract_json(text: str) -> str:
    """从模型输出中取出 JSON 对象,容忍 Markdown 代码块。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        raise SpecError("输出中没有找到 JSON 对象")
    return stripped[start : end + 1]


def _as_str_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"\s+and\s+|[,，;；]", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, list):
        result = []
        for item in value:
            if not isinstance(item, (str, int, float)):
                raise SpecError(f"{field_name} 必须是字符串列表")
            result.append(str(item).strip())
        return [item for item in result if item]
    raise SpecError(f"{field_name} 必须是字符串或字符串列表")


def _as_direction(value: Any) -> str:
    text = str(value or "+-").strip().lower()
    mapping = {
        "+": "+",
        "-": "-",
        "+-": "+-",
        "both": "+-",
        "two-sided": "+-",
        "双侧": "+-",
        "right": "+",
        "右": "+",
        "右侧": "+",
        "left": "-",
        "左": "-",
        "左侧": "-",
    }
    if text not in mapping:
        raise SpecError("direction 只能是 '+', '-' 或 '+-'")
    return mapping[text]


def _as_number(value: Any) -> int:
    if isinstance(value, bool):
        raise SpecError("numbers 必须是整数")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value.strip())
    raise SpecError(f"numbers 中含非整数: {value!r}")


@dataclass
class TaskSpec:
    """一道题的结构化描述。"""

    type: str
    goal: str = ""
    expression: str = ""
    equations: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    bounds: dict[str, str] | None = None
    point: str = ""
    direction: str = "+-"
    center: str = "0"
    order: int = 6
    ode: str = ""
    operation: str = ""
    matrix: list[list[float]] | None = None
    numbers: list[int] = field(default_factory=list)
    domain: str = "integer"
    constraints: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # 构造与校验
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskSpec":
        if not isinstance(data, dict):
            raise SpecError("任务描述必须是 JSON 对象")

        spec = cls(
            type=str(data.get("type", "")).strip().lower(),
            goal=str(data.get("goal", "") or "").strip(),
        )

        expression = data.get("expression", data.get("expr"))
        if expression is None and isinstance(data.get("expressions"), list):
            expression = data["expressions"][0] if data["expressions"] else ""
        spec.expression = str(expression or "").strip()

        raw_equations = data.get("equations", data.get("equation"))
        if raw_equations is not None:
            spec.equations = [
                equation.replace("==", "=").strip()
                for equation in _as_str_list(raw_equations, "equations")
            ]

        spec.variables = _as_str_list(data.get("variables", data.get("variable")), "variables")

        bounds = data.get("bounds")
        if isinstance(bounds, dict):
            if "lower" not in bounds or "upper" not in bounds:
                raise SpecError("bounds 需要同时提供 lower 和 upper")
            spec.bounds = {
                "lower": str(bounds["lower"]).strip(),
                "upper": str(bounds["upper"]).strip(),
            }
        elif isinstance(bounds, (list, tuple)):
            if len(bounds) != 2:
                raise SpecError("bounds 列表应包含两个元素")
            spec.bounds = {
                "lower": str(bounds[0]).strip(),
                "upper": str(bounds[1]).strip(),
            }

        spec.point = str(data.get("point", "") or "").strip()
        spec.direction = _as_direction(data.get("direction"))
        spec.center = str(data.get("center", "0") or "0").strip()
        if data.get("order") is not None:
            try:
                spec.order = int(data["order"])
            except (TypeError, ValueError) as exc:
                raise SpecError("order 必须是整数") from exc
        spec.ode = str(data.get("ode", "") or "").strip()

        operation = str(data.get("operation", "") or "").strip().lower()
        if spec.type == "matrix" and operation:
            spec.operation = _MATRIX_OP_ALIASES.get(operation, operation)
        elif spec.type == "number_theory" and operation:
            spec.operation = _NUMBER_OP_ALIASES.get(operation, operation)
        else:
            spec.operation = operation

        raw_matrix = data.get("matrix")
        if raw_matrix is not None:
            spec.matrix = cls._parse_matrix(raw_matrix)

        if data.get("numbers") is not None:
            numbers = data["numbers"]
            if not isinstance(numbers, list):
                numbers = [numbers]
            spec.numbers = [_as_number(number) for number in numbers]

        domain = str(data.get("domain", "integer") or "integer").strip().lower()
        spec.domain = {
            "int": "integer",
            "integers": "integer",
            "integer": "integer",
            "整数": "integer",
            "real": "real",
            "reals": "real",
            "实数": "real",
        }.get(domain, domain)

        spec.constraints = _as_str_list(data.get("constraints"), "constraints")

        spec.validate()
        return spec

    @staticmethod
    def _parse_matrix(raw: Any) -> list[list[float]]:
        if not isinstance(raw, list) or not raw:
            raise SpecError("matrix 必须是非空二维列表")
        matrix: list[list[float]] = []
        for row in raw:
            if not isinstance(row, (list, tuple)) or not row:
                raise SpecError("matrix 的每一行都必须是非空列表")
            values = []
            for value in row:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise SpecError("matrix 只能包含数值")
                values.append(value)
            matrix.append(values)
        width = len(matrix[0])
        if any(len(row) != width for row in matrix):
            raise SpecError("matrix 必须是矩形")
        return matrix

    @classmethod
    def from_json_text(cls, text: str) -> "TaskSpec":
        try:
            data = json.loads(_extract_json(text))
        except json.JSONDecodeError as exc:
            raise SpecError(f"JSON 解析失败: {exc}") from exc
        return cls.from_dict(data)

    def validate(self) -> None:
        if self.type not in SUPPORTED_TYPES:
            raise SpecError(
                f"不支持的 type: {self.type!r};可选 {', '.join(SUPPORTED_TYPES)}"
            )

        for variable in self.variables:
            if not _VAR_RE.match(variable):
                raise SpecError(f"非法变量名: {variable!r}")

        if self.type in _EXPRESSION_TYPES and not self.expression:
            raise SpecError(f"{self.type} 需要 expression 字段")
        if self.type in _EXPRESSION_TYPES:
            self._validate_expression(self.expression, "expression")

        if self.type == "equation":
            if not self.equations:
                raise SpecError("equation 需要 equations 字段")
            for equation in self.equations:
                if equation.count("=") != 1:
                    raise SpecError(f"方程必须恰好包含一个等号: {equation!r}")
                left, right = equation.split("=", 1)
                self._validate_expression(left, "方程左侧")
                self._validate_expression(right, "方程右侧")

        if self.type == "integral" and self.bounds is not None:
            if not self.bounds["lower"] or not self.bounds["upper"]:
                raise SpecError("积分上下限不能为空")
            self._validate_expression(self.bounds["lower"], "积分下限")
            self._validate_expression(self.bounds["upper"], "积分上限")

        if self.type == "limit":
            if not self.point:
                raise SpecError("limit 需要 point 字段")
            self._validate_expression(self.point, "极限点")

        if self.type == "series":
            if not 1 <= self.order <= 20:
                raise SpecError("order 必须在 1 到 20 之间")
            self._validate_expression(self.center, "展开中心")

        if self.type == "ode":
            if not self.ode or "=" not in self.ode:
                raise SpecError("ode 需要形如 y' = f(x, y) 的方程")

        if self.type == "matrix":
            if self.operation not in _MATRIX_OPS:
                raise SpecError(
                    "matrix 的 operation 只能是 "
                    + ", ".join(sorted(_MATRIX_OPS))
                )
            if not self.matrix:
                raise SpecError("matrix 题需要 matrix 字段")

        if self.type == "number_theory":
            if self.operation not in _NUMBER_OPS:
                raise SpecError(
                    "number_theory 的 operation 只能是 "
                    + ", ".join(sorted(_NUMBER_OPS))
                )
            required = 2 if self.operation in {"gcd", "lcm"} else 1
            if len(self.numbers) < required:
                raise SpecError(f"{self.operation} 至少需要 {required} 个整数")

        if self.type == "constraint":
            if not self.variables:
                raise SpecError("constraint 需要 variables 字段")
            if not self.constraints:
                raise SpecError("constraint 需要 constraints 字段")
            if self.domain not in {"integer", "real"}:
                raise SpecError("domain 只能是 'integer' 或 'real'")

    @staticmethod
    def _validate_expression(text: str, label: str) -> None:
        try:
            parse_symbolic(normalize_text(text))
        except Exception as exc:
            raise SpecError(f"{label} 无法解析: {text!r} ({exc})") from exc

    # ------------------------------------------------------------------
    # 渲染为现有后端接受的规范题面
    # ------------------------------------------------------------------

    @property
    def main_variable(self) -> str:
        return self.variables[0] if self.variables else "x"

    def canonical_problem(self) -> str:
        """把 TaskSpec 转成确定性后端能直接解析的题面。"""
        kind = self.type
        var = self.main_variable

        if kind == "arithmetic":
            return f"compute {self.expression}"
        if kind == "simplify":
            return f"simplify {self.expression}"
        if kind == "derivative":
            return f"differentiate {self.expression} with respect to {var}"
        if kind == "integral":
            if self.bounds is not None:
                return (
                    f"integrate {self.expression} from {self.bounds['lower']} "
                    f"to {self.bounds['upper']} with respect to {var}"
                )
            return f"integrate {self.expression} with respect to {var}"
        if kind == "limit":
            suffix = self.direction if self.direction in {"+", "-"} else ""
            return f"limit of {self.expression} as {var} -> {self.point}{suffix}"
        if kind == "series":
            return (
                f"series of {self.expression} around {var}={self.center} "
                f"to order {self.order}"
            )
        if kind == "equation":
            body = " and ".join(self.equations)
            if len(self.variables) == 1:
                return f"solve {body} for {self.variables[0]}"
            return f"solve {body}"
        if kind == "ode":
            return f"solve the ode {self.ode}"
        if kind == "matrix":
            return f"{self.operation} of {json.dumps(self.matrix)}"
        if kind == "number_theory":
            if self.operation == "factorization":
                return f"factorize {self.numbers[0]}"
            if self.operation == "gcd":
                return f"gcd {self.numbers[0]} {self.numbers[1]}"
            if self.operation == "lcm":
                return f"lcm {self.numbers[0]} {self.numbers[1]}"
            return f"is {self.numbers[0]} prime"
        if kind == "constraint":
            word = "integers" if self.domain == "integer" else "reals"
            variables = " and ".join(self.variables)
            constraints = " and ".join(self.constraints)
            return f"find {word} {variables} such that {constraints}"
        raise SpecError(f"不支持的 type: {kind!r}")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type}
        if self.goal:
            data["goal"] = self.goal
        if self.expression:
            data["expression"] = self.expression
        if self.equations:
            data["equations"] = list(self.equations)
        if self.variables:
            data["variables"] = list(self.variables)
        if self.bounds is not None:
            data["bounds"] = dict(self.bounds)
        if self.point:
            data["point"] = self.point
        if self.type == "limit":
            data["direction"] = self.direction
        if self.type == "series":
            data["center"] = self.center
            data["order"] = self.order
        if self.ode:
            data["ode"] = self.ode
        if self.operation:
            data["operation"] = self.operation
        if self.matrix is not None:
            data["matrix"] = [list(row) for row in self.matrix]
        if self.numbers:
            data["numbers"] = list(self.numbers)
        if self.type == "constraint":
            data["domain"] = self.domain
            data["constraints"] = list(self.constraints)
        return data
