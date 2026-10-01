"""草稿工具：看图追问、查草稿、建草稿和按版本修订草稿，不进 Ledger。

- describe_image / list_drafts / get_draft：read，自动执行；
- create_draft：rev，自动执行，不写 Ledger，所以不需要确认；工具结果带 ``wrote: True``，循环照样计入写入预算；
  草稿不产生 commit，天然不在按运行撤销的范围里。
- update_draft：rev，按版本和块 ID 修改待审草稿；人工改过的目标只返回建议。

错因规则写在服务端：带 cause 就必须带 cause_statement，且它必须是本对话某条用户消息里的原话。
"""
import re
import unicodedata

from ... import drafts
from ...draft_prepare import merge_answer_text_runs as _merge_answer_text_runs
from ...ai_assist import describe_image as ask_image
from ..config import settings
from ..store import AgentStore

DESCRIBE_CAP = 2000
_SPACE_RE = re.compile(r"\s+")


def _norm(text):
    return _SPACE_RE.sub("", unicodedata.normalize("NFKC", str(text or ""))).lower()


def _user_texts(vault, conv_id):
    out = []
    for msg in AgentStore(vault).messages(conv_id):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            content = "".join(p.get("text") or "" for p in content if isinstance(p, dict))
        out.append(content or "")
    return out


def _preview(draft, n=60):
    text = "".join(b.get("text") or "" for b in draft["blocks"] if b["section"] == "题目" and b["kind"] == "text")
    if not text:
        text = "（题目是图片）"
    return text[:n] + ("…" if len(text) > n else "")


def _summary(draft):
    return {"draft_id": draft["id"], "status": draft["status"], "subject": draft["subject"], "category": draft["category"],
            "question_preview": _preview(draft), "created_at": draft["created_at"], "revision": draft.get("revision", 1)}


def _blocks_out(draft, conv_id, vault, editable=False):
    refs = drafts.conversation_refs(vault, conv_id) if conv_id else {}
    return [{**({"block_id": b["id"], "box": b.get("box"), "box_origin": b.get("box_origin")} if editable else {}),
             "section": b["section"], "kind": b["kind"], **({"text": b["text"], **({"note": b.get("note") or ""} if editable else {})} if b["kind"] == "text" else
                                                               {"image": refs.get(b["image_sha"]), "note": b.get("note") or ""})}
            for b in draft["blocks"]]




# ── read ──
def describe_image_tool(ctx, args):
    row = drafts.resolve_image(ctx["vault"], ctx["conversation_id"], args["image"])
    def record(usage):
        ctx["emit_usage"]({"kind": "describe", "ref": row["ref"], "request_id":
                           f"{ctx['run_id']}:describe:{ctx['tool_call_id']}", "usage": usage})
    options = {"usage_callback": record} if ctx.get("emit_usage") else {}
    answer = ask_image(ctx["vault"], drafts.image_data_url(ctx["vault"], row["sha256"]), args["question"].strip(), **options)
    if len(answer) > DESCRIBE_CAP:
        answer = answer[:DESCRIBE_CAP] + "…（已截断）"
    return {"result": {"image": row["ref"], "answer": answer}, "summary": row["ref"]}


def list_drafts_tool(ctx, args):
    conv = None if args.get("all_conversations") else ctx["conversation_id"]
    status = args.get("status") or None
    items = drafts.list_drafts(ctx["vault"], status=status, conversation_id=conv, limit=30)
    if not status:
        items = [d for d in items if d["status"] in ("cropping", "review")]
    return {"result": {"total": len(items), "items": [_summary(d) for d in items]}, "summary": f"{len(items)} 份"}


def get_draft_tool(ctx, args):
    draft = drafts.get_draft(ctx["vault"], args["draft_id"].strip())
    conv = draft.get("conversation_id") or ctx["conversation_id"]
    sources = [{"ref": image.get("ref"), "width": image.get("width"), "height": image.get("height")}
               for image in draft.get("source_images") or []]
    return {"result": {**_summary(draft), "knowledge_points": draft.get("knowledge_points") or [],
                       "cause": draft.get("cause") or "", "note": draft.get("note") or "", "uid": draft.get("uid"),
                       "source_images": sources,
                       "blocks": _blocks_out(draft, conv, ctx["vault"], editable=True)}, "summary": draft["id"]}


