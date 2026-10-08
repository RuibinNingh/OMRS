import argparse
import json
import os
import socket
import socketserver
import sqlite3
import sys
import time

from .common import QUESTIONS_DIR, load_config, questions_root
from .creation import create_question
from .exporting import export_schedule_artifact
from .indexing import build_index
from .optimization import ensure_image_dependencies_interactive
from .scheduling import _normalize_uid_list, schedule_questions
from .server import OMRSHandler
from .sessions import create_session, delete_session, get_session, list_sessions
from .stats import get_stats
from .workspace_sync import start_workspace_scanner


class OMRSTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """One daemon thread per connection; permit immediate rebinding after TIME-WAIT.

    Persistent writes are serialized by omrs.locking.write_lock (see AI/api.md「并发与写锁」).
    """

    allow_reuse_address = True
    daemon_threads = True


def _lan_ips():
    """尽力探测本机局域网 IPv4 地址（用于「外部访问」时提示真实可访问的网址）。"""
    ips = set()
    # 主出口 IP（连一个外部地址但不真正发包，仅让内核选出口网卡）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    # 主机名解析出的地址
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    # 过滤回环/无效
    return sorted(ip for ip in ips if ip and not ip.startswith("127.") and ip != "0.0.0.0")


def main():
    parser = argparse.ArgumentParser(description="OMRS - Obsidian 错题重构系统")
    parser.add_argument("--vault", default=".", help="Obsidian 库根目录，默认为当前目录")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scan", help="扫描并重建错题索引")
    sub.add_parser("export-csv", help="按需导出当前 SQL 题库、反馈和计划为兼容 CSV")

    audit_parser = sub.add_parser("content-audit", help="只读盘点题目正文、投影与 Ledger blob")
    audit_parser.add_argument("--json", action="store_true", help="输出 JSON，不包含正文")

    recovery_parser = sub.add_parser("content-recover", help="核验清单并补回缺失历史正文，默认只预览")
    recovery_parser.add_argument("--manifest", required=True, help="本机正文清单 JSON 路径")
    recovery_parser.add_argument("--apply", action="store_true", help="将已核验且缺失的版本原子补入 Ledger")

    schedule_parser = sub.add_parser("schedule", help="生成复习调度预览")
    schedule_parser.add_argument("-n", "--count", type=int, default=10)
    schedule_parser.add_argument("-s", "--subject", default=None)

    serve_parser = sub.add_parser("serve", help="启动 Web 仪表盘")
    serve_parser.add_argument("-p", "--port", type=int, default=8471)
    serve_parser.add_argument("--mcp-port", type=int, default=None,
                              help="在同一 OMRS 进程启用 MCP Streamable HTTP（推荐由反向代理转发）")
    serve_parser.add_argument("--mcp-public-url", default=None,
                              help="HTTPS 反向代理的完整 /mcp 地址，用于精确 Host/Origin 白名单")
    serve_parser.add_argument('--web-public-url', default=None, help='主 Web 服务的公共来源，用于 MCP 网页确认与下载链接')

    mcp_key_parser = sub.add_parser("mcp-key", help="管理 MCP API Key")
    mcp_key_parser.add_argument("action", choices=["create", "list", "revoke", "update"])
    mcp_key_parser.add_argument("--name", default="", help="显示名称")
    mcp_key_parser.add_argument("--scope", action="append", dest="scopes", help="权限，可重复指定")
    mcp_key_parser.add_argument("--expires-at", default=None, help="ISO-8601 到期时间")
    mcp_key_parser.add_argument("--id", default=None, help="revoke/update 的 key_id")

    sub.add_parser("stats", help="输出统计摘要")

    create_parser = sub.add_parser("create", help="创建新题目骨架")
    create_parser.add_argument("--subject", required=True, help="科目")
    create_parser.add_argument("--category", required=True, help="分类")
    create_parser.add_argument("--difficulty", type=int, default=5, help="难度 1-10")

    export_parser = sub.add_parser("export", help="导出调度为 HTML（A4 打印版 / 屏幕阅读版）")
    export_parser.add_argument("-n", "--count", type=int, default=10, help="题目数量")
    export_parser.add_argument("-s", "--subject", default=None, help="限定科目")
    export_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="输出文件路径，默认当前目录 OMRS-{session}.<format>",
    )
    export_parser.add_argument("--session", default=None, help="导出已有 session_id，跳过重新调度")
    export_parser.add_argument("--uids", default=None, help="逗号分隔的 UID 列表，直接导出临时调度")
    export_parser.add_argument("--format", choices=["a4", "screen"], default="a4", help="导出格式：a4 打印版 / screen 屏幕阅读版")
    export_parser.add_argument("--question-gap-lines", type=int, default=0, help="A4 每道题之间预留的空行数（0-20，默认 0）")

    sessions_parser = sub.add_parser("sessions", help="管理持久化调度 sessions")
    sessions_parser.add_argument("action", choices=["list", "show", "delete", "new"])
    sessions_parser.add_argument("--id", default=None, help="session_id (show/delete)")
    sessions_parser.add_argument("--status", default=None, help="过滤状态 active/completed (list)")
    sessions_parser.add_argument("-n", "--count", type=int, default=10, help="new 的题目数")
    sessions_parser.add_argument("-s", "--subject", default=None, help="new 的科目筛选")

    args = parser.parse_args()
    vault = os.path.abspath(args.vault)
    if args.command == "serve":
        if args.mcp_port is not None and (not 1 <= args.mcp_port <= 65535 or args.mcp_port == args.port):
            parser.error("MCP 端口必须为 1–65535，且不能与 Web 端口相同")
        if args.mcp_public_url and args.mcp_port is None:
            parser.error("--mcp-public-url 需要同时指定 --mcp-port")

    # 目录交换恢复必须早于任何配置读取、建库和扫描；只读盘点拒绝待恢复状态。
    from .backup_store import recover_restore
    recover_restore(vault, allow_recovery=args.command not in {"content-audit", "content-recover"})
    from .question_update import recover_pending as recover_question_updates
    recover_question_updates(vault, allow_recovery=args.command not in {"content-audit", "content-recover"})
    from .label_plan_journal import recover_pending as recover_label_plans
    recover_label_plans(vault, allow_recovery=args.command not in {"content-audit", "content-recover"})
    if args.command == "content-recover":
        from .content_recovery import load_recovery_manifest, recover_content
        try:
            items, digest = load_recovery_manifest(args.manifest)
            result = recover_content(vault, items, digest, apply=args.apply)
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
            print(f"正文补回失败：{exc}", file=sys.stderr)
            raise SystemExit(2)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    if args.command != "content-audit":
        from .config_repository import initialize
        initialize(vault)
        from .inbox_commit import recover_pending
        pending_inbox = recover_pending(vault)
        if pending_inbox["awaiting_images"]:
            print(f"有 {len(pending_inbox['awaiting_images'])} 个入库预留等待原图片重试，未重复创建")

    if args.command == "mcp-key":
        from .mcp.keys import create_key, list_keys, revoke_key, update_scopes
        if args.action == "create":
            print(json.dumps(create_key(vault, args.name, args.scopes, args.expires_at), ensure_ascii=False, indent=2))
        elif args.action == "list":
            print(json.dumps({"keys": list_keys(vault)}, ensure_ascii=False, indent=2))
        else:
            if not args.id:
                raise SystemExit('revoke/update 需要 --id')
            if args.action == 'update' and not args.scopes:
                raise SystemExit('update 需要 --scope')
            key = update_scopes(vault, args.id, args.scopes) if args.action == 'update' else revoke_key(vault, args.id)
            print(json.dumps({'key': key}, ensure_ascii=False, indent=2))
        return

    if args.command == "content-audit":
        from .content_history import audit_content_coverage
        try:
            result = audit_content_coverage(vault)
        except (OSError, ValueError) as exc:
            print(f"正文盘点失败：{exc}", file=sys.stderr)
            raise SystemExit(2)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        else:
            print(f"活动题 {result['active_questions']}；当前缺 blob {len(result['current_missing_blobs'])}；"
                  f"文件冲突 {len(result['file_conflicts'])}；历史缺口 {result['historical_missing_blobs']}")

    elif args.command == "scan":
        print(f"扫描: {questions_root(vault)}")
        try:
            index = build_index(vault)
            print(f"完成，共 {len(index)} 道题")
        except RuntimeError as exc:
            print(str(exc))
            raise SystemExit(1)

    elif args.command == "export-csv":
        from .projections import export_legacy_csv
        export_legacy_csv(vault)
        print("已导出 mastery_data.csv、history_log.csv、sessions.csv 到错题/.omrs/")

    elif args.command == "schedule":
        items = schedule_questions(vault, args.count, args.subject)
        for index, item in enumerate(items, 1):
            print(
                f"  {index}. [{item['UID']}] M={float(item.get('Mastery', 0)):.2f} "
                f"P={item['_priority']} {item.get('Current_Tag', '')}"
            )

    elif args.command == "serve":
        OMRSHandler.vault_path = vault
        ensure_image_dependencies_interactive()
        config = load_config(vault)
        bind_host = "" if config.get("allow_external") else "127.0.0.1"
        OMRSHandler.listen_external = bind_host == ""
        try:
            index = build_index(vault)
            print(f"已索引 {len(index)} 道题（扫描目录: {QUESTIONS_DIR}/）")
        except RuntimeError as exc:
            print(str(exc))
            raise SystemExit(1)
        try:
            from .content_history import backfill_missing_content
            backfill = backfill_missing_content(vault)
            if backfill["conflicts"]:
                print(f"正文回填跳过 {len(backfill['conflicts'])} 道冲突题，请核对身份与哈希后处理")
        except Exception as exc:  # 回填失败不阻止其他页面启动；下次启动再试
            print(f"正文回填未完成：{exc}")
        try:
            from .traincontrol import recover_pending
            recovery = recover_pending(vault)
            if recovery.get("state") not in ("none", "in_progress"):
                op = recovery.get("operation") or {}
                if recovery["state"] == "failed" and op.get("rollback_error"):
                    print("受管检测模型回退未完成，检测服务需人工处理")
                elif recovery["state"] == "failed":
                    print("已处理上次中断的受管检测操作，请核对模型状态")
            elif recovery.get("state") == "in_progress":
                print("受管检测操作仍在处理中，请核对模型状态")
        except Exception as exc:
            print(f"受管检测模型恢复未完成，需人工处理：{exc}")
        from .ai_review import initialize as initialize_reviews
        initialize_reviews(vault)
        from .agent.runtime import get_runtime
        get_runtime(vault)  # 把上次遗留的 running 运行标为 interrupted
        from . import runtime_records
        runtime_records.safely(runtime_records.recover_interrupted, vault)
        start_workspace_scanner(vault)
        OMRSHandler._restart_cmd = [
            sys.executable,
            os.path.abspath(sys.argv[0]),
        ] + list(sys.argv[1:])
        mcp_server = None
        mcp_thread = None
        if args.mcp_port is not None:
            # MCP 适配器和 Web 服务共用本进程的领域对象与写锁；不要为同一
            # Vault 另起一个直接读写 drafts.db 的 MCP 进程。
            import threading
            try:
                import uvicorn
                from .mcp.server import build_app
            except ModuleNotFoundError:
                raise SystemExit("启用 MCP 前请安装 requirements-mcp.txt")
            mcp_server = uvicorn.Server(uvicorn.Config(
                build_app(vault, host="127.0.0.1", port=args.mcp_port, public_url=args.mcp_public_url,
                          web_url=args.web_public_url or f'http://127.0.0.1:{args.port}'),
                host="127.0.0.1", port=args.mcp_port, log_level="warning", access_log=False,
            ))
            mcp_thread = threading.Thread(target=mcp_server.run, name="omrs-mcp", daemon=True)
            mcp_thread.start()
            deadline = time.monotonic() + 10
            while not mcp_server.started and mcp_thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not mcp_server.started:
                mcp_server.should_exit = True
                mcp_thread.join(timeout=2)
                raise SystemExit("MCP 启动失败，请检查端口与依赖")
            print(f"   MCP： http://127.0.0.1:{args.mcp_port}/mcp（与主进程共享写锁）")
        with OMRSTCPServer((bind_host, args.port), OMRSHandler) as httpd:
            print(f"\nOMRS 已启动（端口 {args.port}）")
            print(f"   本机访问： http://127.0.0.1:{args.port}")
            if bind_host == "":
                lan = _lan_ips()
                if lan:
                    print("   其他设备（同一局域网）访问：")
                    for ip in lan:
                        print(f"            http://{ip}:{args.port}")
                else:
                    print("   外部访问已开启，但未探测到局域网 IP；")
                    print("   请用本机的局域网 IP（如 ipconfig 里的 IPv4 地址）+ 端口访问。")
                print("   注意：不要在浏览器里输入 0.0.0.0，那只是「监听所有网卡」的占位地址。")
            else:
                print("   （仅本机可访问；如需局域网访问，请在「设置」开启外部访问并重启）")
            print(f"   Vault: {vault}")
            print(f"   题目目录: {questions_root(vault)}")
            print("   Ctrl+C 停止\n")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n已停止")
            finally:
                if mcp_server is not None:
                    mcp_server.should_exit = True
                if mcp_thread is not None:
                    mcp_thread.join(timeout=5)

    elif args.command == "stats":
        stats = get_stats(vault)
        print(
            f"\n总计 {stats['total']} 题，已击杀 {stats['killed']}，"
            f"待攻克 {stats['attacking']}，平均熟练度 {stats['avg_mastery']:.1%}"
        )
        for subject, data in stats["subject_dist"].items():
            print(f"  {subject}: {data['total']}题，已击杀 {data['killed']}，M={data['avg_m']:.1%}")

    elif args.command == "create":
        result = create_question(vault, args.subject, args.category, args.difficulty)
        print(result["message"])
        print(f"   文件: {result['file_path']}")

    elif args.command == "export":
        if args.session and args.uids:
            print("--session 和 --uids 只能二选一")
            return
        if args.session:
            payload, session_id, default_name, _ = export_schedule_artifact(
                vault,
                None,
                args.session,
                args.format,
                question_gap_lines=args.question_gap_lines,
            )
        elif args.uids:
            payload, session_id, default_name, _ = export_schedule_artifact(
                vault,
                _normalize_uid_list(args.uids.split(",")),
                "",
                args.format,
                question_gap_lines=args.question_gap_lines,
            )
        else:
            session = create_session(vault, args.count, args.subject)
            if not session["items"]:
                print("调度结果为空")
                return
            payload, session_id, default_name, _ = export_schedule_artifact(
                vault,
                None,
                session["session_id"],
                args.format,
                question_gap_lines=args.question_gap_lines,
            )
        output = args.output or os.path.join(os.getcwd(), default_name)
        with open(output, "wb") as file:
            file.write(payload)
        print(f"已导出 {session_id}")
        print(f"   文件: {output} ({len(payload)} 字节)")

    elif args.command == "sessions":
        if args.action == "list":
            sessions = list_sessions(vault, args.status)
            if not sessions:
                print("（无 sessions）")
                return
            for session in sessions:
                subject = session["subject_filter"] or "全部"
                print(
                    f"  {session['session_id']}  [{session['status']:9s}]  "
                    f"{subject}  {session['count']}题  {session['created_at']}"
                )
        elif args.action == "show":
            if not args.id:
                print("需要 --id")
                return
            session = get_session(vault, args.id)
            if not session:
                print(f"未找到 {args.id}")
                return
            print(f"Session: {session['session_id']}  状态: {session['status']}  创建: {session['created_at']}")
            print(f"科目筛选: {session['subject_filter'] or '全部'}  题数: {session['count']}")
            for index, item in enumerate(session["items"], 1):
                print(
                    f"  {index}. [{item.get('UID', '?')}] {item.get('Subject', '')}/"
                    f"{item.get('Category', '')} D={item.get('Difficulty', '?')} "
                    f"M={item.get('Mastery', '?')}"
                )
        elif args.action == "delete":
            if not args.id:
                print("需要 --id")
                return
            print("已删除" if delete_session(vault, args.id) else f"未找到 {args.id}")
        elif args.action == "new":
            session = create_session(vault, args.count, args.subject)
            print(f"已创建 {session['session_id']} ({session['count']} 题)")
            for index, item in enumerate(session["items"], 1):
                print(f"  {index}. [{item['UID']}] M={float(item.get('Mastery', 0)):.2f}")

    else:
        parser.print_help()
