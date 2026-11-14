"""读取项目元数据。版本号只写在 pyproject.toml。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project_version(root: Path | None = None) -> str:
    text = ((root or ROOT) / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if match is None:
        raise RuntimeError("pyproject.toml 中没有 version")
    return match.group(1)
