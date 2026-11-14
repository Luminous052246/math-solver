"""Math Solver 本地网页界面(零第三方依赖)。

运行:
    python webapp.py                 # 默认 http://127.0.0.1:8765
    python webapp.py --port 9000
    python webapp.py --no-browser    # 不自动打开浏览器

页面包含:
    1. 单题求解:输入题目 -> 规则/LLM 规划 -> 符号求解 -> 答案
    2. 图片/手写识别:上传题目图片或在手写板书写,由本地 Ollama 视觉模型识别后填入输入框
    3. 快捷示例与支持的输入格式速查
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import sympy as sp

from solver import solve_with_planner
from solver.core import route_problem
from solver.text import normalize_text, parse_symbolic

ROOT = Path(__file__).resolve().parent
ASSET_ROOT = ROOT / "webapp_assets"
ASSET_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".woff2": "font/woff2",
}

ROUTE_LABELS = {
    "constraint": "约束(Z3)",
    "ode": "微分方程",
    "limit": "极限",
    "series": "级数展开",
    "matrix": "矩阵",
    "derivative": "求导/偏导",
    "integral": "积分",
    "simplify": "化简",
    "number_theory": "数论",
    "equation": "方程",
    "arithmetic": "算术",
}

EXAMPLES = [
    ["算术", "calculate (12 + 8) / 4"],
    ["化简", "simplify sin(x)**2 + cos(x)**2"],
    ["方程", "solve x**2 - 5*x + 6 = 0"],
    ["方程组", "solve x + y = 10 and x - y = 4"],
    ["求导", "differentiate x**3 + 2*x with respect to x"],
    ["积分", "integrate x**2 from 0 to 1"],
    ["极限", "limit of sin(x)/x as x -> 0"],
    ["级数", "series of exp(x) around 0 to order 5"],
    ["微分方程", "solve the ode y' = 2*x"],
    ["矩阵", "determinant of [[1,2],[3,4]]"],
    ["数论", "factorize 360"],
    ["约束", "find integers x and y such that x + y = 10 and x - y = 4"],
]

VISION_PROMPT = (
    "识别图片中的数学题目。只输出题目本身的文字,不要解答或解释,不要使用 Markdown。"
    "数学表达式写成 Python/SymPy 可解析的形式:乘方用 **,乘号用 *,除号用 /,"
    "分数写成 (a)/(b);保留 y'、dy/dx 等导数记号;中文题干原样保留。"
    "如果图片中没有可求解的数学题目,只输出:无法识别"
)


def _vision_model() -> str:
    """视觉模型名称,默认使用本机 qwen2.5vl。"""
    value = (
        os.environ.get("MATH_SOLVER_VISION_MODEL", "")
        .strip()
        .strip('"')
        .strip("'")
        .strip()
    )
    return value or "qwen2.5vl:7b"


def _vision_timeout() -> float:
    raw = (
        os.environ.get("MATH_SOLVER_VISION_TIMEOUT", "180")
        .strip()
        .strip('"')
        .strip("'")
    )
    try:
        value = float(raw)
    except ValueError:
        return 180.0
    return value if value > 0 else 180.0


def _ollama_api_root() -> str:
    """把 OpenAI 兼容地址(.../v1)还原成 Ollama 原生 API 根地址。"""
    base = (
        os.environ.get("MATH_SOLVER_LLM_BASE_URL", "")
        .strip()
        .strip('"')
        .strip("'")
    )
    base = (base or "http://127.0.0.1:11434/v1").rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def recognize_image(raw: bytes) -> str:
    """用本地 Ollama 视觉模型识别图片中的题目。"""
    encoded = base64.b64encode(raw).decode("ascii")
    payload = {
        "model": _vision_model(),
        "stream": False,
        "messages": [
            {"role": "user", "content": VISION_PROMPT, "images": [encoded]}
        ],
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        f"{_ollama_api_root()}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_vision_timeout()) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        raise RuntimeError(f"Ollama 返回 {exc.code}: {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("无法连接本地 Ollama,请先启动服务") from exc
    except TimeoutError as exc:
        raise RuntimeError("图片识别超时,请稍后重试") from exc
    except (ValueError, OSError) as exc:
        raise RuntimeError(f"Ollama 响应异常: {exc}") from exc

    text = str(data.get("message", {}).get("content", "")).strip()
    text = re.sub(r"^```[A-Za-z]*\s*|\s*```$", "", text).strip()
    text = re.sub(r"^(题目|问题|数学题|题干)\s*[:：]\s*", "", text)
    return text


def _split_top_level(text: str, separator: str) -> list[str]:
    """按分隔符切分,忽略括号内的分隔符。"""
    depth = 0
    parts: list[str] = []
    buffer: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        if depth == 0 and text.startswith(separator, index):
            parts.append("".join(buffer))
            buffer = []
            index += len(separator)
            continue
        buffer.append(char)
        index += 1
    parts.append("".join(buffer))
    return [part.strip() for part in parts if part.strip()]


_SUBSCRIPT_RE = re.compile(r"(?<![A-Za-z_])([A-Za-z])(\d+)(?![A-Za-z_])")


def _protect_subscripts(text: str) -> str:
    """把 ``C1`` 转成 ``C_1``,避免隐式乘法把它解析成 ``C*1``。"""
    return _SUBSCRIPT_RE.sub(r"\1_\2", text)


def _matrix_to_latex(text: str) -> str | None:
    """把 ``[[1,2],[3,4]]`` 形式的答案渲染成矩阵。"""
    if not (text.startswith("[") and text.endswith("]")):
        return None
    rows = re.findall(r"\[([^\[\]]*)\]", text[1:-1])
    if not rows:
        return None
    try:
        values = [
            [parse_symbolic(_protect_subscripts(cell)) for cell in row.split(",")]
            for row in rows
        ]
        return sp.latex(sp.Matrix(values))
    except Exception:
        return None


def _factorization_to_latex(text: str) -> str | None:
    """保留 ``2**3 * 3**2 * 5`` 这样的质因数分解形式,不合并成 360。"""
    if "*" not in text:
        return None
    factors = [part.strip() for part in re.split(r"(?<!\*)\*(?!\*)", text)]
    if len(factors) < 2 or any(not factor for factor in factors):
        return None
    parts = []
    for factor in factors:
        power = re.fullmatch(r"(\d+)\s*\*\*\s*(\d+)", factor)
        if power:
            parts.append(f"{power.group(1)}^{{{power.group(2)}}}")
        elif factor.isdigit():
            parts.append(factor)
        else:
            return None
    return r" \cdot ".join(parts)


def _clause_to_latex(clause: str) -> str | None:
    """渲染单个子句:``x = 2``、``y(x) = C1 + x**2`` 或纯表达式。"""
    if "=" in clause:
        lhs, rhs = (side.strip() for side in clause.split("=", 1))
        if not re.fullmatch(r"[A-Za-z]\w*(?:\([^()]*\))?", lhs):
            return None
        try:
            rhs_tex = sp.latex(parse_symbolic(_protect_subscripts(rhs)))
            return f"{lhs} = {rhs_tex}"
        except Exception:
            return None
    try:
        return sp.latex(parse_symbolic(_protect_subscripts(clause)))
    except Exception:
        return None


def answer_to_latex(answer: str | None) -> str | None:
    """把求解器输出的纯文本答案转成 LaTeX;无法解析时返回 None。"""
    if not answer:
        return None
    text = answer.strip()
    if not text or text in {"yes", "no", "无解"}:
        return None

    matrix = _matrix_to_latex(text)
    if matrix:
        return matrix

    factorization = _factorization_to_latex(text)
    if factorization:
        return factorization

    groups = _split_top_level(text, " or ")
    rendered_groups: list[str] = []
    for group in groups:
        clauses = _split_top_level(group, ",")
        if not clauses:
            return None
        rendered = []
        for clause in clauses:
            tex = _clause_to_latex(clause)
            if tex is None:
                return None
            rendered.append(tex)
        rendered_groups.append(r",\quad ".join(rendered))
    return r"\quad\text{或}\quad ".join(rendered_groups)


def solve_payload(text: str) -> dict:
    started = time.perf_counter()
    solution = solve_with_planner(text)
    elapsed_ms = (time.perf_counter() - started) * 1000
    route, hint = route_problem(text)
    if solution.planner == "llm" and solution.problem_type in ROUTE_LABELS:
        route, hint = solution.problem_type, "LLM 规划"
    return {
        "problem": text,
        "normalized": normalize_text(text),
        "route": route,
        "route_label": ROUTE_LABELS.get(route, route),
        "hint": hint,
        "planner": solution.planner,
        "task": solution.task,
        "ok": solution.ok,
        "type": solution.problem_type or route,
        "backend": solution.backend,
        "answer": solution.answer,
        "answer_latex": answer_to_latex(solution.answer) if solution.ok else None,
        "error": solution.error,
        "steps": solution.steps,
        "elapsed_ms": round(elapsed_ms, 1),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MathSolver/1.0"

    def log_message(self, format: str, *args) -> None:  # 保持终端安静
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _send_asset(self, path: str) -> None:
        relative = path[len("/assets/"):]
        target = (ASSET_ROOT / relative).resolve()
        try:
            target.relative_to(ASSET_ROOT.resolve())
        except ValueError:
            self._send_json({"error": "not found"}, 404)
            return
        if not target.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        content_type = ASSET_TYPES.get(
            target.suffix.lower(), "application/octet-stream"
        )
        self._send(200, target.read_bytes(), content_type)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path.startswith("/assets/"):
            self._send_asset(path)
        elif path == "/api/health":
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        limit = 20_000_000 if path == "/api/ocr" else 1_000_000
        if length > limit:
            self._send_json({"error": "请求体过大"}, 413)
            return

        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "请求不是合法 JSON"}, 400)
            return
        if not isinstance(payload, dict):
            self._send_json({"error": "请求格式错误"}, 400)
            return

        if path == "/api/solve":
            text = str(payload.get("problem", "")).strip()
            if not text:
                self._send_json({"error": "请输入题目"}, 400)
                return
            self._send_json(solve_payload(text))
        elif path == "/api/ocr":
            image = payload.get("image", "")
            if not isinstance(image, str) or not image.strip():
                self._send_json({"error": "缺少图片数据"}, 400)
                return
            if image.startswith("data:"):
                image = image.split(",", 1)[-1]
            try:
                raw = base64.b64decode(image, validate=True)
            except (ValueError, binascii.Error):
                self._send_json({"error": "图片数据格式错误"}, 400)
                return
            if len(raw) > 15_000_000:
                self._send_json({"error": "图片过大,请压缩到 15MB 以内"}, 413)
                return
            try:
                text = recognize_image(raw)
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, 502)
                return
            if not text or text in {"无法识别", "无法识别。", "无"}:
                self._send_json(
                    {"error": "未能从图片中识别出题目,请换一张清晰的图片"}, 422
                )
                return
            self._send_json({"text": text, "model": _vision_model()})
        else:
            self._send_json({"error": "not found"}, 404)


INDEX_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Math Solver · 符号计算求解器</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='24' fill='%234f46e5'/%3E%3Ctext x='50' y='71' font-size='56' text-anchor='middle' fill='white' font-family='Georgia,serif'%3E%E2%88%91%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="/assets/katex/katex.min.css">
<script defer src="/assets/katex/katex.min.js"></script>
<style>
  :root {
    --bg: #f5f7fc;
    --card: #ffffff;
    --line: #e4e9f2;
    --text: #1b2333;
    --muted: #667085;
    --faint: #98a2b3;
    --accent: #4f46e5;
    --accent-2: #2563eb;
    --accent-soft: #eef0ff;
    --green: #15803d; --green-soft: #f3faf6; --green-line: #bfe3cb;
    --red: #b42318; --red-soft: #fdf4f3; --red-line: #f0c2bd;
    --shadow-sm: 0 1px 2px rgba(16, 24, 40, .05);
    --shadow-md: 0 12px 32px -18px rgba(16, 24, 40, .28);
    --radius: 16px;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; color: var(--text);
    background:
      radial-gradient(1100px 480px at 12% -8%, rgba(79, 70, 229, .10), transparent 62%),
      radial-gradient(900px 420px at 100% 0%, rgba(14, 165, 233, .09), transparent 58%),
      var(--bg);
    font-family: "Segoe UI", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .shell { width: min(920px, 100%); margin: 0 auto; padding: 44px 20px 56px; }

  header { display: flex; align-items: center; gap: 14px; margin-bottom: 26px; }
  .logo {
    flex: none; width: 50px; height: 50px; border-radius: 15px;
    display: grid; place-items: center; color: #fff;
    font-family: Georgia, "Times New Roman", serif; font-size: 27px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    box-shadow: 0 10px 22px -10px rgba(79, 70, 229, .6);
  }
  header h1 { margin: 0; font-size: 22px; letter-spacing: .01em; }
  header p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
  .badge {
    margin-left: auto; flex: none; padding: 6px 12px; border-radius: 999px;
    background: rgba(255, 255, 255, .7); border: 1px solid var(--line);
    color: var(--muted); font-size: 12px;
  }

  .card {
    background: var(--card); border: 1px solid var(--line);
    border-radius: var(--radius); box-shadow: var(--shadow-sm);
  }
  .input-card { padding: 18px; margin-bottom: 18px; box-shadow: var(--shadow-md); }
  textarea {
    width: 100%; min-height: 112px; resize: vertical; padding: 14px 16px;
    border: 1px solid var(--line); border-radius: 12px; font-size: 15px;
    font-family: "Cascadia Code", Consolas, "Microsoft YaHei", monospace;
    background: #fbfcfe; color: var(--text); outline: none;
    transition: border-color .15s, box-shadow .15s;
  }
  textarea::placeholder { color: #a6b0c0; }
  textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 4px rgba(79, 70, 229, .10); }

  .chips-row { display: flex; gap: 10px; align-items: flex-start; margin-top: 14px; }
  .chips-label { flex: none; color: var(--faint); font-size: 12px; padding-top: 7px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    border: 1px solid var(--line); background: #f9fafd; color: var(--muted);
    border-radius: 999px; padding: 5px 13px; font-size: 12.5px;
    font-family: inherit; cursor: pointer;
    transition: color .15s, border-color .15s, background .15s, transform .15s;
  }
  .chip:hover { color: var(--accent); border-color: #c9cffa; background: var(--accent-soft); transform: translateY(-1px); }

  .toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 16px; }
  .btn {
    border: 1px solid var(--line); background: #fff; color: var(--text);
    padding: 9px 20px; border-radius: 10px; font-size: 14px; font-family: inherit;
    cursor: pointer; transition: background .15s, filter .15s;
  }
  .btn:hover { background: #f2f5fa; }
  .btn.primary {
    border: none; color: #fff;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    box-shadow: 0 8px 18px -10px rgba(79, 70, 229, .8);
  }
  .btn.primary:hover { filter: brightness(1.07); }
  .btn.primary:disabled { opacity: .6; cursor: default; filter: none; }
  .shortcut { color: var(--faint); font-size: 12px; }
  .status { margin-left: auto; color: var(--muted); font-size: 13px; }
  .hidden { display: none !important; }

  .preview-row {
    display: flex; align-items: center; gap: 12px; margin-top: 14px;
    padding: 10px 12px; border: 1px dashed var(--line); border-radius: 12px;
    background: #fbfcfe;
  }
  .preview-row img {
    flex: none; width: 64px; height: 64px; object-fit: cover;
    border: 1px solid var(--line); border-radius: 9px; background: #fff;
  }
  .preview-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .preview-name {
    color: var(--text); font-size: 13px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .preview-note { color: var(--muted); font-size: 12px; }
  .btn.small { margin-left: auto; flex: none; padding: 6px 14px; font-size: 13px; }

  .modal-backdrop {
    position: fixed; inset: 0; z-index: 50; padding: 20px;
    display: flex; align-items: center; justify-content: center;
    background: rgba(16, 24, 40, .48); backdrop-filter: blur(2px);
  }
  .modal {
    width: min(860px, 100%); background: #fff; border-radius: 18px;
    border: 1px solid var(--line); padding: 20px;
    box-shadow: 0 30px 80px -30px rgba(16, 24, 40, .55);
  }
  .modal-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
  .modal-head h3 { margin: 0; font-size: 16px; }
  .modal-note { margin-left: auto; color: var(--muted); font-size: 12.5px; }
  .pad-wrap {
    border: 1px solid var(--line); border-radius: 13px;
    overflow: hidden; background: #fff;
  }
  canvas.pad {
    display: block; width: 100%; height: 330px;
    cursor: crosshair; touch-action: none; background: #fff;
  }
  .modal-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
  .modal-actions .spacer { margin-left: auto; }

  .result { animation: rise .25s ease; }
  @keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
  .metrics { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .metric {
    padding: 6px 14px; border-radius: 999px; background: var(--card);
    border: 1px solid var(--line); box-shadow: var(--shadow-sm);
    color: var(--muted); font-size: 12.5px;
  }
  .metric b { margin-left: 6px; color: var(--text); font-weight: 600; }

  .answer { padding: 22px 24px; border-radius: var(--radius); border: 1px solid; margin-bottom: 14px; }
  .answer.ok { background: linear-gradient(180deg, #f9fdfb, var(--green-soft)); border-color: var(--green-line); }
  .answer.fail { background: linear-gradient(180deg, #fffbfa, var(--red-soft)); border-color: var(--red-line); }
  .answer-label { font-size: 12px; letter-spacing: .09em; margin-bottom: 8px; color: var(--muted); }
  .answer.ok .answer-label { color: var(--green); }
  .answer.fail .answer-label { color: var(--red); }
  .answer-math { font-size: 22px; overflow-x: auto; overflow-y: hidden; padding: 2px 0; }
  .answer-math .katex-display { margin: .3em 0; }
  .answer-text { font-size: 21px; font-weight: 600; color: var(--green); word-break: break-word; }
  .answer-fail-text { color: var(--red); font-size: 14.5px; line-height: 1.65; word-break: break-word; }
  .answer-tip { margin: 10px 0 0; color: var(--muted); font-size: 12.5px; }

  .block { padding: 18px 20px; margin-bottom: 14px; }
  .block h3 { margin: 0 0 10px; color: var(--muted); font-size: 13px; font-weight: 600; letter-spacing: .03em; }
  ol.steps { margin: 0; padding-left: 20px; line-height: 1.95; font-size: 14px; }
  ol.steps li::marker { color: var(--accent); }

  details.meta { margin-bottom: 14px; }
  details.meta > summary {
    cursor: pointer; list-style: none; padding: 14px 18px;
    color: var(--muted); font-size: 13px; user-select: none;
  }
  details.meta > summary::-webkit-details-marker { display: none; }
  details.meta > summary::before {
    content: "▸"; display: inline-block; margin-right: 8px; color: var(--faint);
    transition: transform .15s;
  }
  details.meta[open] > summary::before { transform: rotate(90deg); }
  .meta-body { padding: 0 18px 16px; font-size: 12.5px; line-height: 1.75; }
  .meta-body .row { display: grid; grid-template-columns: 88px 1fr; gap: 10px; padding: 7px 0; border-top: 1px dashed var(--line); }
  .meta-body .row:first-child { border-top: none; }
  .meta-body .k { color: var(--faint); }
  .meta-body .v { color: var(--text); word-break: break-word; }

  details.help { margin-top: 22px; }
  details.help > summary {
    cursor: pointer; list-style: none; padding: 16px 20px;
    color: var(--muted); font-size: 13.5px; user-select: none;
  }
  details.help > summary::-webkit-details-marker { display: none; }
  details.help > summary::before {
    content: "▸"; display: inline-block; margin-right: 8px; color: var(--faint);
    transition: transform .15s;
  }
  details.help[open] > summary::before { transform: rotate(90deg); }
  details.help[open] > summary { border-bottom: 1px solid var(--line); }
  .help-inner { padding: 16px 20px 20px; }
  .help-scroll { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  th { color: var(--muted); font-weight: 600; font-size: 12px; }
  tr:last-child td { border-bottom: none; }
  .help-table td:first-child { white-space: nowrap; }
  .caption { margin: 12px 0 0; color: var(--muted); font-size: 12.5px; line-height: 1.75; }

  code {
    padding: 1px 6px; border-radius: 5px; background: #eef1f7;
    font-family: "Cascadia Code", Consolas, monospace; font-size: 12px;
  }
  footer { margin-top: 30px; text-align: center; color: var(--faint); font-size: 12px; }

  @media (max-width: 680px) {
    .shell { padding: 26px 14px 40px; }
    header h1 { font-size: 19px; }
    header p { font-size: 12px; }
    .badge { display: none; }
    .status { margin-left: 0; width: 100%; }
    .answer { padding: 18px; }
    .answer-math { font-size: 19px; }
    .help-table td:first-child { white-space: normal; }
    .meta-body .row { grid-template-columns: 1fr; gap: 2px; }
    .modal { padding: 14px; }
    canvas.pad { height: 240px; }
    .modal-note { display: none; }
  }
</style>
</head>
<body>
<div class="shell">
  <header>
    <div class="logo">∑</div>
    <div>
      <h1>Math Solver</h1>
      <p>符号计算求解器 · 答案由 SymPy / Z3 计算保证</p>
    </div>
    <span class="badge">本地运行</span>
  </header>

  <main>
    <section class="card input-card">
      <textarea id="problem" spellcheck="false" placeholder="输入数学题，例如：integrate x**2 from 0 to 1"></textarea>
      <div class="chips-row">
        <span class="chips-label">示例</span>
        <div class="chips" id="exampleChips"></div>
      </div>
      <div class="toolbar">
        <button class="btn primary" id="solveBtn">求解</button>
        <button class="btn" id="uploadBtn">上传图片</button>
        <button class="btn" id="padBtn">手写板</button>
        <button class="btn" id="clearBtn">清空</button>
        <input type="file" id="imageInput" accept="image/*" hidden>
        <span class="shortcut">Ctrl + Enter 快速求解</span>
        <span class="status" id="solveStatus"></span>
      </div>
      <div class="preview-row hidden" id="previewRow">
        <img id="imagePreview" alt="题目图片预览">
        <div class="preview-info">
          <span class="preview-name" id="previewName"></span>
          <span class="preview-note" id="previewNote"></span>
        </div>
        <button class="btn small" id="removeImage" type="button">移除</button>
      </div>
    </section>

    <div id="result"></div>

    <details class="card help">
      <summary>支持的题型与输入格式</summary>
      <div class="help-inner">
        <div class="help-scroll">
          <table class="help-table">
            <thead><tr><th>题型</th><th>输入示例</th><th>说明</th></tr></thead>
            <tbody>
              <tr><td>算术</td><td><code>calculate (12 + 8) / 4</code></td><td>也支持直接写 <code>2**10</code></td></tr>
              <tr><td>化简</td><td><code>simplify sin(x)**2 + cos(x)**2</code></td><td>中文 <code>化简</code> 同义</td></tr>
              <tr><td>方程</td><td><code>solve x**2 - 5*x + 6 = 0</code></td><td>方程组用 <code>and</code> 连接</td></tr>
              <tr><td>求导/偏导</td><td><code>differentiate x**3 + 2*x with respect to x</code></td><td><code>partial derivative ...</code> 为偏导</td></tr>
              <tr><td>积分</td><td><code>integrate x**2 from 0 to 1</code></td><td><code>from A to B</code> 表示定积分</td></tr>
              <tr><td>极限</td><td><code>limit of sin(x)/x as x -&gt; 0</code></td><td>支持 <code>0+</code>、<code>0-</code>、<code>infinity</code></td></tr>
              <tr><td>级数</td><td><code>series of exp(x) around 0 to order 5</code></td><td>支持泰勒 / 麦克劳林</td></tr>
              <tr><td>微分方程</td><td><code>solve the ode y' = 2*x</code></td><td>支持 <code>y'</code>、<code>y''</code>、<code>dy/dx</code></td></tr>
              <tr><td>矩阵</td><td><code>determinant of [[1,2],[3,4]]</code></td><td>行列式 / 特征值 / 逆 / 转置 / 秩</td></tr>
              <tr><td>数论</td><td><code>factorize 360</code></td><td>gcd、lcm、质因数、质数</td></tr>
              <tr><td>约束</td><td><code>find integers x and y such that x + y = 10 and x - y = 4</code></td><td>Z3 求解,可判定无解与唯一性</td></tr>
            </tbody>
          </table>
        </div>
        <p class="caption">
          常用中文关键词:计算、化简、解方程、求导、偏导、积分、极限、趋于、泰勒展开、微分方程、矩阵、特征值、质数、最大公约数。<br>
          应用题型或自然语言描述会触发本地 Ollama 规划;也可以点击"上传图片"或在"手写板"上书写,由本地 qwen2.5vl 识别后填入输入框。<br>
          规则驱动不支持图形题与多步应用题。
        </p>
      </div>
    </details>

    <footer>规则优先 · 未命中时由本地 Ollama 规划 · 全部计算在本地完成</footer>
  </main>
</div>

<div class="modal-backdrop hidden" id="padModal">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="padTitle">
    <div class="modal-head">
      <h3 id="padTitle">手写板</h3>
      <span class="modal-note" id="padStatus">按住鼠标或触控笔写下题目</span>
    </div>
    <div class="pad-wrap">
      <canvas class="pad" id="pad"></canvas>
    </div>
    <div class="modal-actions">
      <button class="btn" id="padUndo" type="button">撤销</button>
      <button class="btn" id="padClear" type="button">清空</button>
      <span class="spacer"></span>
      <button class="btn" id="padCancel" type="button">取消</button>
      <button class="btn primary" id="padRecognize" type="button">识别题目</button>
    </div>
  </div>
</div>

<script>
const EXAMPLES = /*__EXAMPLES__*/;

const problemInput = document.getElementById("problem");
const solveStatus = document.getElementById("solveStatus");
const uploadBtn = document.getElementById("uploadBtn");
const imageInput = document.getElementById("imageInput");
const previewRow = document.getElementById("previewRow");
const previewImage = document.getElementById("imagePreview");
const previewName = document.getElementById("previewName");
const previewNote = document.getElementById("previewNote");
const padBtn = document.getElementById("padBtn");
const padModal = document.getElementById("padModal");
const padCanvas = document.getElementById("pad");
const padCtx = padCanvas.getContext("2d");
const padStatus = document.getElementById("padStatus");
let previewUrl = null;
let padStrokes = [];
let padStroke = null;
let padDrawing = false;
let padWidth = 0;
let padHeight = 0;

function make(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function resetPreview() {
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
  previewImage.removeAttribute("src");
  previewName.textContent = "";
  previewNote.textContent = "";
  previewRow.classList.add("hidden");
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || "").split(",")[1] || "");
    reader.onerror = () => reject(new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

async function recognizeImage(file) {
  if (file.size > 15 * 1024 * 1024) {
    solveStatus.textContent = "图片过大，请压缩到 15MB 以内";
    return;
  }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  previewImage.src = previewUrl;
  previewName.textContent = file.name;
  previewNote.textContent = "正在识别…";
  previewRow.classList.remove("hidden");

  const solveButton = document.getElementById("solveBtn");
  uploadBtn.disabled = true;
  padBtn.disabled = true;
  solveButton.disabled = true;
  uploadBtn.textContent = "识别中…";
  solveStatus.textContent = "正在识别图片…（首次加载视觉模型可能较慢）";
  try {
    const image = await fileToBase64(file);
    const response = await fetch("/api/ocr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "HTTP " + response.status);
    problemInput.value = data.text;
    problemInput.focus();
    previewNote.textContent = "识别完成 · " + data.model;
    solveStatus.textContent = "已填入识别结果，请核对后求解";
  } catch (error) {
    previewNote.textContent = "识别失败";
    solveStatus.textContent = "识别失败: " + error.message;
  } finally {
    uploadBtn.disabled = false;
    padBtn.disabled = false;
    solveButton.disabled = false;
    uploadBtn.textContent = "上传图片";
  }
}

function drawPad() {
  const dpr = window.devicePixelRatio || 1;
  padCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  padCtx.clearRect(0, 0, padWidth, padHeight);
  padCtx.fillStyle = "#ffffff";
  padCtx.fillRect(0, 0, padWidth, padHeight);

  if (!padStrokes.length) {
    padCtx.fillStyle = "#c3cbd8";
    padCtx.font = '15px "Segoe UI", "Microsoft YaHei", sans-serif';
    padCtx.textAlign = "center";
    padCtx.textBaseline = "middle";
    padCtx.fillText("在这里写下题目，例如 x**2 - 5*x + 6 = 0", padWidth / 2, padHeight / 2);
    return;
  }

  padCtx.strokeStyle = "#1b2333";
  padCtx.fillStyle = "#1b2333";
  padCtx.lineWidth = 3.5;
  padCtx.lineCap = "round";
  padCtx.lineJoin = "round";
  padStrokes.forEach((stroke) => {
    if (stroke.length === 1) {
      padCtx.beginPath();
      padCtx.arc(stroke[0].x, stroke[0].y, 1.9, 0, Math.PI * 2);
      padCtx.fill();
      return;
    }
    padCtx.beginPath();
    padCtx.moveTo(stroke[0].x, stroke[0].y);
    for (let i = 1; i < stroke.length - 1; i += 1) {
      const midX = (stroke[i].x + stroke[i + 1].x) / 2;
      const midY = (stroke[i].y + stroke[i + 1].y) / 2;
      padCtx.quadraticCurveTo(stroke[i].x, stroke[i].y, midX, midY);
    }
    const last = stroke[stroke.length - 1];
    padCtx.lineTo(last.x, last.y);
    padCtx.stroke();
  });
}

function resizePad() {
  const rect = padCanvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = padWidth ? rect.width / padWidth : 1;
  padWidth = rect.width;
  padHeight = rect.height;
  if (ratio !== 1) {
    padStrokes.forEach((stroke) => {
      stroke.forEach((point) => { point.x *= ratio; });
    });
  }
  const dpr = window.devicePixelRatio || 1;
  padCanvas.width = Math.round(padWidth * dpr);
  padCanvas.height = Math.round(padHeight * dpr);
  drawPad();
}

function padPoint(event) {
  const rect = padCanvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

padCanvas.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  event.preventDefault();
  if (!padWidth) resizePad();
  padDrawing = true;
  padStroke = [padPoint(event)];
  padStrokes.push(padStroke);
  padCanvas.setPointerCapture(event.pointerId);
  drawPad();
});

padCanvas.addEventListener("pointermove", (event) => {
  if (!padDrawing || !padStroke) return;
  event.preventDefault();
  const point = padPoint(event);
  const last = padStroke[padStroke.length - 1];
  if (Math.hypot(point.x - last.x, point.y - last.y) < 1.2) return;
  padStroke.push(point);
  drawPad();
});

function endPadStroke(event) {
  if (!padDrawing) return;
  padDrawing = false;
  padStroke = null;
  if (event && padCanvas.hasPointerCapture(event.pointerId)) {
    padCanvas.releasePointerCapture(event.pointerId);
  }
}

padCanvas.addEventListener("pointerup", endPadStroke);
padCanvas.addEventListener("pointercancel", endPadStroke);

function openPad() {
  padStatus.textContent = "按住鼠标或触控笔写下题目";
  padModal.classList.remove("hidden");
  requestAnimationFrame(() => resizePad());
}

function closePad() {
  padModal.classList.add("hidden");
}

padBtn.addEventListener("click", openPad);
document.getElementById("padCancel").addEventListener("click", closePad);
padModal.addEventListener("click", (event) => {
  if (event.target === padModal) closePad();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !padModal.classList.contains("hidden")) closePad();
});
window.addEventListener("resize", () => {
  if (!padModal.classList.contains("hidden")) resizePad();
});

document.getElementById("padUndo").addEventListener("click", () => {
  padStrokes.pop();
  drawPad();
});

document.getElementById("padClear").addEventListener("click", () => {
  padStrokes = [];
  drawPad();
});

document.getElementById("padRecognize").addEventListener("click", () => {
  if (!padStrokes.length) {
    padStatus.textContent = "请先写下题目再识别";
    return;
  }
  const button = document.getElementById("padRecognize");
  button.disabled = true;
  padCanvas.toBlob((blob) => {
    button.disabled = false;
    if (!blob) {
      padStatus.textContent = "导出图片失败，请重试";
      return;
    }
    closePad();
    recognizeImage(new File([blob], "手写题目.png", { type: "image/png" }));
  }, "image/png");
});

const exampleChips = document.getElementById("exampleChips");
EXAMPLES.forEach(([name, text]) => {
  const chip = make("button", "chip", name);
  chip.type = "button";
  chip.title = text;
  chip.addEventListener("click", () => {
    problemInput.value = text;
    problemInput.focus();
  });
  exampleChips.appendChild(chip);
});

function renderMath(element, tex, fallback, display) {
  if (tex && typeof katex !== "undefined") {
    try {
      katex.render(tex, element, {
        throwOnError: false,
        strict: false,
        displayMode: Boolean(display),
      });
      return;
    } catch (error) { /* 渲染失败则退回纯文本 */ }
  }
  element.textContent = fallback;
}

function renderResult(data) {
  const box = document.getElementById("result");
  box.innerHTML = "";
  const wrap = make("div", "result");

  const plannerLabels = { rule: "规则命中", llm: "Ollama 兜底", spec: "结构化任务" };
  const metrics = make("div", "metrics");
  [
    ["题型", data.route_label],
    ["规划", plannerLabels[data.planner] || data.planner || "规则"],
    ["耗时", data.elapsed_ms + " ms"],
  ].forEach(([key, value]) => {
    const metric = make("div", "metric");
    metric.appendChild(make("span", null, key));
    metric.appendChild(make("b", null, value));
    metrics.appendChild(metric);
  });
  wrap.appendChild(metrics);

  const banner = make("div", "answer " + (data.ok ? "ok" : "fail"));
  if (data.ok) {
    banner.appendChild(make("div", "answer-label", "答案"));
    const answer = make("div", "answer-math");
    if (data.answer_latex) {
      renderMath(answer, data.answer_latex, String(data.answer), true);
    } else {
      answer.classList.add("answer-text");
      answer.textContent = String(data.answer);
    }
    banner.appendChild(answer);
  } else {
    banner.appendChild(make("div", "answer-label", "未能求解"));
    banner.appendChild(make("div", "answer-fail-text", data.error || "未知错误"));
    if (data.planner === "llm") {
      banner.appendChild(make("p", "answer-tip", "如果这是应用题，请确认本地 Ollama 服务已启动（ollama serve）。"));
    }
  }
  wrap.appendChild(banner);

  if (data.ok && data.steps && data.steps.length) {
    const card = make("div", "card block");
    card.appendChild(make("h3", null, "解题过程"));
    const list = make("ol", "steps");
    data.steps.forEach((step) => list.appendChild(make("li", null, step)));
    card.appendChild(list);
    wrap.appendChild(card);
  }

  const meta = document.createElement("details");
  meta.className = "card meta";
  meta.appendChild(make("summary", null, "求解明细"));
  const body = make("div", "meta-body");
  const rows = [
    ["归一化", data.normalized || "(空)"],
    ["题型路由", data.route_label + (data.hint ? " · " + data.hint : "")],
    ["求解后端", data.backend || "-"],
  ];
  if (data.task) {
    rows.push(["规划任务", JSON.stringify(data.task)]);
  }
  rows.forEach(([key, value]) => {
    const row = make("div", "row");
    row.appendChild(make("span", "k", key));
    row.appendChild(make("span", "v", String(value)));
    body.appendChild(row);
  });
  meta.appendChild(body);
  wrap.appendChild(meta);

  box.appendChild(wrap);
}

async function solve() {
  const problem = problemInput.value.trim();
  const button = document.getElementById("solveBtn");
  if (!problem) {
    solveStatus.textContent = "请输入题目";
    problemInput.focus();
    return;
  }
  button.disabled = true;
  button.textContent = "求解中…";
  solveStatus.textContent = "正在计算…";
  try {
    const response = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "HTTP " + response.status);
    renderResult(data);
    solveStatus.textContent = "";
  } catch (error) {
    solveStatus.textContent = "请求失败: " + error.message;
  } finally {
    button.disabled = false;
    button.textContent = "求解";
  }
}

document.getElementById("solveBtn").addEventListener("click", solve);

document.getElementById("clearBtn").addEventListener("click", () => {
  problemInput.value = "";
  document.getElementById("result").innerHTML = "";
  solveStatus.textContent = "";
  resetPreview();
  problemInput.focus();
});

uploadBtn.addEventListener("click", () => imageInput.click());

imageInput.addEventListener("change", async () => {
  const file = imageInput.files && imageInput.files[0];
  if (!file) return;
  await recognizeImage(file);
  imageInput.value = "";
});

document.getElementById("removeImage").addEventListener("click", () => {
  resetPreview();
  solveStatus.textContent = "";
});

problemInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") solve();
});
</script>
</body>
</html>
"""


