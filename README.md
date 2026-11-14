# Math Solver

基于 **SymPy + Z3** 的数学解题器：用规则把数学题转换成形式化表示，再交给符号引擎精确求解。答案由计算保证，每一步都可解释、可验证；大语言模型只负责把自然语言翻译成结构化任务，不参与计算。

## Overview

Math Solver is a rule-first, neuro-symbolic math solver built on **SymPy** and **Z3**. It converts natural-language problems into formal expressions with deterministic rules, computes exact answers with symbolic engines, and then independently verifies each result. Answers come from computation rather than prediction, so every step is explainable and reproducible.

An optional LLM planner acts only as a translator. When rule-based routing fails, it converts the problem into a validated JSON task (`TaskSpec`), and the same symbolic backend computes the answer. The model never produces the final result.

The project also includes a zero-dependency local web UI with LaTeX rendering, image and handwriting input through a local Ollama vision model, a 60-problem benchmark, and a three-state verification layer (passed / failed / unverifiable).

```bash
pip install -r requirements.txt
python solve.py --problem "solve x**2 - 5*x + 6 = 0"
python webapp.py
```

## 特性

- **精确求解**：SymPy 负责代数、微积分、级数、微分方程、矩阵、数论；Z3 负责整数/实数约束与无解判定
- **答案独立验证**：求解后回代原式，或用数值方法、独立算法交叉检查，结果标记为 通过 / 未通过 / 无法验证
- **规则优先，LLM 兜底**：规则能解就不调用模型；规则失败时才让 LLM 把题目翻译成 JSON 任务，再走同一套符号后端
- **本地网页界面**：单页 UI，支持 LaTeX 渲染、示例题、上传图片识别、手写板输入
- **离线可用**：核心计算只依赖 `sympy` 和 `z3-solver`，网页使用 Python 标准库，KaTeX 已随项目内置
- **内置评测**：60 道题覆盖全部题型，求解成功率 100%、答案正确率 100%，独立验证通过 58/60（2 道无解题按设计无法验证）
- **安全解析**：表达式白名单 + AST 解释，不使用 `eval`；LLM 输出只作为任务描述，不能执行代码

## 快速开始

要求 Python 3.10+：

```bash
git clone <你的仓库地址>
cd math-solver
python -m pip install -r requirements.txt
```

命令行求解：

```bash
python solve.py --problem "solve x**2 - 5*x + 6 = 0"
```

启动网页界面（默认 <http://127.0.0.1:8765>）：

```bash
python webapp.py
```

Windows 用户也可以直接双击 `start_web.bat`，脚本会自动查找装有 `sympy`/`z3` 的 Python 并打开浏览器。

## 命令行用法

```bash
# 单题
python solve.py --problem "integrate x**2 from 0 to 1"

# 批量求解，每行一题
python solve.py --file problems.txt

# 交互模式
python solve.py

# 只用规则，不调用 LLM
python solve.py --problem "..." --planner rule

# 直接执行结构化任务
python solve.py --task '{"type":"integral","expression":"x**2","bounds":{"lower":"0","upper":"1"}}'

# 运行内置评测
python evaluate.py --verbose
```

输出示例：

```text
题目: solve x**2 - 5*x + 6 = 0
类型: equation | 后端: sympy
步骤:
  1. 解析方程: Eq(x**2 - 5*x + 6, 0)
  2. 未知数: x
  3. 使用 SymPy solve 求解单个方程
答案: x = 2 or x = 3
验证: 通过 — 回代检验通过:2 个解均满足原方程
```

## 网页界面

`webapp.py` 使用标准库 `http.server`，无需安装 Web 框架：

```bash
python webapp.py
python webapp.py --port 9000 --no-browser
python webapp.py --host 0.0.0.0
```

界面功能：

- **单题求解**：输入题目或点击示例标签，答案以 LaTeX 渲染，并显示解题步骤与“求解明细”（归一化结果、题型路由、求解后端、规划来源）
- **上传图片**：选择题目截图，由本地视觉模型识别后填入输入框，人工核对后再求解
- **手写板**：鼠标、触控屏或手写笔书写，支持撤销/清空；识别时导出白底 PNG，与上传图片共用同一接口
- **输入格式速查**：页面底部可折叠的题型与示例表

