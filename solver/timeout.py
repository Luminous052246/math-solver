"""给可能长时间运行的符号计算加超时保护。

SymPy 的 integrate / limit / series / dsolve 在某些输入上可能长时间不返回。
这里用守护线程 + join(timeout) 实现软超时:超时后返回错误,后台线程不阻塞
解释器退出(代价是极端情况下会残留一个后台计算线程)。
"""

from __future__ import annotations

import os
import threading

def _load_timeout() -> float:
    raw = os.environ.get("MATH_SOLVER_TIMEOUT", "15").strip().strip('"').strip("'")
    try:
        value = float(raw)
    except ValueError:
        return 15.0
    return value if value > 0 else 15.0


DEFAULT_TIMEOUT = _load_timeout()


def run_with_timeout(func, *args, timeout: float | None = None, **kwargs):
    """在后台线程执行 func,超过 timeout 秒抛出 TimeoutError。"""
    limit = DEFAULT_TIMEOUT if timeout is None else timeout
    box: dict = {}

    def target():
        try:
            box["value"] = func(*args, **kwargs)
        except BaseException as exc:  # 原样传回调用方
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(limit)
    if thread.is_alive():
        raise TimeoutError(f"计算超过 {limit:g} 秒,已终止")
    if "error" in box:
        raise box["error"]
    return box["value"]
