"""AI 文档体检：只查「形式」，不判断内容对错。

    python3 tests/check_docs.py          # 有问题时退出码 1

规则（都是这次整理时踩过的坑）：
1. 模块文档里不许再堆 `> **v1.x …**` 式的版本流水账——历史叙述放 AI/changelog.md 和 AI/logs/。
2. 单段超过 MAX_PARA 字符视为「读不下去」，拆段或拆小节。
3. 同一文件里出现重复的编号标题（如两个 `## 6.`）。
4. 文档里提到的 `assets/xxx.js`、`omrs/xxx.py`、`tests/xxx` 路径必须真实存在。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_DIR = os.path.join(ROOT, "AI")
MAX_PARA = 800
SKIP = {"changelog.md", "README.md"}          # changelog 天然是流水账；README 是索引
PATH_RE = re.compile(r"`((?:assets|omrs|tests|Skills|deploy)/[\w./-]+\.(?:js|py|css|html|md|json|service))`")


def check_file(path):
    problems = []
    name = os.path.basename(path)
    text = open(path, encoding="utf-8").read()
    if name not in SKIP:
        for i, line in enumerate(text.split("\n"), 1):
            if re.match(r"> \*\*v\d+\.\d+", line):
                problems.append(f"{name}:{i} 版本流水账段落，应搬到 changelog.md")
    for i, line in enumerate(text.split("\n"), 1):
        if name != "changelog.md" and len(line) > MAX_PARA and not line.lstrip().startswith("|"):
            problems.append(f"{name}:{i} 单段 {len(line)} 字符，超过 {MAX_PARA}，拆一拆")
    seen = {}
    for i, line in enumerate(text.split("\n"), 1):
        m = re.match(r"(#{2,4})\s+(\d+(?:\.\d+)*)\.?\s", line)
        if m:
            key = (m.group(1), m.group(2))
            if key in seen:
                problems.append(f"{name}:{i} 标题编号 {m.group(2)} 与第 {seen[key]} 行重复")
            seen[key] = i
    for m in PATH_RE.finditer(text):
        rel = m.group(1)
        if not os.path.exists(os.path.join(ROOT, rel)):
            problems.append(f"{name}: 引用了不存在的文件 `{rel}`")
    return problems


def main():
    targets = [os.path.join(AI_DIR, f) for f in sorted(os.listdir(AI_DIR)) if f.endswith(".md")]
    targets.append(os.path.join(ROOT, "README.md"))
    all_problems = []
    for path in targets:
        all_problems.extend(check_file(path))
    for p in all_problems:
        print(p)
    print(f"\n检查 {len(targets)} 个文档，{len(all_problems)} 处问题")
    return 1 if all_problems else 0


if __name__ == "__main__":
    sys.exit(main())