默认只监听 `127.0.0.1`。手机/平板访问可双击 `start_web_lan.bat`（监听 `0.0.0.0` 并自动打印局域网地址）；服务没有鉴权，请勿映射到公网。

图片识别与手写识别需要本地 [Ollama](https://ollama.com/) 及视觉模型，详见下一节。

## 可选：接入 LLM 规划器

规则路径永远优先。只有规则失败或答案未通过验证时，规划器才会请求模型，把题目翻译成结构化任务。未配置 LLM 时，程序行为与纯规则求解完全一致。

### 方式一：本地 Ollama（无 API 费用）

```bash
# 先安装并启动 Ollama，然后拉取模型
ollama pull qwen2.5:7b       # 文本规划，约 4.7 GB
ollama pull qwen2.5vl:7b     # 图片/手写识别，约 6.0 GB（可选）

# 让规划器使用本地模型
export MATH_SOLVER_LLM_API_KEY=ollama
export MATH_SOLVER_LLM_BASE_URL=http://127.0.0.1:11434/v1
export MATH_SOLVER_LLM_MODEL=qwen2.5:7b
export MATH_SOLVER_LLM_TIMEOUT=180
```

Windows CMD 使用 `set NAME=VALUE`，需要持久化则用 `setx`。`webapp.py` 默认以 `setdefault` 方式指向本机 Ollama 的 `qwen2.5:7b`，未安装时规则求解不受影响。

### 方式二：任意 OpenAI 兼容 API

```bash
export MATH_SOLVER_LLM_API_KEY=sk-...
export MATH_SOLVER_LLM_BASE_URL=https://api.deepseek.com/v1
export MATH_SOLVER_LLM_MODEL=deepseek-chat
```

| 环境变量 | 说明 |
| --- | --- |
| `MATH_SOLVER_LLM_API_KEY` | API 密钥；本地 Ollama 可填任意值 |
| `MATH_SOLVER_LLM_BASE_URL` | 兼容 `/chat/completions` 的接口地址 |
| `MATH_SOLVER_LLM_MODEL` | 模型名，默认 `qwen2.5:7b` |
| `MATH_SOLVER_LLM_TIMEOUT` | 单次请求超时（秒），本地 CPU 推理建议 ≥ 180 |
| `MATH_SOLVER_VISION_MODEL` | 图片识别模型，默认 `qwen2.5vl:7b` |
| `MATH_SOLVER_VISION_TIMEOUT` | 图片识别超时（秒），默认 180 |
| `MATH_SOLVER_TIMEOUT` | 符号计算超时（秒），默认 15 |

## 支持的题型

| 类型 | 输入示例 | 输出 |
| --- | --- | --- |
| 算术 | `calculate (12 + 8) / 4` | `5` |
| 化简 | `simplify sin(x)**2 + cos(x)**2` | `1` |
| 方程 | `solve 2*x + 3 = 7 for x` | `x = 2` |
| 二次/多解 | `solve x**2 = 4` | `x = -2 or x = 2` |
| 方程组 | `solve x + y = 10 and x - y = 4` | `x = 7, y = 3` |
| 求导 | `differentiate x**3 + 2*x with respect to x` | `3*x**2 + 2` |
| 偏导 | `partial derivative of x**2*y with respect to y` | `x**2` |
| 定/不定积分 | `integrate x**2 from 0 to 1` | `1/3` |
| 极限 | `limit of sin(x)/x as x -> 0` | `1` |
| 级数展开 | `series of exp(x) around 0 to order 5` | `x**4/24 + x**3/6 + x**2/2 + x + 1` |
| 微分方程 | `solve the ode y' = 2*x` | `y(x) = C1 + x**2` |
| 矩阵 | `determinant of [[1,2],[3,4]]` | `-2` |
| 数论 | `factorize 360` / `is 97 prime` | `2**3 * 3**2 * 5` / `yes` |
| 整数约束 | `find integers x and y such that x + y = 10 and x - y = 4` | `x = 7, y = 3` |
| 无解判定 | `find integers x such that x + 1 = x` | `无解` |

同时支持常见中文关键词：`计算`、`化简`、`解方程`、`求导`、`偏导`、`积分`、`极限`、`趋于`、`泰勒展开`、`微分方程`、`矩阵`、`特征值`、`质数`、`最大公约数` 等。极限支持 `0+` / `0-` 单侧方向与 `infinity`/`∞`；矩阵支持行列式、特征值、逆矩阵、转置、秩。

## 结构化任务协议

`solver/taskspec.py` 定义了与自然语言解耦的 `TaskSpec`，可被其他程序或 Agent 直接调用：

```python
from solver import TaskSpec, execute_spec, solve_with_planner

solution = solve_with_planner("求 x^2 从 0 到 1 的定积分")

spec = TaskSpec.from_dict({
    "type": "integral",
    "expression": "x**2",
    "bounds": {"lower": "0", "upper": "1"},
})
solution = execute_spec(spec, "原题")
```

| type | 必填字段 | 可选字段 |
| --- | --- | --- |
| `arithmetic` / `simplify` | `expression` | |
| `equation` | `equations` | `variables` |
| `derivative` | `expression` | `variables`（默认 `x`） |
| `integral` | `expression` | `variables`、`bounds`（缺省为不定积分） |
| `limit` | `expression`、`point` | `variables`、`direction`（`+` / `-` / `+-`） |
| `series` | `expression` | `variables`、`center`、`order` |
| `ode` | `ode` | |
| `matrix` | `operation`、`matrix` | `operation`：`determinant` / `eigenvalues` / `inverse` / `transpose` / `rank` |
| `number_theory` | `operation`、`numbers` | `operation`：`factorization` / `gcd` / `lcm` / `primality` |
| `constraint` | `variables`、`constraints` | `domain`：`integer` / `real` |

## 工作流程

```text
自然语言题目
    │
    ├─ 文本归一化（Unicode/全角/隐式乘法）
    │
    ├─ 规则路由（关键词 → 题型）
    │       └─ SymPy / Z3 求解 → 独立验证 → 返回（零 token）
    │
    └─ 规则失败 → LLM 翻译成 TaskSpec(JSON)
                    └─ 协议校验（不合法则带错误重试一次）
                        └─ 按 type 调用确定性后端
                            └─ 独立验证 → 返回
```

- LLM 只决定“要算什么”，不产生数值答案
- 规则成功且验证未被否决时，不发起任何模型调用
- `Solution.planner`（`rule` / `llm` / `spec`）与 `Solution.task` 记录规划来源和结构化任务

## 独立验证

`solver/verify.py` 使用与求解路径分离的方法检查答案，结果三态：

| 结果 | 含义 |
| --- | --- |
| `True` | 验证通过 |
| `False` | 验证未通过，答案可能有问题 |
| `None` | 无法验证（符号参数、奇点、超时，或“无解”结论） |

各题型的验证方式：

| 题型 | 验证方法 |
| --- | --- |
| 算术 / 化简 | 原式与答案之差化简为 0，失败时随机取点数值兜底 |
| 求导 / 偏导 | 中心差分独立复算，并用符号求导交叉检查 |
| 不定积分 | 对答案求导，应得到被积函数 |
| 定积分 | 数值积分交叉验证 |
| 极限 | 从指定方向在极限点邻域采样，检查是否趋近答案 |
| 级数 | 在展开点邻域比较多项式与函数值 |
| 微分方程 | `checkodesol` 把解代回方程，残差应为 0 |
| 方程 / 方程组 | 每个解代回所有方程，残差应为 0 |
| 矩阵 | 分数消元独立计算行列式/秩；乘法回验逆矩阵；特征方程回验特征值 |
| 数论 | 整除性、乘法复原、试除法（不依赖 SymPy 的判定） |
| Z3 约束 | 把模型代回所有约束逐一检查 |

验证不通过不会丢弃答案，而是在 `Solution.verified` / `Solution.verification` 中标记，便于上层程序决定重试、换方法或提示用户。

## 项目结构

```text
math-solver/
├── solve.py                 # 命令行入口（单题/批量/交互/结构化任务）
├── webapp.py                # 本地网页界面（标准库 http.server）
├── evaluate.py              # 测试集评测
├── solver/
│   ├── __init__.py          # 公共接口
│   ├── text.py              # 文本归一化、表达式安全解析
│   ├── core.py              # 题型路由
│   ├── sympy_backend.py     # SymPy 后端
│   ├── z3_backend.py        # Z3 约束后端
│   ├── timeout.py           # 符号计算超时保护
│   ├── compare.py           # 答案等价比较
│   ├── verify.py            # 答案独立验证
│   ├── taskspec.py          # 结构化任务协议
│   ├── planner.py           # 规则优先 + LLM 兜底
│   ├── llm.py               # OpenAI 兼容客户端（仅标准库）
│   └── types.py             # Solution 数据结构
├── tests/                   # 单元测试（使用假 LLM，不联网）
├── data/problems.jsonl      # 60 道评测题
├── webapp_assets/katex/     # 本地 KaTeX（CSS/JS/字体）
├── tools/
│   ├── build_exe.py         # PyInstaller 打包
│   └── make_release.py      # 源码发布包
├── start_web.bat            # Windows 一键启动网页
├── start_web_lan.bat        # 局域网模式启动
├── requirements.txt
├── THIRD_PARTY_NOTICES.md
└── README.md
```

> 仓库不包含模型权重、`build/`、`dist/`、`.exe`、压缩包和临时文件。模型请用 `ollama pull` 获取。

## 评测与测试

```bash
# 60 道题的求解与独立验证统计
python evaluate.py --verbose

# 单元测试（不访问网络）
python -m unittest discover -s tests -t . -v
```

当前结果：求解成功 60/60，答案正确 60/60，独立验证通过 58/60。两道“无解”题按设计输出“无法验证”。

## 安全设计

- 表达式字符白名单：只允许数字、字母、运算符、括号、逗号、百分号
- 拒绝 `__`、`import`、`eval`、`exec` 等片段
- Z3 约束通过 AST 解释，不执行任意代码
- 矩阵字面量使用 `ast.literal_eval`，只接受数值嵌套列表
- LLM 输出只作为任务描述，经过协议校验后进入同一套安全解析
- 网页服务默认只监听 `127.0.0.1`，无鉴权，不应暴露到公网

## 局限性

- 规则路由不理解复杂自然语言应用题；LLM 规划器支持单步任务翻译，但尚不支持“设未知数 → 列方程 → 求解 → 回代”的多步自动分解
- 方程求解默认在复数域，可能返回复数解
- Z3 后端面向线性整数/实数约束，非线性与整数除法未完整支持
- 不定积分结果省略常数 `C`
- 微分方程只支持未知函数 `y(x)`、自变量 `x` 的一阶/二阶 ODE，不支持初值条件与方程组
- 矩阵只接受字面量，不支持符号矩阵和矩阵乘法链
- 极限与级数只处理单变量、有限阶展开；多元极限未支持
- 不支持不等式组的最优化（maximize / minimize）
- 独立验证无法覆盖“无解”结论，含自由符号参数的答案也可能无法完成验证

## 第三方组件与许可证

- [SymPy](https://www.sympy.org/) — BSD 3-Clause
- [z3-solver](https://github.com/Z3Prover/z3) — MIT
- [KaTeX](https://katex.org/) — MIT，文件位于 `webapp_assets/katex/`
- [Ollama](https://ollama.com/) — MIT（可选运行时）
- `qwen2.5:7b` / `qwen2.5vl:7b` — Apache-2.0（由使用者自行下载，不随仓库分发）

完整声明见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

本项目代码的许可证请见仓库中的 `LICENSE` 文件（如尚未添加，可自行选择 MIT、Apache-2.0 等）。

## 扩展方向

1. **增加题型**：在 `core.py` 加关键词，在 `sympy_backend.py` 写解析与求解函数，并在 `taskspec.py` 增加协议分支
2. **多步规划**：在 `TaskSpec` 之上增加子目标 DAG，支持应用题分解、失败重规划与多工具编排
3. **加入 OR-Tools**：求解排班、路径、装箱等组合优化题
4. **加入 Lean 4**：把几何/数论命题转成形式化证明，由证明助手验证
