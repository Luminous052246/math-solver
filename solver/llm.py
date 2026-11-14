"""OpenAI 兼容的 LLM 客户端(仅用标准库)。

只负责把消息发送到 ``/chat/completions`` 并取回文本,不绑定任何
SDK。DeepSeek、通义、Kimi、OpenAI 等兼容接口都可以通过环境变量
配置使用。

环境变量:
    MATH_SOLVER_LLM_API_KEY     API 密钥(必填,未配置则规划器禁用)
    MATH_SOLVER_LLM_BASE_URL    接口地址,默认 https://api.openai.com/v1
    MATH_SOLVER_LLM_MODEL       模型名,默认 gpt-4o-mini
    MATH_SOLVER_LLM_TIMEOUT     请求超时秒数,默认 30
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 30.0


class LLMError(RuntimeError):
    """LLM 调用失败。"""


def _env_text(name: str) -> str:
    """读取环境变量,去掉误带入的空白与成对引号。"""
    return os.environ.get(name, "").strip().strip('"').strip("'").strip()


def _env_float(name: str, default: float) -> float:
    """读取数值型环境变量;非法值回退默认值,不让配置错误打断求解。"""
    try:
        value = float(_env_text(name))
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=_env_text("MATH_SOLVER_LLM_BASE_URL") or DEFAULT_BASE_URL,
            api_key=_env_text("MATH_SOLVER_LLM_API_KEY"),
            model=_env_text("MATH_SOLVER_LLM_MODEL") or DEFAULT_MODEL,
            timeout=_env_float("MATH_SOLVER_LLM_TIMEOUT", DEFAULT_TIMEOUT),
        )


def llm_available() -> bool:
    """是否配置了可用的 LLM 密钥。"""
    return bool(_env_text("MATH_SOLVER_LLM_API_KEY"))


def complete_chat(
    messages: list[dict[str, str]], config: LLMConfig | None = None
) -> str:
    """调用 OpenAI 兼容接口,返回第一条回复的文本内容。"""
    config = config or LLMConfig.from_env()
    if not config.api_key:
        raise LLMError(
            "未配置 MATH_SOLVER_LLM_API_KEY,无法调用 LLM 规划器"
        )

    base = config.base_url.rstrip("/")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 800,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise LLMError(f"LLM 接口返回 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"无法连接 LLM 接口: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LLMError(f"LLM 请求超过 {config.timeout:g} 秒") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM 返回的不是 JSON: {body[:300]}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"LLM 返回结构异常: {body[:300]}") from exc

    if isinstance(content, list):
        # 部分兼容接口返回内容分块列表
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if not isinstance(content, str) or not content.strip():
        raise LLMError("LLM 返回了空内容")
    return content
