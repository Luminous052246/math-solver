# 功能目录

本文登记已经实现的功能、当前限制和主要代码。运行命令见[使用](usage.md)，任务字段见[任务协议](taskspec.md)，检查方法见[验证](verification.md)。

规则能识别中英文关键词，包括「计算」「化简」「解方程」「求导」「偏导」「积分」「极限」「趋于」「泰勒展开」「微分方程」「矩阵」「特征值」「质数」「最大公约数」。需要先设未知数再列方程的应用题不在规则范围内。

## 题型

| 功能 | 当前行为与限制 | 主要代码 |
| --- | --- | --- |
| 算术 | `calculate (12 + 8) / 4` 得到 `5` | `solver/rules.py`、`solver/sympy_backend.py` |
| 化简 | `simplify sin(x)**2 + cos(x)**2` 得到 `1` | `solver/rules.py`、`solver/sympy_backend.py` |
| 方程 | `solve 2*x + 3 = 7 for x` 得到 `x = 2`。`solve x**2 = 4` 得到 `x = -2 or x = 2`。多个未知数且未指定求解变量时拒绝求解。默认在复数域求解，可能返回复数解 | `solver/rules.py`、`solver/sympy_backend.py` |
| 方程组 | `solve x + y = 10 and x - y = 4` 得到 `x = 7, y = 3` | `solver/rules.py`、`solver/sympy_backend.py` |
| 求导、偏导 | `differentiate x**3 + 2*x with respect to x` 得到 `3*x**2 + 2`。`partial derivative of x**2*y with respect to y` 得到 `x**2`。未指定变量时优先对 `x` 求导，否则取表达式中的第一个符号 | `solver/rules.py`、`solver/sympy_backend.py` |
| 积分 | `integrate x**2 from 0 to 1` 得到 `1/3`。没有上下限时计算不定积分，结果不含常数 `C` | `solver/rules.py`、`solver/sympy_backend.py` |
| 极限 | `limit of sin(x)/x as x -> 0` 得到 `1`。支持 `0+`、`0-`、`infinity` 和 `∞`。只处理单变量极限 | `solver/rules.py`、`solver/sympy_backend.py` |
| 级数 | `series of exp(x) around 0 to order 5` 得到 `x**4/24 + x**3/6 + x**2/2 + x + 1`。只处理单变量、有限阶展开 | `solver/rules.py`、`solver/sympy_backend.py` |
| 微分方程 | `solve the ode y' = 2*x` 得到 `y(x) = C1 + x**2`。只支持未知函数 `y(x)`、自变量 `x` 的一阶或二阶方程，不支持初值条件和方程组 | `solver/rules.py`、`solver/sympy_backend.py` |
| 矩阵 | `determinant of [[1,2],[3,4]]` 得到 `-2`。支持行列式、特征值、逆、转置和秩。只接受数值字面量，不支持符号矩阵和矩阵乘法链 | `solver/rules.py`、`solver/sympy_backend.py` |
| 数论 | `factorize 360` 得到 `2**3 * 3**2 * 5`。`is 97 prime` 得到 `yes`。另支持最大公约数和最小公倍数 | `solver/rules.py`、`solver/sympy_backend.py` |
| 约束 | `find integers x and y such that x + y = 10 and x - y = 4` 得到 `x = 7, y = 3`。`find integers x such that x + 1 = x` 得到 `无解`。`/` 按实数除法解释，`//` 是整数除法，`%` 是整数取模；实数上的 `//` 和 `%` 会报错。不求解最优化 | `solver/rules.py`、`solver/z3_backend.py` |

## 入口

| 功能 | 当前行为与限制 | 主要代码 |
| --- | --- | --- |
| 命令行 | 可解单题、按行批量求解、交互输入，也可只使用规则。直接提交 JSON 任务见[任务协议](taskspec.md) | `app/cli.py` |
| 网页 | 提供示例、LaTeX 答案、步骤和求解明细，并显示验证通过、验证未通过或未能完成验证。可上传题目图片。手写板支持鼠标、触控和手写笔，可撤销、清空，识别时导出白底 PNG。识别结果先填入输入框。默认只监听本机，没有鉴权 | `app/web.py`、`app/assets/` |
| 模型翻译 | 规则没有得到可接受的结果，并且配置了密钥时，把题目翻译成一份任务。不产生数值答案，也不会自动完成设未知数、列方程、求解和回代 | `solver/planner.py`、`solver/llm.py` |
