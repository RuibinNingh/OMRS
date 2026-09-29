"""对话附图：把用户消息里的 ``_images``（IMG-n 引用）按设置展开成模型能读的内容。

- 主 AI 支持图片（``agent_vision``）：最近 MAX_VISION_IMAGES 张以 ``image_url`` 内容块发给主模型，更早的换成占位文字；
- 不支持：逐张调转述模型（``ai_assist.transcribe_image``，按 sha256 + 模型缓存），把转述文字拼进用户消息。

只改送给模型的副本，``agent.db`` 里的消息不变。图片本体与转述缓存在 ``omrs/drafts.py``。见 AI/agent.md「附图」。
"""
import time

from .. import drafts
from ..ai_assist import _ai_config, transcribe_image

MAX_VISION_IMAGES = 4
TRANSCRIPT_CAP = 3000
ROLE_NAMES = {"question": "题目", "answer": "答案", "other": "其他"}


def render_transcript(ref, transcript):
    """把转述 JSON 渲染成给主模型读的文字，截断到 TRANSCRIPT_CAP 字。"""
    lines = [f"[{ref} 转述]"]
    if transcript.get("summary"):
        lines.append("概要：" + str(transcript["summary"]).strip())
    if transcript.get("layout"):
        lines.append("版面：" + str(transcript["layout"]).strip())
    for block in transcript.get("blocks") or []:
        role = ROLE_NAMES.get(block.get("role"), "其他")
        how = "可转文字" if block.get("convertible", True) else "需留图：" + (str(block.get("reason") or "").strip() or "含图形")
        lines.append(f"- {role}（{how}）：{str(block.get('text') or '').strip()}")
    text = "\n".join(lines)
    return text if len(text) <= TRANSCRIPT_CAP else text[:TRANSCRIPT_CAP] + "…（转述过长，已截断；需要细节时调 describe_image）"


def _transcript_for(vault, row, model, emit, abort, run_id=None):
    cached = drafts.get_transcript(vault, row["sha256"], model)
    if cached is not None:
        return cached, None
    if abort is not None and abort.is_set():
        return None, "运行已中止"
    emit("image.transcribe", {"ref": row["ref"], "sha": row["sha256"]})
    started = time.monotonic()
    try:
        def record(usage):
            emit("usage.aux", {"kind": "transcribe", "ref": row["ref"], "request_id":
                 f"{run_id or 'run'}:transcribe:{row['ref']}:{row['sha256']}", "usage": usage})
        options = {"usage_callback": record} if run_id is not None else {}
        transcript = transcribe_image(vault, drafts.image_data_url(vault, row["sha256"]), **options)
    except Exception as exc:  # noqa: BLE001 - 转述失败不终止运行，交给主模型自行决定
        emit("image.transcribed", {"ref": row["ref"], "ok": False, "ms": int((time.monotonic() - started) * 1000),
                                   "error": str(exc)})
        return None, str(exc)
    drafts.set_transcript(vault, row["sha256"], model, transcript)
    emit("image.transcribed", {"ref": row["ref"], "ok": True, "ms": int((time.monotonic() - started) * 1000)})
    return transcript, None


def expand_images(vault, conv_id, stored, vision, emit, abort=None, run_id=None):
    """返回 stored 的副本：带 ``_images`` 的用户消息按模式展开。无图消息原样返回（同一对象）。"""
    if not any(m.get("role") == "user" and m.get("_images") for m in stored):
        return stored
    rows = {}
    for msg in stored:
        for ref in msg.get("_images") or [] if msg.get("role") == "user" else []:
            if ref not in rows:
                try:
                    rows[ref] = {**drafts.resolve_image(vault, conv_id, ref), "ref": ref}
                except ValueError:
                    rows[ref] = None
    out = list(stored)
    if vision:
        budget = MAX_VISION_IMAGES
        for i in range(len(out) - 1, -1, -1):
            msg = out[i]
            if msg.get("role") != "user" or not msg.get("_images"):
                continue
            chunks = []
            for ref in reversed(msg["_images"]):  # 名额从最新的图往前分，同一条消息里也先省略靠前的
                row = rows.get(ref)
                if row is None:
                    chunks.append([{"type": "text", "text": f"[{ref} 图片已不存在]"}])
                elif budget > 0:
                    budget -= 1
                    chunks.append([{"type": "text", "text": f"[{ref}]"},
                                   {"type": "image_url", "image_url": {"url": drafts.image_data_url(vault, row["sha256"])}}])
                else:
                    chunks.append([{"type": "text", "text": f"[{ref} 已省略，需要时调 describe_image]"}])
            parts = [{"type": "text", "text": msg.get("content") or "（只发了图片）"}]
            for chunk in reversed(chunks):
                parts.extend(chunk)
            out[i] = {**msg, "content": parts}
        return out
    model = _ai_config(vault, "extract")[2]
    for i, msg in enumerate(out):
        if msg.get("role") != "user" or not msg.get("_images"):
            continue
        chunks = [msg.get("content") or "（只发了图片）"]
        for ref in msg["_images"]:
            row = rows.get(ref)
            if row is None:
                chunks.append(f"[{ref} 图片已不存在]")
                continue
            transcript, error = _transcript_for(vault, row, model, emit, abort, run_id)
            if transcript is None:
                chunks.append(f"[{ref} 转述失败：{error}。可调 describe_image 再试]")
            else:
                chunks.append(render_transcript(ref, transcript))
        out[i] = {**msg, "content": "\n\n".join(chunks)}
    return out
