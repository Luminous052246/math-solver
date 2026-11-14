# Math Solver

Math Solver 用规则把数学题整理成结构化任务，再交给 SymPy 和 Z3 计算。大语言模型只在规则无法处理时把题目翻译成同一份任务，不产生数值答案。

支持算术、化简、方程、微积分、极限、级数、微分方程、矩阵、数论和整数或实数约束。

## 文档

- [功能目录](docs/features.md)：已实现的功能、限制和相关代码。
- [使用](docs/usage.md)：命令行和网页的启动方式。
- [架构](docs/architecture.md)：模块职责与数据流。
- [任务协议](docs/taskspec.md)：`TaskSpec` 的字段。
- [验证](docs/verification.md)：答案的检查方法。
- [仓库结构](docs/structure.md)：目录、文件及常见改动的位置。
- [构建与贡献](CONTRIBUTING.md)：开发环境、测试和发布。
- [第三方组件声明](THIRD_PARTY_NOTICES.md)：随仓库分发或运行时依赖的许可证。
- [项目开发约定](AGENTS.md)：修改项目时需要遵守的边界。
