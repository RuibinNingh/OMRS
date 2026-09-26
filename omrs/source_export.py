"""Build a source-only OMRS archive for sharing or support."""

from __future__ import annotations

import datetime
import io
import os
import zipfile


# Only project source locations are scanned. Personal vault data and local
# workspaces live outside these locations, regardless of Git status.
_ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "omrs_dashboard.html",
    "omrs_engine.py",
    "pack_for_ai.bat",
    "run.bat",
}
_SOURCE_DIRS = {"AI", "Skills", "assets", "deploy", "omrs", "tests", "web"}
_SOURCE_SUFFIXES = {
    ".bat", ".cjs", ".css", ".html", ".js", ".md", ".mjs",
    ".otf", ".py", ".service", ".sh", ".svg", ".ts", ".tsx",
    ".ttf", ".txt", ".vue", ".woff", ".woff2",
}
_EXCLUDED_DIRS = {
    "__pycache__", ".git", ".mypy_cache", ".playwright-mcp",
    ".pytest_cache", ".ruff_cache", ".vite", "dist", "node_modules",
}
_EXCLUDED_NAMES = {"DEPLOYMENT_SOURCE.json", "config.json"}


def _is_source_file(relative: str) -> bool:
    parts = relative.split("/")
    name = parts[-1]
    if name in _EXCLUDED_NAMES or name.startswith("OMRS-EXP-"):
        return False
    if (name.startswith(".") or ".bak." in name
            or name.endswith((".bak", ".log", ".tmp"))):
        return False
    if len(parts) == 1:
        return name in _ROOT_FILES
    if parts[0] not in _SOURCE_DIRS or any(part.startswith(".") for part in parts[1:-1]):
        return False
    if relative.startswith(("AI/logs/", "AI/omrs_work/")):
        return False
    suffix = os.path.splitext(name)[1].lower()
    if suffix == ".txt":
        return relative.startswith("assets/vendor/fonts/") and name.endswith("-OFL.txt")
    if suffix == ".json":  # 只收测试基线（如 tests/ui_baseline.json）与 assets/app 的 ES 模块声明；其它 JSON 多为配置或运行数据
        return relative.startswith("tests/") or relative == "assets/app/package.json"
    return suffix in _SOURCE_SUFFIXES


def _source_files(root: str) -> tuple[list[str], int]:
    """Find source files on disk without following symlinks or reading vault data."""
    included: list[str] = []
    excluded = 0

    for name in sorted(_ROOT_FILES):
        path = os.path.join(root, name)
        if os.path.isfile(path) and not os.path.islink(path):
            included.append(name)

    for top in sorted(_SOURCE_DIRS):
        directory = os.path.join(root, top)
        if not os.path.isdir(directory) or os.path.islink(directory):
            continue
        for current, dirs, files in os.walk(directory, followlinks=False):
            safe_dirs = []
            for name in sorted(dirs):
                relative = os.path.relpath(os.path.join(current, name), root).replace(os.sep, "/")
                if (name in _EXCLUDED_DIRS or name.startswith(".")
                        or relative in {"AI/logs", "AI/omrs_work"}
                        or os.path.islink(os.path.join(current, name))):
                    excluded += 1
                else:
                    safe_dirs.append(name)
            dirs[:] = safe_dirs
            for name in sorted(files):
                path = os.path.join(current, name)
                relative = os.path.relpath(path, root).replace(os.sep, "/")
                if not os.path.islink(path) and _is_source_file(relative):
                    included.append(relative)
                else:
                    excluded += 1

    return sorted(included), excluded


def create_source_export(vault: str) -> tuple[bytes, str, dict]:
    """Create a ZIP of current source files and a safety manifest."""
    root = os.path.abspath(vault)
    included, excluded = _source_files(root)
    if not included:
        raise ValueError("没有可导出的源码文件")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"OMRS-source-sanitized-{stamp}.zip"
    manifest = [
        "OMRS 脱敏源码包",
        "",
        "按源码目录和文件类型从当前工作区收集文件，包括未提交的源码；不依赖 Git。",
        "仅扫描根目录项目文件及 AI/、Skills/、assets/、deploy/、omrs/、tests/、web/。",
        "不扫描错题/、临时/、Task/、tool/、unused/、logs/ 等个人或工作目录；",
        "排除 AI/logs/、AI/omrs_work/、缓存、构建产物、符号链接和生成的导出文件。",
        "请在分享前检查文件清单与源码内容，避免代码或文档中包含本地秘密。",
        "",
        f"导出时间（UTC）：{stamp}",
        f"文件数量：{len(included)}",
        "",
        "包含文件：",
        *included,
    ]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in included:
            archive.write(os.path.join(root, relative), f"OMRS/{relative}")
        archive.writestr("OMRS/SOURCE_EXPORT_MANIFEST.txt", "\n".join(manifest) + "\n")

    return buffer.getvalue(), filename, {
        "files": len(included),
        "excluded_files": excluded,
        "manifest": "SOURCE_EXPORT_MANIFEST.txt",
    }
