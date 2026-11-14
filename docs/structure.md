# 仓库结构

本文介绍目录用途和常见改动的位置。模块如何协作见[架构](architecture.md)。

```text
math-solver/
├── app/                     命令行和网页入口
│   ├── cli.py               命令行
│   ├── web.py               本地网页服务
│   └── assets/              页面、样式、脚本和 KaTeX
├── solver/                  求解器
│   ├── rules.py             自然语言到 TaskSpec
│   ├── taskspec.py          任务字段与校验
│   ├── planner.py           规则优先，必要时请求模型翻译
│   ├── engine.py            按任务字段执行
│   ├── sympy_backend.py     SymPy 计算
│   ├── z3_backend.py        Z3 约束
│   ├── verify.py            独立验证
│   ├── text.py              表达式字符限制与解析
│   ├── llm.py               OpenAI 兼容的模型客户端
│   ├── compare.py           评测用的答案等价比较
│   ├── timeout.py           符号计算超时
│   ├── types.py             Solution
│   └── core.py              规则求解入口
├── tests/                   单元测试，使用假的模型响应
├── data/problems.jsonl      评测题
├── scripts/                 start_web.bat、start_web.sh
├── tools/                   评测、打包和源码发布
├── docs/
│   ├── features.md          功能目录
│   ├── usage.md             命令行与网页的启动方式
│   ├── architecture.md      求解数据流与模块职责
│   ├── taskspec.md          任务字段
│   ├── verification.md      答案检查方法
│   └── structure.md         本文件
├── README.md                产品概览
├── CONTRIBUTING.md          环境、测试与发布
├── AGENTS.md                项目开发约定
├── pyproject.toml           版本与依赖
└── THIRD_PARTY_NOTICES.md   第三方许可证
```

## 常见改动

| 修改内容 | 主要位置 |
| --- | --- |
| 识别新的题面写法 | `solver/rules.py` |
| 任务字段和校验 | `solver/taskspec.py` |
| 符号计算 | `solver/sympy_backend.py` |
| 整数或实数约束 | `solver/z3_backend.py` |
| 任务分发 | `solver/engine.py` |
| 答案检查 | `solver/verify.py` |
| 表达式允许的字符 | `solver/text.py` |
| 是否请求模型 | `solver/planner.py` |
| 命令行参数和输出 | `app/cli.py` |
| 网页求解、识别和页面 | `app/web.py`、`app/assets/` |
| 评测题 | `data/problems.jsonl`、`tests/` |
| 网页启动脚本 | `scripts/start_web.bat`、`scripts/start_web.sh` |
| 打包和源码发布 | `tools/build.py`、`tools/make_release.py` |

本机虚拟环境、打包产物和模型权重不提交到版本库。
