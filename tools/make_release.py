# -*- coding: utf-8 -*-
"""打包可分发源码 zip。

用法:
    python tools/make_release.py [版本号]   # 默认 1.0.0

产物: dist/math-solver-v<版本号>.zip，解压后为 math-solver/ 目录。
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
EXCLUDE_DIRS = {".git", ".idea", ".vscode", "__pycache__", "build", "dist", "env", "venv"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".spec", ".zip", ".log"}


def should_skip(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS for part in relative.parts):
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if path.name.startswith("_") and not path.name.startswith("__"):
        return True
    return False


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else "1.0.0"
    DIST.mkdir(exist_ok=True)
    target = DIST / f"math-solver-v{version}.zip"

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and not should_skip(path):
                archive.write(path, Path("math-solver") / path.relative_to(ROOT))

    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
    print(f"生成: {target}")
    print(f"文件数: {len(names)}，大小: {target.stat().st_size / 1024:.1f} KB")
    for name in names:
        print("  " + name)


if __name__ == "__main__":
    main()
