import datetime
import os

from .common import (
    FILE_PATTERN,
    MASTERY_HEADERS,
    extract_category,
    extract_knowledge_tags,
    extract_tag,
    load_csv,
    mastery_path,
    omrs_data_dir,
    parse_history_lines,
    parse_yaml_frontmatter,
    questions_root,
    save_csv,
    split_sections,
)
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


def build_index(vault: str) -> list:
    omrs_data_dir(vault)
    scanned = scan_vault(vault)
    existing = load_csv(mastery_path(vault), MASTERY_HEADERS)
    existing_map = {row["UID"]: row for row in existing}
    updated = []
    today = datetime.date.today().isoformat()

    for item in scanned:
        uid = item["uid"]
        meta = item["meta"]
        knowledge_tags = extract_knowledge_tags(meta)
        knowledge_tags_str = "|".join(knowledge_tags)
        if uid in existing_map:
            row = existing_map[uid]
            row["File_Path"] = item["file_path"]
            row["Subject"] = meta.get("科目", row.get("Subject", ""))
            row["Category"] = extract_category(meta)
            row["Difficulty"] = meta.get("难度", row.get("Difficulty", "5"))
            row["Current_Tag"] = extract_tag(meta)
            row["Knowledge_Tags"] = knowledge_tags_str
            row["High_Correct_Streak"] = row.get("High_Correct_Streak", "0") or "0"
        else:
            row = {
                "UID": uid,
                "File_Path": item["file_path"],
                "Subject": meta.get("科目", ""),
                "Category": extract_category(meta),
                "Difficulty": meta.get("难度", "5"),
                "Mastery": "0.0",
                "EF": "2.5",
                "Attempts": "0",
                "High_Correct_Streak": "0",
                "Last_Review": meta.get("录入日期", today),
                "Interval": "0",
                "Due_Date": meta.get("录入日期", today),
                "Repetition": "0",
                "Current_Tag": extract_tag(meta),
                "Entry_Date": meta.get("录入日期", today),
                "Knowledge_Tags": knowledge_tags_str,
            }
        updated.append(row)

    added = sum(1 for item in scanned if item["uid"] not in existing_map)
    save_csv(mastery_path(vault), MASTERY_HEADERS, updated, backup=True)
    log_index(vault, added=added, updated=len(updated) - added, total=len(updated))
    return updated
