"""AI 文档体检与生成器：只查「形式」和「是否同步」，不判断内容对错。

    python3 tests/check_docs.py                    # 形式检查；有问题退出码 1
    python3 tests/check_docs.py --diff [BASE]      # 另查本次改动：改了源码却没改对应文档、没写任务日志
    python3 tests/check_docs.py --write-routes     # 由 omrs/server.py 生成 AI/routes.md
    python3 tests/check_docs.py --write-log-index  # 由 AI/logs/*.md 生成 AI/logs/log.md（只在完整模式运行）

形式规则（违反即失败）：
1. 模块文档不写 `> **v1.x …**` 式版本流水账；行内版本号每份最多 MAX_VERSION_TAGS 处。
2. 单段不超过 MAX_PARA 字符。
3. 同一文件里的编号标题不重复。
4. 文档里引用的 `assets/`、`omrs/`、`tests/`、`AI/` 等路径必须真实存在。
5. 模块文档以「速查」头开头，含职责、入口、不变量、必跑测试、相关五项。
6. 模块文档不链接 `AI/logs/`：日志不随脱敏源码包导出，历史写进 changelog。
7. `AI/routes.md` 与 `omrs/server.py` 的路由一致，且每条路由至少在一份文档里有说明。
8. 存在 `AI/logs/log.md` 时，它必须与日志文件同步（由 --write-log-index 生成）。
9. 计划文件夹 `AI/plans/<计划>/` 必须同时有 plan.md 与 progress.md；progress.md 前 15 行有 `> **状态**`
   块，含目标、阶段、基线、下一步、更新五项。计划文档不是模块文档（不要速查头），引用的路径可以是未来的文件。
提醒（不失败）：单个文档超过 SOFT_MAX_BYTES 时建议拆分册，先例是 `AI/frontend/`。
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_DIR = os.path.join(ROOT, "AI")
LOG_DIR = os.path.join(AI_DIR, "logs")
PLANS_DIR = os.path.join(AI_DIR, "plans")
PLAN_FILES = ("plan.md", "progress.md")
PLAN_STATUS_KEYS = ("目标", "阶段", "基线", "下一步", "更新")
MAX_PARA = 800
MAX_VERSION_TAGS = 10
SOFT_MAX_BYTES = 40 * 1024
NOT_MODULE = {"README.md", "changelog.md", "routes.md"}  # 索引、流水账、生成文件
HEADER_KEYS = ("职责", "入口", "不变量", "必跑测试", "相关")
PATH_RE = re.compile(
    r"`((?:assets|omrs|tests|Skills|deploy)/[\w./-]+\.(?:js|py|css|html|md|json|service)"
    r"|AI/(?!logs/)[\w./-]+\.md)`")
LOG_LINK_RE = re.compile(r"AI/logs/\d|`logs/\d{4}-")
ROUTE_METHODS = {"do_GET": "GET", "_inbox_get": "GET", "_drafts_get": "GET", "do_POST": "POST",
                 "_do_post_routes": "POST", "_inbox_post": "POST", "_annotate_get": "GET", "_annotate_post": "POST",
                 "_auth_post": "POST",
                 "handle_agent_get": "GET", "agent_post_routes": "POST"}
ROUTE_SOURCES = (("omrs", "server.py"), ("omrs", "agent", "http.py"))


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def doc_targets():
    docs = [os.path.join(AI_DIR, f) for f in sorted(os.listdir(AI_DIR)) if f.endswith(".md")]
    front = os.path.join(AI_DIR, "frontend")
    if os.path.isdir(front):
        docs += [os.path.join(front, f) for f in sorted(os.listdir(front)) if f.endswith(".md")]
    return docs + plan_docs() + [os.path.join(ROOT, "README.md")]


def plan_dirs():
    if not os.path.isdir(PLANS_DIR):
        return []
    return [os.path.join(PLANS_DIR, d) for d in sorted(os.listdir(PLANS_DIR))
            if os.path.isdir(os.path.join(PLANS_DIR, d)) and d != "archive"]


def plan_docs():
    docs = [os.path.join(PLANS_DIR, "README.md")] if os.path.isfile(os.path.join(PLANS_DIR, "README.md")) else []
    for folder in plan_dirs():
        docs += [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".md")]
    return docs


def is_plan_doc(path):
    return rel(path).startswith("AI/plans/")


def is_module_doc(path):
    return rel(path).startswith("AI/") and not is_plan_doc(path) and os.path.basename(path) not in NOT_MODULE


def check_plans():
    problems = []
    for folder in plan_dirs():
        name = rel(folder)
        missing = [f for f in PLAN_FILES if not os.path.isfile(os.path.join(folder, f))]
        if missing:
            problems.append(f"{name}/: 计划文件夹缺少 {'、'.join(missing)}")
            continue
        head = "\n".join(open(os.path.join(folder, "progress.md"), encoding="utf-8").read().split("\n")[:15])
        if "> **状态**" not in head or any(f"> - {key}：" not in head for key in PLAN_STATUS_KEYS):
            problems.append(f"{name}/progress.md: 缺少状态块（前 15 行内 `> **状态**` + {'/'.join(PLAN_STATUS_KEYS)}）")
    return problems


def check_file(path):
    problems, warnings = [], []
    name = rel(path)
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")
    module = is_module_doc(path)
    for i, line in enumerate(lines, 1):
        if module and re.match(r"> \*\*v\d+\.\d+", line):
            problems.append(f"{name}:{i} 版本流水账段落，应搬到 changelog.md")
        if not name.endswith("changelog.md") and len(line) > MAX_PARA and not line.lstrip().startswith("|"):
            problems.append(f"{name}:{i} 单段 {len(line)} 字符，超过 {MAX_PARA}，拆一拆")
    seen = {}
    for i, line in enumerate(lines, 1):
        m = re.match(r"(#{2,4})\s+(\d+(?:\.\d+)*)\.?\s", line)
        if m:
            key = (m.group(1), m.group(2))
            if key in seen:
                problems.append(f"{name}:{i} 标题编号 {m.group(2)} 与第 {seen[key]} 行重复")
            seen[key] = i
    for m in ([] if is_plan_doc(path) else PATH_RE.finditer(text)):
        if not os.path.exists(os.path.join(ROOT, m.group(1))):
            problems.append(f"{name}: 引用了不存在的文件 `{m.group(1)}`")
    if module:
        head = "\n".join(lines[:15])
        if "> **速查**" not in head or any(f"> - {key}：" not in head for key in HEADER_KEYS):
            problems.append(f"{name}: 缺少速查头（前 15 行内 `> **速查**` + {'/'.join(HEADER_KEYS)}）")
        tags = len(re.findall(r"v\d+\.\d+", text))
        if tags > MAX_VERSION_TAGS:
            problems.append(f"{name}: 行内版本号 {tags} 处，超过 {MAX_VERSION_TAGS}；模块文档只写现在，历史进 changelog")
        for i, line in enumerate(lines, 1):
            if LOG_LINK_RE.search(line):
                problems.append(f"{name}:{i} 模块文档不链接 AI/logs/（不随源码包导出）")
    size = len(text.encode("utf-8"))
    if size > SOFT_MAX_BYTES and not name.endswith("changelog.md"):
        warnings.append(f"{name}: {size // 1024}KB，超过 {SOFT_MAX_BYTES // 1024}KB，建议拆分册")
    return problems, warnings


# ---------- 路由总表 ----------

def extract_routes():
    """Return {path: set(methods)} for exact routes and {prefix: set(methods)} for prefix dispatch."""
    exact, prefix = {}, {}
    lines = []
    for parts in ROUTE_SOURCES:
        source = os.path.join(ROOT, *parts)
        if os.path.exists(source):
            lines += open(source, encoding="utf-8").read().split("\n") + [""]
    method = None
    for line in lines:
        m = re.match(r"(?:    )?def (\w+)\(", line)
        if m:
            method = ROUTE_METHODS.get(m.group(1))
        if not method:
            continue
        for path in re.findall(r'path == "(/[^"]*)"', line) + re.findall(r'^\s+"(/api/[^"]+)": lambda', line):
            exact.setdefault(path, set()).add(method)
        for path in re.findall(r'path\.startswith\("(/[^"]*)"\)', line):
            prefix.setdefault(path, set()).add(method)
    return exact, prefix


def route_docs(path):
    pattern = re.compile(r"(?<![\w/])" + re.escape(path) + r"(?![\w/-])")
    found = []
    for doc in doc_targets():
        if doc.endswith(os.path.join("AI", "routes.md")) or not rel(doc).startswith("AI/") or is_plan_doc(doc):
            continue
        if pattern.search(open(doc, encoding="utf-8").read()):
            found.append(rel(doc))
    found.sort(key=lambda d: (d != "AI/api.md", d))
    return found


def render_routes():
    exact, prefix = extract_routes()
    out = ["# 路由总表（自动生成）", "",
           "> 由 `python3 tests/check_docs.py --write-routes` 从 `omrs/server.py` 生成，勿手改。",
           "> 请求体、响应字段与错误语义见「说明」列的文档；`AI/api.md` 为主。", "",
           "| 方法 | 路径 | 说明 |", "|---|---|---|"]
    for path in sorted(exact):
        docs = route_docs(path)
        out.append(f"| {'/'.join(sorted(exact[path]))} | `{path}` | {'、'.join(f'`{d}`' for d in docs[:3]) + ('等' if len(docs) > 3 else '') or '（缺）'} |")
    out += ["", "按前缀分派（具体子路由见上表或对应文档）：", ""]
    for path in sorted(prefix):
        out.append(f"- {'/'.join(sorted(prefix[path]))} `{path}…`")
    return "\n".join(out) + "\n"


def check_routes():
    problems = []
    if not os.path.exists(os.path.join(ROOT, "omrs", "server.py")):
        return problems
    exact, _ = extract_routes()
    for path in sorted(exact):
        if not route_docs(path):
            problems.append(f"路由 `{path}` 没有任何 AI 文档说明（至少在 AI/api.md 或对应模块文档写一句）")
    target = os.path.join(AI_DIR, "routes.md")
    current = open(target, encoding="utf-8").read() if os.path.exists(target) else ""
    if current != render_routes():
        problems.append("AI/routes.md 与 omrs/server.py 不同步：运行 python3 tests/check_docs.py --write-routes")
    return problems


# ---------- 任务日志索引 ----------

def render_log_index():
    entries = []
    for name in sorted(os.listdir(LOG_DIR), reverse=True):
        if not re.match(r"\d{4}-\d{2}-\d{2}_.+\.md$", name):
            continue
        title = ""
        for line in open(os.path.join(LOG_DIR, name), encoding="utf-8"):
            if line.startswith("# "):
                title = re.sub(r"^#\s+\d{4}-\d{2}-\d{2}\s*", "", line).strip()
                break
        entries.append(f"- [{name[:-3]}]({name})：{title or '（无标题）'}")
    return ("# 任务日志索引（自动生成）\n\n"
            "> 由 `python3 tests/check_docs.py --write-log-index` 按文件名倒序生成，勿手改。"
            "新增任务只需在本目录新建 `YYYY-MM-DD_<topic>.md`。\n\n" + "\n".join(entries) + "\n")


def check_log_index():
    index = os.path.join(LOG_DIR, "log.md")
    if not os.path.exists(index):
        return []
    if open(index, encoding="utf-8").read() != render_log_index():
        return ["AI/logs/log.md 与日志文件不同步：运行 python3 tests/check_docs.py --write-log-index"]
    return []


# ---------- --diff：改了源码却没改文档 ----------

def doc_map():
    """Parse the 「代码到文档的对应关系」 table in AGENTS.md: [(source patterns, doc patterns)]."""
    rows, in_table = [], False
    for line in open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8"):
        if line.startswith("| 改动范围"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2 or set(cells[0]) <= {"-", " "}:
                continue
            sources = re.findall(r"`([^`]+)`", cells[0])
            docs = [d for d in re.findall(r"`([^`]+)`", cells[1]) if d.startswith("AI/") or d.endswith(".md")]
            if sources and docs:
                rows.append((sources, docs))
    return rows


def matches(path, pattern):
    return path.startswith(pattern) if pattern.endswith("/") else path == pattern


def changed_files(base):
    tracked = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", base], check=True,
                             capture_output=True, text=True).stdout.split()
    untracked = subprocess.run(["git", "-C", ROOT, "ls-files", "--others", "--exclude-standard"],
                               check=True, capture_output=True, text=True).stdout.split()
    return sorted(set(tracked + untracked))


def check_diff(base):
    try:
        changed = changed_files(base)
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"--diff 需要 Git 基线（受限模式先 git init 并提交导出包）：{exc}"]
    problems = []
    for sources, docs in doc_map():
        hit = [p for p in changed if any(matches(p, s) for s in sources)]
        if hit and not any(any(matches(p, d) or (d.endswith(".md") and p.startswith(d[:-3] + "/")) for d in docs)
                           for p in changed):
            problems.append(f"改了 {', '.join(hit[:3])}{' 等' if len(hit) > 3 else ''}，但 {' / '.join(docs)} 都没更新")
    substantive = [p for p in changed if not p.startswith("AI/logs/")]
    if substantive and not any(re.match(r"AI/logs/\d{4}-\d{2}-\d{2}_.+\.md$", p) for p in changed):
        problems.append("有持久化改动但没有新增或更新 AI/logs/YYYY-MM-DD_<topic>.md 任务日志")
    return problems


def main(argv):
    if "--write-routes" in argv:
        open(os.path.join(AI_DIR, "routes.md"), "w", encoding="utf-8").write(render_routes())
        print("已生成 AI/routes.md")
        return 0
    if "--write-log-index" in argv:
        if not os.path.isdir(LOG_DIR):
            print("没有 AI/logs/ 目录（受限模式不生成索引，交给完整模式）")
            return 1
        open(os.path.join(LOG_DIR, "log.md"), "w", encoding="utf-8").write(render_log_index())
        print("已生成 AI/logs/log.md")
        return 0
    targets = doc_targets()
    problems, warnings = [], []
    for path in targets:
        p, w = check_file(path)
        problems += p
        warnings += w
    problems += check_routes() + check_log_index() + check_plans()
    if "--diff" in argv:
        i = argv.index("--diff")
        base = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") else "HEAD"
        problems += check_diff(base)
    for p in problems:
        print(p)
    for w in warnings:
        print("提醒：" + w)
    print(f"\n检查 {len(targets)} 个文档，{len(problems)} 处问题，{len(warnings)} 条提醒")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
