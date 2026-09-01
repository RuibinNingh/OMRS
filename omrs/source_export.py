"""Build a safe, source-only OMRS archive for sharing or support."""

from __future__ import annotations

import datetime
import io
import os
import subprocess
import zipfile


# These paths are either personal data, generated artifacts, or operational
# history.  The archive is deliberately based on tracked files, then applies
# this deny-list as a second safety boundary.
_EXCLUDED_PREFIXES = (
    "错题/",
    "临时/",
    "AI/logs/",
    "AI/omrs_work/",
    "logs/",
)
_EXCLUDED_NAMES = {
    "DEPLOYMENT_SOURCE.json",
}


def _is_excluded(path: str) -> bool:
    path = path.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    return (
        path.startswith(_EXCLUDED_PREFIXES)
        or name in _EXCLUDED_NAMES
        or name.startswith("OMRS-EXP-")
    )


def _tracked_files(root: str) -> list[str]:
    """Return repository-tracked files, without following workspace data."""
    try:
        result = subprocess.run(
            ["git", "-C", root, "ls-files", "-z"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("当前 OMRS 目录不是可读取的 Git 源码仓库") from exc
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def create_source_export(vault: str) -> tuple[bytes, str, dict]:
    """Create a ZIP containing tracked source only and a safety manifest."""
    root = os.path.abspath(vault)
    if not os.path.isdir(os.path.join(root, ".git")):
        raise ValueError("当前 OMRS 目录不是 Git 源码仓库")

    tracked = _tracked_files(root)
    included = [path for path in tracked if not _is_excluded(path)]
    excluded = [path for path in tracked if _is_excluded(path)]
    if not included:
        raise ValueError("没有可导出的源码文件")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"OMRS-source-sanitized-{stamp}.zip"
    manifest = [
        "OMRS 脱敏源码包",
        "",
        "本包只包含 Git 已跟踪的源码、测试和项目文档，不包含个人题库、附件、运行数据、操作日志或生成的导出文件。",
        "未包含：错题/、临时/、AI/logs/、AI/omrs_work/、logs/、DEPLOYMENT_SOURCE.json、OMRS-EXP-*.html。",
        "请在分享前再次检查源码内容，尤其是本地配置或新增未跟踪文件。",
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
            path = os.path.join(root, relative)
            if not os.path.isfile(path):
                continue
            archive.write(path, f"OMRS/{relative.replace(os.sep, '/')}")
        archive.writestr("OMRS/SOURCE_EXPORT_MANIFEST.txt", "\n".join(manifest) + "\n")

    return buffer.getvalue(), filename, {
        "files": len(included),
        "excluded_files": len(excluded),
        "manifest": "SOURCE_EXPORT_MANIFEST.txt",
    }
