"""规则优先、LLM 兜底的规划层。

流程:
    1. 先用规则求解器直接尝试(零 token、零网络)。
    2. 规则失败,或规则结果未通过独立验证,且配置了 LLM 时,
       让模型把题目翻译成 :class:`TaskSpec`(只翻译,不计算)。
    3. 校验任务描述,再交给 SymPy / Z3 确定性执行。

模型输出只决定"算什么",不决定"答案是什么"。
"""

from __future__ import annotations

from typing import Callable

from .core import solve_problem, solve_route
from .llm import complete_chat, llm_available
from .taskspec import SpecError, TaskSpec
from .types import Solution

#: 兼容注入的补全函数签名:接收 messages,返回文本。
Complete = Callable[[list[dict[str, str]]], str]

SYSTEM_PROMPT = """你是"数学题翻译器",不是解题器。你的任务是把用户的数学题翻译成严格 JSON 任务描述,交给确定性符号引擎执行。

规则:
1. 只输出一个 JSON 对象,不要 Markdown 代码块,不要任何解释。
2. 绝不计算答案,只填写题目中的表达式、变量、范围和操作。
3. 表达式使用 Python/SymPy 语法:乘方用 **,自然常数写作 E 或 exp(1),自然对数 log(x),无穷写作 oo。
4. type 只能是以下之一,字段按题型填写:
   {"type":"arithmetic","expression":"..."}
   {"type":"simplify","expression":"..."}
   {"type":"equation","equations":["..."],"variables":["x"]}
   {"type":"derivative","expression":"...","variables":["x"]}
   {"type":"integral","expression":"...","variables":["x"],"bounds":{"lower":"0","upper":"1"}}
   {"type":"limit","expression":"...","variables":["x"],"point":"0","direction":"+-"}
   {"type":"series","expression":"...","variables":["x"],"center":"0","order":6}
   {"type":"ode","ode":"y' = 2*x"}
   {"type":"matrix","operation":"determinant|eigenvalues|inverse|transpose|rank","matrix":[[1,2],[3,4]]}
   {"type":"number_theory","operation":"factorization|gcd|lcm|primality","numbers":[360]}
   {"type":"constraint","domain":"integer|real","variables":["x","y"],"constraints":["x + y = 10","x - y = 4"]}
5. 不定积分省略 bounds;integrals 的上下限、limit 的趋向点、series 的展开中心都要从题目中提取。
6. direction 取 +、- 或 +-(默认双侧)。
7. 变量缺省为 x;不要编造题目中不存在的数据。

示例:
题目: 计算 (12+8)/4
输出: {"type":"arithmetic","expression":"(12+8)/4"}

题目: 求 x**2 从 0 到 1 的定积分
输出: {"type":"integral","expression":"x**2","variables":["x"],"bounds":{"lower":"0","upper":"1"}}

题目: 求 sin(x)/x 当 x 趋于 0 的极限
输出: {"type":"limit","expression":"sin(x)/x","variables":["x"],"point":"0","direction":"+-"}

题目: 把 exp(x) 在 x=0 处展开到 5 阶
输出: {"type":"series","expression":"exp(x)","variables":["x"],"center":"0","order":5}

题目: 解微分方程 y' = 2*x
输出: {"type":"ode","ode":"y' = 2*x"}

题目: 求 [[1,2],[3,4]] 的行列式
输出: {"type":"matrix","operation":"determinant","matrix":[[1,2],[3,4]]}
"""


def plan_with_llm(text: str, complete: Complete) -> TaskSpec:
    """让 LLM 生成 TaskSpec;格式错误时带上错误信息重试一次。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"题目: {text}"},
    ]
    raw = complete(messages)
    try:
        return TaskSpec.from_json_text(raw)
    except SpecError as first_error:
        repair_messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    f"上面的输出不符合任务协议: {first_error}\n"
                    "请只输出修正后的 JSON 对象,不要解释。"
                ),
            },
        ]
        raw_retry = complete(repair_messages)
        try:
            return TaskSpec.from_json_text(raw_retry)
        except SpecError as second_error:
            raise SpecError(
                f"LLM 两次输出都不符合协议: {second_error}"
            ) from second_error


def execute_spec(spec: TaskSpec, original_problem: str) -> Solution:
    """执行结构化任务;题型已确定,直接调用对应后端。"""
    canonical = spec.canonical_problem()
    try:
        solution = solve_route(spec.type, canonical)
    except Exception as exc:
        solution = Solution(
            problem=original_problem,
            problem_type=spec.type,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    solution.problem = original_problem
    solution.problem_type = spec.type
    solution.planner = "spec"
    solution.task = spec.to_dict()
    solution.steps.insert(0, f"结构化任务: {canonical}")
    return solution


def solve_with_planner(
    text: str,
    *,
    allow_llm: bool = True,
    complete: Complete | None = None,
) -> Solution:
    """规则优先求解;必要时回退到 LLM 规划,再确定性执行。"""
    rule_solution = solve_problem(text)
    rule_solution.planner = "rule"

    # 规则成功且未收到"验证失败"信号,直接返回,不消耗 token。
    if rule_solution.ok and rule_solution.verified is not False:
        return rule_solution

    if not allow_llm:
        return rule_solution
    if complete is None:
        if not llm_available():
            return rule_solution
        complete = complete_chat

    try:
        spec = plan_with_llm(text, complete)
        llm_solution = execute_spec(spec, text)
    except Exception as exc:
        if rule_solution.ok:
            rule_solution.steps.append(f"LLM 规划未采用: {exc}")
            return rule_solution
        return Solution(
            problem=text,
            ok=False,
            planner="llm",
            error=(
                f"规则求解失败({rule_solution.error}); "
                f"LLM 规划失败: {exc}"
            ),
        )

    llm_solution.planner = "llm"
    llm_solution.steps.insert(0, "规划来源: LLM(只翻译,不计算)")

    if llm_solution.ok or not rule_solution.ok:
        return llm_solution

    # LLM 规划执行失败,但规则给出了(未通过验证的)结果,保留规则结果。
    rule_solution.steps.append(f"LLM 规划结果执行失败: {llm_solution.error}")
    return rule_solution