def update_draft_tool(ctx, args):
    vault, conv = ctx["vault"], ctx["conversation_id"]
    fields = args.get("fields") or {}
    if "cause" in fields:
        statement = str(args.get("cause_statement") or "").strip()
        if fields["cause"]:
            key = _norm(statement)
            if len(key) < 2 or not any(key in _norm(text) for text in _user_texts(vault, conv)):
                raise ValueError("错因只能引用用户原话，请重新读取对话并核对 cause_statement")
    else:
        statement = ""
    out = drafts.patch_draft(vault, args["draft_id"].strip(), args["expected_revision"],
                             fields, args.get("block_patches") or [],
                             {"conversation_id": conv, "run_id": ctx.get("run_id"),
                              "tool_call_id": ctx.get("tool_call_id"), "cause_statement": statement})
    draft = out["draft"]
    result = {**_summary(draft), "wrote": out["wrote"], "suggestions": out["suggestions"]}
    if out["suggestions"]:
        result["message"] = "这些位置曾由人工编辑，未覆盖；请让用户在草稿区核对并采纳建议。"
    return {"result": result, "summary": draft["id"], "wrote": out["wrote"]}


# ── rev ──
def create_draft_tool(ctx, args):
    vault, conv = ctx["vault"], ctx["conversation_id"]
    shas = {}
    for ref in args.get("images") or []:
        shas[ref.strip()] = drafts.resolve_image(vault, conv, ref)["sha256"]
    blocks = []
    for i, b in enumerate(_merge_answer_text_runs(args["blocks"])):
        if b["kind"] == "image":
            ref = str(b.get("image") or "").strip()
            if not ref:
                raise ValueError(f"第 {i + 1} 块是图片块，要写 image（例如 IMG-1）")
            if ref not in shas:
                raise ValueError(f"第 {i + 1} 块引用的 {ref} 不在 images 列表里")
            blocks.append({"section": b["section"], "kind": "image", "image_sha": shas[ref], "note": b.get("note") or ""})
        else:
            blocks.append({"section": b["section"], "kind": "text", "text": b.get("text") or "", "note": b.get("note") or ""})
    cause = str(args.get("cause") or "").strip()
    statement = str(args.get("cause_statement") or "").strip()
    if cause:
        key = _norm(statement)
        if len(key) < 2 or not any(key in _norm(t) for t in _user_texts(vault, conv)):
            raise ValueError("错因只能用用户说过的话：没在对话里找到 cause_statement。用户没说错因就先问，说「不填」就留空")
    elif statement:
        statement = ""
    draft = drafts.create_draft(vault, {
        "subject": args["subject"], "category": args["category"],
        "knowledge_points": args.get("knowledge_points") or [], "blocks": blocks,
        "source_images": list(shas.values()),
        "cause": cause, "cause_statement": statement,
    }, {"conversation_id": conv, "run_id": ctx.get("run_id"), "tool_call_id": ctx.get("tool_call_id")})
    auto_detect = None
    if settings(vault)["draft_crop_mode"] == "auto" and draft.get("source_images"):
        try:
            # Hooks.execute 此时仍持全局写锁；只登记后台作业，模型调用由作业线程执行。
            drafts.start_detect(vault, draft["id"], draft["revision"], sha=None)
            auto_detect = {"status": "queued", "images": len(draft["source_images"])}
        except Exception:
            # 草稿已成功创建；自动检测启动失败不能诱使模型重复建草稿。
            auto_detect = {"status": "error", "message": "自动框选未能启动，请在草稿区手动处理"}
    result = {**_summary(draft), "blocks": _blocks_out(draft, conv, vault), "cause": cause}
    if auto_detect:
        result["auto_detect"] = auto_detect
    return {"result": result,
            "summary": draft["id"], "wrote": True}


