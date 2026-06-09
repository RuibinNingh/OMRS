#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把转写好的题干/答案 + 裁好的截图，落成一条 OMRS 错题。

确定性的那一半交给本脚本，视觉部分（看图、判断题干/答案分界、裁切、转写、
识别科目/分类）由 Claude 在调用前完成。本脚本只做：

  1. 走 omrs 自带的 create_question() 建骨架（自动编号 UID + 建立锚点 + 重建索引）
  2. 把裁好的图片复制进 错题/附件/，命名为 <UID>-question / <UID>-answer
  3. 填充 # 题目 与 # 答案 两段（含图片 ![[...]] 嵌入），**错因留空**
  4. 把知识点写进 frontmatter（相关知识点 + 知识点/ 标签）
  5. 再跑一次 build_index() 同步难度/标签/知识点到 mastery_data.csv

设计约定（与对话中确定的方案一致）：
  - 难度：默认 5，不由 AI 估算；后续靠 EF / Mastery / 间隔自适应，难度数字本身不动。
  - 错因：录入时一律留空；少数反复错的题由你自己在 Obsidian 里手动补。

用法示例：
  python add_card.py --vault . \
      --subject 数学 --category 三角函数 \
      --question-file q.txt --answer-file a.txt \
      --question-image q.png --answer-image a.png \
      --knowledge 二倍角公式 --knowledge 辅助角公式
"""
import argparse
import os
import re
import shutil
import sys


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
    # 兜底：仍把候选塞进 path，交给 import 报错
    for path in candidates:
        if path not in sys.path:
            sys.path.insert(0, path)
    return candidates[0]


def _read_text(inline, file_path):
    if inline is not None:
        return inline.strip()
    if file_path:
        with open(file_path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    return ""


def _split_sections(content):
    """把 markdown 按一级标题切成 (frontmatter, {标题: 正文}, 标题顺序)。"""
    m = re.match(r"^(---\s*\n.*?\n---\s*\n)", content, re.DOTALL)
    front = m.group(1) if m else ""
    rest = content[len(front):]
    parts = re.split(r"(?m)^# ", rest)
    order, body = [], {}
    # parts[0] 是第一个一级标题前的内容（通常为空）
    lead = parts[0]
    for chunk in parts[1:]:
        line = chunk.split("\n", 1)
        title = line[0].strip()
        text = line[1] if len(line) > 1 else ""
        order.append(title)
        body[title] = text
    return front, lead, order, body


def _rebuild(front, lead, order, body):
    out = front + lead
    for title in order:
        out += f"# {title}\n" + body[title]
    return out


def _embed(text, image_name):
    text = (text or "").rstrip()
    if image_name:
        embed = f"![[{image_name}]]"
        text = (text + "\n\n" + embed) if text else embed
    return "\n" + text + "\n\n"  # 段前空行 + 段后留白，衔接下一个标题


def _add_knowledge_tags(front, knowledge):
    """在 frontmatter 的 tags: 块里追加 知识点/<X>（去重）。"""
    if not knowledge:
        return front
    lines = front.split("\n")
    try:
        tidx = next(i for i, ln in enumerate(lines) if ln.strip() == "tags:")
    except StopIteration:
        return front
    # 找到 tags 块末尾
    end = tidx + 1
    existing = set()
    while end < len(lines) and re.match(r"^\s*-\s+", lines[end]):
        existing.add(lines[end].strip()[2:].strip())
        end += 1
    new_lines = [f"  - 知识点/{k}" for k in knowledge if f"知识点/{k}" not in existing]
    lines[end:end] = new_lines
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="OMRS 截图建错题助手（确定性后半段）")
    ap.add_argument("--vault", default=".", help="Obsidian 库根目录（含 错题/）")
    ap.add_argument("--repo", default=None, help="含 omrs/ 包的目录；默认自动探测")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--difficulty", type=int, default=5, help="默认 5，不建议改")
    ap.add_argument("--question-text", default=None)
    ap.add_argument("--question-file", default=None)
    ap.add_argument("--answer-text", default=None)
    ap.add_argument("--answer-file", default=None)
    ap.add_argument("--question-image", default=None, help="裁好的题干图")
    ap.add_argument("--answer-image", default=None, help="裁好的答案/解析图")
    ap.add_argument("--knowledge", action="append", default=[], help="知识点，可重复")
    args = ap.parse_args()

    _locate_repo(args.repo)
    try:
        from omrs.common import questions_root, ATTACHMENTS_DIR
        from omrs.creation import create_question
        from omrs.indexing import build_index
    except Exception as exc:  # pragma: no cover
        print(f"[错误] 无法导入 omrs 包：{exc}\n请用 --repo 指向含 omrs/ 的目录。")
        raise SystemExit(2)

    vault = os.path.abspath(args.vault)
    q_text = _read_text(args.question_text, args.question_file)
    a_text = _read_text(args.answer_text, args.answer_file)

    # 1) 建骨架（含相关知识点；自动编号 + 重建索引）
    result = create_question(
        vault, args.subject, args.category, args.difficulty,
        related_tags=args.knowledge or None,
    )
    uid = result["uid"]
    file_path = os.path.join(vault, result["file_path"])

    # 2) 复制图片到 错题/附件/
    attach_dir = os.path.join(questions_root(vault), ATTACHMENTS_DIR)
    os.makedirs(attach_dir, exist_ok=True)
    q_name = a_name = None
    if args.question_image and os.path.isfile(args.question_image):
        ext = os.path.splitext(args.question_image)[1] or ".png"
        q_name = f"{uid}-question{ext}"
        shutil.copyfile(args.question_image, os.path.join(attach_dir, q_name))
    if args.answer_image and os.path.isfile(args.answer_image):
        ext = os.path.splitext(args.answer_image)[1] or ".png"
        a_name = f"{uid}-answer{ext}"
        shutil.copyfile(args.answer_image, os.path.join(attach_dir, a_name))

    # 3) 填充 # 题目 / # 答案，错因留空
    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    front, lead, order, body = _split_sections(content)
    if "题目" in body:
        body["题目"] = _embed(q_text, q_name)
    if "答案" in body:
        body["答案"] = _embed(a_text, a_name)

    # 4) 知识点标签
    front = _add_knowledge_tags(front, args.knowledge)

    with open(file_path, "w", encoding="utf-8") as handle:
        handle.write(_rebuild(front, lead, order, body))

    # 5) 再同步一次索引
    build_index(vault)

    print(f"已创建错题 [{uid}]")
    print(f"  文件: {result['file_path']}")
    print(f"  科目/分类: {args.subject}/{args.category}  难度: {args.difficulty}")
    if q_name:
        print(f"  题干图: 错题/{ATTACHMENTS_DIR}/{q_name}")
    if a_name:
        print(f"  答案图: 错题/{ATTACHMENTS_DIR}/{a_name}")
    if args.knowledge:
        print(f"  知识点: {', '.join(args.knowledge)}")
    print("  错因: （留空，按需手动补）")


if __name__ == "__main__":
    main()
