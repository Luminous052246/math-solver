"""在测试集上评估求解器。

指标:
    - 求解成功率:形式化/求解过程没有报错
    - 答案正确率:最终答案与标准答案等价

用法:
    python evaluate.py
    python evaluate.py --file data/problems.jsonl --verbose
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

from solver import answers_equivalent, solve_problem


def load_problems(path: str) -> list[dict]:
    problems = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                problems.append(json.loads(line))
    return problems


def verification_label(solution) -> str:
    return {True: "通过", False: "未通过", None: "未完成"}[solution.verified]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估数学求解器")
    parser.add_argument("--file", type=str, default="data/problems.jsonl")
    parser.add_argument("--verbose", "-v", action="store_true", help="打印每一题")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    problems = load_problems(args.file)

    solved = 0
    correct = 0
    verified = 0
    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])

    for item in problems:
        problem = item["input"]
        expected = item["expected"]
        problem_type = item.get("type", "unknown")

        solution = solve_problem(problem)
        is_solved = solution.ok
        is_correct = is_solved and answers_equivalent(expected, solution.answer)
        is_verified = solution.verified is True

        solved += int(is_solved)
        correct += int(is_correct)
        verified += int(is_verified)

        stats = by_type[problem_type]
        stats[0] += 1
        stats[1] += int(is_solved)
        stats[2] += int(is_correct)
        stats[3] += int(is_verified)

        if args.verbose or not is_correct or solution.verified is False:
            status = "PASS" if is_correct else "FAIL"
            shown = solution.answer if is_solved else solution.error
            print(f"[{status}] ({problem_type}) {problem}")
            print(f"        预期: {expected}")
            print(f"        实际: {shown}")
            if solution.verification:
                print(f"        验证: {verification_label(solution)} — {solution.verification}")

    total = len(problems)
    print()
    print(
        f"共 {total} 题 | 求解成功 {solved} ({solved / total * 100:.1f}%) | "
        f"答案正确 {correct} ({correct / total * 100:.1f}%) | "
        f"独立验证通过 {verified} ({verified / max(solved, 1) * 100:.1f}%)"
    )
    print("按类型:")
    for problem_type, (type_total, type_solved, type_correct, type_verified) in sorted(
        by_type.items()
    ):
        print(
            f"  {problem_type:12s} 正确 {type_correct}/{type_total}"
            f" | 求解成功 {type_solved}/{type_total}"
            f" | 验证通过 {type_verified}/{type_solved}"
        )


if __name__ == "__main__":
    main()
