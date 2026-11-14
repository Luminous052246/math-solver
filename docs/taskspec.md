# 任务协议

`TaskSpec` 是规则解析器、LLM 和外部程序之间的接口。后端只读取这里的字段。

```python
from solver import TaskSpec, execute_spec

spec = TaskSpec.from_dict({
    "type": "integral",
    "expression": "x**2",
    "variables": ["x"],
    "bounds": {"lower": "0", "upper": "1"},
})
solution = execute_spec(spec, "原题")
```

命令行可以直接执行一份 JSON：

```bash
python -m app.cli --task '{"type":"integral","expression":"x**2","bounds":{"lower":"0","upper":"1"}}'
```

表达式使用 Python / SymPy 语法：乘方是 `**`，自然对数是 `log`，无穷是 `oo`。字段在进入后端前会做协议校验；表达式再经过字符白名单解析。

## 字段

| type | 必填 | 可选 |
| --- | --- | --- |
| `arithmetic` / `simplify` | `expression` | |
| `equation` | `equations` | `variables`。缺省时从表达式推断；单个方程有多个未知数且未指定变量时拒绝求解 |
| `derivative` | `expression` | `variables`，默认选择 `x` 或表达式中的第一个符号 |
| `integral` | `expression` | `variables`、`bounds`。没有 `bounds` 时是不定积分，结果不含常数 `C` |
| `limit` | `expression`、`point` | `variables`、`direction`（`+`、`-` 或 `+-`） |
| `series` | `expression` | `variables`、`center`（默认 `0`）、`order`（1 到 20，默认 6） |
| `ode` | `ode` | 形如 `y' = 2*x`。只支持 `y(x)` |
| `matrix` | `operation`、`matrix` | `operation`：`determinant`、`eigenvalues`、`inverse`、`transpose`、`rank` |
| `number_theory` | `operation`、`numbers` | `operation`：`factorization`、`gcd`、`lcm`、`primality` |
| `constraint` | `variables`、`constraints` | `domain`：`integer` 或 `real` |

`goal` 只用于个别步骤说明，不改变计算公式。

LLM 收到的输出格式和上面的字段一致。模型被要求只填写题目中的表达式和参数，不填写答案。不符合协议时会把校验错误发回并重试一次。
