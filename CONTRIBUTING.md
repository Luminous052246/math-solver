# 参与开发

## 开发环境

需要 Python 3.10 或更高版本。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows 激活虚拟环境使用 `.venv\Scripts\activate`。解释器不在默认位置时，设置 `MATH_SOLVER_PYTHON`。

目录和常见改动的位置见[仓库结构](docs/structure.md)，模块职责见[架构](docs/architecture.md)。

可选的本地模型使用 Ollama。未安装时，规则求解不受影响。

```sh
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
```

未设置变量时，求解库使用 `https://api.openai.com/v1` 和 `gpt-4o-mini`。直接运行 `python -m app.web` 时，若变量尚未设置，则指向本机 Ollama 的 `qwen2.5:7b` 和 `qwen2.5vl:7b`。Windows CMD 使用 `set`，需要保留到以后的窗口时使用 `setx`。

| 变量 | 作用 |
| --- | --- |
| `MATH_SOLVER_LLM_API_KEY` | API 密钥。未设置时命令行不调用模型。本地 Ollama 可以填任意非空值 |
| `MATH_SOLVER_LLM_BASE_URL` | 兼容 `/chat/completions` 的地址 |
| `MATH_SOLVER_LLM_MODEL` | 文本模型 |
| `MATH_SOLVER_LLM_TIMEOUT` | 规划请求超时，秒。库的默认值是 30，网页指向 Ollama 时是 180 |
| `MATH_SOLVER_VISION_MODEL` | 图片和手写识别模型 |
| `MATH_SOLVER_VISION_TIMEOUT` | 识别超时，秒。网页默认 180 |
| `MATH_SOLVER_TIMEOUT` | 单次符号计算超时，默认 15 秒 |

## 测试

在仓库根目录运行：

```sh
python -m unittest discover -s tests -t . -v
python tools/evaluate.py
python tools/evaluate.py --verbose
```

单元测试使用假的模型响应，不访问网络。`tools/evaluate.py` 读取 `data/problems.jsonl`，该文件有 60 题。评测只调用规则求解器 `solve_problem`，不调用模型。它统计三件事：求解过程是否报错，答案是否与 `expected` 等价，以及 `Solution.verified` 是否为通过。

## 打包与发布

版本号只写在 `pyproject.toml`。

`python tools/build.py` 在当前操作系统和 CPU 架构上用 PyInstaller 构建可执行文件。macOS 还要区分 Intel 和 Apple Silicon。脚本不负责签名。

`python tools/make_release.py` 读取 `pyproject.toml` 中的版本，并按 Git 已跟踪文件生成源码包。未跟踪的 `.env`、虚拟环境和 `models/` 不会进入压缩包。需要发布的新文件必须先被 Git 跟踪。
