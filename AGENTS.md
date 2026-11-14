# 项目开发约定

开始修改前，阅读[架构](docs/architecture.md)、[仓库结构](docs/structure.md)和[功能目录](docs/features.md)，确认模块职责、代码位置和现有行为。任务字段见[任务协议](docs/taskspec.md)，检查方法见[验证](docs/verification.md)。环境、测试和发布见[构建与贡献](CONTRIBUTING.md)。同一项事实应有一个主要维护位置，其他文档按需链接。

## 项目边界

- 数值答案只由 SymPy 或 Z3 产生。模型只把题目翻译成 `TaskSpec`。
- `solver/engine.py` 按任务字段执行。`canonical_problem()` 只用于展示。
- 用户输入的表达式经过 `solver/text.py` 的字符限制后解析，不使用 `eval`。Z3 约束用 AST 解释。矩阵字面量用 `ast.literal_eval`。
- 网页默认只监听 `127.0.0.1`，没有鉴权。
- 版本号只写在 `pyproject.toml`。`tools/make_release.py` 只打包 Git 已跟踪的文件。

## 同步文档

新增、修改或删除用户可用的功能，或调整功能的行为与限制时，同步更新[功能目录](docs/features.md)。

任务字段变化时，同步检查[任务协议](docs/taskspec.md)。检查方法变化时，同步检查[验证](docs/verification.md)。模块职责或求解数据流变化时，同步检查[架构](docs/architecture.md)。新增、移动或删除主要目录与模块时，同步检查[仓库结构](docs/structure.md)。启动方式变化时，同步检查[使用](docs/usage.md)。
