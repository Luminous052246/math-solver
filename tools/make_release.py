"""按 Git 已跟踪文件生成源码 zip。

不扫描工作区。未跟踪的 .env、虚拟环境和本地模型不会进入压缩包；
即便这些路径曾被误提交，下面的拒绝列表也会把它们排除。

版本号来自 pyproject.toml。

用法:
    python tools/make_release.py

产物: dist/math-solver-v<版本号>.zip
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

from project_meta import ROOT, project_version

DIST = ROOT / "dist"
DENY_DIRS = {".git", ".venv", "venv", "env", "models", "dist", "build"}


def tracked_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"无法读取 Git 文件清单: {exc}") from exc
    return [
        name.decode("utf-8")
        for name in result.stdout.split(b"\0")
        if name
    ]


def denied(relative: str) -> bool:
    path = Path(relative)
    if any(part in DENY_DIRS for part in path.parts):
        return True
    name = path.name
    return name == ".env" or name.startswith(".env.")


def main() -> None:
    version = project_version()
    files = tracked_files()
    if not files:
        raise SystemExit("Git 文件清单为空。请在仓库内运行，并先提交需要发布的文件。")

    skipped = [name for name in files if denied(name)]
    included = [name for name in files if name not in set(skipped)]
    for name in skipped:
        print(f"已排除: {name}", file=sys.stderr)

    DIST.mkdir(exist_ok=True)
    target = DIST / f"math-solver-v{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in included:
            path = ROOT / name
            if path.is_file():
                archive.write(path, Path("math-solver") / name)

    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
    print(f"版本: {version}")
    print(f"生成: {target}")
    print(f"文件数: {len(names)}，大小: {target.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
