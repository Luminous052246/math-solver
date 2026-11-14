"""结构化任务协议与规划层测试(不访问网络)。"""

from __future__ import annotations

import json
import unittest

from unittest.mock import patch

from solver import (
    SpecError,
    TaskSpec,
    answers_equivalent,
    execute_spec,
    solve_with_planner,
)
from solver.planner import plan_with_llm


class FakeLLM:
    """按顺序返回预设响应的假模型。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("LLM 被调用了超出预期的次数")
        return self.responses.pop(0)


INTEGRAL_SPEC = {
    "type": "integral",
    "expression": "x**2",
    "variables": ["x"],
    "bounds": {"lower": "0", "upper": "1"},
}


class RuleFirstTests(unittest.TestCase):
    def test_rule_success_skips_llm(self) -> None:
        fake = FakeLLM([])
        solution = solve_with_planner("calculate (12 + 8) / 4", complete=fake)
        self.assertTrue(solution.ok)
        self.assertEqual(solution.answer, "5")
        self.assertEqual(solution.planner, "rule")
        self.assertEqual(solution.task["type"], "arithmetic")
        self.assertEqual(solution.task["expression"], "(12 + 8) / 4")
        self.assertEqual(fake.calls, [])

    def test_natural_language_falls_back_to_llm(self) -> None:
        fake = FakeLLM([json.dumps(INTEGRAL_SPEC, ensure_ascii=False)])
        solution = solve_with_planner(
            "求 x^2 从 0 到 1 的定积分", complete=fake
        )
        self.assertTrue(solution.ok, solution.error)
        self.assertEqual(solution.planner, "llm")
        self.assertTrue(answers_equivalent("1/3", solution.answer))
        self.assertIs(solution.verified, True)
        self.assertEqual(solution.task["type"], "integral")
        self.assertEqual(solution.problem, "求 x^2 从 0 到 1 的定积分")
        self.assertEqual(len(fake.calls), 1)

    def test_llm_disabled_keeps_rule_failure(self) -> None:
        solution = solve_with_planner(
            "求 x^2 从 0 到 1 的定积分", allow_llm=False
        )
        self.assertFalse(solution.ok)
        self.assertEqual(solution.planner, "rule")


class PlanRepairTests(unittest.TestCase):
    def test_invalid_json_is_retried_once(self) -> None:
        fake = FakeLLM(["这不是 JSON", json.dumps(INTEGRAL_SPEC)])
        spec = plan_with_llm("求定积分", fake)
        self.assertEqual(spec.type, "integral")
        self.assertEqual(len(fake.calls), 2)
        repair_prompt = fake.calls[1][-1]["content"]
        self.assertIn("不符合任务协议", repair_prompt)

    def test_invalid_twice_reports_failure(self) -> None:
        fake = FakeLLM(["nope", "still nope"])
        with self.assertRaises(SpecError):
            plan_with_llm("求定积分", fake)

    def test_solver_reports_llm_failure(self) -> None:
        fake = FakeLLM(["nope", "still nope"])
        solution = solve_with_planner(
            "求 x^2 从 0 到 1 的定积分", complete=fake
        )
        self.assertFalse(solution.ok)
        self.assertIn("LLM 规划失败", solution.error or "")

    def test_fenced_json_is_accepted(self) -> None:
        spec = TaskSpec.from_json_text(
            '```json\n{"type":"arithmetic","expression":"2+2"}\n```'
        )
        self.assertEqual(spec.type, "arithmetic")


class ExecuteSpecTests(unittest.TestCase):
    CASES = [
        ("arithmetic", {"type": "arithmetic", "expression": "(12+8)/4"}, "5"),
        (
            "simplify",
            {"type": "simplify", "expression": "sin(x)**2 + cos(x)**2"},
            "1",
        ),
        (
            "equation",
            {
                "type": "equation",
                "equations": ["x**2 - 5*x + 6 = 0"],
                "variables": ["x"],
            },
            "x = 2 or x = 3",
        ),
        (
            "derivative",
            {
                "type": "derivative",
                "expression": "x**3",
                "variables": ["x"],
            },
            "3*x**2",
        ),
        ("integral", INTEGRAL_SPEC, "1/3"),
        (
            "limit",
            {
                "type": "limit",
                "expression": "sin(x)/x",
                "variables": ["x"],
                "point": "0",
            },
            "1",
        ),
        (
            "series",
            {
                "type": "series",
                "expression": "exp(x)",
                "variables": ["x"],
                "center": "0",
                "order": 5,
            },
            "1 + x + x**2/2 + x**3/6 + x**4/24",
        ),
        (
            "ode",
            {"type": "ode", "ode": "y' = 2*x"},
            "y(x) = C1 + x**2",
        ),
        (
            "matrix",
            {
                "type": "matrix",
                "operation": "determinant",
                "matrix": [[1, 2], [3, 4]],
            },
            "-2",
        ),
        (
            "number_theory",
            {
                "type": "number_theory",
                "operation": "factorization",
                "numbers": [360],
            },
            "2**3 * 3**2 * 5",
        ),
        (
            "constraint",
            {
                "type": "constraint",
                "domain": "integer",
                "variables": ["x", "y"],
                "constraints": ["x + y = 10", "x - y = 4"],
            },
            "x = 7, y = 3",
        ),
    ]

    def test_all_types_execute_and_verify(self) -> None:
        for name, data, expected in self.CASES:
            with self.subTest(type=name):
                solution = execute_spec(TaskSpec.from_dict(data), "原题")
                self.assertTrue(solution.ok, solution.error)
                self.assertEqual(solution.planner, "spec")
                self.assertEqual(solution.task["type"], name)
                self.assertTrue(
                    answers_equivalent(expected, solution.answer),
                    f"{expected!r} != {solution.answer!r}",
                )
                self.assertIsNot(
                    solution.verified,
                    False,
                    solution.verification,
                )

    def test_execution_does_not_reparse_canonical_text(self) -> None:
        spec = TaskSpec.from_dict(
            {
                "type": "limit",
                "expression": "1/x",
                "variables": ["x"],
                "point": "0",
                "direction": "-",
            }
        )
        with patch.object(
            TaskSpec,
            "canonical_problem",
            side_effect=AssertionError("执行路径不应回读题面"),
        ):
            solution = execute_spec(spec, "原题")
        self.assertTrue(solution.ok, solution.error)
        self.assertEqual(solution.answer, "-oo")


class CanonicalTests(unittest.TestCase):
    def test_equation_with_target_variable(self) -> None:
        spec = TaskSpec.from_dict(
            {
                "type": "equation",
                "equations": ["a*x + b = 0"],
                "variables": ["x"],
            }
        )
        self.assertEqual(spec.canonical_problem(), "solve a*x + b = 0 for x")

    def test_limit_direction(self) -> None:
        spec = TaskSpec.from_dict(
            {
                "type": "limit",
                "expression": "1/x",
                "variables": ["x"],
                "point": "0",
                "direction": "-",
            }
        )
        self.assertEqual(spec.canonical_problem(), "limit of 1/x as x -> 0-")

    def test_integral_indefinite(self) -> None:
        spec = TaskSpec.from_dict(
            {"type": "integral", "expression": "x**2", "variables": ["x"]}
        )
        self.assertEqual(
            spec.canonical_problem(), "integrate x**2 with respect to x"
        )

    def test_constraint(self) -> None:
        spec = TaskSpec.from_dict(
            {
                "type": "constraint",
                "domain": "real",
                "variables": ["x"],
                "constraints": ["x > 3", "x < 6"],
            }
        )
        self.assertEqual(
            spec.canonical_problem(),
            "find reals x such that x > 3 and x < 6",
        )


class ValidationTests(unittest.TestCase):
    def test_unsupported_type(self) -> None:
        with self.assertRaises(SpecError):
            TaskSpec.from_dict({"type": "linear_algebra"})

    def test_missing_expression(self) -> None:
        with self.assertRaises(SpecError):
            TaskSpec.from_dict({"type": "integral"})

    def test_bad_bounds(self) -> None:
        with self.assertRaises(SpecError):
            TaskSpec.from_dict(
                {
                    "type": "integral",
                    "expression": "x",
                    "bounds": {"lower": "0"},
                }
            )

    def test_bad_direction(self) -> None:
        with self.assertRaises(SpecError):
            TaskSpec.from_dict(
                {
                    "type": "limit",
                    "expression": "x",
                    "point": "0",
                    "direction": "up",
                }
            )

    def test_non_rectangular_matrix(self) -> None:
        with self.assertRaises(SpecError):
            TaskSpec.from_dict(
                {
                    "type": "matrix",
                    "operation": "determinant",
                    "matrix": [[1, 2], [3]],
                }
            )

    def test_injection_blocked(self) -> None:
        with self.assertRaises(SpecError):
            TaskSpec.from_dict(
                {
                    "type": "arithmetic",
                    "expression": "__import__('os').system('dir')",
                }
            )


if __name__ == "__main__":
    unittest.main()
