"""系统运行记录：独立于学习 Ledger 的 MCP 调用生命周期与脱敏摘要。"""
import datetime
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import uuid
from contextlib import closing

from .common import omrs_data_dir

_LOCK = threading.RLock()
TITLES = {
    "list_taxonomy": "读取科目与分类", "search_questions": "搜索题目",
    "get_question": "读取题目", "get_overview": "读取科目概况",
    "get_question_image": "读取题图",
    "get_recommendations": "查询复习推荐", "list_sessions": "读取练习列表",
    "get_session": "读取练习详情", "list_drafts": "读取草稿列表",
    "get_draft": "读取草稿", "create_draft": "创建待审核草稿",
    "get_questions": "批量读取题目", "get_question_content": "读取完整正文",
    "get_draft_image": "读取草稿原图", "get_question_history": "读取单题历史",
    "get_learning_history": "读取学习时间线",
    "get_analytics": "读取详细分析", "list_reports": "读取报告列表",
    "get_report": "读取报告源码", "create_report": "保存分析报告",
    "update_draft": "修订待审核草稿",
}
ERRORS = {
    "revision_conflict": "目标版本已变化，请重新读取。",
    "state_conflict": "目标已结束，不能执行此操作。",
    "operation_pending": "目标存在未恢复的操作。",
    "invalid": "补丁格式不合法。",
    "request_conflict": "同一请求编号的内容不同，请使用新编号。",
    "not_found": "目标不存在或不可读取。", "content_conflict": "正文已变化，请重新读取。",
    "forbidden": "所用密钥缺少权限，或在处理期间已失效。",
    "unknown_tool": "此工具未开放。", "invalid_arguments": "参数不符合工具要求。",
    "invalid_request": "请求内容不合法，请检查分类、原图或幂等请求。",
    "write_busy": "写入繁忙，请稍后重试。", "internal_error": "执行失败，请稍后重试。",
    "interrupted": "调用已中断；请核对草稿队列后再决定是否重试。",
}
_TEXT_FIELDS = {"subject", "category", "uid", "session_id", "draft_id", "status", "source", "due_range", "match"}
_NUMBER_FIELDS = {"count", "limit", "page", "page_size", "mastery_min", "mastery_max", "difficulty_min", "difficulty_max",
                  "image_index"}
_PRIVATE = re.compile(r"omrs_mcp_\S+|\bbearer\s+\S+|https?://\S+|data:\S+", re.I)


def path(vault):
    return os.path.join(omrs_data_dir(vault), "runtime.db")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def _safe_text(value):
    if not isinstance(value, str):
        return ""
    return _PRIVATE.sub("[已隐藏]", value[:512]).replace("\x00", "")[:160]


def _safe_number(value):
    return type(value) in (int, float) and abs(value) <= 1e12 and math.isfinite(value)


def argument_summary(arguments):
    """只存选定的筛选值和数量，不存正文、图片、附件、URL 或客户端自由文本。"""
    if not isinstance(arguments, dict):
        return {}
    result = {key: _safe_text(value) for key, value in arguments.items() if key in _TEXT_FIELDS and isinstance(value, str)}
    result.update({key: value for key, value in arguments.items() if key in _NUMBER_FIELDS
                   and _safe_number(value)})
    for field in ("images", "blocks", "keywords", "labels", "knowledge_points"):
        if isinstance(arguments.get(field), list):
            result[f"{field}_count"] = len(arguments[field])
    return result


def result_summary(result):
    """SDK 结果只取有限的标识、状态与计数，绝不保存原始返回内容。"""
    value = result if isinstance(result, dict) else None
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        value = result[1]
    if value is None and isinstance(result, (list, tuple)):
        for item in result:
            text = getattr(item, "text", None)
            if not isinstance(text, str) or len(text) > 1_000_000:
                continue
            try:
                candidate = json.loads(text)
            except ValueError:
                continue
            if isinstance(candidate, dict):
                value = candidate
                break
    if not isinstance(value, dict):
        return {}
    result = {key: _safe_text(value[key]) for key in ("draft_id", "uid", "subject", "status", "session_id")
              if isinstance(value.get(key), str)}
    for key in ("total", "count", "total_questions", "page", "page_size"):
        if _safe_number(value.get(key)):
            result[key] = value[key]
    if isinstance(value.get("reused"), bool):
        result["reused"] = value["reused"]
    for field in ("items", "questions", "sessions", "recommendations", "source_images", "blocks"):
        if isinstance(value.get(field), list):
            result[f"{field}_count"] = len(value[field])
    return result


