import datetime
import http.server
import json
import os
import time
import urllib.parse

from .common import HISTORY_HEADERS, history_path, load_config, load_csv, save_config
from .analytics import build_review_markdown, get_analytics
from .reports import create_report, delete_report, get_report_html, list_reports
from .ai_assist import recognize_question
from .creation import create_question
from .exporting import _find_image, _read_image_info, export_schedule_artifact
from .feedback import process_feedback
from .indexing import build_index
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
from .projections import ledger_history, ledger_retraction_state, rebuild_projection
from .question_ops import get_question_raw, move_question, save_question_markdown
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
from .version import __version__
from .workspace_sync import get_scan_status, scan_workspace


class OMRSHandler(http.server.SimpleHTTPRequestHandler):
    vault_path = "."
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_monotonic = time.monotonic()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = dict(urllib.parse.parse_qsl(parsed.query))

        if path == "/api/stats":
            self._json(get_stats(self.vault_path))
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
        elif path == "/api/export-review":
            try:
                payload, filename = build_review_markdown(self.vault_path)
                filename_encoded = urllib.parse.quote(filename)
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename=\"OMRS-review.md\"; filename*=UTF-8''{filename_encoded}",
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
            try:
                scan = scan_workspace(self.vault_path)
                index = build_index(self.vault_path)
                self._json({"status": "ok", "count": len(index), "scan": scan})
            except RuntimeError as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)
        elif path == "/api/config":
            self._json(load_config(self.vault_path))
        elif path == "/api/reports":
            try:
                self._json({"status": "ok", "reports": list_reports(self.vault_path)})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/report/view":
            try:
                html = get_report_html(self.vault_path, params.get("id", ""))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
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
                rec = generate_recommendations(
                    self.vault_path,
                    due_count=max(1, min(50, due_count)),
                    prof_count=max(1, min(50, prof_count)),
                    subject=subject,
                    category=category,
                    knowledge_tag=knowledge_tag,
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
                self.send_header("Cache-Control", "max-age=86400")
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
        if path == "/api/backup/import":
            self._handle_backup_import()
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")

        if path == "/api/schedule":
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
                image = data.get("image", "")
                mode = data.get("mode", "classify")
                result = recognize_question(
                    self.vault_path, image, mode=mode,
                    hint_subject=data.get("subject", ""),
                    hint_category=data.get("category", ""),
                )
                self._json({"status": "ok", **result})
            except Exception as exc:
                self._json({"status": "error", "msg": str(exc)}, 400)

        elif path == "/api/config":
            try:
                data = json.loads(body) if body else {}
                save_config(self.vault_path, data)
                self._json({"status": "ok"})
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
                )
                self._json({"status": "ok", **result})
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
                if len(selected) == 1:
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
                if not uids and not session_id:
                    self._json({"status": "error", "msg": "需要 session_id 或 uids"}, 400)
                    return
                payload, sid, filename, content_type = export_schedule_artifact(
                    self.vault_path,
                    uids or None,
                    session_id,
                    export_format,
                    include_answers=include_answers,
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
        else:
            self._json({"error": "not found"}, 404)

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
        ".map": "application/json",
    }

    def _serve_asset(self, path):
        """提供 assets/ 静态资源（css/js/图片等），含路径穿越防护。"""
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
        with open(target, "rb") as file:
            data = file.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] {fmt % args}")