def _commit_target(ctx, args):
    """确认前和执行时均从持久配置及草稿重读，旧许可不能提交新版本。"""
    if settings(ctx["vault"])["draft_mode"] != "confirm":
        raise ValueError("AI 录题方式已改变，请在草稿区审核")
    draft_id = args["draft_id"].strip()
    revision = args["revision"]
    if type(revision) is not int or revision < 1:
        raise ValueError("草稿版本无效，请重新读取草稿")
    try:
        draft = drafts.get_draft(ctx["vault"], draft_id)
    except Exception as exc:
        raise ValueError("无法读取草稿，请在草稿区检查后重试") from exc
    if draft.get("conversation_id") != ctx["conversation_id"]:
        raise ValueError("只能提交本对话创建的草稿")
    if draft["status"] != "review":
        raise ValueError("草稿当前不是待审核状态，请在草稿区处理")
    if draft.get("revision") != revision:
        raise ValueError("草稿已经变化，请重新读取并重新请求确认")
    return draft


def _training_summary(training):
    """工具结果只给模型看登记数量，图片 SHA 和本地错误留在草稿 API。"""
    if not isinstance(training, dict):
        training = {}
    status = training.get("status")
    if status not in ("off", "not_requested", "complete", "partial", "pending"):
        status = "off"
    result = {"status": status}
    for key in ("registered", "failed", "pending"):
        entries = training.get(key)
        result[key] = len(entries) if isinstance(entries, list) else 0
    if result["failed"]:
        result["message"] = "训练数据登记失败，请在草稿区查看并重试"
    return result


def commit_draft_preview(ctx, args):
    draft = _commit_target(ctx, args)
    blocks = [{"section": b["section"], "kind": b["kind"],
               "text": b.get("text") or "", "image_sha": b.get("image_sha") or "",
               "box": b.get("box"), "note": b.get("note") or ""} for b in draft["blocks"]]
    return {"draft_id": draft["id"], "revision": draft["revision"], "subject": draft["subject"],
            "category": draft["category"], "difficulty": draft["difficulty"],
            "knowledge_points": draft.get("knowledge_points") or [], "labels": draft.get("labels") or [],
            "cause": draft.get("cause") or "", "note": draft.get("note") or "", "blocks": blocks,
            "source_images": draft.get("source_images") or []}


def commit_draft_tool(ctx, args):
    _commit_target(ctx, args)
    try:
        out = drafts.commit_draft(ctx["vault"], args["draft_id"].strip(), args["revision"])
    except drafts.DraftError as exc:
        if exc.code == "revision_conflict":
            raise ValueError("草稿已变化，请重新读取并重新请求确认") from exc
        if exc.code == "state_conflict":
            raise ValueError("草稿状态已变化，请在草稿区检查后重新请求确认") from exc
        raise ValueError("草稿入库失败，请在草稿区查看并重试") from exc
    except Exception as exc:
        raise ValueError("草稿入库失败，请在草稿区查看并重试") from exc
    committed = out["draft"]
    result = out["result"]
    return {"result": {"draft_id": committed["id"], "revision": committed["revision"],
                       "status": committed["status"], "uid": result.get("uid"),
                       "question_id": result.get("question_id"), "reused": bool(out.get("reused")),
                       "training": _training_summary(out.get("training"))},
            "summary": committed["id"], "wrote": not out.get("reused", False)}


_S = {"type": "string", "minLength": 1}
_IMG = {"type": "string", "pattern": "^IMG-[0-9]+$"}
_BLOCK = {"type": "object", "required": ["section", "kind"], "properties": {
    "section": {"type": "string", "enum": ["题目", "答案"]}, "kind": {"type": "string", "enum": ["text", "image"]},
    "text": {"type": "string"}, "image": _IMG, "note": {"type": "string"}}}