def _connect(vault, write=False):
    target = path(vault)
    if os.path.islink(target):
        raise ValueError("运行记录路径不允许符号链接")
    if write:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        descriptor = os.open(target, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        db = sqlite3.connect(target, timeout=5)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT NOT NULL UNIQUE, source TEXT NOT NULL,
                    tool TEXT NOT NULL, title TEXT NOT NULL, key_id TEXT NOT NULL,
                    key_name TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                    status TEXT NOT NULL, duration_ms INTEGER,
                    arguments_json TEXT NOT NULL, result_json TEXT NOT NULL DEFAULT '{}',
                    error_code TEXT NOT NULL DEFAULT '', draft_id TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS runtime_draft ON records(draft_id, seq);
                CREATE INDEX IF NOT EXISTS runtime_key ON records(key_id, seq);
            """)
        except BaseException:
            db.close()
            raise
    else:
        db = sqlite3.connect(Path(target).as_uri() + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def begin(vault, tool, arguments, identity=None):
    identity = identity or {}
    tool = tool if tool in TITLES else "unknown_tool"
    with _LOCK, closing(_connect(vault, write=True)) as db:
        row = db.execute("INSERT INTO records(call_id,source,tool,title,key_id,key_name,started_at,status,arguments_json) "
                         "VALUES(?,?,?,?,?,?,?,'running',?)", (
                             uuid.uuid4().hex, "mcp", tool, TITLES.get(tool, "调用未开放工具"),
                             _safe_text(identity.get("key_id")), _safe_text(identity.get("name")),
                             _now(), json.dumps(argument_summary(arguments), ensure_ascii=False)))
        db.commit()
        return row.lastrowid


def finish(vault, seq, duration_ms, result=None, error_code=""):
    summary = result_summary(result) if not error_code else {}
    status = "interrupted" if error_code == "interrupted" else "failure" if error_code else "success"
    with _LOCK, closing(_connect(vault, write=True)) as db:
        db.execute("UPDATE records SET finished_at=?,status=?,duration_ms=?,result_json=?,error_code=?,draft_id=? "
                   "WHERE seq=? AND status='running'", (
                       _now(), status, max(0, int(duration_ms)), json.dumps(summary, ensure_ascii=False),
                       error_code if error_code in ERRORS else "internal_error" if error_code else "",
                       summary.get("draft_id", ""), seq))
        db.commit()


def safely(fn, *args, **kwargs):
    """记录设备故障不能改变已授权领域操作的结果，诊断不输出原始异常。"""
    try:
        return fn(*args, **kwargs)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        logging.getLogger("omrs.runtime").warning("系统运行记录暂时无法写入，请检查存储。")
        return None


def recover_interrupted(vault):
    if not os.path.isfile(path(vault)):
        return 0
    with _LOCK, closing(_connect(vault, write=True)) as db:
        changed = db.execute("UPDATE records SET status='interrupted',finished_at=?,error_code='interrupted' "
                             "WHERE status='running'", (_now(),)).rowcount
        db.commit()
        return changed


def filters(params):
    """两类历史共用有界搜索与 ISO 时间区间；游标仅控制页面，不改变汇总。"""
    result = {}
    for key in ("q", "key_id", "status", "source"):
        value = params.get(key, "")
        if not isinstance(value, str) or len(value) > 200:
            raise ValueError("筛选条件过长或格式不正确")
        result[key] = value.strip()
    if result["source"] not in ("", "mcp") or result["status"] not in ("", "success", "failure", "running", "interrupted"):
        raise ValueError("记录来源或状态不正确")
    for key in ("since", "until"):
        value = params.get(key, "")
        if value:
            try:
                date = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
                if date.tzinfo is None:
                    raise ValueError()
            except (ValueError, AttributeError):
                raise ValueError("筛选时间必须是带时区的 ISO 时间") from None
            result[key] = date.astimezone(datetime.timezone.utc).isoformat()
        else:
            result[key] = ""
    if result["since"] and result["until"] and result["since"] >= result["until"]:
        raise ValueError("筛选开始时间必须早于结束时间")
    return result


def _where(options):
    clauses, values = ["source='mcp'"], []
    for key in ("key_id", "status"):
        if options.get(key):
            clauses.append(f"{key}=?")
            values.append(options[key])
    for field, operator in (("since", ">="), ("until", "<")):
        if options.get(field):
            clauses.append(f"julianday(started_at){operator}julianday(?)")
            values.append(options[field])
    if options.get("q"):
        clauses.append("(title LIKE ? ESCAPE '\\' OR tool LIKE ? ESCAPE '\\' OR key_name LIKE ? ESCAPE '\\' OR arguments_json LIKE ? ESCAPE '\\')")
        query = "%" + options["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        values.extend([query] * 4)
    return " AND ".join(clauses), values


def _row(row, detail=False):
    item = dict(row)
    arguments = json.loads(item.pop("arguments_json"))
    result = json.loads(item.pop("result_json"))
    item["scope_summary"] = " / ".join(str(arguments[key]) for key in ("subject", "category", "uid") if arguments.get(key))
    if item["error_code"]:
        item["summary"] = ERRORS.get(item["error_code"], ERRORS["internal_error"])
    elif item["status"] == "running":
        item["summary"] = "正在处理请求"
    elif item["tool"] == "create_draft":
        item["summary"] = "复用已有草稿" if result.get("reused") else "已创建待审核草稿"
    else:
        count = next((result[key] for key in ("total", "total_questions", "count", "items_count", "questions_count") if key in result), None)
        item["summary"] = f"返回 {count} 项结果" if count is not None else "查询完成"
    if detail:
        item.update(arguments=arguments, result=result)
    return item


def list_records(vault, params):
    options = filters(params)
    try:
        limit = int(params.get("limit", 60))
        cursor = int(params["before_seq"]) if params.get("before_seq") else None
        if not 1 <= limit <= 200 or (cursor is not None and cursor <= 0):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("分页参数不正确") from None
    empty = {"records": [], "has_more": False, "next_before_seq": None,
             "summary": {"total": 0, "success": 0, "failure": 0, "running": 0, "interrupted": 0}, "keys": []}
    if not os.path.isfile(path(vault)):
        return empty
    where, values = _where(options)
    with closing(_connect(vault)) as db:
        # 固定同一读取快照，避免并发调用使本页与汇总自相矛盾。
        db.execute("BEGIN")
        summary = {**empty["summary"], **{row["status"]: row["n"] for row in db.execute(
            f"SELECT status,COUNT(*) AS n FROM records WHERE {where} GROUP BY status", values)}}
        summary["total"] = sum(summary[key] for key in ("success", "failure", "running", "interrupted"))
        cursor_clause = " AND seq<?" if cursor is not None else ""
        rows = db.execute(f"SELECT * FROM records WHERE {where}{cursor_clause} ORDER BY seq DESC LIMIT ?",
                          [*values, *([cursor] if cursor is not None else []), limit + 1]).fetchall()
        keys = [{"key_id": row["key_id"], "name": row["key_name"] or row["key_id"]} for row in db.execute(
            "SELECT key_id,key_name,MAX(seq) FROM records WHERE key_id<>'' GROUP BY key_id ORDER BY key_name")]
    more = len(rows) > limit
    return {"records": [_row(row) for row in rows[:limit]], "summary": summary, "keys": keys,
            "has_more": more, "next_before_seq": rows[limit-1]["seq"] if more else None}


def calls_for_draft(vault, draft_id):
    if not draft_id or not os.path.isfile(path(vault)):
        return []
    with closing(_connect(vault)) as db:
        return [_row(row) for row in db.execute("SELECT * FROM records WHERE draft_id=? ORDER BY seq DESC LIMIT 20", (draft_id,))]


def detail(vault, seq):
    if not os.path.isfile(path(vault)):
        return None
    with closing(_connect(vault)) as db:
        row = db.execute("SELECT * FROM records WHERE seq=?", (seq,)).fetchone()
    if row is None:
        return None
    item = _row(row, detail=True)
    item["related_commits"] = []
    if not item["draft_id"]:
        return item
    from . import drafts
    try:
        draft = drafts.get_draft(vault, item["draft_id"], readonly=True)
        item["draft"] = {"id": draft["id"], "status": draft["status"]}
    except ValueError:
        item["draft"] = {"id": item["draft_id"], "status": "missing"}
    from .ledger import ledger_path
    target = ledger_path(vault)
    if os.path.isfile(target):
        with closing(sqlite3.connect(Path(target).as_uri() + "?mode=ro", uri=True)) as db:
            for seq, commit_id, created_at, payload in db.execute(
                    "SELECT seq,commit_id,created_at,payload_json FROM commits WHERE commit_type='question.create' "
                    "AND json_extract(payload_json,'$._draft.draft_id')=? ORDER BY seq DESC", (item["draft_id"],)):
                question = json.loads(payload).get("question", {})
                item["related_commits"].append({"seq": seq, "commit_id": commit_id, "created_at": created_at,
                                               "title": "审核草稿并入库", "uid": question.get("uid", "")})
    return item
