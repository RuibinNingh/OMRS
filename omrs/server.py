import base64
import datetime
import email.utils
import http.server
import json
import mmap
import sqlite3
import os
import re
import secrets
import shutil
import tempfile
import time
import urllib.parse
from http.cookies import SimpleCookie

from .common import HISTORY_HEADERS, history_path, load_config, load_csv, save_config, validate_draft_config
from .analytics import build_review_export, get_analytics
from .catalog import build_tree
from .reports import create_report, delete_report, get_report_html, list_reports, signed_report_images
from . import traincontrol
from . import security
from . import locking
from . import boards as board_mod
from .errors import RequestError
from .ai_assist import recognize_question, collect_taxonomy
from .creation import create_question
from .exporting import _find_image, _read_image_info, export_schedule_artifact, export_board_html, board_export_filename
from .labels import delete_label, list_label_defs, merge_labels, save_label
from .boards import (
    add_items as board_add_items,
    create_board,
    create_folder as board_create_folder,
    delete_board,
    delete_folder as board_delete_folder,
    duplicate_board,
    get_board,
    list_boards,
    list_folders as board_list_folders,
    move_board as board_move,
    record_printed as board_record_printed,
    remove_items as board_remove_items,
    reset_printed as board_reset_printed,
    update_board,
    update_folder as board_update_folder,
)
from .feedback import process_feedback
from .indexing import build_index
from . import trainpanel as trainpanel_mod
from . import trainaudit as trainaudit_mod
from . import annotate as annotate_mod
from . import drafts as drafts_mod
from . import inbox as inbox_mod
from . import entry_background
from .ledger import append_commit, get_commit, get_commit_by_id, read_commits, verify_ledger
from .optimization import (
    create_backup_export,
    get_job,
    prepare_backup_import,
    restore_backup,
    scan_compression,
    start_compression,
    storage_summary,
)
from .content_history import ContentConflict, content_versions, restore_content
from .ledger import get_blob
from .projections import ledger_history, ledger_history_detail, ledger_retraction_state, rebuild_projection
from .question_ops import (
    delete_question,
    get_question_raw,
    move_question,
    resume_question,
    save_question_markdown,
    suspend_question,
)
from .scheduling import generate_recommendations
from .sessions import (
    create_session,
    create_session_from_selection,
    delete_session,
    get_session,
    list_sessions,
    active_session_uids,
)
from .stats import get_question_content, get_stats
from .source_export import create_source_export
from .version import __version__
from .workspace_sync import get_scan_status, scan_workspace

# Random per-process generation id, exposed on GET /api/auth/session so the
# settings page can tell a restarted service apart from the old process.
# It is public readiness metadata, never a credential.
OMRS_INSTANCE_ID = secrets.token_hex(16)


