# 使用

环境、依赖和模型变量见[构建与贡献](../CONTRIBUTING.md)。各功能的限制见[功能目录](features.md)。

## 命令行

在仓库根目录运行：

```bash
python solve.py --problem "solve x**2 - 5*x + 6 = 0"
python solve.py --file problems.txt
python solve.py --problem "integrate x**2 from 0 to 1" --planner rule
python solve.py
```

`--problem` 解一题。`--file` 按行读取题目。不带这两个参数时进入交互模式，空行退出。`--planner rule` 只用规则。直接执行 JSON 任务的写法见[任务协议](taskspec.md)。

规则求解的输出形如：

```text
题目: solve x**2 - 5*x + 6 = 0
类型: equation | 后端: sympy
步骤:
  1. 执行 equation 任务
  2. 解析方程: Eq(x**2 - 5*x + 6, 0)
  3. 未知数: x
  4. 使用 SymPy solve 求解单个方程
答案: x = 2 or x = 3
验证: 通过 — 回代检验通过:2 个解均满足原方程
```

验证在命令行上显示为「通过」「未通过」或「未完成」。使用了模型时，还会打印规划来源和任务 JSON。

## 网页

```bash
python webapp.py
python webapp.py --port 9000 --no-browser
python webapp.py --host 0.0.0.0
```

Windows 使用 `scripts/start_web.bat`，macOS 和 Linux 使用 `scripts/start_web.sh`。两个脚本把额外参数传给 `webapp.py`。`--host 0.0.0.0` 会打印局域网地址。手机或平板需要和电脑在同一网络；若无法打开，检查防火墙是否放行该端口。
