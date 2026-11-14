# -*- coding: utf-8 -*-
"""构建 Windows 单文件 exe（需 PyInstaller、sympy、z3-solver）。

用法:
    python tools/build_exe.py

产物: dist/math-solver.exe，内置 Python / SymPy / Z3 与网页资源，
对方无需安装任何环境，双击即可使用。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "math-solver",
        "--collect-all",
        "z3",
        "--add-data",
        "webapp_assets;webapp_assets",
        "--add-data",
        "data;data",
        "webapp.py",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    print("构建完成: dist/math-solver.exe")


if __name__ == "__main__":
    main()
