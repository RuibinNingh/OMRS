"""AI 草稿区（drafts）：主 AI 聊天里建的题目草稿，独立管理，不进 Ledger。

数据全部放在 `错题/.omrs/drafts/`：
- drafts.db          SQLite：images / conv_images / drafts / blocks
- images/<sha256>.<ext>  聊天里贴的图片原件，按内容哈希命名，重复贴图自动合并
- events.jsonl       append-only 事件：image.add / image.transcribe / draft.create（P2 起还有
                      draft.update / draft.crop / draft.commit / draft.discard / image.train）

图片属于对话，不属于草稿：同一张图（同 sha256）在库里只存一份，`conv_images` 记它在某个对话里
叫 IMG-几（每个对话从 1 开始连续编号，重复贴同一张图沿用旧编号）。草稿的块（block）按 `ord`
排序，`section` 为「题目」或「答案」，`kind` 为 `text`（正文）或 `image`（引用某张图，配 `note`
说明位置；框选 `box` 在 P1 恒为空，由 P3 补）。

本模块只实现存储与只读查询（P1-1）；`/api/drafts/*` 的写接口在 P2 加。
"""

import base64
import datetime
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid

from .common import omrs_data_dir, load_config
from . import locking
from .inbox import image_size

DRAFTS_DIR = "drafts"
_LOCK = threading.RLock()

STATUSES = ("cropping", "review", "done", "discarded")
SECTIONS = ("题目", "答案")
KINDS = ("text", "image")
_MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif"}
_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|gif);base64,(.+)$", re.DOTALL)
_IMG_REF_RE = re.compile(r"^IMG-(\d+)$")
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_JPEG_EOI = b"\xff\xd9"


def _complete_jpeg(mime, data):
    """沿 JPEG 标记定位真实结尾，去掉相册尾数据或补结束标记，保留编码像素。"""
    if mime != "image/jpeg" or not data.startswith(b"\xff\xd8"):
        return data
    offset, scan = 2, False
    while offset < len(data):
        if scan:
            offset = data.find(b"\xff", offset)
            if offset < 0:
                return data + _JPEG_EOI
        if data[offset] != 0xff:
            return data
        while offset < len(data) and data[offset] == 0xff:
            offset += 1
        if offset == len(data):
            return data + b"\xd9" if scan else data
        marker = data[offset]
        offset += 1
        if marker == 0xd9:
            return data[:offset]
        if scan and (marker == 0 or 0xd0 <= marker <= 0xd7):
            continue
        if marker == 1:
            continue
        if marker in (0, 0xd8) or offset + 2 > len(data):
            return data
        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            return data
        scan = marker == 0xda or (scan and marker == 0xdc)
        offset += length
    if scan:
        return data + _JPEG_EOI
    return data


