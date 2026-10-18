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
    "requirements-mcp.txt",
    "requirements-zuoyebang.txt",
    "run.bat",
}
_SOURCE_DIRS = {"AI", "Skills", "assets", "deploy", "omrs", "services", "tests", "tools", "web"}
_SOURCE_SUFFIXES = {
    ".bat", ".cjs", ".css", ".html", ".js", ".md", ".mjs",
    ".otf", ".py", ".service", ".sh", ".svg", ".ts", ".tsx",
    ".ttf", ".txt", ".vue", ".woff", ".woff2",
}
_EXCLUDED_DIRS = {
    "__pycache__", ".git", ".mypy_cache", ".playwright-mcp",
    ".pytest_cache", ".ruff_cache", ".vite", "dist", "node_modules",
}
_EXCLUDED_NAMES = {"DEPLOYMENT_SOURCE.json", "config.json", "admin-secret.txt"}
_GATEWAY_FILES = {
    "services/zuoyebang/.gitignore", "services/zuoyebang/pyproject.toml",
    "services/zuoyebang/requirements.txt", "services/zuoyebang/requirements-dev.txt",
    "services/zuoyebang/vendor-manifest.json",
    "services/zuoyebang/deploy/zuoyebang.service.example",
    "services/zuoyebang/deploy/zuoyebang.nginx.example",
}
_BOXDETECT_FILES = {
    'services/boxdetect/.gitignore', 'services/boxdetect/README.md',
    'services/boxdetect/pyproject.toml', 'services/boxdetect/requirements.txt',
}
_BOXDETECT_DIRS = {'services/boxdetect/boxdetect_service', 'services/boxdetect/tests', 'services/boxdetect/boxdetect_service/assets'}
_TRAINING_FILES = {'tools/boxdetect/' + name for name in (
    'README.md', '_service.py', 'audit.py', 'bootstrap_control.py', 'build_dataset.py',
    'common.py', 'decision.py', 'evaluate.py', 'inference.py', 'probe.py', 'publish.py',
    'reweight.py', 'serve.py', 'train.py', 'requirements-serve.txt',
    'requirements-train.txt', 'crop-prompt-v2.txt',
)}

# 精确登记运行必需的二进制资源和第三方来源／许可；不扩大 JSON／TXT 通配范围。
_PUBLIC_ASSET_FILES = {
    "assets/vendor/entry-fallback.webp",
    "assets/vendor/entry-scene.manifest.json",
    "assets/vendor/entry-scene-THREE-LICENSE",
    "assets/vendor/katex/LICENSE", "assets/vendor/katex/manifest.json",
    "assets/vendor/mathjax/LICENSE", "assets/vendor/mathjax/manifest.json",
    "assets/vendor/fonts/SOURCES.json", "assets/vendor/fonts/PRINT_SOURCES.json",
}


def _is_source_file(relative: str) -> bool:
    parts = relative.split("/")
    name = parts[-1]
    if (relative in _GATEWAY_FILES or relative in _BOXDETECT_FILES
            or relative in _TRAINING_FILES or relative in _PUBLIC_ASSET_FILES):
        return True
    if name in _EXCLUDED_NAMES or name.startswith("OMRS-EXP-"):
        return False
    if (name.startswith(".") or ".bak." in name
            or name.endswith((".bak", ".log", ".tmp"))):
        return False
    if len(parts) == 1:
        return name in _ROOT_FILES
    if parts[0] not in _SOURCE_DIRS or any(part.startswith(".") for part in parts[1:-1]):
        return False
    if parts[0] == 'tools':
        return False  # 工具只收上方明确登记的训练源码，未知文件不导出。
    if parts[0] == 'services':
        if len(parts) < 3 or parts[1] not in ('zuoyebang', 'boxdetect'):
            return False
        if parts[1] == 'boxdetect':
            return ((len(parts) == 4 and '/'.join(parts[:3]) in _BOXDETECT_DIRS and name.endswith('.py'))
                    or (relative.startswith('services/boxdetect/boxdetect_service/assets/') and len(parts)==5 and name in ('index.html','panel.js','panel.css')))
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
                        or (relative.startswith("services/") and
                            (name == "private" or name.startswith(("tmp", "isolated-test"))))
                        or (current == directory and top == "services" and name not in {"zuoyebang", "boxdetect"})
                        or (current == directory and top == 'tools' and name != 'boxdetect')
                        or relative.startswith('tools/boxdetect/')
                        or (relative.startswith('services/boxdetect/') and relative not in _BOXDETECT_DIRS)
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
        "仅扫描根目录项目文件及 AI/、Skills/、assets/、deploy/、omrs/、services/zuoyebang/、services/boxdetect/、tests/、tools/boxdetect/、web/。",
        "不扫描错题/、临时/、Task/、tool/、unused/、logs/ 等个人或工作目录；",
        "排除 AI/logs/、AI/omrs_work/、服务私有目录及管理员密码、缓存、构建产物、符号链接和生成的导出文件。",
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
