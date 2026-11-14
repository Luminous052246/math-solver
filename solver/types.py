"""求解结果的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Solution:
    problem: str
    problem_type: str = "unknown"
    backend: str = ""
    ok: bool = False
    answer: str = ""
    steps: list[str] = field(default_factory=list)
    error: str | None = None
    verified: bool | None = None
    verification: str = ""
    # 结果由谁规划:rule(关键词路由)/ llm(LLM 翻译)/ spec(外部结构化任务)
    planner: str = "rule"
    task: dict | None = None
