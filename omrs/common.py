import csv
import datetime
import json
import os
import re


QUESTIONS_DIR = "错题"
OMRS_DIR = ".omrs"
MASTERY_CSV = "mastery_data.csv"
HISTORY_CSV = "history_log.csv"
SESSIONS_CSV = "sessions.csv"
SESSIONS_HEADERS = [
    "Session_ID",
    "Created_At",
    "Subject_Filter",
    "Count",
    "UIDs",
    "Status",
    "Completed_At",
]
FILE_PATTERN = re.compile(r".*\d\.md$")

MASTERY_HEADERS = [
    "UID",
    "File_Path",
    "Subject",
    "Category",
    "Difficulty",
    "Mastery",
    "EF",
    "Attempts",
    "High_Correct_Streak",
    "Last_Review",
    "Interval",
    "Due_Date",
    "Repetition",
    "Current_Tag",
    "Entry_Date",
    "Knowledge_Tags",
]
HISTORY_HEADERS = [
    "Log_ID",
    "UID",
    "Date",
    "Action",
    "Sub_Score",
    "Is_Correct",
    "Session_ID",
    "Note",
]
ATTACHMENTS_DIR = "附件"


def questions_root(vault: str) -> str:
    return os.path.join(vault, QUESTIONS_DIR)


def omrs_data_dir(vault: str) -> str:
    data_dir = os.path.join(questions_root(vault), OMRS_DIR)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def mastery_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), MASTERY_CSV)


def history_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), HISTORY_CSV)


def sessions_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), SESSIONS_CSV)


def config_path(vault: str) -> str:
    return os.path.join(omrs_data_dir(vault), "config.json")


# 配置默认值：缺失键按此回退。ai_restrict_tags 默认 True，与历史行为一致
# （AI 识别的知识点硬过滤为「已有分类 ∪ 已有知识点」）。
CONFIG_DEFAULTS = {"allow_external": False, "ai_restrict_tags": True}


def load_config(vault: str) -> dict:
    path = config_path(vault)
    if not os.path.exists(path):
        return dict(CONFIG_DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as file:
            return {**CONFIG_DEFAULTS, **json.load(file)}
    except Exception:
        return dict(CONFIG_DEFAULTS)


def save_config(vault: str, config: dict) -> None:
    path = config_path(vault)
    existing = load_config(vault)
    existing.update(config)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(existing, file, ensure_ascii=False, indent=2)
    reset_tuning_cache(vault)


def parse_yaml_frontmatter(content: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    meta, current_key, list_vals = {}, None, []
    for line in m.group(1).split("\n"):
        stripped = line.strip()
        if stripped.startswith("- ") and current_key:
            list_vals.append(stripped[2:].strip())
            meta[current_key] = list_vals
            continue
        kv = re.match(r"^(\S.*?):\s*(.*)", line)
        if kv:
            current_key = kv.group(1).strip()
            val = kv.group(2).strip().strip('"').strip("'")
            if val:
                if val == "[]":
                    meta[current_key] = []
                elif val.startswith("[") and val.endswith("]") and not val.startswith("[["):
                    inner = val[1:-1].strip()
                    meta[current_key] = [
                        item.strip().strip('"').strip("'")
                        for item in inner.split(",")
                        if item.strip()
                    ] if inner else []
                else:
                    meta[current_key] = val
                list_vals = []
            else:
                list_vals = []
        else:
            current_key, list_vals = None, []
    return meta


def split_sections(content: str) -> dict:
    parts = re.split(r"^#\s+", content, flags=re.MULTILINE)
    sections = {"_frontmatter": parts[0] if parts else ""}
    for part in parts[1:]:
        lines = part.split("\n", 1)
        sections[lines[0].strip()] = lines[1].strip() if len(lines) > 1 else ""
    return sections


def parse_history_lines(text: str) -> list:
    records = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(
            r"(\d{4}-\d{2}-\d{2})\s+主观:(\d+),\s*(对|错)(?:,\s*备注:(.*))?",
            line,
        )
        if match:
            records.append(
                {
                    "date": match.group(1),
                    "sub_score": int(match.group(2)),
                    "correct": match.group(3) == "对",
                    "note": (match.group(4) or "").strip(),
                }
            )
    return records


def extract_tag(meta: dict) -> str:
    tags = meta.get("tags", [])
    if isinstance(tags, list):
        for tag in tags:
            if tag.startswith("状态/"):
                return f"#{tag}"
    elif isinstance(tags, str) and tags.startswith("状态/"):
        return f"#{tags}"
    return "#状态/待攻克"


def extract_category(meta: dict) -> str:
    raw = meta.get("分类", "")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return re.sub(r"\[\[|\]\]", "", str(raw)).strip()


def extract_knowledge_tags(meta: dict) -> list:
    raw = meta.get("相关知识点", [])
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list) and raw:
        return [
            re.sub(r"\[\[|\]\]", "", tag).strip().strip('"').strip("'")
            for tag in raw
            if isinstance(tag, str) and tag.strip()
        ]
    tags = meta.get("tags", [])
    if not isinstance(tags, list):
        tags = [tags] if isinstance(tags, str) else []
    return [
        tag.replace("知识点/", "", 1)
        for tag in tags
        if isinstance(tag, str) and tag.startswith("知识点/")
    ]


def extract_images(text: str) -> list:
    """从题面文本解析引用的图片文件名（去重保序）。

    支持 Obsidian 嵌入 `![[名.png]]`、`![[名.png|宽]]` 与标准 `![alt](路径)`。
    返回的是文件名（仅 basename），与 `/api/image?name=` 对接。
    """
    names = []
    seen = set()

    def add(raw):
        name = (raw or "").split("/")[-1].split("\\")[-1].strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    for m in re.finditer(r"!\[\[([^\]|]+?)(?:\|\d+)?\]\]", text or ""):
        add(m.group(1))
    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text or ""):
        add(m.group(1))
    return names


