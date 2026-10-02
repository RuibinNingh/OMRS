"""审计修复的真实页面闭环：旧计划绑定、稳定身份预览、大图与助手历史。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from browser_runtime import launch_chromium, open_app
from fixtures.make_vault import free_port
from tests.e2e.create import png


def api(base, path, body=None):
    request = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def seed(vault):
    from omrs.common import save_config
    from omrs.creation import create_question
    from omrs.ledger import append_commit
    from omrs.projections import rebuild_projection
    from omrs.agent.store import AgentStore

    question = create_question(vault, "数学", "代数", 5, question_text="绑定题面", answer_text="答案")
    save_config(vault, {"agent_enabled": True, "agent_vision": True})
    append_commit(vault, "test", "legacy.bootstrap", "旧计划夹具", {
        "session_rows": [{"Session_ID": "S0", "UIDs": json.dumps([question["uid"]]), "Status": "active"}]})
    rebuild_projection(vault)
    store = AgentStore(vault)
    for index in range(65):
        store.create_conversation(f"old_{index:02d}", f"旧对话{index:02d}")
    store.create_conversation("many", "完整历史")
    for index in range(45):
        run = f"history_{index:02d}"
        store.create_run(run, "many", "test")
        store._exec("UPDATE runs SET started_at=? WHERE id=?", (f"2026-10-01T00:{index:02d}:00Z", run))
        text = f"历史用户{index:02d} " + ("内容" * 350 if index == 44 else "原文")
        store.add_message("many", run, {"role": "user", "content": text})
        events = [{"type": "round.start", "t": 0, "data": {"n": 1}}]
        if index == 44:
            events.extend({"type": "delta", "t": i + 1, "data": {"kind": "text", "n": 1, "text": "段"}}
                          for i in range(407))
        events.extend([
            {"type": "delta", "t": 500, "data": {"kind": "text", "n": 1, "text": f"末尾标记{index:02d}"}},
            {"type": "round.end", "t": 501, "data": {"n": 1, "usage": {}}},
            {"type": "run.end", "t": 502, "data": {"reason": "completed"}}])
        store.save_run(run, status="done", reason="completed", events=events, ended=True)
    store._exec("UPDATE conversations SET updated_at='2099-01-01T00:00:00Z' WHERE id='many'")
    return question


def main():
    from playwright.sync_api import sync_playwright
    results, errors = [], []

    def check(name, ok):
        results.append(bool(ok))
        print(("PASS " if ok else "FAIL ") + name, flush=True)

    with tempfile.TemporaryDirectory(prefix="omrs-audit-ui-") as work:
        vault = str(Path(work) / "vault")
        subprocess.run([sys.executable, str(ROOT / "tests/fixtures/make_vault.py"), "--out", vault, "--profile", "empty"],
                       check=True, stdout=subprocess.DEVNULL)
        question = seed(vault)
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, OMRS_AGENT_FAUX_SCRIPT=str(ROOT / "tests/fixtures/agent_faux.json"))
        env.pop("OMRS_SYSTEMD_SERVICE", None)
        env.pop("OMRS_BOXDETECT_CONTROL", None)
        with (Path(work) / "server.log").open("w") as log:
            server = subprocess.Popen([sys.executable, str(ROOT / "omrs_engine.py"), "--vault", vault, "serve", "-p", str(port)],
                                      cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        api(base, "/api/status")
                        break
                    except OSError:
                        time.sleep(.1)
                with sync_playwright() as playwright:
                    browser = launch_chromium(playwright)
                    page = browser.new_page(viewport={"width": 1440, "height": 900})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    open_app(page, base, "schedule")
                    page.locator('#sch-tab-plans').click()
                    page.locator('[data-action="schedule.open"][data-arg="S0"]').click()
                    page.locator('[data-action="schedule.bind"]').wait_for()
                    check("旧计划保留编号且绑定前禁止导出", page.locator('.schd-q__n').inner_text() == "1"
                          and page.locator('[data-action="schedule.export"]').first.is_disabled())
                    page.locator('[data-action="schedule.bind"]').click()
                    page.locator('#question-pick-value').select_option(question["question_id"])
                    page.locator('dialog[open] [data-dialog-ok]').click()
                    page.wait_for_function("() => !document.querySelector('[data-action=\"schedule.bind\"]')")
                    bound = api(base, "/api/session?id=S0")
                    check("人工确认后绑定稳定题目并保持条目编号", bound["entries"][0]["question_id"] == question["question_id"]
                          and page.locator('.schd-q__n').inner_text() == "1")

                    preview_questions = [api(base, '/api/create', {"subject": "数学", "category": "预览原位", "difficulty": 5,
                        "question_text": f"计划原身份题面{index}", "answer_text": "答案"}) for index in range(2)]
                    preview_plan = api(base, '/api/confirm-schedule', {"persist": True, "selected": [
                        {"question_id": item["question_id"], "source": "due"} for item in preview_questions]})
                    page.evaluate("async () => { const d = await import('/assets/app/domain/data.js'); await d.reloadData(); }")
                    page.locator('[data-action="schedule.refresh"]').click()
                    preview_open = page.locator(f'[data-action="schedule.open"][data-arg="{preview_plan["session_id"]}"]')
                    preview_open.wait_for()
                    preview_open.click()
                    page.wait_for_function("() => document.querySelectorAll('[data-action=\"schedule.preview\"]').length === 2")
                    for index, item in enumerate(preview_questions):
                        api(base, '/api/question/move', {"question_id": item["question_id"], "subject": "数学", "category": f"预览迁移{index}"})
                    replacements = [api(base, '/api/create', {"subject": "数学", "category": "预览原位", "difficulty": 5,
                        "question_text": f"复用编号替代题面{index}"}) for index in range(2)]
                    page.evaluate("async () => { const d = await import('/assets/app/domain/data.js'); await d.reloadData(); }")
                    check("计划旧UID快照保持但当前题库已复用编号", [item['uid'] for item in preview_questions] == [item['uid'] for item in replacements]
                          and page.locator('.schd-q__main strong').all_text_contents() == [item['uid'] for item in preview_questions])
                    with page.expect_response(lambda response: '/api/question?question_id=' + preview_questions[0]['question_id'] in response.url) as first_preview:
                        page.locator('[data-action="schedule.preview"]').first.click()
                    page.wait_for_function("() => document.querySelector('#modal .qv')?.textContent.includes('计划原身份题面0')")
                    check("旧UID复用后计划预览仍读取原稳定身份", first_preview.value.json()['question_id'] == preview_questions[0]['question_id']
                          and '复用编号替代题面' not in page.locator('#modal .qv').inner_text())
                    with page.expect_response(lambda response: '/api/question?question_id=' + preview_questions[1]['question_id'] in response.url) as next_preview:
                        page.locator('#modal [data-qv-nav="next"]').click()
                    page.wait_for_function("() => document.querySelector('#modal .qv')?.textContent.includes('计划原身份题面1')")
                    check("计划预览翻页上下文仍绑定下一题原身份", next_preview.value.json()['question_id'] == preview_questions[1]['question_id']
                          and '复用编号替代题面' not in page.locator('#modal .qv').inner_text())
                    page.locator('#modal [data-dialog-cancel]').click()

                    catalog = api(base, '/api/boards')
                    board = api(base, '/api/board/create', {"name": "同UID身份隔离", "question_refs": [{"question_id": question["question_id"]}],
                                "expected_catalog_revision": catalog["catalog_revision"]})["board"]
                    api(base, '/api/question/delete', {"question_id": question["question_id"]})
                    reused = api(base, '/api/create', {"subject": "数学", "category": "代数", "difficulty": 5,
                                                      "question_text": "复用UID的新题面", "answer_text": "新答案"})
                    board = api(base, '/api/board/items/add', {"id": board["id"], "question_refs": [{"question_id": reused["question_id"]}],
                                "expected_revision": board["revision"]})["board"]
                    open_app(page, base, "board")
                    page.locator(f'[data-action="board.open"][data-arg="{board["id"]}"]').click()
                    page.locator(f'[data-board-key="{reused["question_id"]}"]').wait_for()
                    row = page.locator(f'[data-board-key="{reused["question_id"]}"]')
                    with page.expect_response(lambda response: '/api/board/update' in response.url and response.request.method == 'POST') as saving:
                        row.locator('[data-action="board.gapStep"][data-arg$=":1"]').click()
                    current = api(base, '/api/board?id=' + board["id"])["board"]
                    old, new = current["items"]
                    check("同UID旧归档与新题行独立，留白只写选中的稳定身份", reused["uid"] == question["uid"]
                          and old["missing"] and old.get("gap_lines") is None and new["gap_lines"] == 3
                          and page.locator('.brd-row').count() == 2)
                    row.locator('.brd-row__uid').click()
                    page.wait_for_function("() => document.querySelector('#bd-inspector .qv')?.textContent.includes('复用UID的新题面')")
                    check("同UID新题详情展示自己的题面", page.locator('#bd-inspector [data-qv-host]').get_attribute('data-question-id') == reused["question_id"])
                    held = []
                    pattern = '**/api/question?question_id=' + question["question_id"]
                    page.route(pattern, lambda route: held.append(route))
                    page.evaluate("""async ([uid, oldId, newId]) => {
                        const { qvRender } = await import('/assets/app/domain/question/index.js');
                        const target = document.createElement('div'); target.id = 'audit-qv-race';
                        document.body.append(target);
                        window.__auditOldRead = qvRender(target, uid, { question_id: oldId });
                        await qvRender(target, uid, { question_id: newId });
                    }""", [reused["uid"], question["question_id"], reused["question_id"]])
                    page.wait_for_timeout(100)
                    held[0].fulfill(status=200, content_type='application/json', body=json.dumps({"uid": question["uid"],
                        "question_id": question["question_id"], "question": "迟到的旧身份题面"}))
                    page.evaluate('window.__auditOldRead')
                    check("同UID不同身份的迟到详情不覆盖新题挂载", "复用UID的新题面" in page.locator('#audit-qv-race').inner_text()
                          and "迟到的旧身份题面" not in page.locator('#audit-qv-race').inner_text())
                    page.unroute(pattern)
                    page.evaluate("document.querySelector('#audit-qv-race').remove()")

                    open_app(page, base, "create")
                    large = png(75) + b"x" * (16 * 1024 * 1024 + 128)
                    chunks = []
                    page.on("request", lambda request: chunks.append(len(request.post_data_buffer or b""))
                            if "/api/uploads/chunk?" in request.url else None)
                    page.locator('#ib-file').set_input_files({"name": "原始大图.png", "mimeType": "image/png", "buffer": large})
                    page.wait_for_function("() => document.querySelector('#ib-up-status')?.textContent.includes('已接收')", timeout=30000)
                    item = next(item for item in api(base, "/api/inbox/items")["items"] if item["file"] == "原始大图.png")
                    with urllib.request.urlopen(base + "/api/inbox/raw?id=" + item["id"]) as response:
                        raw, mime = response.read(), response.headers["Content-Type"]
                    check("大于16MiB原图真实分块且原字节、MIME和名称保持", len(chunks) == 2 and max(chunks) <= 16 * 1024 * 1024
                          and raw == large and mime == "image/png" and item["sha256"] == hashlib.sha256(large).hexdigest())

                    open_app(page, base, "assistant")
                    page.locator('.ast-user').first.wait_for()
                    check("助手首屏有界读取最新20个运行组", page.locator('.ast-user').count() == 20 and page.locator('.ast-turn').count() == 20)
                    page.locator('[data-action="assistant.moreConversations"]').click()
                    page.wait_for_function("() => document.querySelectorAll('.ast-conv').length === 60")
                    page.locator('[data-action="assistant.moreConversations"]').click()
                    page.wait_for_function("() => document.querySelectorAll('.ast-conv').length === 66")
                    check("更多对话可读完全部66条且无重复", page.locator('.ast-conv').evaluate_all("rows => new Set(rows.map(row => row.dataset.arg)).size") == 66)
                    page.locator('[data-action="assistant.toggleLong"]').click()
                    page.evaluate("window.__auditUser = [...document.querySelectorAll('.ast-user')].at(-1)")
                    page.locator('[data-action="assistant.loadHistory"]').click()
                    page.wait_for_function("() => document.querySelectorAll('.ast-turn').length === 40")
                    page.locator('[data-action="assistant.loadHistory"]').click()
                    page.wait_for_function("() => document.querySelectorAll('.ast-turn').length === 45")
                    check("逐页读完45次历史且当前长消息DOM与展开态保留", page.locator('.ast-user').count() == 45
                          and page.evaluate("window.__auditUser === [...document.querySelectorAll('.ast-user')].at(-1)")
                          and page.locator('[data-action="assistant.toggleLong"]').inner_text() == "收起")
                    check("部分轨迹明确提示尚未全部读取", page.locator('[data-action="assistant.loadRunEvents"]').count() == 1
                          and "末尾标记44" not in page.locator('[data-key="run-history_44"]').inner_text())
                    page.locator('[data-action="assistant.loadRunEvents"]').click()
                    page.wait_for_timeout(250)
                    page.locator('[data-action="assistant.loadRunEvents"]').click()
                    page.wait_for_function("() => !document.querySelector('[data-action=\"assistant.loadRunEvents\"]')")
                    answer = page.locator('[data-key="run-history_44"] .ast-result').inner_text()
                    check("全部411事件可续接读完并显示最终完整回答", answer.count("段") == 407 and "末尾标记44" in answer)
                    check("专项页面路径没有脚本错误", not errors)
                    page.close()
                    browser.close()
            finally:
                server.terminate()
                server.wait(timeout=10)
    print(f"E2E audit_identity：{sum(results)}/{len(results)} 通过")
    return int(not all(results))


if __name__ == "__main__":
    raise SystemExit(main())
