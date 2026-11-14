"""命令行入口:求解单题、批量文件或交互模式。

用法:
    python solve.py --problem "solve 2*x + 3 = 7"
    python solve.py --file problems.txt
    python solve.py --problem "..." --planner rule   # 只用规则,不调 LLM
    python solve.py --task '{"type":"integral","expression":"x**2","bounds":{"lower":"0","upper":"1"}}'
    python solve.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from solver import (
    SpecError,
    TaskSpec,
    execute_spec,
    solve_problem,
    solve_with_planner,
)
from solver.types import Solution


def print_solution(solution: Solution) -> None:
    print(f"题目: {solution.problem}")
    print(f"类型: {solution.problem_type} | 后端: {solution.backend or '-'}")
    if solution.planner != "rule":
        task = json.dumps(solution.task, ensure_ascii=False) if solution.task else "-"
        print(f"规划: {solution.planner} | 任务: {task}")
    if solution.steps:
        print("步骤:")
        for index, step in enumerate(solution.steps, 1):
            print(f"  {index}. {step}")
    if solution.ok:
        print(f"答案: {solution.answer}")
        if solution.verification:
            label = {True: "通过", False: "未通过", None: "未完成"}[solution.verified]
            print(f"验证: {label} — {solution.verification}")
    else:
        print(f"错误: {solution.error}")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SymPy / Z3 数学求解器")
    parser.add_argument("--problem", "-p", type=str, help="单道数学题")
    parser.add_argument("--file", "-f", type=str, help="题目文件,每行一题")
    parser.add_argument(
        "--planner",
        choices=("auto", "rule"),
        default="auto",
        help="auto: 规则优先,失败时用 LLM 兜底(需配置 API key);rule: 只用规则",
    )
    parser.add_argument(
        "--task",
        type=str,
        help="直接执行 JSON 结构化任务(跳过自然语言理解)",
    )
    return parser.parse_args()


def solve_one(problem: str, planner: str) -> Solution:
    if planner == "rule":
        return solve_problem(problem)
    return solve_with_planner(problem)


def run_task(raw: str, problem: str | None) -> None:
    try:
        spec = TaskSpec.from_dict(json.loads(raw))
    except json.JSONDecodeError as exc:
        print(f"任务 JSON 解析失败: {exc}")
        return
    except SpecError as exc:
        print(f"任务描述错误: {exc}")
        return
    print_solution(execute_spec(spec, problem or raw))


def main() -> None:
    args = parse_args()

    if args.task:
        run_task(args.task, args.problem)
        return

    if args.problem:
        print_solution(solve_one(args.problem, args.planner))
        return

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    print_solution(solve_one(line, args.planner))
        return

    print("交互模式:输入数学题,空行退出。")
    while True:
        try:
            problem = input("题目> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not problem:
            break
        print_solution(solve_one(problem, args.planner))


if __name__ == "__main__":
    main()
