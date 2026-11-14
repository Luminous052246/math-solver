"""在当前操作系统上构建本机可执行文件。

PyInstaller 不能交叉编译。Windows、Linux 和 macOS 都要在对应系统上运行本脚本。
macOS 还要在目标 CPU 架构上构建；应用签名不在此脚本中处理。

用法:
    python -m pip install -e ".[build]"
    python tools/build.py

产物位于 dist/。Windows 为 math-solver.exe，其他系统为 math-solver。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    separator = os.pathsep
    suffix = ".exe" if sys.platform == "win32" else ""
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
        f"app/assets{separator}app/assets",
        "--add-data",
        f"data{separator}data",
        "app/web.py",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"构建完成: dist/math-solver{suffix}")
    print("该产物只适用于当前操作系统和 CPU 架构。")


if __name__ == "__main__":
    main()
