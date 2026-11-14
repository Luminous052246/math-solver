# 开发、测试与发布

版本号只写在 `pyproject.toml` 的 `version` 字段。发布脚本和文档都从这里读取，不要在脚本里另写一个版本。

## 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows 激活虚拟环境使用 `.venv\Scripts\activate`。解释器不在默认位置时，设置 `MATH_SOLVER_PYTHON`。

可选的本地模型使用 Ollama。未安装时，规则求解不受影响。

| 变量 | 作用 |
| --- | --- |
| `MATH_SOLVER_LLM_API_KEY` | API 密钥。本地 Ollama 可以填任意非空值 |
| `MATH_SOLVER_LLM_BASE_URL` | 兼容 `/chat/completions` 的地址 |
| `MATH_SOLVER_LLM_MODEL` | 文本规划模型。网页默认尝试 `qwen2.5:7b` |
| `MATH_SOLVER_LLM_TIMEOUT` | 规划请求超时，秒 |
| `MATH_SOLVER_VISION_MODEL` | 图片和手写识别模型，默认 `qwen2.5vl:7b` |
| `MATH_SOLVER_VISION_TIMEOUT` | 识别超时，秒 |
| `MATH_SOLVER_TIMEOUT` | 单次符号计算超时，默认 15 秒 |

`webapp.py` 只在环境变量尚未设置时，用 `setdefault` 指向本机 Ollama。

## 测试

```bash
python -m unittest discover -s tests -t . -v
python evaluate.py
python evaluate.py --verbose
```

单元测试使用假的 LLM 响应，不访问网络。

`evaluate.py` 读取 `data/problems.jsonl`，对每题调用规则求解器 `solve_problem`，不调用 LLM。三项指标是：

- 求解成功：求解过程没有报错
- 答案正确：成功，且答案与 `expected` 在 `answers_equivalent` 下等价
- 独立验证通过：`Solution.verified is True`

2026-11-14 在 macOS、Python 3.12.10、SymPy 1.14.0、z3-solver 5.4.1.0 上运行，60 题求解成功 60、答案正确 60、独立验证通过 58。未通过验证的两题是数据集中的“无解”题，验证状态按设计为无法验证。换依赖版本后应重新运行命令，不要把这次输出当成固定证书。

## 平台

| 能力 | 现状 |
| --- | --- |
| 命令行和网页的 Python 源码 | Windows、Linux、macOS 使用同一入口。本次在 macOS 上运行了单元测试和评测；Linux 和 Windows 没有在本次执行 |
| 一键启动 | 只有 Windows 的 `start_web.bat`。它转发参数，局域网模式是 `--host 0.0.0.0`。其他系统直接运行 `python webapp.py` |
| 原生可执行文件 | `python tools/build.py` 调用 PyInstaller，并按当前系统选择 `--add-data` 分隔符。必须在目标操作系统和 CPU 架构上构建。本次没有运行 PyInstaller，因此没有验证任何平台的二进制产物 |
| 源码包 | `python tools/make_release.py` 只打包 `git ls-files` 列出的文件，版本取自 `pyproject.toml` |

PyInstaller 不能在一个系统上编译出另一个系统的可执行文件。macOS 还要区分 Intel 和 Apple Silicon，签名也不由该脚本完成。

## 发布包不会包含的文件

发布脚本读取 Git 已跟踪文件，不扫描整个工作目录。因此未跟踪的 `.env`、`.venv/` 和 `models/` 不会进入 zip。脚本还会拒绝同名的已跟踪敏感路径。需要发布的新文件必须先被 Git 跟踪。
