from .data_repository import mastery_rows
import datetime
import os

from .common import FILE_PATTERN, omrs_data_dir, parse_history_lines, parse_yaml_frontmatter, questions_root, split_sections
from .log_utils import log_index


def scan_vault(vault: str) -> list:
    qroot = questions_root(vault)
    if not os.path.isdir(qroot):
        os.makedirs(qroot, exist_ok=True)
        return []

    results = []
    uid_set = {}
    for root, dirs, files in os.walk(qroot):
        dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
        for fname in files:
            if not FILE_PATTERN.match(fname):
                continue
            uid = os.path.splitext(fname)[0]
            fullpath = os.path.join(root, fname)
            relpath = os.path.relpath(fullpath, vault)

            if uid in uid_set:
                raise RuntimeError(
                    f"❌ UID 冲突：'{uid}'\n  1) {uid_set[uid]}\n  2) {relpath}"
                )
            uid_set[uid] = relpath

            with open(fullpath, "r", encoding="utf-8") as file:
                content = file.read()
            meta = parse_yaml_frontmatter(content)
            sections = split_sections(content)
            history = parse_history_lines(sections.get("历史", ""))
            results.append(
                {
                    "uid": uid,
                    "file_path": relpath,
                    "full_path": fullpath,
                    "meta": meta,
                    "sections": sections,
                    "history": history,
                    "content": content,
                }
            )
    return results


def build_index(vault: str, return_scan=False):
    omrs_data_dir(vault)
    from .migration import ensure_ledger_bootstrap
    from .projections import rebuild_projection
    from .workspace_sync import scan_workspace

    ensure_ledger_bootstrap(vault)
    scan = scan_workspace(vault)
    if scan.get("status") == "conflict":
        raise RuntimeError("工作区自检发现冲突：\n" + "\n".join(scan.get("conflicts", [])))
    rebuild_projection(vault)
    rows = mastery_rows(vault)
    log_index(vault, added=0, updated=len(rows), total=len(rows))
    return (rows, scan) if return_scan else rows