class DraftError(ValueError):
    """草稿写接口的稳定错误码。"""

    def __init__(self, message, status=400, code="invalid", current_revision=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.current_revision = current_revision


# ────────────────────────── 路径 / 时间 / 工具 ──────────────────────────

def drafts_dir(vault):
    path = os.path.join(omrs_data_dir(vault), DRAFTS_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def images_dir(vault):
    path = os.path.join(drafts_dir(vault), "images")
    os.makedirs(path, exist_ok=True)
    return path


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _new_draft_id():
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    return f"DR-{stamp}-{uuid.uuid4().hex[:6]}"


def _loads(text, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def _log(vault, event, payload):
    """append-only 事件流。"""
    record = {"ts": _now(), "event": event, **payload}
    path = os.path.join(drafts_dir(vault), "events.jsonl")
    with locking.write_lock(), _LOCK:
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


# ────────────────────────── 存储 ──────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
  sha256 TEXT PRIMARY KEY, file TEXT, mime TEXT, width INTEGER, height INTEGER, bytes INTEGER,
  created_at TEXT, transcript TEXT, transcript_model TEXT, train INTEGER, inbox_item_id TEXT
);
CREATE TABLE IF NOT EXISTS conv_images (
  conversation_id TEXT, n INTEGER, sha256 TEXT, run_id TEXT, created_at TEXT,
  PRIMARY KEY (conversation_id, n)
);
CREATE INDEX IF NOT EXISTS conv_images_sha ON conv_images(conversation_id, sha256);
CREATE TABLE IF NOT EXISTS drafts (
  id TEXT PRIMARY KEY, status TEXT, conversation_id TEXT, run_id TEXT, tool_call_id TEXT,
  subject TEXT, category TEXT, knowledge_points TEXT, difficulty INTEGER, labels TEXT,
  cause TEXT, cause_statement TEXT, note TEXT, uid TEXT, question_id TEXT,
  created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS drafts_conv ON drafts(conversation_id);
CREATE TABLE IF NOT EXISTS blocks (
  id TEXT PRIMARY KEY, draft_id TEXT, section TEXT, ord INTEGER, kind TEXT, text TEXT,
  image_sha TEXT, x REAL, y REAL, w REAL, h REAL, box_origin TEXT, ai_box TEXT, note TEXT
);
CREATE INDEX IF NOT EXISTS blocks_draft ON blocks(draft_id);
CREATE TABLE IF NOT EXISTS draft_images (
  draft_id TEXT NOT NULL, image_sha TEXT NOT NULL, ord INTEGER NOT NULL,
  PRIMARY KEY (draft_id, image_sha)
);
CREATE INDEX IF NOT EXISTS draft_images_sha ON draft_images(image_sha);
CREATE TABLE IF NOT EXISTS commit_operations (
  draft_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, uid TEXT NOT NULL,
  question_id TEXT NOT NULL, file_path TEXT NOT NULL, phase TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT 'api', result_json TEXT, artifacts_json TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS training_tasks (
  id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, image_sha TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', error TEXT, created_at TEXT, updated_at TEXT,
  manual_override INTEGER NOT NULL DEFAULT 0, force_crop INTEGER NOT NULL DEFAULT 0,
  UNIQUE(draft_id,image_sha)
);
CREATE TABLE IF NOT EXISTS training_boxes (
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL, section TEXT NOT NULL, ord INTEGER NOT NULL,
  x REAL NOT NULL,y REAL NOT NULL,w REAL NOT NULL,h REAL NOT NULL,
  box_origin TEXT NOT NULL,ai_box TEXT,source_block_id TEXT
);
CREATE INDEX IF NOT EXISTS training_boxes_task ON training_boxes(task_id);
CREATE TABLE IF NOT EXISTS draft_jobs (
  id TEXT PRIMARY KEY,draft_id TEXT NOT NULL,type TEXT NOT NULL,status TEXT NOT NULL,
  revision INTEGER NOT NULL,snapshot_json TEXT,processed INTEGER NOT NULL,total INTEGER NOT NULL,
  result_json TEXT,errors_json TEXT,created_at TEXT,updated_at TEXT
);
CREATE INDEX IF NOT EXISTS draft_jobs_draft ON draft_jobs(draft_id,created_at);
CREATE TABLE IF NOT EXISTS cleanup_candidates (image_sha TEXT PRIMARY KEY,marked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS draft_manual_edits (
  draft_id TEXT NOT NULL, target TEXT NOT NULL, PRIMARY KEY(draft_id,target)
);
"""


def connect(vault):
    path = os.path.join(drafts_dir(vault), "drafts.db")
    db = sqlite3.connect(path, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(_SCHEMA)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(drafts)")}
    if "revision" not in cols:
        db.execute("ALTER TABLE drafts ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
    if "sources_complete" not in cols:
        db.execute("ALTER TABLE drafts ADD COLUMN sources_complete INTEGER NOT NULL DEFAULT 0")
    if "cleaned_at" not in cols:
        db.execute("ALTER TABLE drafts ADD COLUMN cleaned_at TEXT")
    op_cols = {r["name"] for r in db.execute("PRAGMA table_info(commit_operations)")}
    if "artifacts_json" not in op_cols:
        db.execute("ALTER TABLE commit_operations ADD COLUMN artifacts_json TEXT")
    task_cols = {r["name"] for r in db.execute("PRAGMA table_info(training_tasks)")}
    if "manual_override" not in task_cols:
        db.execute("ALTER TABLE training_tasks ADD COLUMN manual_override INTEGER NOT NULL DEFAULT 0")
    if "force_crop" not in task_cols:
        db.execute("ALTER TABLE training_tasks ADD COLUMN force_crop INTEGER NOT NULL DEFAULT 0")
    db.commit()
    return db


# ────────────────────────── 图片 ──────────────────────────

def _decode_image_data_url(data_url):
    """校验并解码 `data:image/(png|jpeg|gif);base64,...`。返回 (mime, width, height, bytes)。"""
    if not isinstance(data_url, str) or not data_url:
        raise ValueError("缺少图片数据")
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise ValueError("图片格式不支持，只接受 PNG / JPEG / GIF 的 data URL")
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except Exception:
        raise ValueError("图片数据不是合法的 base64")
    if not data:
        raise ValueError("图片数据为空")
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError(f"图片超过 {_MAX_IMAGE_BYTES // (1024 * 1024)}MB 限制")
    try:
        mime, width, height = image_size(data)
    except ValueError:
        raise ValueError("无法识别图片尺寸，可能不是有效的 PNG / JPEG / GIF")
    data = _complete_jpeg(mime, data)
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError(f"图片超过 {_MAX_IMAGE_BYTES // (1024 * 1024)}MB 限制")
    return mime, width, height, data


def add_image(vault, data_url, conversation_id, run_id):
    """存一张聊天贴的图，按对话编号 IMG-n；同对话内同一张图（同 sha256）沿用旧编号。"""
    if not conversation_id:
        raise ValueError("缺少 conversation_id")
    mime, width, height, data = _decode_image_data_url(data_url)
    sha = hashlib.sha256(data).hexdigest()
    now = _now()
    with locking.write_lock(), _LOCK:
        db = connect(vault)
        try:
            existing_conv = db.execute(
                "SELECT n FROM conv_images WHERE conversation_id=? AND sha256=?",
                (conversation_id, sha)).fetchone()
            if existing_conv:
                n = existing_conv["n"]
            else:
                row = db.execute(
                    "SELECT MAX(n) AS mx FROM conv_images WHERE conversation_id=?",
                    (conversation_id,)).fetchone()
                n = int(row["mx"] or 0) + 1
                db.execute(
                    "INSERT INTO conv_images (conversation_id, n, sha256, run_id, created_at) VALUES (?,?,?,?,?)",
                    (conversation_id, n, sha, run_id, now))
            img_row = db.execute("SELECT sha256 FROM images WHERE sha256=?", (sha,)).fetchone()
            if not img_row:
                ext = _MIME_EXT.get(mime, "png")
                path = os.path.join(images_dir(vault), f"{sha}.{ext}")
                if not os.path.exists(path):
                    with open(path, "wb") as file:
                        file.write(data)
                db.execute(
                    "INSERT INTO images (sha256, file, mime, width, height, bytes, created_at, transcript, "
                    "transcript_model, train, inbox_item_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (sha, os.path.basename(path), mime, width, height, len(data), now, None, None, None, None))
            db.commit()
        finally:
            db.close()
    _log(vault, "image.add", {"conversation_id": conversation_id, "run_id": run_id, "sha256": sha,
                              "n": n, "ref": f"IMG-{n}", "mime": mime, "width": width, "height": height,
                              "bytes": len(data)})
    return {"sha256": sha, "n": n, "ref": f"IMG-{n}", "width": width, "height": height, "mime": mime,
            "bytes": len(data)}


def resolve_image(vault, conversation_id, ref):
    """`"IMG-3"` → 本对话里那张图的信息；找不到抛 ValueError。"""
    match = _IMG_REF_RE.match(str(ref or "").strip())
    db = connect(vault)
    try:
        row = None
        if match:
            n = int(match.group(1))
            row = db.execute(
                "SELECT ci.n AS n, ci.sha256 AS sha256, ci.run_id AS run_id, i.mime AS mime, i.width AS width, "
                "i.height AS height, i.bytes AS bytes FROM conv_images ci JOIN images i ON i.sha256=ci.sha256 "
                "WHERE ci.conversation_id=? AND ci.n=?", (conversation_id, n)).fetchone()
    finally:
        db.close()
    if not row:
        raise ValueError(f"本对话里没有 {ref}")
    return {"sha256": row["sha256"], "n": row["n"], "ref": f"IMG-{row['n']}", "mime": row["mime"],
            "width": row["width"], "height": row["height"], "bytes": row["bytes"], "run_id": row["run_id"]}


def conversation_refs(vault, conversation_id):
    """本对话里全部图片的 {sha256: "IMG-n"}（同一张图只有一个编号）。"""
    db = connect(vault)
    try:
        rows = db.execute("SELECT n, sha256 FROM conv_images WHERE conversation_id=? ORDER BY n",
                          (conversation_id,)).fetchall()
    finally:
        db.close()
    return {row["sha256"]: f"IMG-{row['n']}" for row in rows}

def image_path(vault, sha):
    """图片原件的磁盘路径；sha 未知或文件缺失时抛 ValueError。"""
    db = connect(vault)
    try:
        row = db.execute("SELECT mime FROM images WHERE sha256=?", (sha,)).fetchone()
    finally:
        db.close()
    if not row:
        raise ValueError(f"图片不存在：{sha}")
    path = os.path.join(images_dir(vault), f"{sha}.{_MIME_EXT.get(row['mime'], 'png')}")
    if not os.path.exists(path):
        raise ValueError(f"图片文件缺失：{sha}")
    return path


def image_data_url(vault, sha):
    db = connect(vault)
    try:
        row = db.execute("SELECT mime FROM images WHERE sha256=?", (sha,)).fetchone()
    finally:
        db.close()
    if not row:
        raise ValueError(f"图片不存在：{sha}")
    path = image_path(vault, sha)
    with open(path, "rb") as file:
        data = file.read()
    return f"data:{row['mime']};base64," + base64.b64encode(_complete_jpeg(row['mime'], data)).decode("ascii")


def get_transcript(vault, sha, model):
    """按 sha256 + 模型名取缓存的转述；没有缓存或模型不一致返回 None。"""
    db = connect(vault)
    try:
        row = db.execute("SELECT transcript, transcript_model FROM images WHERE sha256=?", (sha,)).fetchone()
    finally:
        db.close()
    if not row or not row["transcript"] or row["transcript_model"] != model:
        return None
    return _loads(row["transcript"], None)


def set_transcript(vault, sha, model, transcript):
    """写入转述缓存（单槽：新模型覆盖旧的）。"""
    with locking.write_lock(), _LOCK:
        db = connect(vault)
        try:
            row = db.execute("SELECT sha256 FROM images WHERE sha256=?", (sha,)).fetchone()
            if not row:
                raise ValueError(f"图片不存在：{sha}")
            db.execute("UPDATE images SET transcript=?, transcript_model=? WHERE sha256=?",
                       (json.dumps(transcript, ensure_ascii=False), model, sha))
            db.commit()
        finally:
            db.close()
    _log(vault, "image.transcribe", {"sha256": sha, "model": model})
    return transcript


# ────────────────────────── 草稿 ──────────────────────────

def _row_block(row):
    box = None
    if row["x"] is not None:
        box = {"x": row["x"], "y": row["y"], "w": row["w"], "h": row["h"]}
    return {
        "id": row["id"], "section": row["section"], "ord": row["ord"], "kind": row["kind"],
        "text": row["text"], "image_sha": row["image_sha"], "box": box,
        "box_origin": row["box_origin"], "ai_box": _loads(row["ai_box"], None), "note": row["note"] or "",
    }


def _row_draft(row, blocks):
    return {
        "id": row["id"], "status": row["status"], "conversation_id": row["conversation_id"],
        "revision": row["revision"], "sources_complete": bool(row["sources_complete"]),
        "run_id": row["run_id"], "tool_call_id": row["tool_call_id"], "subject": row["subject"],
        "category": row["category"], "knowledge_points": _loads(row["knowledge_points"], []),
        "difficulty": row["difficulty"] if row["difficulty"] is not None else 5,
        "labels": _loads(row["labels"], []), "cause": row["cause"] or "",
        "cause_statement": row["cause_statement"] or "", "note": row["note"] or "",
        "uid": row["uid"], "question_id": row["question_id"],
        "created_at": row["created_at"], "updated_at": row["updated_at"], "blocks": blocks,
    }


def _question_available(vault, row):
    if row["status"] != "done" or not row["question_id"]:
        return None
    from .ledger import connect as ledger_connect
    ledger = ledger_connect(vault)
    try:
        question = ledger.execute("SELECT file_path,archived FROM question_projection WHERE question_id=?",
                                  (row["question_id"],)).fetchone()
    finally:
        ledger.close()
    return bool(question and not question["archived"] and
                os.path.isfile(os.path.join(vault, question["file_path"])))


def _draft_blocks(db, draft_id):
    return [_row_block(r) for r in db.execute(
        "SELECT * FROM blocks WHERE draft_id=? ORDER BY ord", (draft_id,))]


def _source_view(vault, db, row, blocks):
    """旧草稿只从精确工具调用或图片块恢复来源，绝不猜整个对话。"""
    conv = row["conversation_id"]
    candidates = db.execute(
        "SELECT ci.n,ci.sha256,i.width,i.height,i.mime,i.train,i.inbox_item_id "
        "FROM conv_images ci JOIN images i ON i.sha256=ci.sha256 "
        "WHERE ci.conversation_id=? ORDER BY ci.n", (conv,)).fetchall()
    by_sha = {r["sha256"]: r for r in candidates}
    by_ref = {f"IMG-{r['n']}": r["sha256"] for r in candidates}
    if row["cleaned_at"]:
        return [], bool(row["sources_complete"]), [
            {"sha256": r["sha256"], "ref": f"IMG-{r['n']}", "width": r["width"],
             "height": r["height"], "mime": r["mime"], "train": bool(r["train"]),
             "inbox_item_id": r["inbox_item_id"]} for r in candidates]
    associated = [r["image_sha"] for r in db.execute(
        "SELECT image_sha FROM draft_images WHERE draft_id=? ORDER BY ord", (row["id"],))]
    complete = bool(row["sources_complete"])
    if not complete and row["run_id"] and row["tool_call_id"]:
        agent_db = os.path.join(omrs_data_dir(vault), "agent.db")
        if os.path.isfile(agent_db):
            try:
                agent = sqlite3.connect(f"file:{agent_db}?mode=ro", uri=True)
                try:
                    call = agent.execute(
                        "SELECT args_json FROM tool_calls WHERE run_id=? AND call_id=? AND name='create_draft'",
                        (row["run_id"], row["tool_call_id"])).fetchone()
                finally:
                    agent.close()
                if call:
                    refs = _loads(call[0], {}).get("images")
                    if isinstance(refs, list) and all(isinstance(ref, str) and ref in by_ref for ref in refs):
                        exact = list(dict.fromkeys(by_ref[ref] for ref in refs))
                        if all(b["image_sha"] in exact for b in blocks if b["image_sha"]):
                            db.execute("DELETE FROM draft_images WHERE draft_id=?", (row["id"],))
                            db.executemany("INSERT INTO draft_images(draft_id,image_sha,ord) VALUES(?,?,?)",
                                           [(row["id"], sha, i) for i, sha in enumerate(exact)])
                            db.execute("UPDATE drafts SET sources_complete=1 WHERE id=?", (row["id"],))
                            db.commit()
                            associated, complete = exact, True
            except (sqlite3.Error, OSError):
                pass
    for sha in (b["image_sha"] for b in blocks if b["image_sha"]):
        if sha not in associated:
            associated.append(sha)
            db.execute("INSERT OR IGNORE INTO draft_images(draft_id,image_sha,ord) VALUES(?,?,?)",
                       (row["id"], sha, len(associated) - 1))
            db.commit()
    from .draft_training import sync_tasks
    sync_tasks(db, row["id"])
    db.commit()

    def view(r):
        return {"sha256": r["sha256"], "ref": f"IMG-{r['n']}", "width": r["width"],
                "height": r["height"], "mime": r["mime"], "train": bool(r["train"]),
                "inbox_item_id": r["inbox_item_id"]}

    sources = [view(by_sha[sha]) for sha in associated if sha in by_sha]
    conversation = [view(r) for r in candidates]
    return sources, complete, conversation


def create_draft(vault, data, origin=None):
    """建一份草稿。`data`：subject/category/knowledge_points/blocks/cause/cause_statement；
    `origin`：conversation_id/run_id/tool_call_id。校验失败抛 ValueError（中文），不建行。"""
    data = data or {}
    origin = origin or {}
    subject = str(data.get("subject") or "").strip()
    category = str(data.get("category") or "").strip()
    if not subject:
        raise ValueError("科目不能为空")
    if not category:
        raise ValueError("分类不能为空")
    knowledge_points = [str(p).strip() for p in (data.get("knowledge_points") or []) if str(p).strip()]
    if len(knowledge_points) > 8:
        raise ValueError("知识点最多 8 个")
    raw_blocks = data.get("blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ValueError("草稿至少要有一个块")
    cause = str(data.get("cause") or "").strip()
    cause_statement = str(data.get("cause_statement") or "").strip()
    if cause and not cause_statement:
        raise ValueError("错因只能用用户说过的话：cause_statement 不能为空")
    labels = [str(v).strip() for v in (data.get("labels") or []) if str(v).strip()]
    source_images = data.get("source_images")
    if source_images is not None and (not isinstance(source_images, list) or
                                      any(not isinstance(v, str) for v in source_images)):
        raise ValueError("source_images 必须是图片 SHA 数组")

    with locking.write_lock(), _LOCK:
        db = connect(vault)
        try:
            blocks = []
            for index, raw in enumerate(raw_blocks):
                if not isinstance(raw, dict):
                    raise ValueError(f"第 {index + 1} 块格式不对")
                section = raw.get("section")
                if section not in SECTIONS:
                    raise ValueError(f"第 {index + 1} 块的 section 必须是「题目」或「答案」")
                kind = raw.get("kind")
                if kind not in KINDS:
                    raise ValueError(f"第 {index + 1} 块的 kind 必须是 text 或 image")
                note = str(raw.get("note") or "").strip()
                if kind == "text":
                    text = str(raw.get("text") or "").strip()
                    if not text:
                        raise ValueError(f"第 {index + 1} 块是文字块但没有文本")
                    blocks.append({"section": section, "ord": index, "kind": kind, "text": text,
                                   "image_sha": None, "note": note})
                else:
                    image_sha = str(raw.get("image_sha") or "").strip()
                    if not image_sha:
                        raise ValueError(f"第 {index + 1} 块是图片块但没有 image_sha")
                    exists = db.execute("SELECT 1 FROM images WHERE sha256=?", (image_sha,)).fetchone()
                    if not exists:
                        raise ValueError(f"第 {index + 1} 块引用的图片不存在：{image_sha}")
                    if origin.get("conversation_id") and not db.execute(
                            "SELECT 1 FROM conv_images WHERE conversation_id=? AND sha256=?",
                            (origin["conversation_id"], image_sha)).fetchone():
                        raise ValueError(f"第 {index + 1} 块引用的图片不属于本对话")
                    blocks.append({"section": section, "ord": index, "kind": kind, "text": None,
                                   "image_sha": image_sha, "note": note})
            if not any(b["section"] == "题目" for b in blocks):
                raise ValueError("草稿至少要有一个题目块")

            if source_images is None:
                source_images = list(dict.fromkeys(b["image_sha"] for b in blocks if b["image_sha"]))
                sources_complete = False
            else:
                source_images = list(dict.fromkeys(source_images))
                sources_complete = True
            for sha in source_images:
                if not db.execute("SELECT 1 FROM conv_images WHERE conversation_id=? AND sha256=?",
                                  (origin.get("conversation_id"), sha)).fetchone():
                    raise ValueError(f"来源图片不属于本对话：{sha}")
            if any(b["image_sha"] and b["image_sha"] not in source_images for b in blocks):
                if sources_complete:
                    raise ValueError("图片区块引用了来源列表外的图片")
                source_images.extend(b["image_sha"] for b in blocks
                                     if b["image_sha"] and b["image_sha"] not in source_images)

            status = "cropping" if any(b["kind"] == "image" for b in blocks) else "review"
            draft_id = _new_draft_id()
            now = _now()
            db.execute(
                "INSERT INTO drafts (id, status, conversation_id, run_id, tool_call_id, subject, category, "
                "knowledge_points, difficulty, labels, cause, cause_statement, note, uid, question_id, "
                "created_at, updated_at, revision, sources_complete) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (draft_id, status, origin.get("conversation_id"), origin.get("run_id"),
                 origin.get("tool_call_id"), subject, category, json.dumps(knowledge_points, ensure_ascii=False),
                 5, json.dumps(labels, ensure_ascii=False), cause, cause_statement, "", None, None, now, now,
                 1, int(sources_complete)))
            for index, sha in enumerate(source_images):
                db.execute("INSERT INTO draft_images(draft_id,image_sha,ord) VALUES(?,?,?)",
                           (draft_id, sha, index))
                db.execute("UPDATE images SET train=? WHERE sha256=? AND train IS NULL",
                           (int(bool(load_config(vault).get("draft_train_default", False))), sha))
            from .draft_training import sync_tasks
            force_crop = bool(source_images and all(b["kind"] == "text" for b in blocks) and
                              load_config(vault).get("draft_force_crop", False))
            sync_tasks(db, draft_id, force_crop=force_crop)
            for block in blocks:
                db.execute(
                    "INSERT INTO blocks (id, draft_id, section, ord, kind, text, image_sha, x, y, w, h, "
                    "box_origin, ai_box, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"blk_{uuid.uuid4().hex[:10]}", draft_id, block["section"], block["ord"], block["kind"],
                     block["text"], block["image_sha"], None, None, None, None, None, None, block["note"]))
            db.commit()
        finally:
            db.close()
    _log(vault, "draft.create", {"draft_id": draft_id, "conversation_id": origin.get("conversation_id"),
                                 "run_id": origin.get("run_id"), "tool_call_id": origin.get("tool_call_id"),
                                 "subject": subject, "category": category, "status": status,
                                 "blocks": len(blocks)})
    try:
        from .draft_training import cleanup
        cleanup(vault)
    except Exception as exc:
        _log(vault, "draft.cleanup.error", {"draft_id": draft_id, "error": str(exc)})
    return get_draft(vault, draft_id)


def get_draft(vault, draft_id):
    from .draft_jobs import recover_orphan_jobs
    with locking.write_lock(), _LOCK:
        recover_orphan_jobs(vault, draft_id)
        db = connect(vault)
        try:
            row = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if not row:
                raise ValueError(f"没有这份草稿：{draft_id}")
            blocks = _draft_blocks(db, draft_id)
            source_images, complete, conversation_images = _source_view(vault, db, row, blocks)
            from .draft_training import task_view
            training_tasks = task_view(db, draft_id)
            from .draft_jobs import jobs_for_draft
            jobs = jobs_for_draft(db, draft_id)
        finally:
            db.close()
    return {**_row_draft(row, blocks), "question_available": _question_available(vault, row),
            "source_images": source_images,
            "sources_complete": complete, "conversation_images": conversation_images,
            "training_tasks": training_tasks, "jobs": jobs}


def list_drafts(vault, status=None, conversation_id=None, limit=50):
    """默认排除 discarded（含 done）；按 created_at 倒序。"""
    try:
        limit = max(1, min(int(limit or 50), 500))
    except (TypeError, ValueError):
        limit = 50
    clauses, params = [], []
    if status == "pending":
        clauses.append("status IN ('cropping','review')")
    elif status:
        clauses.append("status=?")
        params.append(status)
    else:
        clauses.append("status!='discarded'")
    if conversation_id:
        clauses.append("conversation_id=?")
        params.append(conversation_id)
    where = " AND ".join(clauses)
    with locking.write_lock(), _LOCK:
        db = connect(vault)
        try:
            rows = db.execute(
                f"SELECT * FROM drafts WHERE {where} ORDER BY created_at DESC LIMIT ?",
                (*params, limit)).fetchall()
            return [{**_row_draft(row, _draft_blocks(db, row["id"])),
                     "source_images": _source_view(vault, db, row, _draft_blocks(db, row["id"]))[0]}
                    for row in rows]
        finally:
            db.close()


def counts(vault):
    db = connect(vault)
    try:
        rows = db.execute("SELECT status, COUNT(*) AS n FROM drafts GROUP BY status").fetchall()
    finally:
        db.close()
    result = {"cropping": 0, "review": 0, "done": 0, "discarded": 0}
    for row in rows:
        if row["status"] in result:
            result[row["status"]] = row["n"]
    return result


def update_draft(vault, draft_id, revision, fields, blocks, source_images=None):
    from .draft_write import update_draft as run
    return run(vault, draft_id, revision, fields, blocks, source_images)


def patch_draft(vault, draft_id, revision, fields, block_patches, actor):
    from .draft_write import patch_draft as run
    return run(vault, draft_id, revision, fields, block_patches, actor)


def discard_draft(vault, draft_id, revision):
    from .draft_write import discard_draft as run
    return run(vault, draft_id, revision)


def commit_draft(vault, draft_id, revision, crops=None, actor="api"):
    from .draft_write import commit_draft as run
    result = run(vault, draft_id, revision, crops, actor)
    from .draft_training import register_ready
    try:
        result["training"] = register_ready(vault, draft_id)
    except Exception as exc:
        result["training"] = {"status": "partial", "registered": [],
                              "failed": [{"sha": None, "error": str(exc)}], "pending": []}
    result["draft"] = get_draft(vault, draft_id)
    return result


def set_boxes(vault, draft_id, revision, blocks=None, training_boxes=None):
    from .draft_write import set_boxes as run
    return run(vault, draft_id, revision, blocks, training_boxes)


def start_extract(vault, draft_id, revision, block_ids, crops=None):
    from .draft_jobs import start_extract as run
    return run(vault, draft_id, revision, block_ids, crops)


def start_detect(vault, draft_id, revision, sha=None):
    from .draft_detect import start_detect as run
    return run(vault, draft_id, revision, sha)


def set_image_training(vault, draft_id, revision, sha, enabled):
    from .draft_training import set_image_training as run
    return run(vault, draft_id, revision, sha, enabled)


def get_job(vault, job_id):
    from .draft_jobs import get_job as run
    return run(vault, job_id)


def cleanup(vault):
    from .draft_training import cleanup as run
    return run(vault)
