"""Math Solver 本地网页界面(零第三方依赖)。

运行:
    python -m app.web                 # 默认 http://127.0.0.1:8765
    python -m app.web --port 9000
    python -m app.web --no-browser    # 不自动打开浏览器

页面文件在 app/assets/（index.html、style.css、app.js）。
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
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

import sympy as sp

from solver import solve_with_planner
from solver.core import route_problem
from solver.text import normalize_text, parse_symbolic

_ASSETS = files("app").joinpath("assets")
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
        "verified": solution.verified,
        "verification": solution.verification,
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
        parts = Path(relative).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            self._send_json({"error": "not found"}, 404)
            return
        target = _ASSETS.joinpath(*parts)
        if not target.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        content_type = ASSET_TYPES.get(
            Path(relative).suffix.lower(), "application/octet-stream"
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



def _load_index_html() -> str:
    """读取页面模板，并填入示例题。"""
    template = _ASSETS.joinpath("index.html").read_text(encoding="utf-8")
    return template.replace("/*__EXAMPLES__*/", json.dumps(EXAMPLES, ensure_ascii=False))


INDEX_HTML = _load_index_html()



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
            lookup = "ipconfig" if os.name == "nt" else "ifconfig 或 ip addr"
            print(f"Math Solver 界面已启动(局域网),请用 {lookup} 查看本机 IPv4")
        print(f"本机访问: http://127.0.0.1:{port}")
        if os.name == "nt":
            print("手机/平板需与本机处于同一网络;若无法访问,请允许 Python 通过防火墙")
        else:
            print("手机/平板需与本机处于同一网络;若无法访问,请检查防火墙是否放行该端口")
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
