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
import contextlib
from http.cookies import SimpleCookie

from .common import load_config, save_config, validate_draft_config
from .analytics import build_review_export, get_analytics
from .catalog import build_tree
from .reports import create_report, delete_report, get_report_html, list_reports, signed_report_images
from . import traincontrol
from . import security
from . import locking
from . import http_io, uploads, vault_lifecycle
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


from .http.learning import LearningRoutes
from .http.questions import QuestionsRoutes
from .http.boards import BoardsRoutes
from .http.core import CoreRoutes
from .http.inbox import InboxRoutes
from .http.training import TrainingRoutes
from .http.drafts import DraftsRoutes
from .http.mcp import McpRoutes
from .http.ai_review import AiReviewRoutes
from .http.auth import AuthRoutes
from .http.media import MediaRoutes
from .http.history import HistoryRoutes


class OMRSHandler(QuestionsRoutes, BoardsRoutes, LearningRoutes, CoreRoutes, InboxRoutes, TrainingRoutes, DraftsRoutes, AiReviewRoutes, McpRoutes, AuthRoutes, MediaRoutes, HistoryRoutes, http.server.SimpleHTTPRequestHandler):
    @property
    def services(self):
        # 领域层通过此对象复用应用服务，测试替换仍只需修改 omrs.server。
        import sys
        return sys.modules[__name__]

    vault_path = "."
    listen_external = False  # set by cli.py: True when bound to all interfaces
    started_at = datetime.datetime.now(datetime.timezone.utc)
    started_monotonic = time.monotonic()

    def do_HEAD(self):
        writer = self.wfile
        self._head_only = True
        try:
            self.do_GET()
        finally:
            self.wfile = writer
            self._head_only = False

    def end_headers(self):
        super().end_headers()
        if getattr(self, "_head_only", False):
            self.wfile = http_io.HeadWriter()

    @contextlib.contextmanager
    def _response_capture(self, protected=True):
        """磁盘段生成完整响应；租约和写锁释放后才向慢客户端发送。"""
        if not hasattr(self, "wfile"):
            manager = vault_lifecycle.lease(self.vault_path) if protected else contextlib.nullcontext()
            with manager:
                yield
            return
        writer = self.wfile
        with tempfile.TemporaryFile("w+b") as response:
            previous_capture = getattr(self, "_captured_response", None)
            self._captured_response = response
            self.wfile = response
            try:
                manager = vault_lifecycle.lease(self.vault_path) if protected else contextlib.nullcontext()
                with manager:
                    yield
            except BaseException:
                self._headers_buffer = []
                raise
            finally:
                self.wfile = writer
                if previous_capture is None:
                    self.__dict__.pop("_captured_response", None)
                else:
                    self._captured_response = previous_capture
            response.seek(0)
            shutil.copyfileobj(response, writer, 65536)

    def _image_references(self, value, purpose):
        if isinstance(value, dict):
            if "upload_ref" in value:
                return uploads.image_data_url(self.vault_path, value, purpose=purpose)
            return {key: self._image_references(item, purpose) for key, item in value.items()}
        if isinstance(value, list):
            return [self._image_references(item, purpose) for item in value]
        return value

    def _question_uid(self, reference):
        from .data_repository import resolve_question
        uid, identity = reference.get("uid", ""), reference.get("question_id", "")
        if not identity:
            return uid
        row = resolve_question(self.vault_path, uid, identity)
        if row is None:
            raise http_io.BodyError("题目不存在或已归档", 404)
        return row["uid"]

    def _error(self, exc):
        response = getattr(self, "_captured_response", None)
        if response is not None:
            response.seek(0)
            response.truncate()
            self.wfile = response
            self._headers_buffer = []
        status = getattr(exc, "status", None)
        if status is None:
            status = 400 if isinstance(exc, (ValueError, TypeError, KeyError)) else 500
        payload = {"status": "error", "msg": str(exc)}
        if getattr(exc, "code", None):
            payload["code"] = exc.code
        self._json(payload, status)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        protected = not (path.startswith("/api/agent/") or path in (
            "/api/annotate/export", "/api/source/export", "/api/export-review",
            "/api/trainpanel/service", "/api/trainpanel/manager"))
        try:
            with self._response_capture(protected):
                self._dispatch_get()
        except (vault_lifecycle.VaultBusy, vault_lifecycle.VaultChanged) as exc:
            self._error(exc)
        except Exception as exc:
            self._error(exc)

    def _dispatch_get(self):
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

        from .http.registry import dispatch
        dispatch(self, "GET", path, params)

    def do_POST(self):
        try:
            with vault_lifecycle.task(self.vault_path):
                self._post_current()
        except Exception as exc:
            self._error(exc)

    def _post_current(self):
        path = urllib.parse.urlparse(self.path).path
        if self._mcp_credential_present():
            self._json({"status": "error", "code": "mcp_boundary", "msg": "MCP Key 不能调用普通 OMRS 接口"}, 403)
            return
        if not self._check_write_origin():
            return
        if path != "/api/auth/login" and not self._authorize(path, {}):
            return
        original = self.rfile
        spool = None
        try:
            spool = http_io.receive(self, path)
            self.rfile = spool
            with vault_lifecycle.lease(self.vault_path):
                pass  # 网络接收完成后重查，旧世代正文不进入新题库。
            owner = (getattr(self, "_active_session", None) or {}).get("id")
            if owner is None:
                owner = "direct:" + self._security_context()[1]
            with uploads.request_owner(owner):
                content_type = self.headers.get("Content-Type", "")
                media_type = content_type.split(";", 1)[0].strip().lower()
                if media_type == "multipart/form-data" and path in ("/api/inbox/upload", "/api/annotate/upload", "/api/backup/import"):
                    from .http.multipart import files
                    purpose = "backup" if path == "/api/backup/import" else "inbox" if path == "/api/inbox/upload" else "annotate"
                    self._prepared_files = files(spool, content_type, self.vault_path, purpose)
                if (path != "/api/uploads/chunk" and
                        media_type != "multipart/form-data" and
                        path != "/api/entry-background" and
                        (path != "/api/backup/import" or "json" in media_type)):
                    if path in ("/api/create", "/api/inbox/upload", "/api/inbox/commit", "/api/inbox/crops") and http_io.content_length(self):
                        from .http.bodies import parse_images
                        self._prepared_json = parse_images(spool, self.vault_path, "create" if path == "/api/create" else "inbox")
                    else:
                        self._prepared_json = http_io.json_body(self)
                    spool.seek(0)
                protected = not (path.startswith(("/api/agent/", "/api/auth/", "/api/uploads/"))
                    or path in ("/api/backup/export", "/api/backup/restore", "/api/backup/import",
                                "/api/ai-recognize", "/api/trainpanel/try", "/api/entry-background", "/api/restart", "/api/export"))
                with self._response_capture(protected):
                    self._dispatch_post(path)
        except http_io.BodyError as exc:
            self.close_connection = True
            self._json({"status": "error", "msg": str(exc)}, exc.status)
        except (vault_lifecycle.VaultBusy, vault_lifecycle.VaultChanged) as exc:
            self._error(exc)
        except UnicodeError:
            self.close_connection = True
            self._json({"status": "error", "msg": "请求体必须是有效 UTF-8"}, 400)
        finally:
            self.rfile = original
            self.__dict__.pop("_prepared_json", None)
            self.__dict__.pop("_prepared_files", None)
            if spool is not None:
                spool.close()

    def _agent_get(self, path, params):
        from .agent.http import handle_agent_get
        handle_agent_get(self, path, params)

    def _agent_post(self, path):
        from .agent.http import handle_agent_post
        handle_agent_post(self, path)

    def _dispatch_post(self, path):
        from .http.registry import dispatch, target
        if target("POST", path) is None:
            self._json({"status": "error", "msg": "接口不存在"}, 404)
            return
        if (path.startswith(("/api/agent/", "/api/mcp/", "/api/uploads/")) or
                path in ("/api/backup/export", "/api/backup/restore", "/api/backup/import", "/api/export") or locking.post_exempt(path)):
            dispatch(self, "POST", path)
            return
        started = time.monotonic()
        try:
            with locking.write_lock():
                dispatch(self, "POST", path)
        except locking.WriteLockTimeout:
            print(f"[omrs] 写锁等待超时：POST {path}，{time.monotonic() - started:.1f} 秒", flush=True)
            self._json({"status": "error", "msg": "写入繁忙，请稍后重试"}, 503)


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



    # ────────────── 框选标注集 /api/annotate/* 与独立标注页 /annotate ──────────────


    # ────────────────────────── AI 草稿区 /api/drafts/* 只读接口（P1-1；写接口见 P2） ──────────────────────────


    # ────────────────────────── 系统运行记录 ──────────────────────────

    # ────────────────────────── MCP Key 管理 ──────────────────────────


    def _mcp_credential_present(self):
        """普通 Web 端口拒绝 MCP 专用凭据，防止跨接口借道。"""
        # 一些只调用路由方法的单元测试 handler 不经过 BaseHTTPRequestHandler
        # 初始化，因此没有 headers 属性；缺少请求头等同于没有 MCP 凭据。
        headers = getattr(self, "headers", None)
        if headers is None:
            return False
        return bool(headers.get("X-OMRS-MCP-Key") or
                    (headers.get("Authorization") or "").lower().startswith("bearer "))








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

    def _download_file(self, path, filename, content_type, headers=None):
        with open(path, "rb") as source:
            self._download_headers(os.fstat(source.fileno()).st_size, filename, content_type, headers)
            shutil.copyfileobj(source, self.wfile, 65536)

    def _download_headers(self, size, filename, content_type, headers=None):
        ascii_name = "".join(ch for ch in str(filename) if 32 <= ord(ch) < 127 and ch not in '"\\') or "download"
        encoded = urllib.parse.quote(str(filename))
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}")
        self.send_header("Content-Length", str(size))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if urllib.parse.urlparse(self.path).path.startswith('/api/mcp/exports/'):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()

    def _download(self, payload, filename, content_type, headers=None):
        """带中文文件名的附件响应：ASCII 兜底 + RFC 5987 filename*，避免 latin-1 编码报错。"""
        self._download_headers(len(payload), filename, content_type, headers)
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
