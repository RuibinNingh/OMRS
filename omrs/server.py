import base64
import datetime
import email.utils
import http.server
import json
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
from .ai_assist import recognize_question
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
from .projections import ledger_history, ledger_retraction_state, rebuild_projection
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

        if path == "/login":
            self._serve_login()
            return
        if path == "/api/auth/session":
            self._auth_status()
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
        if path.startswith("/api/drafts/"):
            self._drafts_get(path, params)
            return

        if path == "/api/stats":
            self._json(get_stats(self.vault_path))
        elif path == "/api/labels":
            self._json({"status": "ok", "labels": list_label_defs(self.vault_path)})
        elif path == "/api/boards":
            self._json({"status": "ok", "boards": list_boards(self.vault_path),
                        "folders": board_list_folders(self.vault_path)})
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
                self._json({
                    "status": "ok",
                    "commits": ledger_history(self.vault_path, before, max(1, min(500, limit))),
                    "retraction_state": ledger_retraction_state(self.vault_path),
                    "history": load_csv(history_path(self.vault_path), HISTORY_HEADERS)[-100:],
                })
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
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
                    note=data.get("note", ""),
                    related_tags=data.get("related_tags", []),
                    labels=data.get("labels", []),
                    question_text=data.get("question_text", ""),
                    answer_text=data.get("answer_text", ""),
                    cause=data.get("cause", ""),
                    question_images=data.get("question_images", []),
                    answer_images=data.get("answer_images", []),
                )
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/ai-recognize":
            try:
                data = json.loads(body) if body else {}
                # 兼容旧字段名 image，新的使用 question_image
                question_image = data.get("question_image") or data.get("image", "")
                answer_image = data.get("answer_image", "")
                mode = data.get("mode", "classify")
                result = recognize_question(
                    self.vault_path, question_image, mode=mode,
                    hint_subject=data.get("subject", ""),
                    hint_category=data.get("category", ""),
                    answer_image=answer_image,
                )
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
                )
                self._json({"status": "ok", "board": board})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/update":
            try:
                data = json.loads(body) if body else {}
                board_id = str(data.get("id") or "").strip()
                if not board_id:
                    raise ValueError("展示板 id 不能为空")
                changes = {key: data[key] for key in ("name", "note", "print", "items", "source_labels", "folder_id") if key in data}
                self._json({"status": "ok", "board": update_board(self.vault_path, board_id, **changes)})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/items/add":
            try:
                data = json.loads(body) if body else {}
                self._json({"status": "ok", "board": board_add_items(
                    self.vault_path, str(data.get("id") or ""), data.get("uids") or [], data.get("position"),
                )})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/items/remove":
            try:
                data = json.loads(body) if body else {}
                self._json({"status": "ok", "board": board_remove_items(
                    self.vault_path, str(data.get("id") or ""), data.get("uids") or [],
                )})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/duplicate":
            try:
                data = json.loads(body) if body else {}
                self._json({"status": "ok", "board": duplicate_board(
                    self.vault_path, str(data.get("id") or ""), data.get("name", ""),
                )})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/folder/create":
            try:
                data = json.loads(body) if body else {}
                self._json({"status": "ok", "folder": board_create_folder(self.vault_path, data.get("name", ""))})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/folder/update":
            try:
                data = json.loads(body) if body else {}
                changes = {key: data[key] for key in ("name", "order") if key in data}
                self._json({"status": "ok", "folder": board_update_folder(
                    self.vault_path, str(data.get("id") or ""), **changes,
                )})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/folder/delete":
            try:
                data = json.loads(body) if body else {}
                keep = data.get("keep_boards", True)
                result = board_delete_folder(self.vault_path, str(data.get("id") or ""), keep is not False)
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/move":
            try:
                data = json.loads(body) if body else {}
                self._json({"status": "ok", "board": board_move(
                    self.vault_path, str(data.get("id") or ""),
                    data.get("folder_id"), data.get("index"),
                )})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/delete":
            try:
                data = json.loads(body) if body else {}
                ok = delete_board(self.vault_path, str(data.get("id") or ""))
                self._json({"status": "ok" if ok else "error", "deleted": ok})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/printed":
            try:
                data = json.loads(body) if body else {}
                board = board_record_printed(
                    self.vault_path,
                    str(data.get("id") or ""),
                    str(data.get("mode") or "all"),
                    data.get("layout") if isinstance(data.get("layout"), dict) else {},
                )
                self._json({"status": "ok", "board": board})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/board/printed/reset":
            try:
                data = json.loads(body) if body else {}
                self._json({"status": "ok", "board": board_reset_printed(self.vault_path, str(data.get("id") or ""))})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        else:
            self._json({"error": "not found"}, 404)

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
                value = traincontrol.submit(self.vault_path, json.loads(self.rfile.read(length)))
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
                    self.vault_path, data.get("id", ""), data.get("boxes"), data.get("status"))})
            elif path == "/api/annotate/delete":
                self._json({"status": "ok", **annotate_mod.delete(self.vault_path, data.get("id", ""))})
            else:
                self._json({"status": "error", "msg": "not found"}, 404)
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
                self._json({"status": "ok", "item": inbox_mod.update_item(self.vault_path, data.get("id", ""), data)})
            elif path == "/api/inbox/discard":
                ids = data.get("ids") or ([data["id"]] if data.get("id") else [])
                self._json({"status": "ok", "results": [inbox_mod.discard_item(self.vault_path, i) for i in ids]})
            elif path == "/api/inbox/jobs":
                self._json({"status": "ok", "job": inbox_mod.start_job(self.vault_path, data.get("type", ""), data)})
            elif path == "/api/inbox/commit":
                self._json({"status": "ok", **inbox_mod.commit_item(
                    self.vault_path, data.get("id", ""), card=data.get("card", 1),
                    form=data.get("form") or {}, crops=data.get("crops") or {})})
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

    def _authorize(self, path, params):
        remote, _, _ = self._security_context()
        self._active_session = None
        if not remote or self._direct_lan_exempt():
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

    def _serve_login(self):
        page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OMRS 登录</title><style>body{font:16px system-ui,sans-serif;background:#f6f2eb;color:#27231f;display:grid;place-items:center;min-height:100vh;margin:0}main{background:white;padding:32px;border:1px solid #ddd;border-radius:12px;max-width:360px;width:85%}input,button{font:inherit;padding:12px;width:100%;box-sizing:border-box;margin-top:12px}button{background:#765c45;color:white;border:0;border-radius:6px;cursor:pointer}p{line-height:1.5}</style><main><h1>OMRS 远端登录</h1><p id="hint">输入 PIN 后继续访问。</p><form id="login"><input id="pin" type="password" inputmode="numeric" pattern="[0-9]{4,12}" minlength="4" maxlength="12" autocomplete="off" placeholder="4 到 12 位 PIN" required><button>登录</button></form></main><script>const hint=document.getElementById('hint');const next=()=>{try{const u=new URL(new URLSearchParams(location.search).get('next')||'/',location.origin);return u.origin===location.origin?u.pathname+u.search+u.hash:'/'}catch(_){return '/'}};fetch('/api/auth/session').then(r=>r.json()).then(s=>{if(!s.pin_configured)hint.textContent='尚未配置 PIN，请在本机设置页完成配置。';if(s.authenticated)location.replace(next())});document.getElementById('login').onsubmit=async e=>{e.preventDefault();try{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:document.getElementById('pin').value})});const j=await r.json();if(!r.ok)throw Error(j.msg||'登录失败');const s=await(await fetch('/api/auth/session')).json();if(s.warning_required){alert('当前通过 HTTP 访问，PIN 和会话可能被同一网络中的设备看到。建议使用 HTTPS。');await fetch('/api/auth/warning-ack',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}location.replace(next())}catch(err){hint.textContent=err.message}}</script></html>'''.encode("utf-8")
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
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
