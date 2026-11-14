# 架构

求解只有一条计算路径：先得到 `TaskSpec`，再按字段调用 SymPy 或 Z3。规则和 LLM 的差别只在于谁产生这份任务。字段见[任务协议](taskspec.md)，检查方法见[验证](verification.md)，功能与限制见[功能目录](features.md)。

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
| `solver/text.py` | 把 Unicode、全角符号和隐式乘法归一化后解析。表达式只允许数字、字母、运算符、括号、逗号、百分号和空白，并拒绝 `__`、`import`、`eval`、`exec`、`lambda`、`open(`、`os.`、`sys.`。不使用 `eval`。矩阵字面量用 `ast.literal_eval` |
| `webapp.py` | 标准库 HTTP 服务。页面在 `webapp_assets/` |

`Solution.planner` 记录来源：`rule`、`llm` 或 `spec`。`Solution.task` 保存实际执行的任务。规则成功且验证没有失败时，不请求模型。