def parse_date(value: str):
    """兼容 YYYY-MM-DD 和 YYYY/M/D 两种格式，解析失败返回 None。"""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        pass
    try:
        parts = value.split("/")
        if len(parts) == 3:
            return datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, TypeError):
        pass
    return None


def load_csv(filepath, headers=None):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


BACKUP_KEEP = 3  # 滚动备份保留份数


def _rotate_backups(filepath, keep=BACKUP_KEEP):
    """把当前文件滚动备份为 <name>.bak.1（最新）.. .bak.N（最旧）。"""
    if not os.path.exists(filepath):
        return
    # 先把旧的依次后移：.bak.(N-1) -> .bak.N ... .bak.1 -> .bak.2
    for idx in range(keep, 1, -1):
        src = f"{filepath}.bak.{idx - 1}"
        dst = f"{filepath}.bak.{idx}"
        if os.path.exists(src):
            os.replace(src, dst)
    # 当前文件复制为 .bak.1（复制而非移动，避免主文件短暂缺失）
    try:
        with open(filepath, "rb") as fsrc, open(f"{filepath}.bak.1", "wb") as fdst:
            fdst.write(fsrc.read())
    except OSError:
        pass


def save_csv(filepath, headers, rows, backup=False):
    """原子写：先写临时文件并 fsync，再 os.replace 覆盖，避免写到一半损坏。

    backup=True 时，在覆盖前对现有文件做滚动备份（保留最近 BACKUP_KEEP 份）。
    """
    if backup:
        _rotate_backups(filepath)
    tmp = f"{filepath}.tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, filepath)


