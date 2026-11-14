# Math Solver

用规则把数学题整理成结构化任务，再交给 **SymPy** 和 **Z3** 做精确计算。大语言模型只在规则失败时把题目翻译成同一份任务，不产生数值答案。

## 安装

需要 Python 3.10 或更高版本。Windows、Linux、macOS 使用同一套命令；Windows 把下面的 `.venv/bin` 换成 `.venv\Scripts`。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`requirements.txt` 会按 `pyproject.toml` 安装本项目和运行依赖。依赖装好后，也可以直接用已有解释器运行，不必激活虚拟环境。

## 使用

```bash
.venv/bin/python solve.py --problem "solve x**2 - 5*x + 6 = 0"
.venv/bin/python solve.py                          # 交互
.venv/bin/python solve.py --planner rule           # 不调用 LLM
.venv/bin/python webapp.py                         # http://127.0.0.1:8765
.venv/bin/python webapp.py --host 0.0.0.0          # 局域网
```

Windows 可以双击 `start_web.bat`。它会依次查找 `MATH_SOLVER_PYTHON`、项目里的 `.venv` 和 `python`，并把额外参数传给 `webapp.py`，例如 `start_web.bat --host 0.0.0.0`。服务没有鉴权，不要暴露到公网。

安装后也可以使用命令 `math-solver`，参数与 `solve.py` 相同。网页需要仓库里的 `webapp_assets/`，请在项目目录中运行 `python webapp.py`。

## 支持的题型

| 类型 | 示例 | 输出 |
| --- | --- | --- |
| 算术 | `calculate (12 + 8) / 4` | `5` |
| 化简 | `simplify sin(x)**2 + cos(x)**2` | `1` |
| 方程 | `solve 2*x + 3 = 7 for x` | `x = 2` |
| 方程组 | `solve x + y = 10 and x - y = 4` | `x = 7, y = 3` |
| 求导 / 偏导 | `differentiate x**3 + 2*x with respect to x` | `3*x**2 + 2` |
| 积分 | `integrate x**2 from 0 to 1` | `1/3` |
| 极限 | `limit of sin(x)/x as x -> 0` | `1` |
| 级数 | `series of exp(x) around 0 to order 5` | 多项式 |
| 微分方程 | `solve the ode y' = 2*x` | `y(x) = C1 + x**2` |
| 矩阵 | `determinant of [[1,2],[3,4]]` | `-2` |
| 数论 | `factorize 360` | `2**3 * 3**2 * 5` |
| 整数约束 | `find integers x and y such that x + y = 10 and x - y = 4` | `x = 7, y = 3` |

也识别常见中文关键词，例如 `计算`、`化简`、`解方程`、`求导`、`积分`、`极限`、`微分方程`。规则不能稳定理解需要自行设未知数的应用题。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | 组件边界和计算流程 |
| [docs/taskspec.md](docs/taskspec.md) | 任务协议 |
| [docs/verification.md](docs/verification.md) | 验证能保证什么、不能保证什么 |
| [docs/development.md](docs/development.md) | 环境、测试、发布、打包和平台差异 |

第三方组件的许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
