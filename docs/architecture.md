# 架构

求解只有一条计算路径：先得到 `TaskSpec`，再按字段调用 SymPy 或 Z3。规则和 LLM 的差别只在于谁产生这份任务。

```text
自然语言
  ├─ solver/rules.py      关键词路由，提取表达式、变量、范围和操作
  └─ solver/planner.py    规则失败或验证未通过时，请求 LLM 翻译
           │
           ▼
        TaskSpec
           │
           ▼
   solver/engine.py       按字段执行，不把任务再渲染成英文题面
      ├─ sympy_backend.py
      └─ z3_backend.py
           │
           ▼
   solver/verify.py       用另一条计算路径检查答案
```

## 组件

| 模块 | 职责 |
| --- | --- |
| `solver/rules.py` | 文本归一化和题型识别。输出 `TaskSpec`，不算结果 |
| `solver/planner.py` | 决定是否调用模型。模型只返回 JSON，格式错误时带上错误重试一次 |
| `solver/taskspec.py` | 校验字段。`canonical_problem()` 只生成给人看的题面，执行时不解析它 |
| `solver/engine.py` | 规则、LLM 和外部调用方共用的执行入口 |
| `solver/sympy_backend.py` | 算术、化简、方程、微积分、级数、微分方程、矩阵、数论 |
| `solver/z3_backend.py` | 整数或实数约束。表达式用 AST 解释 |
| `solver/verify.py` | 独立检查。结果是通过、未通过或无法验证 |
| `solver/text.py` | 字符白名单和符号解析。不使用 `eval` |
| `webapp.py` | 标准库 HTTP 服务。页面在 `webapp_assets/` |

`Solution.planner` 记录来源：`rule`、`llm` 或 `spec`。`Solution.task` 保存实际执行的任务。规则成功时不会请求模型。

## 规则做不到的事

关键词路由不理解需要先设未知数、再列方程的应用题。LLM 目前也只翻译单个任务，不会自动拆成多步求解。方程默认在复数域。Z3 路径面向可以用算术和比较表达的约束，非线性与整数除法没有完整支持。微分方程只处理未知函数 `y(x)`，没有初值条件。