INDEX_HTML = INDEX_TEMPLATE.replace(
    "/*__EXAMPLES__*/", json.dumps(EXAMPLES, ensure_ascii=False)
)


def _configure_llm_defaults() -> None:
    """未显式配置 LLM 时,默认用本机 Ollama 做规则失败后的自动兜底。"""
    os.environ.setdefault("MATH_SOLVER_LLM_API_KEY", "ollama")
    os.environ.setdefault("MATH_SOLVER_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    os.environ.setdefault("MATH_SOLVER_LLM_MODEL", "qwen2.5:7b")
    os.environ.setdefault("MATH_SOLVER_LLM_TIMEOUT", "180")
    os.environ.setdefault("MATH_SOLVER_VISION_MODEL", "qwen2.5vl:7b")
    os.environ.setdefault("MATH_SOLVER_VISION_TIMEOUT", "180")


def _lan_ipv4() -> str | None:
    """获取本机局域网 IPv4(不实际发送数据);取不到时返回 None。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Math Solver 本地网页界面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    _configure_llm_defaults()

    if os.name == "nt":
        # Windows 上 SO_REUSEADDR 会允许两个进程监听同一端口,
        # 关闭后端口被占用时才能进入自动换端口的分支。
        ThreadingHTTPServer.allow_reuse_address = False
    server = None
    for offset in range(11):
        try:
            server = ThreadingHTTPServer((args.host, args.port + offset), Handler)
            break
        except OSError:
            continue
    if server is None:
        print(f"端口 {args.port}-{args.port + 10} 均被占用,请用 --port 指定其他端口")
        return
    port = server.server_address[1]
    if args.host in {"0.0.0.0", "::"}:
        lan_ip = _lan_ipv4()
        if lan_ip:
            print(f"Math Solver 界面已启动(局域网): http://{lan_ip}:{port}")
        else:
            print("Math Solver 界面已启动(局域网),请用 ipconfig 查看本机 IPv4")
        print(f"本机访问: http://127.0.0.1:{port}")
        print("手机/平板需与本机处于同一网络;若无法访问,请允许 Python 通过 Windows 防火墙的专用网络")
        url = f"http://127.0.0.1:{port}"
    else:
        url = f"http://{args.host}:{port}"
        print(f"Math Solver 界面已启动: {url}")
    print("按 Ctrl+C 停止")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
