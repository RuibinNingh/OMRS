import argparse
import os
import socket
import socketserver
import sys

from .common import QUESTIONS_DIR, load_config, questions_root
from .creation import create_question
from .exporting import export_schedule_artifact
from .indexing import build_index
from .scheduling import _normalize_uid_list, schedule_questions
from .server import OMRSHandler
from .sessions import create_session, delete_session, get_session, list_sessions
from .stats import get_stats


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

    schedule_parser = sub.add_parser("schedule", help="生成复习调度预览")
    schedule_parser.add_argument("-n", "--count", type=int, default=10)
    schedule_parser.add_argument("-s", "--subject", default=None)

    serve_parser = sub.add_parser("serve", help="启动 Web 仪表盘")
    serve_parser.add_argument("-p", "--port", type=int, default=8471)

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

    sessions_parser = sub.add_parser("sessions", help="管理持久化调度 sessions")
    sessions_parser.add_argument("action", choices=["list", "show", "delete", "new"])
    sessions_parser.add_argument("--id", default=None, help="session_id (show/delete)")
    sessions_parser.add_argument("--status", default=None, help="过滤状态 active/completed (list)")
    sessions_parser.add_argument("-n", "--count", type=int, default=10, help="new 的题目数")
    sessions_parser.add_argument("-s", "--subject", default=None, help="new 的科目筛选")

    args = parser.parse_args()
    vault = os.path.abspath(args.vault)

    if args.command == "scan":
        print(f"扫描: {questions_root(vault)}")
        try:
            index = build_index(vault)
            print(f"完成，共 {len(index)} 道题")
        except RuntimeError as exc:
            print(str(exc))
            raise SystemExit(1)

    elif args.command == "schedule":
        items = schedule_questions(vault, args.count, args.subject)
        for index, item in enumerate(items, 1):
            print(
                f"  {index}. [{item['UID']}] M={float(item.get('Mastery', 0)):.2f} "
                f"P={item['_priority']} {item.get('Current_Tag', '')}"
            )

    elif args.command == "serve":
        OMRSHandler.vault_path = vault
        config = load_config(vault)
        bind_host = "" if config.get("allow_external") else "127.0.0.1"
        try:
            index = build_index(vault)
            print(f"已索引 {len(index)} 道题（扫描目录: {QUESTIONS_DIR}/）")
        except RuntimeError as exc:
            print(str(exc))
            raise SystemExit(1)
        OMRSHandler._restart_cmd = [
            sys.executable,
            os.path.abspath(sys.argv[0]),
        ] + list(sys.argv[1:])
        with socketserver.TCPServer((bind_host, args.port), OMRSHandler) as httpd:
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
            )
        elif args.uids:
            payload, session_id, default_name, _ = export_schedule_artifact(
                vault,
                _normalize_uid_list(args.uids.split(",")),
                "",
                args.format,
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