SPECS = [
    ("describe_image", "read",
     "针对本对话里的一张图（IMG-n）提一个具体问题，让识图模型再仔细看一次，例如「第 3 步的分母是什么」「图里的几何图形标了哪些点」。"
     "转述看不清或需要局部细节时用。",
     {"type": "object", "required": ["image", "question"], "properties": {
         "image": _IMG, "question": {"type": "string", "minLength": 2, "maxLength": 300}}}, describe_image_tool),
    ("list_drafts", "read", "列出 AI 草稿区里的草稿。默认只列本对话、还没入库也没丢弃的；status 可筛 cropping（待框选）/ review（待审核）/ done / discarded。",
     {"type": "object", "properties": {
         "status": {"type": "string", "enum": list(drafts.STATUSES)}, "all_conversations": {"type": "boolean"}}},
     list_drafts_tool),
    ("get_draft", "read", "读一份草稿的全部内容：科目、分类、知识点、错因、各块（文字 / 图片）与状态。",
     {"type": "object", "required": ["draft_id"], "properties": {"draft_id": _S}}, get_draft_tool),
    ("update_draft", "rev", "按 get_draft 读到的 expected_revision 修改本对话待审草稿。只改指定字段或已有 block_id 的文字/说明；人工编辑过的目标只给建议，冲突后必须重新读取，不得盲目重试。不会入库。",
     {"type": "object", "required": ["draft_id", "expected_revision"], "additionalProperties": False,
      "properties": {"draft_id": _S, "expected_revision": {"type": "integer", "minimum": 1},
                     "fields": {"type": "object", "additionalProperties": False,
                                "properties": {"subject": _S, "category": _S,
                                               "knowledge_points": {"type": "array", "maxItems": 8, "items": _S},
                                               "cause": {"type": "string"}, "note": {"type": "string"}}},
                     "cause_statement": {"type": "string"},
                     "block_patches": {"type": "array", "maxItems": 20,
                                       "items": {"type": "object", "required": ["block_id"], "additionalProperties": False,
                                                 "properties": {"block_id": _S, "text": {"type": "string"},
                                                                "note": {"type": "string"}}}}}}, update_draft_tool),
    ("create_draft", "rev",
     "把一道题录成草稿，放进录入页的 AI 草稿区，由用户审核后入库（不直接写题库，所以不需要用户允许）。"
     "blocks 按原题阅读顺序写题目和答案，可混排文字与图片：能完整转述的写 kind=text（公式用 $LaTeX$），独立且能准确框出的局部图写 kind=image。"
     "题干、图表和小问相互依赖，或不能确定拆开后仍完整时，整道题目写为一个图片块，框住题干、必要图表和全部小问；不要机械拆段。"
     "答案没有图片时必须只有一个 kind=text 块，所有步骤、公式和段落用换行写在一起，不能按段落拆块；只有图片夹在答案文字中间时才在图片两侧分块，图片在开头或结尾时也合并相邻文字。"
     "同一来源图确有多个独立局部时可引用多次。image 填 IMG-n，note 写明要框的范围。images 列出这道题用到的全部截图。难度固定 5。"
     "错因只能用用户原话：带 cause 时 cause_statement 必须原样摘自用户消息；用户没说就先问，不要自己编。",
     {"type": "object", "required": ["subject", "category", "blocks"], "properties": {
         "subject": _S, "category": _S,
         "knowledge_points": {"type": "array", "maxItems": 8, "items": _S},
         "images": {"type": "array", "maxItems": 12, "items": _IMG},
         "blocks": {"type": "array", "minItems": 1, "maxItems": 20, "items": _BLOCK},
         "cause": {"type": "string"}, "cause_statement": {"type": "string"}}},
     create_draft_tool),
    ("commit_draft", "confirm",
     "在用户明确允许后，把本对话的一份待审核草稿入库。先用 get_draft 读取当前 revision；等待确认期间草稿变化时必须重新读取并重新申请。",
     {"type": "object", "required": ["draft_id", "revision"], "properties": {
         "draft_id": _S, "revision": {"type": "integer", "minimum": 1}}},
     commit_draft_tool, commit_draft_preview),
]
