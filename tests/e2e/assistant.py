"""AI 助手页：隔离 Vault + 假模型（OMRS_AGENT_FAUX_SCRIPT）的真实浏览器流程与版式审计。

覆盖：入口显示、空状态权限表、流式回答与引用芯片、需确认写入（对话框允许 / 内联拒绝）、停止、运行中插话、
检查器、按运行撤销、窄屏抽屉；审计无行内样式（KaTeX 除外）、无横向溢出。用法：python3 tests/e2e/assistant.py
"""
import json
import os
import base64
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, ROOT)
from browser_runtime import launch_chromium  # noqa: E402
from tests.test_drafts import make_png  # noqa: E402

FAUX = os.path.join(ROOT, "tests", "fixtures", "agent_faux.json")
AUDIT = """() => {
  const root = document.getElementById('panel-assistant');
  const shown = [...root.querySelectorAll('*')].filter(e => e.getClientRects().length && !e.closest('.katex'));
  return { inline: shown.filter(e => (e.getAttribute('style') || '').trim()).map(e => e.className).slice(0, 5),
           overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""


def make_vault():
    vault = tempfile.mkdtemp(prefix="omrs-ast-")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault], check=True,
                   stdout=subprocess.DEVNULL)
    from omrs.common import save_config
    save_config(vault, {"agent_enabled": True, "agent_vision": True})
    return vault


def start(vault, port):
    env = dict(os.environ, OMRS_AGENT_FAUX_SCRIPT=FAUX)
    env.pop("OMRS_SYSTEMD_SERVICE", None)
    log = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "omrs_engine.py"), "--vault", vault, "serve", "-p", str(port)],
                            env=env, stdout=log, stderr=log)
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auth/session", timeout=2)
            break
        except OSError:
            time.sleep(0.2)
    return proc


def api(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main():
    from playwright.sync_api import sync_playwright
    from fixtures.make_vault import free_port
    vault, port = make_vault(), free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start(vault, port)
    results, errors = [], []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)[:300]))

    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.on("console", lambda m: m.type == "error" and errors.append(m.text[:300]))
            page.goto(f"{base}/#/assistant", wait_until="networkidle")
            page.wait_for_selector(".ast-empty", timeout=8000)
            check("侧栏入口在启用后显示", page.is_visible('.tab[data-tab="assistant"]'))
            check("空状态列出四级权限", page.locator(".ast-perm__row").count() == 4)

            def say(text):
                page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000)  # 弹窗关闭动画结束后再输入
                page.fill("#ast-input", text)
                page.press("#ast-input", "Enter")

            def done(n, timeout=30000):
                page.wait_for_function(f"() => document.querySelectorAll('.ast-turn:not(.is-live)').length >= {n}", timeout=timeout)

            say("找一下和「周期」有关的题")
            page.wait_for_selector(".ast-turn.is-live", timeout=5000)
            page.fill("#ast-input", "顺便看看数列")
            page.press("#ast-input", "Enter")
            done(1)
            last = ".ast-turn:last-of-type"
            check("流式回答完成并渲染引用芯片", page.locator(f"{last} .ast-md .ast-ref").count() >= 1)
            check("运行中插话显示为送达的插话", page.wait_for_selector(f"{last} .ast-user--steer", timeout=3000) is not None,
                  page.locator(f"{last} .ast-user--steer").first.text_content() if page.locator(f"{last} .ast-user--steer").count() else "")
            page.locator(f"{last} .ast-md .ast-ref").first.click()
            check("点引用芯片打开题目", page.wait_for_selector("dialog[open]", timeout=5000) is not None)
            page.keyboard.press("Escape")
            check("Esc 关闭题目弹窗", page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000) is not None)

            say("帮我把今天要复习的题排出来，8 道以内。另外三角函数1的错因补一下")
            page.wait_for_selector(".ast-gate", timeout=20000)
            check("需确认写入先停在确认卡", page.locator(".ast-tool.is-waiting").count() == 1)
            page.click(".ast-gate [data-action='assistant.gate']")
            page.wait_for_selector(".ast-gate-dlg", timeout=5000)
            check("确认框展示现在 / 修改后", page.locator(".ast-gate-dlg .ast-diff__box").count() >= 2)
            page.click(".ast-gate-dlg [data-gate='allow']")
            done(2)
            check("允许后写入两条 commit", "写入 2" in page.locator(f"{last} .ast-foot").text_content())
            md = api(base, "/api/question?uid=" + urllib.request.quote("三角函数1")).get("markdown", "")
            check("错因写进题目文件", "第二象限" in json.dumps(api(base, "/api/question/raw?uid=" + urllib.request.quote("三角函数1")), ensure_ascii=False) or "第二象限" in md)

            page.click("[data-action='assistant.toggleInsp']")
            check("检查器列出写入记录", page.wait_for_selector(".ast-insp .ast-commit", timeout=3000) is not None)
            check("检查器画出时间线", page.locator(".ast-insp svg.ast-wf rect").count() >= 4)

            say("第一道做错了，自评 3 分；第二道做对了，8 分")
            page.wait_for_selector(".ast-gate", timeout=20000)
            page.click(".ast-gate [data-action='assistant.deny']")
            done(3)
            check("内联拒绝后反馈没有执行", page.locator(f"{last} .ast-tool.is-denied").count() == 1)

            page.locator(".ast-turn").nth(1).locator("[data-action='assistant.undo']").click()
            page.wait_for_selector(".ui-dialog .ast-undo-list", timeout=5000)
            page.click(".ui-dialog [data-dialog-ok]")
            page.wait_for_function("() => document.querySelectorAll('.ast-turn')[1].querySelector('.ast-foot')?.textContent.includes('已撤销')", timeout=10000)
            check("按运行撤销成功", True)
            check("撤销后 Ledger 仍有效", api(base, "/api/ledger/verify").get("valid", True))

            say("最近哪块最弱？")
            page.wait_for_selector("[data-action='assistant.stop']", timeout=5000)
            page.click("[data-action='assistant.stop']")
            done(4)
            check("停止后运行标为已中止", "已中止" in page.locator(f"{last} .ast-foot").text_content())

            page.set_input_files("#ast-image-picker", {"name": "question.png", "mimeType": "image/png", "buffer": make_png(12, 12)})
            page.wait_for_function("() => document.querySelectorAll('.ast-attachment').length === 1")
            check("选择图片出现可删除缩略图", page.locator('.ast-attachment__remove').count() == 1)
            page.set_input_files("#ast-image-picker", {"name": "too-large.png", "mimeType": "image/png", "buffer": b"x" * (8 * 1024 * 1024 + 1)})
            check("超过 8MB 的图片被忽略", page.locator('.ast-attachment').count() == 1)
            page.set_input_files("#ast-image-picker", [
                {"name": f"extra-{n}.png", "mimeType": "image/png", "buffer": make_png(12, 12, (n * 20, 0, 0))}
                for n in range(1, 7)])
            page.wait_for_function("() => document.querySelectorAll('.ast-attachment').length === 6")
            check("一次最多接收 6 张", page.locator('.ast-attachment').count() == 6)
            for _ in range(6):
                page.locator('.ast-attachment__remove').first.click()
            page.wait_for_function("() => document.querySelectorAll('.ast-attachment').length === 0")
            page.set_input_files("#ast-image-picker", {"name": "wide.png", "mimeType": "image/png", "buffer": make_png(4097, 1)})
            page.wait_for_function("() => document.querySelector('.ast-attachment img')?.naturalWidth === 4096")
            check("长边超过 4096 会缩放并转 JPEG", page.locator('.ast-attachment img').first.get_attribute('src').startswith('data:image/jpeg;base64,'))
            page.locator('.ast-attachment__remove').click()
            for kind, color in (("paste", (200, 0, 0)), ("drop", (0, 0, 200))):
                encoded = base64.b64encode(make_png(12, 12, color)).decode("ascii")
                page.evaluate("""({kind, encoded}) => {
                  const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
                  const data = new DataTransfer();
                  data.items.add(new File([bytes], `${kind}.png`, {type: 'image/png'}));
                  const target = kind === 'paste' ? document.getElementById('ast-input') : document.querySelector('.ast-composer');
                  target.dispatchEvent(kind === 'paste'
                    ? new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true})
                    : new DragEvent('drop', {dataTransfer: data, bubbles: true, cancelable: true}));
                }""", {"kind": kind, "encoded": encoded})
            page.wait_for_function("() => document.querySelectorAll('.ast-attachment').length === 2")
            check("粘贴和拖入都接收图片", page.locator('.ast-attachment').count() == 2)
            say("录一下这张截图")
            done(5)
            check("带图消息显示两张缩略图与 IMG 编号", page.locator('.ast-user__images .ast-image').count() == 2 and
                  "IMG-1" in page.locator('.ast-user__images').last.text_content())
            card = page.locator('.ast-tool').filter(has_text='建 AI 草稿').last
            check("草稿工具卡片显示编号和待框选", card.locator('.ast-draft-card').count() == 1 and
                  "DR-" in card.text_content() and "待框选" in card.text_content())
            crop_conv = page.evaluate("() => document.querySelector('.ast-conv.is-active')?.closest('[data-key]')?.dataset.key")
            page.wait_for_function("() => document.querySelector('.ast-draft-card')?.textContent.includes('我来框')", timeout=8000)
            check("询问模式卡片提供我来框", card.locator('[data-action="assistant.openDraft"]').filter(has_text='我来框').count() == 1)
            check("询问模式卡片提供 AI 框", card.locator('[data-action="assistant.detectDraft"]').count() == 1)
            page.evaluate("async () => fetch('/api/config', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inbox_detect_provider:'local_http',inbox_local_detect_url:'http://127.0.0.1:1/detect'})})")
            with page.expect_response(lambda r: r.url.endswith('/api/drafts/detect') and r.request.method == 'POST', timeout=10000) as detect_response:
                card.locator('[data-action="assistant.detectDraft"]').click()
            check("聊天卡片提交后台 AI 框选任务", detect_response.value.status == 200)
            crop_id = card.locator('.ast-draft-card code').first.inner_text()
            page.wait_for_function("id => [...document.querySelectorAll('.ast-draft-card')].some(card => card.textContent.includes(id) && card.textContent.includes('AI'))",
                                   arg=crop_id, timeout=10000)
            crop_detail = api(base, f'/api/drafts/item?id={crop_id}')["draft"]
            check("草稿详情可见 detect 作业", any(job["type"] == "detect" for job in crop_detail["jobs"]))
            page.wait_for_function("id => [...document.querySelectorAll('.ast-draft-card')].some(card => card.textContent.includes(id) && card.textContent.includes('重试 AI 框'))",
                                   arg=crop_id, timeout=10000)
            check("检测提供方失败后卡片可重试", card.locator('[data-action="assistant.detectDraft"]').filter(has_text='重试 AI 框').count() == 1)
            card.locator('[data-action="assistant.detectDraft"]').filter(has_text='重试 AI 框').click()
            page.wait_for_function("async id => (await (await fetch('/api/drafts/item?id=' + encodeURIComponent(id))).json()).draft.jobs.filter(j => j.type === 'detect').length >= 2",
                                   arg=crop_id, timeout=10000)
            check("重试新建第二个后台任务且不重复建草稿", len([job for job in api(base, f'/api/drafts/item?id={crop_id}')["draft"]["jobs"]
                                                if job["type"] == "detect"]) >= 2)
            check("图片原件可通过草稿接口打开", page.locator('.ast-user__images .ast-image').last.get_attribute('href').startswith('/api/drafts/image?sha='))

            page.wait_for_function("async () => (await (await fetch('/api/agent/status')).json()).active.length === 0", timeout=10000)
            old_conv = page.evaluate("() => document.querySelector('.ast-conv.is-active')?.closest('[data-key]')?.dataset.key")
            page.click('[data-action="assistant.newConv"]')
            page.wait_for_function("old => document.querySelector('.ast-conv.is-active')?.closest('[data-key]')?.dataset.key !== old && !!document.querySelector('.ast-empty')", arg=old_conv, timeout=5000)
            page.set_input_files('#ast-image-picker', {"name": "text-source.png", "mimeType": "image/png", "buffer": make_png(12, 12)})
            say("文字截图草稿")
            done(1)
            text_draft = api(base, '/api/drafts/list')["drafts"][0]
            detail = api(base, f'/api/drafts/item?id={text_draft["id"]}')["draft"]
            check("纯文字草稿保留指定来源截图", detail["status"] == "review" and
                  len(detail["source_images"]) == 1 and all(b["kind"] == "text" for b in detail["blocks"]),
                  {"id": detail["id"], "status": detail["status"], "sources": detail["source_images"], "blocks": detail["blocks"]})

            page.wait_for_function("async () => (await (await fetch('/api/agent/status')).json()).active.length === 0", timeout=10000)
            old_conv = page.evaluate("() => document.querySelector('.ast-conv.is-active')?.closest('[data-key]')?.dataset.key")
            page.click('[data-action="assistant.newConv"]')
            page.wait_for_function("old => document.querySelector('.ast-conv.is-active')?.closest('[data-key]')?.dataset.key !== old && !!document.querySelector('.ast-empty')", arg=old_conv, timeout=5000)
            page.evaluate("async () => fetch('/api/config', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({draft_mode:'confirm'})})")
            check("确认模式动态注册草稿入库工具", api(base, '/api/agent/status')["tools"].get('commit_draft') == 'confirm')
            say("确认草稿")
            page.wait_for_selector('.ast-turn .ast-gate', timeout=15000)
            gate = page.locator('.ast-turn .ast-gate').last
            check("草稿入库预览等待用户确认", '第 1 版' in gate.text_content())
            pending = api(base, '/api/drafts/list')["drafts"][0]
            before = api(base, f'/api/drafts/item?id={pending["id"]}')["draft"]
            changed = page.evaluate("""async ({id,revision,blocks}) => {
              const response = await fetch('/api/drafts/update', {method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({id,revision,fields:{note:'确认期间改过'},blocks})});
              return {status:response.status,data:await response.json()};
            }""", {"id": pending["id"], "revision": before["revision"], "blocks": before["blocks"]})
            check("确认等待期间编辑产生新版本", changed["status"] == 200 and
                  changed["data"]["draft"]["revision"] == before["revision"] + 1, changed)
            gate.locator('[data-action="assistant.gate"]').click()
            page.wait_for_selector('dialog[open] .ast-draft-review', timeout=5000)
            page.locator('dialog[open] [data-gate="allow"]').click()
            done(1)
            after = api(base, f'/api/drafts/item?id={pending["id"]}')["draft"]
            check("旧确认不能把改过的草稿入库", after["status"] == "review" and after["uid"] is None and
                  '草稿已经变化' in page.locator('.ast-turn').last.text_content())

            page.wait_for_function("async () => (await (await fetch('/api/agent/status')).json()).active.length === 0", timeout=10000)
            say("确认草稿")
            page.wait_for_selector('.ast-turn:last-of-type .ast-gate', timeout=15000)
            approved_id = page.locator('.ast-turn').last.locator('.ast-draft-card code').first.inner_text()
            page.locator('.ast-turn').last.locator('[data-action="assistant.gate"]').click()
            page.wait_for_selector('dialog[open] .ast-draft-review', timeout=5000)
            page.locator('dialog[open] [data-gate="allow"]').click()
            done(2)
            approved = api(base, f'/api/drafts/item?id={approved_id}')["draft"]
            check("确认模式允许后入库一次", approved["status"] == "done" and bool(approved["uid"]) and
                  api(base, '/api/ledger/verify').get('valid', True))

            discarded = page.evaluate("""async ({id,revision}) => {
              const response = await fetch('/api/drafts/discard', {method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({id,revision})}); return {status:response.status,data:await response.json()};
            }""", {"id": pending["id"], "revision": after["revision"]})
            check("测试草稿已丢弃", discarded["status"] == 200)
            page.goto(f"{base}/#/settings", wait_until='networkidle')
            page.goto(f"{base}/#/assistant", wait_until='networkidle')
            old_card = page.locator('.ast-draft-card').filter(has_text=pending["id"]).first
            old_card.wait_for(timeout=8000)
            page.wait_for_function("id => [...document.querySelectorAll('.ast-draft-card')].some(card => card.textContent.includes(id) && card.textContent.includes('已丢弃'))",
                                   arg=pending["id"], timeout=8000)
            check("旧卡片重新进入后显示当前已丢弃状态", '已丢弃' in old_card.text_content())

            audit = page.evaluate(AUDIT)
            check("桌面：没有行内样式、没有横向溢出", not audit["inline"] and not audit["overflow"], audit)

            page.goto(f"{base}/#/settings", wait_until="networkidle")
            page.click("#st-tab-assistant")
            page.wait_for_function("() => document.getElementById('st-agent-enabled')?.checked === true", timeout=5000)
            check("设置页显示主 AI 支持图片", page.locator('#st-agent-vision').is_checked())
            check("设置页读取 AI 录题方式", page.locator('#st-draft-mode').input_value() == 'confirm')
            check("框选与训练默认值正确", page.locator('#st-draft-crop-mode').input_value() == 'ask' and
                  not page.locator('#st-draft-train-default').is_checked() and
                  not page.locator('#st-draft-force-crop').is_checked())
            page.uncheck("#st-agent-enabled")
            page.click("[data-action='settings.saveAgent']")
            page.wait_for_function("() => document.querySelector('.tab[data-tab=\"assistant\"]').hidden", timeout=5000)
            check("设置里关闭后侧栏入口隐藏", api(base, "/api/agent/status")["enabled"] is False)
            page.check("#st-agent-enabled")
            page.select_option('#st-draft-crop-mode', 'manual')
            page.check('#st-draft-train-default')
            page.click("[data-action='settings.agentTest']")
            page.wait_for_function("() => document.getElementById('st-agent-status')?.textContent.includes('连接正常')", timeout=10000)
            check("测试连接成功且入口恢复", page.is_visible('.tab[data-tab="assistant"]'))
            check("测试连接显示图片直传结果", "图片直传正常" in page.locator('#st-agent-status').text_content())
            cfg = api(base, '/api/config')
            check("手动框选与训练默认开关已持久化", cfg['draft_crop_mode'] == 'manual' and cfg['draft_train_default'] is True)
            page.goto(f"{base}/#/assistant", wait_until='networkidle')
            page.click(f'[data-action="assistant.openConv"][data-arg="{crop_conv}"]')
            page.wait_for_function("() => document.querySelector('.ast-draft-card')?.textContent.includes('待框选')", timeout=8000)
            check("手动模式不在聊天卡片显示我来框", '我来框' not in page.locator('.ast-draft-card').first.text_content())

            page.goto(f"{base}/#/settings", wait_until='networkidle')
            page.click("#st-tab-assistant")
            page.select_option('#st-draft-crop-mode', 'auto')
            page.check('#st-draft-force-crop')
            page.click("[data-action='settings.saveAgent']")
            page.wait_for_function("() => document.getElementById('st-agent-status')?.textContent.includes('已保存')", timeout=5000)
            cfg = api(base, '/api/config')
            check("自动框选与全文字训练设置已持久化", cfg['draft_crop_mode'] == 'auto' and cfg['draft_force_crop'] is True)
            page.goto(f"{base}/#/assistant", wait_until='networkidle')
            page.click('[data-action="assistant.newConv"]')
            page.wait_for_selector('.ast-empty', timeout=5000)
            page.set_input_files('#ast-image-picker', {"name": "force-source.png", "mimeType": "image/png",
                                                        "buffer": make_png(12, 12, (0, 120, 0))})
            say("文字截图草稿")
            done(1)
            auto_draft = api(base, '/api/drafts/list')["drafts"][0]
            auto_detail = api(base, f'/api/drafts/item?id={auto_draft["id"]}')["draft"]
            check("全文字来源草稿生成独立训练任务且正文待审核", auto_detail['status'] == 'review' and
                  all(block['kind'] == 'text' for block in auto_detail['blocks']) and
                  any(task.get('force_crop') for task in auto_detail['training_tasks']))
            check("自动模式新建草稿只登记后台 detect", any(job['type'] == 'detect' for job in auto_detail['jobs']))
            check("自动模式卡片不显示我来框", '我来框' not in page.locator('.ast-draft-card').last.text_content())

            mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            mobile.goto(f"{base}/#/assistant", wait_until="networkidle")
            mobile.wait_for_selector(".ast-turn", timeout=8000)
            audit = mobile.evaluate(AUDIT)
            check("390px：没有行内样式、没有横向溢出", not audit["inline"] and not audit["overflow"], audit)
            mobile.click("[data-action='assistant.toggleRail']")
            mobile.wait_for_timeout(400)
            check("390px：对话列表从左侧抽屉打开", mobile.evaluate("() => document.querySelector('.ast').dataset.rail === 'open' && document.querySelector('.ast-rail').getBoundingClientRect().left >= 0"))
            mobile.wait_for_function("async () => (await (await fetch('/api/agent/status')).json()).active.length === 0", timeout=10000)
            mobile.click('[data-action="assistant.newConv"]')
            mobile.wait_for_selector('.ast-empty', timeout=5000)
            jpeg = base64.b64decode(mobile.evaluate("""() => {
              const canvas = document.createElement('canvas');
              canvas.width = 12; canvas.height = 12;
              canvas.getContext('2d').fillRect(0, 0, 12, 12);
              return canvas.toDataURL('image/jpeg').split(',')[1];
            }"""))
            check("浏览器生成的 JPEG 原图完整", jpeg.endswith(b'\xff\xd9'))
            mobile.set_input_files('#ast-image-picker', {"name": "phone.jpg", "mimeType": "image/jpeg", "buffer": jpeg[:-2]})
            mobile.wait_for_function("() => document.querySelectorAll('.ast-attachment').length === 1")
            prepared = mobile.locator('.ast-attachment img').first.get_attribute('src')
            check("缺少结束标记的手机 JPEG 在发送前重新编码", prepared.startswith('data:image/jpeg;base64,') and
                  base64.b64decode(prepared.split(',', 1)[1]).endswith(b'\xff\xd9'))
            mobile.fill('#ast-input', '添加题目')
            mobile.press('#ast-input', 'Enter')
            mobile.wait_for_function("() => document.querySelectorAll('.ast-turn:not(.is-live)').length >= 1", timeout=30000)
            image_url = mobile.locator('.ast-user__images .ast-image').last.get_attribute('href')
            with urllib.request.urlopen(base + image_url, timeout=10) as response:
                saved = response.read()
            check("修复后的 JPEG 已保存并能通过图片接口读取", saved.endswith(b'\xff\xd9'))
            browser.close()
    except Exception as exc:  # noqa: BLE001
        results.append(("执行出错", False, repr(exc)[:400]))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(vault, ignore_errors=True)
    check("页面没有脚本错误", not errors, errors[:3])
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")
    print(f"{len(results) - len(failed)}/{len(results)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