class OMRSHandler(http.server.SimpleHTTPRequestHandler):
    vault_path = "."
    listen_external = False  # set by cli.py: True when bound to all interfaces
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_monotonic = time.monotonic()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        params = dict(query_pairs)

        # 先拒绝 MCP 凭据，再处理普通端口的公开页面和登录状态接口，避免
        # 通过 /api/auth/login 等路径借道建立 Web 会话。
        if self._mcp_credential_present():
            self._json({"status": "error", "code": "mcp_boundary", "msg": "MCP Key 不能调用普通 OMRS 接口"}, 403)
            return

        if path == "/login":
            self._serve_entry()
            return
        if path == "/api/auth/session":
            self._auth_status()
            return
        if path == "/api/entry-background":
            self._serve_entry_background()
            return
        # The first visit is always the lock-screen entry.  The unlocked
        # dashboard is still protected by the normal remote authorization
        # check below, so this public page never exposes vault data or assets.
        if path in ("/", "/index.html") and params.get("unlocked") != "1":
            self._serve_entry()
            return
        if not self._authorize(path, params):
            return

        if path.startswith("/api/inbox/") or path == "/m":
            self._inbox_get(path, params)
            return
        if path.startswith("/api/trainpanel/") or path == "/train":
            self._trainpanel_get(path, params)
            return
        if path.startswith("/api/annotate/") or path == "/annotate":
            self._annotate_get(path, params)
            return
        if path.startswith("/api/agent/"):
            from .agent.http import handle_agent_get
            handle_agent_get(self, path, params)
            return
        if path.startswith("/api/mcp/"):
            self._mcp_get(path, params)
            return
        if path.startswith("/api/drafts/"):
            self._drafts_get(path, params)
            return

        if path == "/api/stats":
            self._json(get_stats(self.vault_path))
        elif path == "/api/taxonomy":
            self._json({"status": "ok", "taxonomy": collect_taxonomy(self.vault_path)})
        elif path == "/api/labels":
            self._json({"status": "ok", "labels": list_label_defs(self.vault_path)})
        elif path == "/api/boards":
            self._json({"status": "ok", **board_mod.catalog(self.vault_path)})
        elif path == "/api/board":
            board = get_board(self.vault_path, params.get("id", ""))
            if board is None:
                self._json({"status": "error", "msg": "展示板不存在"}, 404)
            else:
                self._json({"status": "ok", "board": board})
        elif path == "/api/status":
            try:
                stats = get_stats(self.vault_path)
                self._json(
                    {
                        "status": "ok",
                        "version": __version__,
                        "started_at": self.started_at.isoformat(),
                        "uptime_seconds": int(time.monotonic() - self.started_monotonic),
                        "question_count": int(stats.get("total", 0)),
                        "listen_external": bool(self.listen_external),
                        "vault_path": os.path.abspath(self.vault_path),
                        "workspace_scan": get_scan_status(self.vault_path),
                    }
                )
            except Exception as exc:
                self._json({"status": "error", "version": __version__, "msg": str(exc)}, 500)
        elif path == "/api/analytics":
            try:
                self._json(get_analytics(self.vault_path))
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/source/export":
            try:
                payload, filename, _meta = create_source_export(self.vault_path)
                filename_encoded = urllib.parse.quote(filename)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename_encoded}",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/export-review":
            try:
                include_images = params.get("include_images", "").strip().lower() in {"1", "true", "yes"}
                payload, filename, content_type = build_review_export(
                    self.vault_path, include_images=include_images
                )
                filename_encoded = urllib.parse.quote(filename)
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename=\"OMRS-AI-data.{'zip' if include_images else 'md'}\"; "
                    f"filename*=UTF-8''{filename_encoded}",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/sessions":
            self._json({"sessions": list_sessions(self.vault_path, params.get("status"))})
        elif path == "/api/session":
            session_id = params.get("id", "")
            session = get_session(self.vault_path, session_id)
            if session is None:
                self._json({"status": "error", "msg": f"session {session_id} 不存在"}, 404)
            else:
                self._json(session)
        elif path == "/api/question":
            self._json(get_question_content(self.vault_path, params.get("uid", "")))
        elif path == "/api/question/raw":
            try:
                self._json({"status": "ok", **get_question_raw(self.vault_path, params.get("uid", ""))})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 404)
        elif path == "/api/history":
            try:
                before = params.get("before_seq") or None
                limit = int(params.get("limit", 100))
                limit = max(1, min(500, limit))
                summary_only = params.get("view") == "summary"
                from .runtime_records import filters
                options = filters(params)
                commits = ledger_history(self.vault_path, before, limit + 1 if summary_only else limit,
                                         summary_only=summary_only, **{key: options[key] for key in ("q", "since", "until")})
                has_more = summary_only and len(commits) > limit
                if has_more:
                    commits = commits[1:]
                self._json({
                    "status": "ok",
                    "commits": commits,
                    "has_more": has_more,
                    "next_before_seq": min((row["seq"] for row in commits), default=None) if has_more else None,
                    "retraction_state": ledger_retraction_state(self.vault_path),
                    **({} if summary_only else {"history": load_csv(history_path(self.vault_path), HISTORY_HEADERS)[-100:]}),
                })
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/history/detail":
            try:
                detail = ledger_history_detail(self.vault_path, int(params.get("seq", "0")))
                if detail is None:
                    self._json({"status": "error", "msg": "历史节点不存在"}, 404)
                else:
                    from .runtime_records import calls_for_draft
                    try:
                        detail["runtime_calls"] = calls_for_draft(self.vault_path,
                            detail.get("payload", {}).get("_draft", {}).get("draft_id"))
                    except (OSError, sqlite3.Error, ValueError):
                        detail["runtime_calls"] = []
                        detail["runtime_calls_error"] = "来源调用暂时无法读取，请稍后刷新。"
                    self._json({"status": "ok", "detail": detail})
            except (ValueError, TypeError) as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/runtime/records":
            self._runtime_records_get(params)
        elif path == "/api/runtime/records/detail":
            self._runtime_records_get(params, detail=True)
        elif path == "/api/question/content/history":
            try:
                self._json({"status": "ok", **content_versions(
                    self.vault_path, uid=params.get("uid") or None, question_id=params.get("question_id") or None)})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 404)
        elif path == "/api/question/content/version":
            content = get_blob(self.vault_path, params.get("hash", ""))
            if content is None:
                self._json({"status": "error", "msg": "这个版本的正文不在 Ledger 里"}, 404)
            else:
                self._json({"status": "ok", "hash": params.get("hash", ""), "markdown": content})
        elif path == "/api/ledger/verify":
            self._json(verify_ledger(self.vault_path))
        elif path == "/api/optimize/summary":
            try:
                self._json(storage_summary(self.vault_path))
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/optimize/job":
            job = get_job(params.get("id", ""))
            if not job:
                self._json({"status": "error", "msg": "job 不存在"}, 404)
            else:
                self._json({"status": "ok", "job": job})
        elif path == "/api/scan":
            self._json({"status": "error", "msg": "请使用 POST /api/scan"}, 405)
        elif path == "/api/tree":
            try:
                self._json({"status": "ok", **build_tree(self.vault_path)})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/config":
            config = load_config(self.vault_path)
            key_configured = bool(config.get("ai_api_key"))
            config.pop("ai_api_key", None)
            config["ai_api_key_configured"] = key_configured
            agent_key_configured = bool(config.get("agent_api_key"))
            config.pop("agent_api_key", None)
            config["agent_api_key_configured"] = agent_key_configured
            config.update(security.auth_summary(self.vault_path))
            config["entry_background"] = entry_background.public_state(self.vault_path)
            self._json(config)
        elif path == "/api/reports":
            try:
                self._json({"status": "ok", "reports": list_reports(self.vault_path)})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/report/view":
            try:
                html = get_report_html(self.vault_path, params.get("id", ""))
                if self._active_session:
                    html = signed_report_images(html, self._sign_report_image)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Security-Policy", "sandbox allow-scripts allow-downloads allow-popups")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 404)
        elif path == "/api/recommend":
            try:
                due_count = int(params.get("due_count", 10))
                prof_count = int(params.get("prof_count", 10))
                subject = params.get("subject") or None
                category = params.get("category") or None
                knowledge_tag = params.get("knowledge_tag") or None
                requested_labels = [value for key, value in query_pairs if key == "label" and value]
                label = requested_labels if requested_labels else (params.get("label") or None)
                rec = generate_recommendations(
                    self.vault_path,
                    due_count=due_count,
                    prof_count=prof_count,
                    subject=subject,
                    category=category,
                    knowledge_tag=knowledge_tag,
                    label=label,
                    # Bulk requests use larger limits but must preserve the
                    # same active-session exclusion as normal recommendations.
                    exclude_uids=active_session_uids(self.vault_path),
                )
                self._json({"status": "ok", **rec})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/image":
            name = params.get("name", "")
            if not name:
                self._json({"error": "missing name"}, 400)
                return
            fpath = _find_image(self.vault_path, name)
            if not fpath:
                self._json({"error": f"image not found: {name}"}, 404)
                return
            try:
                data, _, _, _, content_type = _read_image_info(fpath)
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                remote, _, _ = self._security_context()
                self.send_header("Cache-Control", "no-store" if remote else "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self._json({"error": f"cannot read image: {name}"}, 500)
        elif path in ("/", "/index.html"):
            self._serve("omrs_dashboard.html", "text/html")
        elif path.startswith("/assets/"):
            self._serve_asset(path)
        else:
            self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if self._mcp_credential_present():
            self._json({"status": "error", "code": "mcp_boundary", "msg": "MCP Key 不能调用普通 OMRS 接口"}, 403)
            return
        if not self._check_write_origin():
            return
        if path == "/api/auth/login":
            self._auth_login()
            return
        if not self._authorize(path, {}):
            return
        if path.startswith("/api/auth/"):
            self._auth_post(path)
            return
        if path.startswith("/api/agent/"):
            from .agent.http import handle_agent_post
            handle_agent_post(self, path)
            return
        if path.startswith("/api/mcp/"):
            self._mcp_post(path)
            return
        if locking.post_exempt(path):
            self._do_post_routes(path)
            return
        # 其余 POST 一律在进程级写锁内处理（见 AI/api.md「并发与写锁」）
        started = time.monotonic()
        try:
            with locking.write_lock():
                self._do_post_routes(path)
        except locking.WriteLockTimeout:
            print(f"[omrs] 写锁等待超时：POST {path}，{time.monotonic() - started:.1f} 秒", flush=True)
            self._json({"status": "error", "msg": "写入繁忙，请稍后重试"}, 503)

    def _do_post_routes(self, path):
        if path == "/api/backup/import":
            self._handle_backup_import()
            return
        if path == "/api/entry-background":
            self._entry_background_post()
            return
        if path.startswith("/api/inbox/"):
            self._inbox_post(path)
            return
        if path.startswith("/api/trainpanel/"):
            self._trainpanel_post(path)
            return
        if path.startswith("/api/drafts/"):
            self._drafts_post(path)
            return
        if path.startswith("/api/annotate/"):
            self._annotate_post(path)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")

        if path == "/api/scan":
            try:
                scan = scan_workspace(self.vault_path)
                index = build_index(self.vault_path)
                self._json({"status": "ok", "count": len(index), "scan": scan})
            except RuntimeError as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/schedule":
            try:
                data = json.loads(body) if body else {}
                session = create_session(
                    self.vault_path,
                    int(data.get("count", 10)),
                    data.get("subject") or None,
                )
                self._json(
                    {
                        "status": "ok",
                        "session_id": session["session_id"],
                        "created_at": session["created_at"],
                        "subject_filter": session["subject_filter"],
                        "count": session["count"],
                        "session_status": session["status"],
                        "completed_at": session["completed_at"],
                        "items": session["items"],
                    }
                )
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/session/delete":
            try:
                data = json.loads(body)
                ok = delete_session(self.vault_path, data.get("session_id", ""))
                self._json({"status": "ok" if ok else "error", "deleted": ok})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/feedback":
            try:
                data = json.loads(body)
                results = process_feedback(
                    self.vault_path,
                    data.get("feedbacks", []),
                    data.get("session_id", ""),
                    attempt_id=data.get("attempt_id", ""),
                )
                self._json({"status": "ok", "results": results})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/create":
            try:
                data = json.loads(body)
                result = create_question(
                    self.vault_path,
                    subject=data["subject"],
                    category=data["category"],
                    difficulty=int(data.get("difficulty", 5)),
                    related_tags=data.get("related_tags", []),
                    labels=data.get("labels", []),
                    question_text=data.get("question_text", ""),
                    answer_text=data.get("answer_text", ""),
                    cause=data.get("cause", ""),
                    question_images=data.get("question_images", []),
                    answer_images=data.get("answer_images", []),
                )
                self._json({"status": "ok", **result,
                            **({"deprecated_fields": ["note"]} if "note" in data else {})})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/ai-recognize":
            try:
                data = json.loads(body) if body else {}
                quick_scope = data.get("scope") == "quick"
                # 兼容旧字段名 image，新的使用 question_image
                question_image = data.get("question_image") or data.get("image", "")
                answer_image = data.get("answer_image", "")
                mode = data.get("mode", "classify")
                result = recognize_question(
                    self.vault_path, question_image, mode=mode,
                    hint_subject=data.get("subject", ""),
                    hint_category=data.get("category", ""),
                    answer_image=answer_image,
                    allow_labels=not quick_scope,
                )
                if quick_scope:
                    allowed = ({"mode", "subject", "category", "difficulty", "knowledge_tags",
                                "cause_candidate", "restrict_tags"} if mode == "classify" else
                               {"mode", "question_text"} if mode in ("question_text", "question") else
                               {"mode", "answer"})
                    result = {key: value for key, value in result.items() if key in allowed}
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/config":
            try:
                data = json.loads(body) if body else {}
                if not isinstance(data, dict):
                    raise ValueError("配置必须是 JSON 对象")
                if "ai_thinking" in data and not isinstance(data["ai_thinking"], bool):
                    raise ValueError("ai_thinking 必须是布尔值")
                if "inbox_detect_provider" in data and data["inbox_detect_provider"] not in inbox_mod.PROVIDERS:
                    raise ValueError("未知框选提供方")
                if "lan_pin_exempt_cidrs" in data:
                    data["lan_pin_exempt_cidrs"] = security.normalize_lan_cidrs(data["lan_pin_exempt_cidrs"])
                effective = {**load_config(self.vault_path), **data}
                if (effective.get("allow_external") and
                        not security.auth_summary(self.vault_path)["pin_configured"] and
                        not security.normalize_lan_cidrs(effective.get("lan_pin_exempt_cidrs", []))):
                    raise ValueError("启用外部访问前请设置 PIN 或配置局域网免 PIN 网段")
                if data.pop("clear_ai_api_key", False):
                    data["ai_api_key"] = ""
                elif data.get("ai_api_key") == "":
                    data.pop("ai_api_key")
                if data.pop("clear_agent_api_key", False):
                    data["agent_api_key"] = ""
                elif data.get("agent_api_key") == "":
                    data.pop("agent_api_key")
                from .agent.config import validate_agent_config
                validate_agent_config(data)
                validate_draft_config(data)
                data.pop("pin_hash", None)
                data.pop("salt", None)
                save_config(self.vault_path, data)
                self._json({"status": "ok"})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/label/save":
            try:
                data = json.loads(body) if body else {}
                result = save_label(
                    self.vault_path,
                    value=data.get("id"),
                    name=data.get("name"),
                    color=data.get("color"),
                    priority_bonus=data.get("priority_bonus"),
                    order=data.get("order"),
                )
                self._json({"status": "ok", "label": result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/label/delete":
            try:
                data = json.loads(body) if body else {}
                result = delete_label(
                    self.vault_path,
                    data.get("id") or data.get("name"),
                    detach=data.get("detach", True) is not False,
                )
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/label/merge":
            try:
                data = json.loads(body) if body else {}
                result = merge_labels(
                    self.vault_path,
                    data.get("from") or data.get("source"),
                    data.get("into") or data.get("target"),
                )
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/question/labels":
            try:
                data = json.loads(body) if body else {}
                from .question_ops import set_question_labels
                result = set_question_labels(
                    self.vault_path, data.get("uid", ""), data.get("labels") or [],
                )
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/questions/labels":
            try:
                data = json.loads(body) if body else {}
                from .question_ops import set_question_labels
                uids = list(dict.fromkeys(
                    str(uid).strip() for uid in data.get("uids") or [] if str(uid).strip()
                ))
                add = [str(value).strip() for value in data.get("add") or [] if str(value).strip()]
                remove = {str(value).strip() for value in data.get("remove") or [] if str(value).strip()}
                changed = 0
                failed = []
                for uid in uids:
                    try:
                        question = get_question_content(self.vault_path, uid)
                        current = list(question.get("labels") or [])
                        next_labels = [
                            value for value in dict.fromkeys(current + add)
                            if value not in remove
                        ]
                        result = set_question_labels(
                            self.vault_path, uid, next_labels, scan=False,
                        )
                        changed += int(result.get("changed", False))
                    except Exception as exc:
                        failed.append({"uid": uid, "msg": str(exc)})
                scan = scan_workspace(self.vault_path) if changed else {"status": "ok", "changes": 0, "conflicts": []}
                self._json({"status": "ok", "changed": changed, "failed": failed, "scan": scan})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/workspace/scan":
            try:
                self._json({"status": "ok", **scan_workspace(self.vault_path)})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/optimize/scan":
            try:
                self._json(scan_compression(self.vault_path))
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/optimize/compress":
            try:
                data = json.loads(body) if body else {}
                self._json(start_compression(
                    self.vault_path,
                    data.get("scan_id", ""),
                    data.get("backup_token", ""),
                    confirm=bool(data.get("confirm")),
                ))
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/backup/export":
            try:
                payload, filename, token = create_backup_export(self.vault_path)
                filename_encoded = urllib.parse.quote(filename)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename_encoded}",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("X-OMRS-Backup-Token", token)
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/backup/restore":
            try:
                data = json.loads(body) if body else {}
                self._json(restore_backup(
                    self.vault_path,
                    data.get("restore_id", ""),
                    confirm=bool(data.get("confirm")),
                ))
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/question/markdown":
            try:
                data = json.loads(body) if body else {}
                result = save_question_markdown(
                    self.vault_path,
                    data.get("uid", ""),
                    data.get("markdown", ""),
                    expected_content_hash=str(data.get("expected_content_hash") or ""),
                )
                self._json({"status": "ok", **result})
            except ContentConflict as exc:
                self._json({"status": "error", "msg": str(exc)}, 409)
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/question/content/restore":
            try:
                data = json.loads(body) if body else {}
                result = restore_content(self.vault_path, data.get("uid", ""), data.get("hash", ""),
                                         expected_hash=str(data.get("expected_content_hash") or "") or None)
                self._json({"status": "ok", **result})
            except ContentConflict as exc:
                self._json({"status": "error", "msg": str(exc)}, 409)
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/question/move":
            try:
                data = json.loads(body) if body else {}
                result = move_question(
                    self.vault_path,
                    data.get("uid", ""),
                    data.get("subject", ""),
                    data.get("category", ""),
                )
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/question/suspend":
            try:
                data = json.loads(body) if body else {}
                result = suspend_question(
                    self.vault_path,
                    data.get("uid", ""),
                    data.get("reason", ""),
                )
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/question/resume":
            try:
                data = json.loads(body) if body else {}
                result = resume_question(
                    self.vault_path,
                    data.get("uid", ""),
                    data.get("reason", ""),
                )
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/question/delete":
            try:
                data = json.loads(body) if body else {}
                result = delete_question(self.vault_path, data.get("uid", ""))
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/history/review/replace":
            self._history_commit("review.replace", "修改旧反馈", body)

        elif path == "/api/history/review/retract":
            self._history_commit("review.retract", "撤销旧反馈", body)

        elif path == "/api/history/review/restore":
            self._history_commit("review.restore", "恢复旧反馈", body)

        elif path == "/api/history/session/retract":
            self._history_commit("session.retract", "撤销 Session", body)

        elif path == "/api/history/session/restore":
            self._history_commit("session.restore", "恢复 Session", body)

        elif path == "/api/history/state/restore":
            self._history_commit("state.restore", "还原到历史节点", body)

        elif path == "/api/report/create":
            try:
                data = json.loads(body) if body else {}
                meta = create_report(
                    self.vault_path,
                    data.get("name", ""),
                    data.get("html", ""),
                )
                self._json({"status": "ok", **meta})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/report/delete":
            try:
                data = json.loads(body) if body else {}
                ok = delete_report(self.vault_path, data.get("id", ""))
                self._json({"status": "ok" if ok else "error", "deleted": ok})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/restart":
            self._json({"status": "ok", "msg": "正在重启..."})
            import subprocess
            import threading
            import time

            def _restart():
                # When OMRS is managed by systemd, let systemd own the
                # lifecycle.  The old self-reexec path exits successfully;
                # with Restart=on-failure systemd then correctly leaves the
                # service stopped, and the child is killed with the unit.
                service_name = os.environ.get("OMRS_SYSTEMD_SERVICE", "").strip()
                if service_name:
                    try:
                        result = subprocess.run(
                            ["systemctl", "restart", "--no-block", service_name],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                        )
                        if result.returncode == 0:
                            return
                    except OSError:
                        pass

                # Fallback for a manually launched OMRS process.  Wait (≤30 s) for the
                # in-flight write to finish before the listener stops.
                locking.acquire_for_shutdown(30.0)
                self.server.shutdown()
                time.sleep(1.5)
                cmd = getattr(OMRSHandler, "_restart_cmd", None)
                if cmd:
                    subprocess.Popen(cmd)

            threading.Thread(target=_restart, daemon=False).start()

        elif path == "/api/confirm-schedule":
            try:
                data = json.loads(body) if body else {}
                selected = data.get("selected", [])
                if not isinstance(selected, list) or len(selected) < 1:
                    self._json({"status": "error", "msg": "至少选择 1 道题"}, 400)
                    return
                if "persist" in data and not isinstance(data["persist"], bool):
                    raise ValueError("persist 必须为布尔值")
                if len(selected) == 1 and not data.get("persist", False):
                    # 单题：TMP- 自定义调度
                    from .scheduling import get_items_by_uids
                    import datetime as dt_mod
                    uid = selected[0].get("uid", selected[0]) if isinstance(selected[0], dict) else selected[0]
                    items = get_items_by_uids(self.vault_path, [uid])
                    session_id = f"TMP-{dt_mod.datetime.now().strftime('%Y%m%d%H%M%S')}"
                    self._json({
                        "status": "ok",
                        "session_id": session_id,
                        "session_type": "tmp",
                        "count": 1,
                        "items": items,
                    })
                else:
                    session = create_session_from_selection(
                        self.vault_path,
                        selected,
                        data.get("subject") or None,
                    )
                    self._json({"status": "ok", "session_type": "exp", **session})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/export":
            try:
                data = json.loads(body)
                uids = data.get("uids", [])
                session_id = data.get("session_id", "")
                export_format = (data.get("format") or "a4").strip().lower()
                include_answers = bool(data.get("include_answers", False))
                question_gap_lines = data.get("question_gap_lines", 0)
                a4_two_columns = data.get("a4_two_columns", True)
                if export_format == "board":
                    board_id = str(data.get("board_id") or data.get("id") or "").strip()
                    if not board_id:
                        self._json({"status": "error", "msg": "board_id 不能为空"}, 400)
                        return
                    mode = "new" if str(data.get("mode") or "").lower() == "new" else "all"
                    payload = export_board_html(
                        self.vault_path,
                        board_id,
                        mode=mode,
                        include_answers=data.get("include_answers"),
                        overrides=data.get("overrides") if isinstance(data.get("overrides"), dict) else None,
                    )
                    board = get_board(self.vault_path, board_id) or {}
                    self._download(payload, board_export_filename(board, mode), "text/html; charset=utf-8")
                    return
                if not uids and not session_id:
                    self._json({"status": "error", "msg": "需要 session_id 或 uids"}, 400)
                    return
                payload, sid, filename, content_type = export_schedule_artifact(
                    self.vault_path,
                    uids or None,
                    session_id,
                    export_format,
                    include_answers=include_answers,
                    question_gap_lines=question_gap_lines,
                    a4_two_columns=a4_two_columns,
                )
                filename_encoded = urllib.parse.quote(filename)
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename_encoded}",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/create":
            try:
                data = json.loads(body) if body else {}
                uids = list(data.get("uids") or [])
                if data.get("label") and not uids:
                    rows = get_stats(self.vault_path).get("items", [])
                    uids = [
                        row.get("uid") for row in rows
                        if data.get("label") in (row.get("labels") or [])
                    ]
                board = create_board(
                    self.vault_path,
                    data.get("name", ""),
                    uids,
                    data.get("label", ""),
                    str(data.get("folder_id") or ""),
                    **self._board_versions(data, catalog=True),
                )
                self._board_json({"status": "ok", "board": board})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/update":
            try:
                data = json.loads(body) if body else {}
                board_id = str(data.get("id") or "").strip()
                if not board_id:
                    raise ValueError("展示板 id 不能为空")
                changes = {key: data[key] for key in ("name", "note", "print", "items", "source_labels", "folder_id") if key in data}
                self._board_json({"status": "ok", "board": update_board(self.vault_path, board_id, **changes, **self._board_versions(data, board=True, catalog="folder_id" in changes or "name" in changes))})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/items/add":
            try:
                data = json.loads(body) if body else {}
                self._board_json({"status": "ok", "board": board_add_items(
                    self.vault_path, str(data.get("id") or ""), data.get("uids") or [], data.get("position"),
                    **self._board_versions(data, board=True),
                )})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/items/remove":
            try:
                data = json.loads(body) if body else {}
                self._board_json({"status": "ok", "board": board_remove_items(
                    self.vault_path, str(data.get("id") or ""), data.get("uids") or [], **self._board_versions(data, board=True),
                )})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/duplicate":
            try:
                data = json.loads(body) if body else {}
                self._board_json({"status": "ok", "board": duplicate_board(
                    self.vault_path, str(data.get("id") or ""), data.get("name", ""), **self._board_versions(data, board=True, catalog=True),
                )})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/folder/create":
            try:
                data = json.loads(body) if body else {}
                self._board_json({"status": "ok", "folder": board_create_folder(self.vault_path, data.get("name", ""), **self._board_versions(data, catalog=True))})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/folder/update":
            try:
                data = json.loads(body) if body else {}
                changes = {key: data[key] for key in ("name", "order") if key in data}
                self._board_json({"status": "ok", "folder": board_update_folder(
                    self.vault_path, str(data.get("id") or ""), **changes, **self._board_versions(data, catalog=True),
                )})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/folder/delete":
            try:
                data = json.loads(body) if body else {}
                keep = data.get("keep_boards", True)
                result = board_delete_folder(self.vault_path, str(data.get("id") or ""), keep is not False, **self._board_versions(data, catalog=True))
                self._board_json({"status": "ok", **result})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/move":
            try:
                data = json.loads(body) if body else {}
                self._board_json({"status": "ok", "board": board_move(
                    self.vault_path, str(data.get("id") or ""),
                    data.get("folder_id"), data.get("index"), **self._board_versions(data, board=True, catalog=True),
                )})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/delete":
            try:
                data = json.loads(body) if body else {}
                ok = delete_board(self.vault_path, str(data.get("id") or ""), **self._board_versions(data, board=True, catalog=True))
                self._board_json({"status": "ok" if ok else "error", "deleted": ok})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/printed":
            try:
                data = json.loads(body) if body else {}
                board = board_record_printed(
                    self.vault_path,
                    str(data.get("id") or ""),
                    str(data.get("mode") or "all"),
                    data.get("layout") if isinstance(data.get("layout"), dict) else {}, **self._board_versions(data, board=True),
                )
                self._board_json({"status": "ok", "board": board})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/printed/reset":
            try:
                data = json.loads(body) if body else {}
                self._board_json({"status": "ok", "board": board_reset_printed(self.vault_path, str(data.get("id") or ""), **self._board_versions(data, board=True))})
            except board_mod.BoardConflict as exc:
                self._board_json({"status": "error", "error": exc.code, "msg": str(exc)}, 409)
            except Exception as exc:
                self._board_json({"status": "error", "msg": str(exc)}, 400)
        else:
            self._json({"error": "not found"}, 404)

    def _board_versions(self, data, board=False, catalog=False):
        result = {}
        for needed, key in ((board, 'expected_revision'), (catalog, 'expected_catalog_revision')):
            if needed:
                value = data.get(key)
                if type(value) is not int or value < (1 if key == 'expected_revision' else 0):
                    raise ValueError(f'{key} 必须提供当前版本')
                result[key] = value
        return result

    def _board_json(self, data, status=200):
        self._json({**data, 'catalog_revision': board_mod.load_boards(self.vault_path)['catalog_revision']}, status)

    # ────────────── 收件箱 /api/inbox/* 与手机上传页 /m ──────────────
    def _inbox_get(self, path, params):
        try:
            if path == "/m":
                self._serve("assets/inbox_mobile.html", "text/html")
            elif path == "/api/inbox/items":
                self._json({"status": "ok", "items": inbox_mod.list_items(
                    self.vault_path, status=params.get("status") or None)})
            elif path == "/api/inbox/item":
                self._json({"status": "ok", "item": inbox_mod.get_item(self.vault_path, params.get("id", ""))})
            elif path == "/api/inbox/raw":
                mime, data = inbox_mod.raw_file(self.vault_path, params.get("id", ""))
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            elif path == "/api/inbox/job":
                self._json({"status": "ok", "job": inbox_mod.get_job(self.vault_path, params.get("id", ""))})
            elif path == "/api/inbox/slice-plan":
                plan = inbox_mod.slice_plan(int(params.get("width", 0) or 0), int(params.get("height", 0) or 0))
                self._json({"status": "ok", "strips": [{"y0": a, "y1": b} for a, b in plan]})
            elif path == "/api/inbox/dataset/stats":
                self._json({"status": "ok", **inbox_mod.dataset_stats(self.vault_path)})
            elif path == "/api/inbox/dataset/export":
                data = inbox_mod.export_dataset(self.vault_path, fmt=params.get("format", "omrs_jsonl"),
                                                include_raw=params.get("raw", "1") != "0")
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="omrs-dataset-{stamp}.zip"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except Exception as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    def _trainpanel_post(self, path):
        if path == "/api/trainpanel/control":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 4096:
                    self.close_connection = True
                    raise ValueError("控制请求过大或为空")
                remote, client_ip, _ = self._security_context()
                session = self._active_session
                actor = {'auth_mode': 'pin_session' if session else
                         'lan_exempt' if remote else 'local',
                         'session_id': session['id'] if session else '',
                         'client_ip': client_ip}
                value = traincontrol.submit(self.vault_path, json.loads(self.rfile.read(length)), actor=actor)
                self._json({"status":"ok", "operation":value}, 202)
            except traincontrol.Conflict as exc:
                self._json({"status":"error", "msg":str(exc)}, 409)
            except (ValueError, OSError, KeyError) as exc:
                self._json({"status":"error", "msg":str(exc)}, 400)
            return
        if path == "/api/trainpanel/review":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 16384:
                    self.close_connection = True
                    raise ValueError("复核请求过大或为空")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict): raise ValueError("复核请求必须是对象")
                value = trainaudit_mod.save_review(trainpanel_mod.train_dir(self.vault_path),
                    data.get("audit", ""), data.get("case", ""), data.get("revision"),
                    data.get("action"), data.get("verdict"), data.get("note", ""), source="user")
                self._json({"status":"ok", **value})
            except trainaudit_mod.Conflict as exc:
                self._json({"status":"error", "msg":str(exc)}, 409)
            except (ValueError, OSError, sqlite3.Error) as exc:
                self._json({"status":"error", "msg":str(exc)}, 400)
            return
        if path != "/api/trainpanel/try":
            self._json({"status": "error", "msg": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            content_type = self.headers.get("Content-Type", "")
            if length <= 0 or length > trainpanel_mod.MAX_UPLOAD_BYTES + 65536:
                self.close_connection = True
                raise ValueError("请求超过 15 MB 或为空")
            if "multipart/form-data" not in content_type:
                raise ValueError("请用 multipart/form-data 上传图片")
            body = self.rfile.read(length)
            result = trainpanel_mod.try_image(self.vault_path, self._multipart_files(body, content_type))
            self._json({"status": "ok", **result})
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    def _trainpanel_get(self, path, params):
        try:
            if path == "/train":
                self._serve("assets/app/trainpanel.html", "text/html")
            elif path == "/api/trainpanel/manager":
                self._json({"status":"ok", **traincontrol.overview(self.vault_path)})
            elif path == "/api/trainpanel/audits":
                self._json({"status":"ok", **trainaudit_mod.list_audits(self.vault_path)})
            elif path == "/api/trainpanel/audit":
                self._json({"status":"ok", **trainaudit_mod.detail(self.vault_path, params.get("id", ""), params)})
            elif path == "/api/trainpanel/reviews":
                root = trainpanel_mod.train_dir(self.vault_path)
                trainaudit_mod.audit(root, params.get("id", ""))
                rows = trainaudit_mod.reviews(root, params.get("id", ""), params.get("case", ""))
                self._json({"status":"ok", "reviews":rows[-100:]})
            elif path == "/api/trainpanel/audit-image":
                image = trainaudit_mod.image_path(self.vault_path, params.get("id", ""), params.get("resource", ""))
                data = image.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png" if image.suffix.lower()==".png" else "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, no-store")
                self.end_headers()
                self.wfile.write(data)
            elif path == "/api/trainpanel/overview":
                self._json({"status": "ok", **trainpanel_mod.overview(self.vault_path)})
            elif path == "/api/trainpanel/run":
                self._json({"status": "ok", **trainpanel_mod.run_detail(self.vault_path, params.get("name", ""))})
            elif path == "/api/trainpanel/service":
                self._json({"status": "ok", **trainpanel_mod.service(self.vault_path)})
            elif path == "/api/trainpanel/overlay":
                image = trainpanel_mod.overlay_path(self.vault_path, params.get("run", ""), params.get("name", ""))
                data = image.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png" if image.suffix.lower() == ".png" else "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, no-store")
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    # ────────────── 框选标注集 /api/annotate/* 与独立标注页 /annotate ──────────────
    def _annotate_get(self, path, params):
        try:
            if path == "/annotate":
                self._serve("assets/app/annotate.html", "text/html")
            elif path == "/api/annotate/images":
                self._json({"status": "ok", "images": annotate_mod.list_images(self.vault_path),
                            "stats": annotate_mod.stats(self.vault_path)})
            elif path == "/api/annotate/stats":
                self._json({"status": "ok", **annotate_mod.stats(self.vault_path)})
            elif path == "/api/annotate/raw":
                mime, data = annotate_mod.raw_file(self.vault_path, params.get("id", ""))
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            elif path == "/api/annotate/export":
                # 大批量标注集可能有几 GB：先写临时文件，再分块发送
                with tempfile.TemporaryFile() as tmp:
                    size = annotate_mod.export(self.vault_path, fmt=params.get("format", "omrs_jsonl"),
                                               include_todo=params.get("all", "") in {"1", "true", "yes"}, fileobj=tmp)
                    tmp.seek(0)
                    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", f'attachment; filename="omrs-annotate-{stamp}.zip"')
                    self.send_header("Content-Length", str(size))
                    self.end_headers()
                    shutil.copyfileobj(tmp, self.wfile, 1024 * 1024)
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except Exception as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    def _annotate_post(self, path):
        try:
            length = int(self.headers.get("Content-Length", 0))
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(length)
            if path == "/api/annotate/upload":
                if "multipart/form-data" not in content_type:
                    raise ValueError("请用 multipart/form-data 上传图片")
                self._json({"status": "ok", **annotate_mod.upload(
                    self.vault_path, self._multipart_files(body, content_type))})
                return
            data = json.loads(body.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError("请求体必须是 JSON 对象")
            if path == "/api/annotate/save":
                self._json({"status": "ok", "image": annotate_mod.save(
                    self.vault_path, data.get("id", ""), data.get("boxes"), data.get("status"),
                    data.get("expected_revision"))})
            elif path == "/api/annotate/delete":
                self._json({"status": "ok", **annotate_mod.delete(
                    self.vault_path, data.get("id", ""), data.get("expected_revision"))})
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except annotate_mod.RevisionConflict as exc:
            self._json({"status": "error", "code": "revision_conflict", "msg": str(exc),
                        "current_revision": exc.current_revision}, 409)
        except Exception as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    # ────────────────────────── AI 草稿区 /api/drafts/* 只读接口（P1-1；写接口见 P2） ──────────────────────────
    def _drafts_get(self, path, params):
        try:
            if path == "/api/drafts/list":
                self._json({"status": "ok", "drafts": drafts_mod.list_drafts(
                    self.vault_path, status=params.get("status") or None,
                    conversation_id=params.get("conversation") or None,
                    limit=params.get("limit") or 50)})
            elif path == "/api/drafts/item":
                self._json({"status": "ok", "draft": drafts_mod.get_draft(self.vault_path, params.get("id", ""))})
            elif path == "/api/drafts/image":
                sha = params.get("sha", "")
                if not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
                    raise ValueError("sha 参数不合法")
                data_url = drafts_mod.image_data_url(self.vault_path, sha)
                mime, encoded = data_url.split(";base64,", 1)
                mime = mime[len("data:"):]
                data = base64.b64decode(encoded)
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            elif path == "/api/drafts/counts":
                self._json({"status": "ok", "counts": drafts_mod.counts(self.vault_path)})
            elif path == "/api/drafts/job":
                self._json({"status": "ok", "job": drafts_mod.get_job(self.vault_path, params.get("id", ""))})
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except drafts_mod.DraftError as exc:
            payload = {"status": "error", "msg": str(exc), "code": exc.code}
            if exc.current_revision is not None:
                payload["current_revision"] = exc.current_revision
            self._json(payload, exc.status)
        except Exception as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    def _drafts_post(self, path):
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                raise drafts_mod.DraftError("请求必须是 JSON 对象")
            draft_id, revision = data.get("id"), data.get("revision")
            if path == "/api/drafts/update":
                result = {"draft": drafts_mod.update_draft(
                    self.vault_path, draft_id, revision, data.get("fields"), data.get("blocks"),
                    data.get("source_images"))}
            elif path == "/api/drafts/discard":
                result = {"draft": drafts_mod.discard_draft(self.vault_path, draft_id, revision)}
            elif path == "/api/drafts/commit":
                result = drafts_mod.commit_draft(self.vault_path, draft_id, revision, data.get("crops"))
            elif path == "/api/drafts/boxes":
                result = {"draft": drafts_mod.set_boxes(self.vault_path, draft_id, revision,
                                                          data.get("blocks"), data.get("training_boxes"))}
            elif path == "/api/drafts/extract":
                result = {"job": drafts_mod.start_extract(self.vault_path, draft_id, revision,
                                                            data.get("block_ids"), data.get("crops"))}
            elif path == "/api/drafts/detect":
                result = {"job": drafts_mod.start_detect(self.vault_path, draft_id, revision,
                                                           data.get("sha"))}
            elif path == "/api/drafts/image/train":
                result = drafts_mod.set_image_training(self.vault_path, draft_id, revision,
                                                       data.get("sha"), data.get("enabled"))
            elif path == "/api/drafts/cleanup":
                if data:
                    raise drafts_mod.DraftError("cleanup 不接受自定义参数")
                result = drafts_mod.cleanup(self.vault_path)
            else:
                self._json({"status": "error", "msg": "not found", "code": "not_found"}, 404)
                return
            self._json({"status": "ok", **result})
        except drafts_mod.DraftError as exc:
            payload = {"status": "error", "msg": str(exc), "code": exc.code}
            if exc.current_revision is not None:
                payload["current_revision"] = exc.current_revision
            self._json(payload, exc.status)
        except (ValueError, TypeError) as exc:
            self._json({"status": "error", "msg": str(exc), "code": "invalid"}, 400)

    # ────────────────────────── 系统运行记录 ──────────────────────────
    def _runtime_records_get(self, params, detail=False):
        from . import runtime_records
        try:
            if detail:
                seq = int(params.get("seq", "0"))
                if seq <= 0:
                    raise ValueError("记录编号不正确")
                row = runtime_records.detail(self.vault_path, seq)
                self._json({"status": "ok", "detail": row} if row else
                           {"status": "error", "msg": "运行记录不存在"}, 200 if row else 404)
            else:
                self._json({"status": "ok", **runtime_records.list_records(self.vault_path, params)})
        except (ValueError, TypeError) as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)
        except (OSError, sqlite3.Error):
            self._json({"status": "error", "msg": "运行记录暂时无法读取，请检查存储后重试。"}, 503)

    # ────────────────────────── MCP Key 管理 ──────────────────────────
    def _mcp_get(self, path, params):
        try:
            if path == "/api/mcp/keys":
                from .mcp.keys import list_keys
                self._json({"status": "ok", "keys": list_keys(self.vault_path)})
            elif path == '/api/mcp/operations/detail':
                from .mcp_operations import get
                self._json({'status': 'ok', 'operation': get(self.vault_path, params.get('operation_id', ''))})
            elif path == '/api/mcp/exports/download':
                from .mcp_exports import download
                payload, filename = download(self.vault_path, params.get('export_id', ''))
                self._download(payload, filename, 'text/html; charset=utf-8')
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except RequestError as exc:
            self._json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 404 if exc.code == 'not_found' else 410 if exc.code == 'export_expired' else 409)
        except (ValueError, TypeError) as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)
        except (OSError, sqlite3.Error):
            self._json({'status': 'error', 'msg': 'MCP 管理数据暂时无法读取'}, 503)

    def _mcp_post(self, path):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 <= length <= 16 * 1024:
                raise ValueError("Key 管理请求超过大小限制")
            body = self.rfile.read(length)
            data = json.loads(body or b"{}")
            if not isinstance(data, dict):
                raise ValueError("请求必须是 JSON 对象")
            from .mcp.keys import create_key, revoke_key, update_scopes
            if path == "/api/mcp/keys":
                if set(data) - {"name", "scopes", "expires_at"}:
                    raise ValueError("Key 管理请求包含不允许的字段")
                self._json({"status": "ok", "key": create_key(
                    self.vault_path, data.get("name", ""), data.get("scopes"), data.get("expires_at"))})
            elif path == "/api/mcp/keys/revoke":
                if set(data) != {"key_id"}:
                    raise ValueError("吊销请求只能包含 key_id")
                self._json({"status": "ok", "key": revoke_key(self.vault_path, data.get("key_id", ""))})
            elif path == '/api/mcp/keys/update':
                if set(data) != {'key_id', 'scopes'}:
                    raise ValueError('权限编辑只接受 key_id 和 scopes')
                self._json({'status': 'ok', 'key': update_scopes(self.vault_path, data['key_id'], data['scopes'])})
            elif path == '/api/mcp/operations/decide':
                if set(data) != {'operation_id', 'decision'}:
                    raise ValueError('确认请求只接受 operation_id 和 decision')
                from .mcp_operations import decide
                self._json({'status': 'ok', 'operation': decide(self.vault_path, data['operation_id'], data['decision'])})
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except RequestError as exc:
            self._json({'status': 'error', 'error': exc.code, 'msg': str(exc)}, 404 if exc.code == 'not_found' else 409)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)
        except (OSError, sqlite3.Error):
            self._json({'status': 'error', 'msg': 'MCP 管理数据暂时无法保存，请重试'}, 503)

    def _mcp_credential_present(self):
        """普通 Web 端口拒绝 MCP 专用凭据，防止跨接口借道。"""
        # 一些只调用路由方法的单元测试 handler 不经过 BaseHTTPRequestHandler
        # 初始化，因此没有 headers 属性；缺少请求头等同于没有 MCP 凭据。
        headers = getattr(self, "headers", None)
        if headers is None:
            return False
        return bool(headers.get("X-OMRS-MCP-Key") or
                    (headers.get("Authorization") or "").lower().startswith("bearer "))

    def _entry_background_post(self):
        """分块接收入口背景，文件落盘后才在写锁内提交配置。"""
        raw_path = None
        upload_path = None
        try:
            length = int(self.headers.get("Content-Length", 0))
            max_request = entry_background.MAX_UPLOAD_BYTES + 1024 * 1024
            if length <= 0 or length > max_request:
                raise ValueError("入口背景请求不能超过 200 MB")
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                raise ValueError("请用 multipart/form-data 上传入口背景")
            fields, file_info, raw_path = self._read_entry_background_multipart(length, content_type)
            upload = None
            if file_info:
                filename, declared_mime, upload_path = file_info
                upload = entry_background.inspect_upload(upload_path, filename, declared_mime)
                upload["path"] = upload_path
            mode = fields.get("mode", entry_background.DEFAULT_MODE)
            style = fields.get("style", entry_background.DEFAULT_STYLE)
            blur = fields.get("blur_px", entry_background.DEFAULT_BLUR_PX)
            asset_id = fields.get("asset_id", "")
            with locking.write_lock():
                state = entry_background.save_state(
                    self.vault_path, mode, style, blur, asset_id=asset_id, upload=upload,
                )
            upload_path = None  # save_state 已经把新文件原子移动到最终路径
            self._json({"status": "ok", "entry_background": state})
        except (ValueError, TypeError, OSError) as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)
        finally:
            for path in (raw_path, upload_path):
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def _read_entry_background_multipart(self, length, content_type):
        """把 multipart 请求先流式写入临时文件，再用 mmap 分离字段和文件。

        这样 200MB 视频不会同时驻留在 Python 堆内存中；请求只允许一个 file 字段。
        """
        marker_text = "boundary="
        if marker_text not in content_type:
            raise ValueError("缺少 multipart boundary")
        boundary = content_type.split(marker_text, 1)[1].strip().strip('"').split(";", 1)[0]
        if not boundary or len(boundary) > 200:
            raise ValueError("multipart boundary 不合法")
        upload_dir = entry_background.background_dir(self.vault_path)
        fd, raw_path = tempfile.mkstemp(prefix=".request-", suffix=".multipart", dir=upload_dir)
        try:
            with os.fdopen(fd, "wb") as raw:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("上传请求提前结束")
                    raw.write(chunk)
                    remaining -= len(chunk)
                raw.flush()
                os.fsync(raw.fileno())
            fields = {}
            file_info = None
            boundary_bytes = b"--" + boundary.encode("ascii", errors="strict")
            with open(raw_path, "rb") as raw, mmap.mmap(raw.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                marker = mapped.find(boundary_bytes)
                if marker < 0:
                    raise ValueError("multipart 请求缺少边界")
                while marker >= 0:
                    after = marker + len(boundary_bytes)
                    if mapped[after:after + 2] == b"--":
                        break
                    if mapped[after:after + 2] != b"\r\n":
                        raise ValueError("multipart 边界格式错误")
                    part_start = after + 2
                    next_marker = mapped.find(boundary_bytes, part_start)
                    if next_marker < 0:
                        raise ValueError("multipart 请求不完整")
                    part_end = next_marker - 2 if mapped[next_marker - 2:next_marker] == b"\r\n" else next_marker
                    header_end = mapped.find(b"\r\n\r\n", part_start, part_end)
                    if header_end < 0:
                        raise ValueError("multipart 字段缺少头部")
                    header_text = bytes(mapped[part_start:header_end]).decode("utf-8", errors="replace")
                    headers = {}
                    for line in header_text.split("\r\n"):
                        if ":" in line:
                            key, value = line.split(":", 1)
                            headers[key.strip().lower()] = value.strip()
                    disposition = headers.get("content-disposition", "")
                    name_match = re.search(r'name="([^"]+)"', disposition)
                    if not name_match:
                        raise ValueError("multipart 字段缺少 name")
                    name = name_match.group(1)
                    body_start = header_end + 4
                    body_size = max(0, part_end - body_start)
                    filename_match = re.search(r'filename="([^"]*)"', disposition)
                    if filename_match:
                        if file_info is not None:
                            raise ValueError("一次只能上传一个入口背景文件")
                        filename = os.path.basename(filename_match.group(1)) or "background"
                        fd, path = tempfile.mkstemp(prefix=".media-", suffix=".upload", dir=upload_dir)
                        with os.fdopen(fd, "wb") as target:
                            offset = body_start
                            while offset < part_end:
                                block = mapped[offset:min(offset + 1024 * 1024, part_end)]
                                target.write(block)
                                offset += len(block)
                            target.flush()
                            os.fsync(target.fileno())
                        file_info = (filename, headers.get("content-type", ""), path)
                    else:
                        if body_size > 64 * 1024:
                            raise ValueError("入口背景字段过大")
                        fields[name] = bytes(mapped[body_start:part_end]).decode("utf-8", errors="strict")
                    marker = next_marker
            return fields, file_info, raw_path
        except Exception:
            try:
                os.remove(raw_path)
            except OSError:
                pass
            raise

    def _multipart_files(self, body, content_type):
        """解析 multipart 里的全部文件 → [(filename, bytes)]。"""
        marker = "boundary="
        if marker not in content_type:
            raise ValueError("缺少 multipart boundary")
        boundary = content_type.split(marker, 1)[1].strip().strip('"').split(";")[0]
        delimiter = ("--" + boundary).encode("utf-8")
        files = []
        for part in body.split(delimiter):
            if b"Content-Disposition" not in part or b"\r\n\r\n" not in part:
                continue
            headers, payload = part.split(b"\r\n\r\n", 1)
            if payload.endswith(b"\r\n"):
                payload = payload[:-2]
            header_text = headers.decode("utf-8", errors="ignore")
            if "filename=" not in header_text:
                continue
            filename = "image"
            # 只看 Content-Disposition 行，避免把 Content-Type 行拼进文件名
            header_text = next((line for line in header_text.split("\r\n") if "Content-Disposition" in line), header_text)
            for item in header_text.split(";"):
                item = item.strip()
                if item.startswith("filename="):
                    filename = item.split("=", 1)[1].strip().strip('"') or filename
                    break
            files.append((os.path.basename(filename), payload))
        return files

    def _inbox_post(self, path):
        try:
            length = int(self.headers.get("Content-Length", 0))
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(length)
            if path == "/api/inbox/upload":
                if "multipart/form-data" in content_type:
                    files = self._multipart_files(body, content_type)
                    source = "phone" if "Mobile" in (self.headers.get("User-Agent") or "") else "desktop"
                    result = inbox_mod.upload_images(self.vault_path, files, source=source)
                else:
                    data = json.loads(body.decode("utf-8") or "{}")
                    files = []
                    for entry in data.get("images", []):
                        mime, raw = inbox_mod._data_url_bytes(entry.get("data") if isinstance(entry, dict) else entry)
                        files.append((entry.get("name", "image") if isinstance(entry, dict) else "image", raw))
                    result = inbox_mod.upload_images(self.vault_path, files, source=data.get("source", "desktop"))
                self._json({"status": "ok", **result})
                return
            data = json.loads(body.decode("utf-8") or "{}")
            if path == "/api/inbox/item/update":
                cards = data.get("cards") if isinstance(data.get("cards"), dict) else {}
                deprecated = [f"cards.{key}.page" for key, form in cards.items()
                              if isinstance(form, dict) and "page" in form]
                self._json({"status": "ok", "item": inbox_mod.update_item(self.vault_path, data.get("id", ""), data,
                                                                            require_epoch=True, require_version=True),
                            **({"deprecated_fields": deprecated} if deprecated else {})})
            elif path == "/api/inbox/item/reset":
                self._json({"status": "ok", "item": inbox_mod.reset_item(
                    self.vault_path, data.get("id", ""), data.get("expected_revision"),
                    data.get("reset_epoch"), require_version=True)})
            elif path == "/api/inbox/discard":
                entries = data.get("items") or ([data] if data.get("id") else [
                    {"id": item_id} for item_id in data.get("ids") or []])
                self._json({"status": "ok", "results": inbox_mod.discard_items(
                    self.vault_path, entries, require_version=True)})
            elif path == "/api/inbox/jobs":
                self._json({"status": "ok", "job": inbox_mod.start_job(self.vault_path, data.get("type", ""), data)})
            elif path == "/api/inbox/commit":
                deprecated = ["form.page"] if "page" in (data.get("form") or {}) else []
                self._json({"status": "ok", **inbox_mod.commit_item(
                    self.vault_path, data.get("id", ""), card=data.get("card", 1),
                    form=data.get("form") or {}, crops=data.get("crops") or {},
                    expected_revision=data.get("expected_revision"), reset_epoch=data.get("reset_epoch"),
                    require_version=True), **({"deprecated_fields": deprecated} if deprecated else {})})
            elif path == "/api/inbox/crops":
                saved = [inbox_mod.save_crop(self.vault_path, rid, url) for rid, url in (data.get("crops") or {}).items()]
                self._json({"status": "ok", "saved": len(saved)})
            elif path == "/api/inbox/cleanup":
                days = data.get("discarded_days")
                self._json({"status": "ok", **inbox_mod.cleanup(
                    self.vault_path, discarded_days=int(days) if days not in (None, "") else None,
                    crops=bool(data.get("crops")))})
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except inbox_mod.InboxConflict as exc:
            self._json({"status": "error", "msg": str(exc), "code": exc.code,
                        "current_revision": exc.current_revision}, 409)
        except Exception as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    def _handle_backup_import(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(length)
            filename, payload = self._multipart_file(body, content_type)
            result = prepare_backup_import(self.vault_path, payload, filename)
            self._json(result)
        except Exception as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    def _multipart_file(self, body, content_type):
        if "multipart/form-data" not in content_type:
            filename = self.headers.get("X-Filename", "backup.zip")
            return filename, body
        marker = "boundary="
        if marker not in content_type:
            raise ValueError("缺少 multipart boundary")
        boundary = content_type.split(marker, 1)[1].strip().strip('"')
        delimiter = ("--" + boundary).encode("utf-8")
        for part in body.split(delimiter):
            if b"Content-Disposition" not in part or b"\r\n\r\n" not in part:
                continue
            headers, payload = part.split(b"\r\n\r\n", 1)
            if payload.endswith(b"\r\n"):
                payload = payload[:-2]
            header_text = headers.decode("utf-8", errors="ignore")
            if "filename=" not in header_text:
                continue
            filename = "backup.zip"
            for item in header_text.split(";"):
                item = item.strip()
                if item.startswith("filename="):
                    filename = item.split("=", 1)[1].strip().strip('"') or filename
                    break
            return os.path.basename(filename), payload
        raise ValueError("未找到上传的备份文件")

    def _security_context(self):
        # Directly constructed handlers in unit tests have no socket metadata.
        synthetic = not hasattr(self, "client_address")
        peer = self.client_address[0] if not synthetic else "127.0.0.1"
        headers = getattr(self, "headers", {})
        host = (headers.get("Host") or ("127.0.0.1" if synthetic else "")).strip()
        try:
            hostname = urllib.parse.urlsplit("http://" + host).hostname or ""
        except ValueError:
            hostname = ""
        trusted = {value.strip() for value in os.environ.get("OMRS_TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if value.strip()}
        proxy = peer in trusted
        forwarded = (headers.get("X-Real-IP") or "").strip() if proxy else ""
        client_ip = forwarded if forwarded and self._valid_ip(forwarded) else peer
        scheme = "http"
        if proxy and (headers.get("X-Forwarded-Proto") or "").strip().lower() in {"http", "https"}:
            scheme = headers["X-Forwarded-Proto"].strip().lower()
        proxy_headers_present = proxy and any(headers.get(name) for name in (
            "X-Real-IP", "X-Forwarded-Proto", "X-Forwarded-Host"))
        direct_local = (security.is_loopback(peer) and
                        (security.is_loopback(hostname) or hostname == "localhost") and
                        not proxy_headers_present)
        remote = not direct_local
        return remote, client_ip, scheme

    @staticmethod
    def _valid_ip(value):
        import ipaddress
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    def _cookie_token(self):
        try:
            jar = SimpleCookie()
            jar.load(self.headers.get("Cookie") or "")
            return jar[security.COOKIE_NAME].value if security.COOKIE_NAME in jar else ""
        except Exception:
            return ""

    def _sign_report_image(self, name):
        if not security.report_image_allowed(self.vault_path, name):
            raise ValueError("报告图片必须是附件目录中的文件名")
        return security.sign_image(self._active_session, name)

    def _serve_entry_background(self):
        media = entry_background.media_content(self.vault_path)
        if not media:
            self.send_error(404)
            return
        path, asset = media
        try:
            stat = os.stat(path)
            etag = f'W/"{asset["id"]}-{stat.st_size:x}-{stat.st_mtime_ns:x}"'
            if self._asset_not_modified(etag, int(stat.st_mtime)):
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", asset["mime"])
            self.send_header("Content-Length", str(stat.st_size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("ETag", etag)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with open(path, "rb") as stream:
                shutil.copyfileobj(stream, self.wfile, length=1024 * 1024)
        except (OSError, ValueError):
            self.send_error(404)

    def _authorize(self, path, params):
        remote, _, _ = self._security_context()
        self._active_session = None
        # A configured PIN also gates the lock-screen handoff on local access.
        # The existing local API exemption remains unchanged after the
        # dashboard has been opened.
        if path in ("/", "/index.html") and params.get("unlocked") == "1" and \
                security.auth_summary(self.vault_path)["pin_configured"]:
            session = security.session_for(self.vault_path, self._cookie_token())
            if session:
                self._active_session = session
                return True
            self.send_response(302)
            self.send_header("Location", "/login?next=" + urllib.parse.quote(self.path, safe=""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        if not remote or self._direct_lan_exempt():
            return True
        if path in {
            "/assets/vendor/entry-scene.js",
            "/assets/vendor/entry-math-atlas.svg",
            "/assets/vendor/entry-fallback.webp",
        }:
            return True
        session = security.session_for(self.vault_path, self._cookie_token())
        if session:
            self._active_session = session
            return True
        if path == "/api/image" and security.valid_image_grant(
                self.vault_path, params.get("name", ""), params.get("grant_session", ""),
                params.get("grant_expires", ""), params.get("grant_signature", "")):
            return True
        if path.startswith("/api/") or path.startswith("/assets/"):
            self._json({"status": "error", "msg": "请先输入 PIN 登录"}, 401)
        else:
            self.send_response(302)
            self.send_header("Location", "/login?next=" + urllib.parse.quote(self.path, safe=""))
            self.send_header("Content-Length", "0")
            self.end_headers()
        return False

    def _direct_lan_exempt(self):
        peer = self.client_address[0] if hasattr(self, "client_address") else "127.0.0.1"
        trusted = {value.strip() for value in os.environ.get(
            "OMRS_TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if value.strip()}
        return security.direct_lan_exempt(self.vault_path, peer, peer in trusted)

    def _check_write_origin(self):
        site = (self.headers.get("Sec-Fetch-Site") or "").lower()
        if site and site not in {"same-origin", "none"}:
            self._json({"status": "error", "msg": "拒绝跨站状态修改请求"}, 403)
            return False
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        _, _, scheme = self._security_context()
        try:
            submitted = urllib.parse.urlsplit(origin)
            expected = urllib.parse.urlsplit(f"{scheme}://{self.headers.get('Host', '').strip()}")
            default_port = 443 if scheme == "https" else 80
            valid = (submitted.scheme == scheme and submitted.hostname == expected.hostname and
                     (submitted.port or default_port) == (expected.port or default_port) and
                     not submitted.path and not submitted.query and not submitted.fragment and
                     not submitted.username and not submitted.password)
        except ValueError:
            valid = False
        if not valid:
            self._json({"status": "error", "msg": "拒绝跨站状态修改请求"}, 403)
            return False
        return True

    def _auth_status(self):
        remote, _, scheme = self._security_context()
        session = security.session_for(self.vault_path, self._cookie_token()) if remote else None
        lan_exempt = remote and self._direct_lan_exempt()
        self._json({"status": "ok", "instance_id": OMRS_INSTANCE_ID,
                    "remote": remote, "authenticated": bool(session) or not remote or lan_exempt,
                    "lan_pin_exempt": lan_exempt,
                    "pin_configured": security.auth_summary(self.vault_path)["pin_configured"],
                    "warning_required": bool(remote and session and scheme == "http" and not session["warning_ack"])})

    def _auth_login(self):
        remote, client_ip, scheme = self._security_context()
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body or b"{}")
            if not isinstance(data, dict):
                raise ValueError("登录请求必须是 JSON 对象")
            token, _ = security.login(self.vault_path, str(data.get("pin", "")), client_ip)
            self.send_response(200)
            attrs = f"{security.COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={security.ABSOLUTE_SECONDS}"
            if scheme == "https":
                attrs += "; Secure"
            self.send_header("Set-Cookie", attrs)
            payload = b'{"status":"ok"}'
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    def _auth_post(self, path):
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body or b"{}")
            if not isinstance(data, dict):
                raise ValueError("请求体必须是 JSON 对象")
            remote, client_ip, _ = self._security_context()
            session = self._active_session
            if path == "/api/auth/pin":
                # Remote callers must prove the existing PIN. A LAN-exempt device may
                # set the very first PIN: it already has full access, so nothing widens.
                if (remote and security.auth_summary(self.vault_path)["pin_configured"] and
                        not security.verify_pin_limited(
                            self.vault_path, str(data.get("current_pin", "")), client_ip)):
                    raise ValueError("当前 PIN 错误")
                if data.get("pin"):
                    result = security.set_pin(self.vault_path, str(data["pin"]), data.get("idle_minutes", 30))
                else:
                    result = security.set_idle_minutes(self.vault_path, data.get("idle_minutes", 30))
                self._json({"status": "ok", **result})
            elif path == "/api/auth/disable":
                if remote or load_config(self.vault_path).get("allow_external"):
                    raise ValueError("关闭局域网访问后才能停用 PIN")
                security.disable_pin(self.vault_path)
                self._json({"status": "ok"})
            elif path == "/api/auth/activity":
                if session:
                    security.activity(session)
                self._json({"status": "ok"})
            elif path == "/api/auth/warning-ack":
                if session:
                    session["warning_ack"] = True
                self._json({"status": "ok"})
            elif path == "/api/auth/logout":
                security.logout(self._cookie_token())
                self.send_response(200)
                self.send_header("Set-Cookie", f"{security.COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    def _serve_entry(self):
        background = entry_background.public_state(self.vault_path)
        asset = background.get("asset")
        entry_payload = {
            "mode": background.get("mode", entry_background.DEFAULT_MODE),
            "style": background.get("style", entry_background.DEFAULT_STYLE),
            "blur_px": background.get("blur_px", entry_background.DEFAULT_BLUR_PX),
            "kind": asset.get("kind") if asset else "",
            "asset_url": f"/api/entry-background?v={asset.get('id')}" if asset else "",
            # A fresh process gets a fresh handoff token, so a browser cannot
            # reuse a cached dashboard document from before a restart/deploy.
            "reload_token": OMRS_INSTANCE_ID,
        }
        entry_payload_json = json.dumps(entry_payload, ensure_ascii=False).replace("</", "<\\/")
        page = '''\n<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#020304"><title>OMRS · 入口</title><style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#020304;color:#d0c4ab}*{box-sizing:border-box}html{scrollbar-width:none;background:#020304}html::-webkit-scrollbar{width:0;height:0;display:none}body{background:#020304;min-width:320px;min-height:100vh;margin:0;scrollbar-width:none}body::-webkit-scrollbar{width:0;height:0;display:none}.gravity-journey{background:#020304;min-height:850svh;position:relative}.gravity-viewport{opacity:0;touch-action:pan-y;width:100%;height:100dvh;transition:opacity 1.5s;position:fixed;inset:0;overflow:hidden}.gravity-viewport canvas{width:100%;height:100%;display:block}.gravity-journey[data-status=ready] .gravity-viewport,.gravity-journey[data-status=custom-ready] .gravity-viewport,.gravity-journey[data-status=fallback] .gravity-viewport{opacity:1}.entry-custom{display:none;position:absolute;inset:-4%;overflow:hidden;background:#020304}.gravity-journey[data-status=custom-ready] .entry-custom{display:block}.entry-custom:after{content:\"\";position:absolute;inset:0;background:linear-gradient(180deg,#02030444,#02030466 60%,#020304bb)}.entry-custom img,.entry-custom video{display:block;width:100%;height:100%;object-fit:cover;transform:scale(1.05);filter:blur(var(--entry-blur,0px))}.gravity-core-handle,.gravity-core-handle:hover{z-index:2;box-shadow:none;cursor:grab;touch-action:none;user-select:none;border:0;border-radius:50%;padding:0;transition:none;position:absolute;transform:translate(-50%,-50%);background:transparent!important}.gravity-core-handle[data-dragging=true]{cursor:grabbing}.gravity-core-handle:focus-visible{outline-offset:5px;outline:1px solid #d5bc8277}.gravity-journey:not([data-status=ready]) .gravity-core-handle{visibility:hidden}.gravity-loading{background:#020304;flex-direction:column;justify-content:center;align-items:center;gap:24px;display:flex;position:fixed;inset:0}.gravity-loading-orbit{border:1px solid #51422b;border-top-color:#e5c58c;border-radius:50%;width:38px;height:38px;animation:gravity-orbit 2.5s linear infinite}.gravity-loading-label{color:#d0c4ab;letter-spacing:.23em;border:0;padding:0;font-size:10px;font-weight:400}.gravity-fallback{background:#000;position:fixed;inset:0}.gravity-fallback img{object-fit:cover;width:100%;height:100%}.gravity-fallback .gravity-loading-label{white-space:normal;background:#000b;max-width:90vw;padding:12px;line-height:1.7;position:absolute;bottom:40px;left:50%;transform:translate(-50%)}@keyframes gravity-orbit{to{transform:rotate(360deg)}}[data-layout]{color:#d0c4ab;opacity:.65;letter-spacing:.08em;pointer-events:none;height:100dvh;position:fixed;inset:0;z-index:50;padding:40px}.layout-grid{display:grid;height:100%;width:100%;grid-template-columns:repeat(6,minmax(0,1fr));grid-template-rows:repeat(6,minmax(0,1fr));font-size:14px;text-transform:uppercase}.layout-top{height:40px;width:100%;grid-column:1/8}.layout-nav{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}.layout-nav div:nth-child(2){text-align:center}.layout-nav div:nth-child(3){text-align:right}.layout-footer{display:flex;flex-direction:column;justify-content:flex-end;grid-row:7/8}.layout-footer.left{grid-column:2/3}.layout-footer.links{grid-column:1/2}.layout-footer.right{grid-column:7/8}.entry-access{pointer-events:auto;position:absolute;right:clamp(22px,9vw,140px);bottom:clamp(88px,15vh,150px);width:min(340px,calc(100vw - 44px));padding:20px 0 18px;border-top:1px solid #d5bc8277;border-bottom:1px solid #d5bc8244;text-transform:none;letter-spacing:.03em;opacity:1;color:#e4d6b8;text-shadow:0 1px 10px #000}.entry-access:before{content:"";position:absolute;top:-2px;left:0;width:34px;height:3px;background:#e5c58c;box-shadow:0 0 16px #d5bc8277}.entry-access .kicker{margin:0 0 10px;color:#d5bc82;font:10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.2em;text-transform:uppercase}.entry-access h1{margin:0 0 8px;font-size:20px;font-weight:400;letter-spacing:.04em}.entry-access .hint{min-height:20px;margin:0 0 17px;color:#b2a68f;font-size:12px;line-height:1.55}.entry-access .hint.error{color:#e6a9a0}.entry{display:grid;gap:10px}.entry[hidden]{display:none}.entry input{width:100%;height:38px;padding:0 2px;border:0;border-bottom:1px solid #d5bc82aa;border-radius:0;background:transparent;color:#f8ecd4;outline:none;font-size:18px;letter-spacing:.4em}.entry input::placeholder{color:#d5bc8266;font:10px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.14em}.entry input:focus{border-bottom-color:#f1d79e;box-shadow:0 8px 18px -15px #f1d79e}.entry button{display:flex;align-items:center;justify-content:space-between;width:100%;height:38px;padding:0 12px;border:1px solid #d5bc82aa;border-radius:0;background:transparent;color:#e5c58c;font-size:10px;letter-spacing:.18em;text-transform:uppercase;cursor:pointer;transition:background-color .18s ease,color .18s ease,transform .18s cubic-bezier(.23,1,.32,1)}.entry button:after{content:"↗";font-size:17px;line-height:1}.entry button:hover{background:#e5c58c;color:#080807;transform:translateY(-1px)}.entry button:disabled{cursor:wait;opacity:.5;transform:none}.entry#enter[hidden]{display:none}.entry#enter{display:flex;align-items:center;justify-content:space-between;width:100%;height:38px;padding:0 12px;border:1px solid #d5bc82aa;border-radius:0;background:transparent;color:#e5c58c;font-size:10px;letter-spacing:.18em;text-transform:uppercase;cursor:pointer;transition:background-color .18s ease,color .18s ease,transform .18s cubic-bezier(.23,1,.32,1)}.entry#enter:after{content:"↗";font-size:17px;line-height:1}.entry#enter:hover{background:#e5c58c;color:#080807;transform:translateY(-1px)}.entry-meta{display:flex;justify-content:space-between;margin-top:15px;color:#b2a68f99;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.11em;text-transform:uppercase}.entry-meta strong{color:#e5c58c;font-size:12px;font-weight:400}.entry-meta .workspace{color:#b2a68f99}.gravity-journey[data-exploring=true] .entry-access{opacity:.18;transition:opacity .5s ease}.gravity-journey[data-exploring=true] .entry-access:hover,.entry-access:focus-within{opacity:1}@media (max-width:700px){.gravity-journey{min-height:720svh}.gravity-viewport{transition-duration:.5s}[data-layout]{padding:max(22px,env(safe-area-inset-top)) 20px;font-size:8px}.entry-access{right:20px;bottom:21vh;width:calc(100vw - 40px);padding-top:16px}.layout-footer.left{grid-column:3/4}.layout-footer.links{grid-column:1/2}.layout-footer.right{display:none}}@media (prefers-reduced-motion:reduce){.gravity-loading-orbit{animation:none}.gravity-viewport{transition-duration:.2s}.entry button,.entry#enter{transition:none}.gravity-journey[data-exploring=true] .entry-access{opacity:1}}
</style></head><body><main class="gravity-journey" id="gravity" data-status="loading" aria-label="OMRS 引力入口"><div class="gravity-viewport" id="gravity-viewport"><div class="entry-custom" id="entry-custom"></div><button class="gravity-core-handle" data-gravity-drag-handle aria-label="拖动黑洞移动位置，也可使用方向键" tabindex="-1"></button></div><div class="gravity-loading" id="gravity-loading" role="status"><span class="gravity-loading-orbit"></span><span class="gravity-loading-label">正在展开宇宙</span></div></main><div data-layout><div class="layout-grid"><div class="layout-top"><div class="layout-nav"><div>( Deploy )</div><div>( Preview )</div><div>( Ship )</div></div></div><div class="layout-footer left"><div>Built By</div><div>OMRS</div></div><div class="layout-footer links"><div>Private</div><div>Workspace</div></div><div class="layout-footer right"><div>© OMRS</div></div><section class="entry-access" aria-labelledby="entry-title"><p class="kicker">Access point / 001</p><h1 id="entry-title">准备进入 OMRS</h1><p class="hint" id="hint" role="status">正在检查访问状态…</p><form class="entry" id="entry-form" hidden><input id="pin" type="password" inputmode="numeric" pattern="[0-9]{4,12}" minlength="4" maxlength="12" autocomplete="current-password" placeholder="输入 4–12 位 PIN" aria-label="PIN"><button type="submit" id="submit"><span>解锁学习空间</span></button></form><button class="entry" id="enter" type="button" hidden><span>进入 OMRS</span></button><div class="entry-meta"><span><strong id="clock" aria-label="当前时间">--:--</strong> LOCAL TIME</span><span class="workspace">PRIVATE STUDY WORKSPACE</span></div></section></div></div><script>
const $=id=>document.getElementById(id),gravity=$("gravity"),viewport=$("gravity-viewport"),custom=$("entry-custom"),loading=$("gravity-loading"),clock=$("clock"),hint=$("hint"),form=$("entry-form"),pin=$("pin"),enter=$("enter"),submit=$("submit");
const entryBackground=__ENTRY_BACKGROUND__;
const nextParam=new URLSearchParams(location.search).get("next");function destination(){try{const raw=(nextParam?(nextParam+(nextParam.includes("#")?"":location.hash)):null)||(location.hash?"/"+location.hash:"/?unlocked=1#/dashboard");const url=new URL(raw,location.origin);if(url.origin!==location.origin)return "/?unlocked=1&omrs_reload=1#/dashboard";if(url.pathname==="/"||url.pathname==="/index.html"){url.searchParams.set("unlocked","1");url.searchParams.set("omrs_reload",entryBackground.reload_token||"1");return url.pathname+url.search+url.hash}return url.pathname+url.search+url.hash}catch(_){return "/?unlocked=1&omrs_reload=1#/dashboard"}}const hasHash=location.hash.length>1||Boolean(nextParam&&nextParam.includes("#"));
let disposeScene=()=>{},media=null;function tick(){const now=new Date();clock.textContent=now.toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit",hour12:false})}tick();setInterval(tick,1000);function stopMedia(){if(media){try{media.pause()}catch(_){ }media.remove()}media=null}function unlock(){stopMedia();disposeScene();location.replace(destination())}function fail(message){hint.textContent=message;hint.className="hint error"}function show(s){if(s.pin_configured){form.hidden=false;pin.focus();hint.textContent="输入 PIN 解锁你的学习空间";return}const allowed=!s.remote||s.authenticated||s.lan_pin_exempt;if(allowed){enter.hidden=false;hint.textContent="这是你的学习空间入口";if(hasHash)unlock()}else hint.textContent="此设备未配置可用的 PIN，请在本机设置访问方式"}function showSceneFallback(){stopMedia();custom.hidden=true;try{const scenePromise=import("/assets/vendor/entry-scene.js");scenePromise.then(async scene=>{await scene.prepareGravityScene();disposeScene=scene.createGravityScene(viewport,()=>{gravity.dataset.status="ready";loading.remove()},()=>{gravity.dataset.status="fallback";loading.remove();viewport.innerHTML='<div class="gravity-fallback"><img src="/assets/vendor/entry-fallback.webp" alt="金白色黑洞与弯曲公式曲面的参考主视觉"><span class="gravity-loading-label">此设备暂不支持 WebGL，当前展示参考主视觉。</span></div>'})}).catch(error=>{console.warn("OMRS gravity scene unavailable",error);gravity.dataset.status="fallback";loading.remove();viewport.innerHTML='<div class="gravity-fallback"><img src="/assets/vendor/entry-fallback.webp" alt="金白色黑洞与弯曲公式曲面的参考主视觉"><span class="gravity-loading-label">当前展示参考主视觉。</span></div>'})}catch(error){console.warn("OMRS gravity scene unavailable",error);gravity.dataset.status="fallback";loading.remove()}}function activateCustom(){if(!entryBackground.asset_url){showSceneFallback();return}const reduced=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;gravity.dataset.status="custom-loading";custom.style.setProperty("--entry-blur",String(entryBackground.blur_px||0)+"px");media=document.createElement(entryBackground.kind==="video"?"video":"img");media.className="entry-custom-media";media.src=entryBackground.asset_url;if(entryBackground.kind==="video"){media.muted=true;media.loop=true;media.controls=false;media.playsInline=true;media.autoplay=!reduced;media.setAttribute("aria-label","自定义入口视频背景");media.addEventListener("loadeddata",()=>{custom.hidden=false;gravity.dataset.status="custom-ready";loading.remove();if(!reduced)media.play().catch(()=>{})},{once:true})}else{media.alt="自定义入口背景";media.addEventListener("load",()=>{custom.hidden=false;gravity.dataset.status="custom-ready";loading.remove()},{once:true})}media.addEventListener("error",showSceneFallback,{once:true});custom.replaceChildren(media)}
fetch("/api/auth/session",{cache:"no-store"}).then(r=>r.json()).then(show).catch(()=>fail("无法读取访问状态，请检查服务是否运行"));enter.onclick=unlock;form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;hint.className="hint";hint.textContent="正在验证…";try{const r=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pin:pin.value})});const data=await r.json();if(!r.ok)throw Error(data.msg||"PIN 错误");const state=await(await fetch("/api/auth/session",{cache:"no-store"})).json();if(state.warning_required){alert("当前通过 HTTP 访问，PIN 和会话可能被同一网络中的设备看到。建议使用 HTTPS。");await fetch("/api/auth/warning-ack",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"})}unlock()}catch(error){fail(error.message||"PIN 错误");pin.select();submit.disabled=false}};if(entryBackground.mode==="custom")activateCustom();else showSceneFallback();
</script></body></html>
'''.replace("__ENTRY_BACKGROUND__", entry_payload_json).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def _download(self, payload, filename, content_type):
        """带中文文件名的附件响应：ASCII 兜底 + RFC 5987 filename*，避免 latin-1 编码报错。"""
        ascii_name = "".join(ch for ch in str(filename) if ord(ch) < 128 and ch not in '"\\') or "download"
        encoded = urllib.parse.quote(str(filename))
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}")
        self.send_header("Content-Length", str(len(payload)))
        if urllib.parse.urlparse(self.path).path.startswith('/api/mcp/exports/'):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if urllib.parse.urlparse(self.path).path.startswith(("/api/mcp/", "/api/runtime/")):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve(self, filename, content_type):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, filename)
        if not os.path.exists(file_path):
            self.send_error(404)
            return
        with open(file_path, "rb") as file:
            data = file.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        # The dashboard shell embeds the module entrypoint and its import graph.
        # Do not let a browser keep an old shell after a deployment and pair it
        # with the current static assets; the lock-screen handoff also carries a
        # build marker for browsers that already cached the previous document.
        if filename.endswith((".html", ".htm")):
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _history_commit_payload(self, commit_type, data):
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        if commit_type.startswith("review."):
            return self._history_review_payload(commit_type, data)
        if commit_type.startswith("session."):
            session_id = str(data.get("session_id") or "").strip()
            if not session_id:
                raise ValueError("session_id 不能为空")
            if not self._known_history_session(session_id):
                raise ValueError(f"Session 不存在或没有历史反馈：{session_id}")
            return {**data, "session_id": session_id, "reason": str(data.get("reason") or "").strip()}
        if commit_type == "state.restore":
            target_seq = self._history_nonnegative_int(data.get("target_seq"), "target_seq")
            if target_seq <= 0:
                raise ValueError("target_seq 必须大于 0")
            if get_commit(self.vault_path, target_seq) is None:
                raise ValueError(f"目标 seq 不存在：{target_seq}")
            return {**data, "target_seq": target_seq, "reason": str(data.get("reason") or "").strip()}
        return data

    def _history_review_payload(self, commit_type, data):
        target_commit_id = str(data.get("target_commit_id") or "").strip()
        if not target_commit_id:
            raise ValueError("target_commit_id 不能为空")
        target = get_commit_by_id(self.vault_path, target_commit_id)
        if not target or target.get("commit_type") != "review.batch_submit":
            raise ValueError(f"目标反馈提交不存在：{target_commit_id}")
        reviews = target.get("payload", {}).get("feedbacks") or target.get("payload", {}).get("reviews") or []
        index = self._history_nonnegative_int(data.get("target_review_index"), "target_review_index")
        if index >= len(reviews):
            raise ValueError(f"target_review_index 越界：{index}")
        cleaned = {
            **data,
            "target_commit_id": target_commit_id,
            "target_review_index": index,
            "reason": str(data.get("reason") or "").strip(),
        }
        if commit_type == "review.replace":
            replacement = data.get("replacement")
            if not isinstance(replacement, dict):
                raise ValueError("replacement 必须是 JSON 对象")
            score = self._history_score(replacement.get("sub_score"))
            cleaned["replacement"] = {
                "sub_score": score,
                "is_correct": self._history_bool(replacement.get("is_correct"), "replacement.is_correct"),
                "note": str(replacement.get("note") or ""),
            }
        return cleaned

    def _history_nonnegative_int(self, value, field):
        try:
            result = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field} 必须是整数")
        if result < 0:
            raise ValueError(f"{field} 不能小于 0")
        return result

    def _history_score(self, value):
        try:
            score = int(round(float(value)))
        except (TypeError, ValueError):
            raise ValueError("replacement.sub_score 必须是 0-10 的数字")
        if score < 0 or score > 10:
            raise ValueError("replacement.sub_score 必须在 0-10 之间")
        return score

    def _history_bool(self, value, field):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"true", "1", "yes", "y", "对", "正确"}:
                return True
            if text in {"false", "0", "no", "n", "错", "错误"}:
                return False
        raise ValueError(f"{field} 必须是布尔值")

    def _known_history_session(self, session_id):
        for commit in read_commits(self.vault_path, ascending=True):
            payload = commit.get("payload") or {}
            ctype = commit.get("commit_type")
            if ctype == "legacy.bootstrap":
                if any(row.get("Session_ID") == session_id for row in payload.get("session_rows", [])):
                    return True
                if any(row.get("Session_ID") == session_id for row in payload.get("history_rows", [])):
                    return True
            if ctype == "session.create":
                session = payload.get("session") or payload
                if session.get("session_id") == session_id:
                    return True
            if ctype == "review.batch_submit":
                if payload.get("session_id") == session_id:
                    return True
                reviews = payload.get("feedbacks") or payload.get("reviews") or []
                if any(review.get("session_id") == session_id for review in reviews):
                    return True
        return False

    def _history_commit(self, commit_type, message, body):
        try:
            data = json.loads(body) if body else {}
            data = self._history_commit_payload(commit_type, data)
            commit = append_commit(self.vault_path, "api", commit_type, message, data)
            rebuild_projection(self.vault_path)
            self._json({"status": "ok", **commit})
        except Exception as exc:
            self._json({"status": "error", "msg": str(exc)}, 400)

    _ASSET_TYPES = {
        ".css": "text/css", ".js": "application/javascript",
        ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".gif": "image/gif", ".ico": "image/x-icon",
        ".json": "application/json", ".woff": "font/woff", ".woff2": "font/woff2",
        ".map": "application/json", ".html": "text/html",
        ".mjs": "application/javascript",
    }

    def _serve_asset(self, path):
        """提供 assets/ 静态资源（css/js/图片等），含路径穿越防护。

        带弱 ETag（mtime_ns + 大小）与 Last-Modified；请求带 If-None-Match / If-Modified-Since 且文件未变时回 304、不发正文。
        Cache-Control 仍是 no-cache：浏览器每次都来问，但文件没变时只收到一个空的 304。
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assets_dir = os.path.join(base_dir, "assets")
        rel = urllib.parse.unquote(path.lstrip("/"))
        target = os.path.normpath(os.path.join(base_dir, rel))
        if not (target == assets_dir or target.startswith(assets_dir + os.sep)) \
                or not os.path.isfile(target):
            self.send_error(404)
            return
        ext = os.path.splitext(target)[1].lower()
        ctype = self._ASSET_TYPES.get(ext, "application/octet-stream")
        stat = os.stat(target)
        etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        last_modified = email.utils.formatdate(stat.st_mtime, usegmt=True)
        if self._asset_not_modified(etag, int(stat.st_mtime)):
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", last_modified)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return
        with open(target, "rb") as file:
            data = file.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", last_modified)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _asset_not_modified(self, etag, mtime):
        """If-None-Match 优先（弱比较，支持逗号列表与 *）；没有它时才看 If-Modified-Since（秒级）。"""
        if_none_match = self.headers.get("If-None-Match")
        if if_none_match is not None:
            tags = [tag.strip() for tag in if_none_match.split(",")]
            bare = etag[2:] if etag.startswith("W/") else etag
            return "*" in tags or any((tag[2:] if tag.startswith("W/") else tag) == bare for tag in tags)
        since = self.headers.get("If-Modified-Since")
        if not since:
            return False
        try:
            return mtime <= int(email.utils.parsedate_to_datetime(since).timestamp())
        except (TypeError, ValueError, IndexError, OverflowError):
            return False

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] {fmt % args}")