def append_csv(filepath, headers, rows):
    """追加写：只把新行 append 到文件末尾（崩溃不会截断已有数据）。

    文件不存在或为空时先写表头。用于只增不改的 history_log.csv。
    """
    if not rows:
        return
    need_header = (not os.path.exists(filepath)) or os.path.getsize(filepath) == 0
    # 已存在文件用普通 utf-8 追加（BOM 只在文件开头出现一次）
    encoding = "utf-8-sig" if need_header else "utf-8"
    with open(filepath, "a", encoding=encoding, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        if need_header:
            writer.writeheader()
        writer.writerows(rows)
        file.flush()
        os.fsync(file.fileno())


# ── SM-2 排期核心 ──

SM2_DEFAULT_INTERVAL = 1
SM2_INTERVAL_AFTER_FIRST = 6
SM2_EF_MIN = 1.3
SM2_EF_MAX = 3.0
# 熟练度来源答对时，间隔乘以该系数（折中方案：有进展但保守）
SM2_PROFICIENCY_CORRECT_FACTOR = 0.7


# ── 可调参数（algorithm tuning）──
# 全部可在 错题/.omrs/config.json 的 "tuning" 键下覆盖；缺省时用以下默认值，
# 默认值与历史硬编码完全一致，不改 config 行为不变。
DEFAULT_TUNING = {
    # 时间衰减：decayed = mastery × e^(-days / (mastery×decay_mastery_factor + decay_base))
    "decay_mastery_factor": 30,
    "decay_base": 5,
    # 熟练度状态机
    "high_score_threshold": 7,   # 主观分 ≥ 此值视为「高分/自信」
    "kill_streak": 2,            # 连续高分答对达到此次数才「已击杀」
    # EF 更新
    "ef_cold_attempts": 3,       # 复习次数（含本次）< 此值时冻结 EF（冷启动）
    "ef_up": 0.15,               # 高分答对 EF 增量
    "ef_down": 0.2,              # 答错 EF 减量
    # 调度优先级：priority = (1-decayed)×(eff_diff/10) + (days/days_divisor)×days_weight
    "priority_days_divisor": 60,
    "priority_days_weight": 0.3,
    "attack_bonus": 0.5,             # 待攻克且低熟练度的额外加成
    "attack_mastery_threshold": 0.3,
    # SM-2 折中
    "proficiency_factor": SM2_PROFICIENCY_CORRECT_FACTOR,
    # Leech（顽固题）检测
    "leech_fail_threshold": 4,   # 历史累计答错次数 ≥ 此值标记为 leech
    "leech_priority_bonus": 0.4,  # leech 在熟练度列表的优先级加成
}

_TUNING_CACHE = {}


def load_tuning(vault: str) -> dict:
    """读取合并后的可调参数（带进程内缓存）。config 改动后由 save_config 失效缓存。"""
    key = os.path.abspath(vault)
    cached = _TUNING_CACHE.get(key)
    if cached is not None:
        return cached
    merged = dict(DEFAULT_TUNING)
    cfg = load_config(vault)
    user = cfg.get("tuning")
    if isinstance(user, dict):
        for k, v in user.items():
            if k in merged and isinstance(v, (int, float)):
                merged[k] = v
    _TUNING_CACHE[key] = merged
    return merged


def reset_tuning_cache(vault: str = None) -> None:
    if vault is None:
        _TUNING_CACHE.clear()
    else:
        _TUNING_CACHE.pop(os.path.abspath(vault), None)


def calc_sm2_interval(old_interval: int, repetition: int, ef: float,
                      source: str = "due", proficiency_factor: float = None) -> int:
    """计算 SM-2 下次间隔（天数）。

    source='due'     → 标准 SM-2 全量更新
    source='proficiency' → 答对时乘 0.7 折中系数（答错在外部重置）
    """
    if repetition <= 0:
        new_interval = SM2_DEFAULT_INTERVAL
    elif repetition == 1:
        new_interval = SM2_INTERVAL_AFTER_FIRST
    else:
        new_interval = round(old_interval * max(SM2_EF_MIN, min(SM2_EF_MAX, ef)))

    if source == "proficiency":
        factor = SM2_PROFICIENCY_CORRECT_FACTOR if proficiency_factor is None else proficiency_factor
        new_interval = max(1, round(new_interval * factor))

    return new_interval


def compute_due_date(last_review, interval: int):
    """根据上次复习日期和间隔计算到期日。"""
    if not last_review:
        return datetime.date.today().isoformat()
    dt = parse_date(last_review)
    if not dt:
        return datetime.date.today().isoformat()
    return (dt + datetime.timedelta(days=interval)).isoformat()


def is_due(due_date: str, today=None) -> bool:
    """判断题目是否到期（Due_Date ≤ 今天）。"""
    if not due_date:
        return True
    today = today or datetime.date.today()
    dt = parse_date(due_date)
    if not dt:
        return True
    return dt <= today


def resolve_sm2_fields(row: dict) -> dict:
    """为缺少 SM-2 字段的旧数据行填充默认值。"""
    if "Interval" not in row or not row.get("Interval"):
        row["Interval"] = "0"
    if "Due_Date" not in row or not row.get("Due_Date"):
        last = row.get("Last_Review", "")
        if last:
            row["Due_Date"] = last
        else:
            row["Due_Date"] = datetime.date.today().isoformat()
    if "Repetition" not in row or not row.get("Repetition"):
        row["Repetition"] = "0"
    return row
