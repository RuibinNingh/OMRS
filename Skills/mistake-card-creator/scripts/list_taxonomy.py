#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出题库里已有的全部科目 / 分类 / 知识点。

录新题前先跑一下，让 Claude 把新题的分类、知识点对齐到已有的，
避免建出「二倍角公式」「二倍角」并存这种重复。

数据来源是 错题/.omrs/mastery_data.csv（含 Subject / Category /
Knowledge_Tags 三列，Knowledge_Tags 以 `|` 分隔）。本脚本只读不写，
**复用** omrs 自己的 mastery_path() / load_csv()，不另起一份 CSV 解析逻辑——
和 add_card.py 复用 create_question() 同理。

注意区别：分类是带科目限定的（同一分类名可能挂在不同科目下），
知识点是全库去重的（一个知识点常被多科目/多分类共享）。

用法：
  python Skills/mistake-card-creator/scripts/list_taxonomy.py --vault .
  python Skills/mistake-card-creator/scripts/list_taxonomy.py --vault . --json
  python Skills/mistake-card-creator/scripts/list_taxonomy.py --vault . --subject 数学
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict


def _locate_repo(explicit):
    """让 `import omrs` 能成功。优先 --repo，其次脚本上溯 3 层（Skills/<skill>/scripts）。"""
    candidates = []
    if explicit:
        candidates.append(os.path.abspath(explicit))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.abspath(os.path.join(here, "..", "..", "..")))  # repo 根
    candidates.append(os.getcwd())
    for path in candidates:
        if os.path.isdir(os.path.join(path, "omrs")):
            if path not in sys.path:
                sys.path.insert(0, path)
            return path
    for path in candidates:
        if path not in sys.path:
            sys.path.insert(0, path)
    return candidates[0]


def collect(vault, subject_filter=None):
    """读 mastery_data.csv，汇总三套去重清单（带题数）。"""
    from omrs.common import mastery_path, load_csv

    rows = load_csv(mastery_path(vault))

    subjects = Counter()                       # 科目 -> 题数
    categories = defaultdict(Counter)          # 科目 -> {分类 -> 题数}
    knowledge = Counter()                       # 知识点 -> 出现题数（全库去重）

    for row in rows:
        subject = (row.get("Subject") or "").strip()
        category = (row.get("Category") or "").strip()
        if subject_filter and subject != subject_filter:
            continue
        if subject:
            subjects[subject] += 1
        if subject and category:
            categories[subject][category] += 1
        raw = row.get("Knowledge_Tags") or ""
        for tag in raw.split("|"):
            tag = tag.strip()
            if tag:
                knowledge[tag] += 1

    return rows, subjects, categories, knowledge


def main():
    ap = argparse.ArgumentParser(description="列出题库已有科目/分类/知识点（供录题对齐）")
    ap.add_argument("--vault", default=".", help="Obsidian 库根目录（含 错题/）")
    ap.add_argument("--repo", default=None, help="含 omrs/ 包的目录；默认自动探测")
    ap.add_argument("--subject", default=None, help="只看某个科目下的分类/知识点")
    ap.add_argument("--json", action="store_true", help="输出 JSON（便于程序消费）")
    args = ap.parse_args()

    _locate_repo(args.repo)
    try:
        from omrs.common import mastery_path  # noqa: F401  仅为尽早暴露导入错误
    except Exception as exc:  # pragma: no cover
        print(f"[错误] 无法导入 omrs 包：{exc}\n请用 --repo 指向含 omrs/ 的目录。")
        raise SystemExit(2)

    vault = os.path.abspath(args.vault)
    rows, subjects, categories, knowledge = collect(vault, args.subject)

    if not rows:
        print("[提示] mastery_data.csv 为空或不存在——题库还没有题，或先跑一次重建索引。")
        # 不当成错误：空库也是合法状态
        if args.json:
            print(json.dumps({"subjects": [], "categories": {}, "knowledge": []},
                             ensure_ascii=False))
        return

    if args.json:
        out = {
            "subjects": [
                {"name": s, "count": c}
                for s, c in sorted(subjects.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            "categories": {
                subj: [
                    {"name": cat, "count": cnt}
                    for cat, cnt in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))
                ]
                for subj, cats in sorted(categories.items())
            },
            "knowledge": [
                {"name": k, "count": c}
                for k, c in sorted(knowledge.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # 人类可读输出
    scope = f"（科目：{args.subject}）" if args.subject else "（全库）"
    shown = sum(subjects.values())  # 过滤后实际计入的题数（带科目筛选时 < 文件总行数）
    print(f"题库分类总览 {scope}  共 {shown} 道题\n")

    print(f"■ 科目（{len(subjects)}）")
    for s, c in sorted(subjects.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {s}  ×{c}")

    total_cats = sum(len(v) for v in categories.values())
    print(f"\n■ 分类（{total_cats}，按科目分组）")
    for subj in sorted(categories):
        cats = categories[subj]
        names = "  ".join(
            f"{cat}×{cnt}"
            for cat, cnt in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        print(f"  [{subj}] {names}")

    print(f"\n■ 知识点（{len(knowledge)}，全库去重，括号为出现题数）")
    if knowledge:
        line = "  ".join(
            f"{k}({c})"
            for k, c in sorted(knowledge.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        print(f"  {line}")
    else:
        print("  （暂无知识点标签）")


if __name__ == "__main__":
    main()
