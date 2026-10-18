"""展示板空纸面专项：真实 HTTP、加题／移除、导出拦截、主题截图与请求取消。"""
import json
import os
from pathlib import Path

from browser_runtime import open_app


def run_empty_paths(browser, base, port, results, http, record):
    shots = Path(os.environ.get("OMRS_BOARD_EMPTY_SHOTS", "/tmp/omrs-board-empty-v284-states"))
    shots.mkdir(parents=True, exist_ok=True)
    def question(text):
        return http(port, "/api/create", {"subject": "数学", "category": "空板回归", "question_text": text})
    q = question("求函数 $f(x)=x+1$ 在 $x=1$ 时的值。")
    off, lost = question("停用对照题"), question("归档对照题")
    def create(name, entry=None):
        return http(port, "/api/board/create", {"name": name, "question_refs": [{"question_id": entry["question_id"]}] if entry else []})["board"]["id"]
    empty, suspended, missing, populated = create("空板回归"), create("全停用回归", off), create("全缺失回归", lost), create("错误回归", q)
    http(port, "/api/question/suspend", {"question_id": off["question_id"]})
    http(port, "/api/question/delete", {"question_id": lost["question_id"]})
    for theme in ("light", "dark"):
        for width in (1440, 390):
            context = browser.new_context(viewport={"width": width, "height": 900 if width == 1440 else 844})
            context.add_init_script(path=os.path.join(os.path.dirname(__file__), "p8_test_modules.js"))
            context.add_init_script(f"localStorage.setItem('omrs-theme', {json.dumps(theme)})")
            page = context.new_page()
            page.set_default_timeout(15000)
            errors, exports, popups = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("popup", lambda popup: popups.append(popup))
            def requested(request):
                if request.url.endswith("/api/export"):
                    exports.append(request.post_data_json["board_id"])
            page.on("request", requested)
            prefix = f"{theme}-{width}"
            def shot(name):
                page.screenshot(path=str(shots / f"{prefix}-{name}.png"), full_page=True)
            def load(bid):
                page.evaluate("id => boardLoad(id)", bid)
                page.wait_for_function("id => BOARD_DETAIL?.id === id", arg=bid)
            def empty_ready(message):
                page.wait_for_function("""message => {
                    const stage = document.querySelector('#bd-stage');
                    return stage?.hidden && document.querySelector('.brd-desk-empty')?.textContent === message &&
                      !document.querySelector('.brd-preview-err') && !boardPreviewIsReady() &&
                      boardPreviewLayout() === null && boardPreviewFrame()?.srcdoc === '';
                }""", arg=message)
            try:
                open_app(page, base, "board")
                page.wait_for_function("() => typeof boardLoad === 'function'")
                load(empty)
                empty_ready("板里还没有题，添加题目后可预览")
                page.evaluate("() => { window.__emptyFrame = boardPreviewFrame(); }")
                disabled = page.locator('[data-action="board.primary"]').is_disabled() and page.locator('.brd-bar [data-action="board.export"]').is_disabled()
                page.keyboard.press("p")
                page.evaluate("() => boardExportCurrent(false)")
                page.locator('.brd-bar [data-action="board.menu"]').click()
                page.locator('.ui-menu__item', has_text="导出 HTML").click()
                record(results, f"{prefix}：初始空板、按钮／快捷键／菜单拦截，无请求或弹窗", disabled and empty not in exports and not popups)
                shot("empty")

                page.locator('[data-action="board.add"]').first.click()
                page.locator(f'dialog#bd-add-dialog [data-bdadd-uid="{q["uid"]}"]').check()
                page.locator('dialog#bd-add-dialog [data-dialog-ok]').click()
                page.wait_for_function("id => boardPreviewIsReady() && boardPreviewLayout()?.board_id === id", arg=empty)
                record(results, f"{prefix}：从空板加题后自动预览，同一 iframe", page.evaluate("() => boardPreviewFrame() === window.__emptyFrame"))
                shot("filled")
                before = exports.count(empty)
                page.locator('.brd-row').first.click()
                page.locator('#bd-inspector [data-action="board.remove"]').click()
                page.wait_for_function("() => BOARD_DETAIL.items.length === 0")
                empty_ready("板里还没有题，添加题目后可预览")
                record(results, f"{prefix}：移除最后一题清空纸面、页码与旧状态，不再次导出", exports.count(empty) == before and page.locator('[data-board-page-input]').is_disabled())
                shot("cleared")
                for bid, name, reason in ((suspended, "all-suspended", "停用"), (missing, "all-missing", "缺失")):
                    load(bid)
                    empty_ready("当前没有可打印的题目")
                    record(results, f"{prefix}：全部{reason}显示原因、无预览请求", bid not in exports and reason in page.locator('.brd-warn').inner_text())
                    shot(name)
                record(results, f"{prefix}：空状态无横向溢出或脚本错误", not errors and page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"), errors)
            except Exception as error:
                record(results, f"{prefix}：空状态路径中途出错", False, str(error).splitlines()[0])
            finally:
                context.close()

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(path=os.path.join(os.path.dirname(__file__), "p8_test_modules.js"))
    page = context.new_page()
    try:
        open_app(page, base, "board")
        page.wait_for_function("() => typeof boardLoad === 'function'")
        page.evaluate("id => boardLoad(id)", empty)
        held = []
        page.route("**/api/export", lambda route: held.append(route))
        with page.expect_request("**/api/export"):
            page.evaluate("id => boardLoad(id)", populated)
        page.evaluate("id => boardLoad(id)", empty)
        page.wait_for_function("() => document.querySelector('#bd-stage').hidden && !boardPreviewIsReady()")
        try:
            held[0].fulfill(status=500, content_type="application/json", body=json.dumps({"msg": "旧板延迟失败"}))
        except Exception:
            pass  # AbortController 已取消浏览器请求时，路由无法再回包。
        record(results, "浏览器慢请求：切空板取消在途导出，晚到失败不能恢复旧内容或错误",
               page.evaluate("() => boardPreviewFrame().srcdoc === '' && !document.querySelector('.brd-preview-err')"))
        page.unroute("**/api/export")
        for network, message in ((True, "Failed to fetch"), (False, "测试生成错误")):
            page.evaluate("id => boardLoad(id)", empty)
            def fail(route):
                if network:
                    route.abort("failed")
                else:
                    route.fulfill(status=500, content_type="application/json", body=json.dumps({"status": "error", "msg": message}))
            page.route("**/api/export", fail)
            page.evaluate("id => boardLoad(id)", populated)
            page.locator('.brd-preview-err').wait_for()
            record(results, "真实网络请求失败仍显示具体原因：" + message, message in page.locator('.brd-preview-err').get_attribute("title"))
            page.unroute("**/api/export", fail)
    except Exception as error:
        record(results, "慢请求／真实失败路径中途出错", False, str(error).splitlines()[0])
    finally:
        context.close()
    (shots / "checks.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
