"""Responses 闭环：真实设置/聊天页面、临时 Vault、随机端口与合成 HTTP 模型服务。"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from browser_runtime import launch_chromium, open_app  # noqa: E402
from fixtures.make_vault import free_port  # noqa: E402
from omrs.agent.store import AgentStore  # noqa: E402
from tests.test_llm_responses import message, reasoning, response, terminal, tool_call  # noqa: E402


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        try:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.requests.append((self.path, payload))
            assert self.path == "/v1/responses", "必须使用 Responses 路径"
            assert "input" in payload and "messages" not in payload, "必须使用 input"
            assert payload["store"] is False and "previous_response_id" not in payload, "上下文必须保存在本地"
            assert "max_output_tokens" in payload and "stream_options" not in payload, "输出上限字段错误"
            assert all("function" not in tool and tool["strict"] is False for tool in payload.get("tools", [])), "工具必须平铺且保留可选参数"
            serial = len(self.server.requests)
            items = payload["input"]
            if not payload["stream"]:
                if payload.get("tools"):
                    output = [tool_call("ping", "{}", f"call_ping_{serial}")]
                else:
                    assert any(part.get("type") == "input_image" for item in items
                               for part in item.get("content", []) if isinstance(part, dict)), "图片必须转换为 input_image"
                    output = [message("白色")]
            elif items[-1].get("type") == "function_call_output":
                assert any(item.get("encrypted_content") == "完整的加密推理" for item in items), "工具续轮缺加密推理"
                call_id = items[-1]["call_id"]
                assert any(item.get("type") == "function_call" and item["call_id"] == call_id for item in items), "结果必须匹配 call_id"
                result = json.loads(items[-1]["output"])
                assert isinstance(result, dict) and result, "应读取真实题库概况"
                output = [message("Responses 已查询数学概况。")]
            else:
                output = [reasoning(), tool_call("get_overview", '{"subject":"数学"}', f"call_overview_{serial}")]
            output = copy.deepcopy(output)
            for index, item in enumerate(output):
                item["id"] = f"{item['id']}_{serial}_{index}"
            data = response(output)
            data["id"] = f"resp_{serial}"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream" if payload["stream"] else "application/json")
            self.end_headers()
            if not payload["stream"]:
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
                return
            events = []
            for index, item in enumerate(output):
                start = {**item, "arguments": ""} if item["type"] == "function_call" else item
                events.append({"type": "response.output_item.added", "output_index": index, "item": start})
                if item["type"] == "function_call":
                    for text in (item["arguments"][:7], item["arguments"][7:]):
                        events.append({"type": "response.function_call_arguments.delta", "output_index": index, "delta": text})
                elif item["type"] == "reasoning":
                    events.append({"type": "response.reasoning_summary_text.delta", "delta": "先查询"})
                else:
                    events.append({"type": "response.output_text.delta", "delta": item["content"][0]["text"]})
                events.append({"type": "response.output_item.done", "output_index": index, "item": item})
            events.append(terminal(data))
            for event in events:
                self.wfile.write(("event: " + event["type"] + "\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode())
                self.wfile.flush()
        except Exception as error:  # noqa: BLE001 - 合成供应商的断言失败要传回页面并记录
            self.server.errors.append(str(error))
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": str(error)}}).encode())


def main():
    from playwright.sync_api import sync_playwright
    vault = tempfile.mkdtemp(prefix="omrs-responses-")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    server.requests, server.errors = [], []
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    process = None
    results, errors = [], []

    def check(label, ok):
        results.append((label, bool(ok)))

    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "tests/fixtures/make_vault.py"), "--out", vault],
                       check=True, stdout=subprocess.DEVNULL)
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ)
        for key in ("OMRS_SYSTEMD_SERVICE", "OMRS_BOXDETECT_CONTROL", "OMRS_AGENT_FAUX_SCRIPT"):
            env.pop(key, None)
        with tempfile.NamedTemporaryFile(prefix="omrs-responses-server-", suffix=".log", mode="w+") as log:
            process = subprocess.Popen([sys.executable, os.path.join(ROOT, "omrs_engine.py"), "--vault", vault,
                                        "serve", "-p", str(port)], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base + "/api/auth/session", timeout=2):
                        break
                except OSError:
                    time.sleep(0.2)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                open_app(page, base, "settings")
                page.locator('[data-st-section="assistant"]').click()
                page.wait_for_selector("#st-agent-compat")
                page.wait_for_function("() => !!document.querySelector('#st-agent-key-state')?.textContent")
                check("选项显示 OpenAI（Responses）", page.locator('#st-agent-compat option[value="openai"]').text_content() == "OpenAI（Responses）")
                page.check("#st-agent-enabled")
                page.check("#st-agent-vision")
                page.fill("#st-agent-base", f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions")
                page.fill("#st-agent-key", "responses-test-key")
                page.fill("#st-agent-model", "responses-test")
                page.select_option("#st-agent-compat", "openai")
                page.click('[data-action="settings.agentTest"]')
                page.wait_for_function("() => /连接正常|连接失败/.test(document.querySelector('#st-agent-status')?.textContent || '')")
                check("连接测试验证工具与图片", "支持工具调用" in page.locator("#st-agent-status").inner_text()
                      and "图片直传正常" in page.locator("#st-agent-status").inner_text())
                page.reload(wait_until="networkidle")
                page.locator('[data-st-section="assistant"]').click()
                page.wait_for_function("() => document.querySelector('#st-agent-compat')?.value === 'openai'")
                check("刷新保留协议选择", page.input_value("#st-agent-compat") == "openai")
                page.click('.tab[data-tab="assistant"]')
                page.wait_for_selector("#ast-input")
                page.fill("#ast-input", "查一下数学科目的概况")
                page.click('[data-action="assistant.send"]')
                page.wait_for_selector(".ast-turn:not(.is-live)", timeout=30000)
                check("Responses 工具执行后显示最终回答", "Responses 已查询数学概况。" in page.locator(".ast-turn").inner_text())
                check("推理摘要显示在聊天轨迹", "先查询" in page.locator(".ast-turn").inner_text())
                check("工具请求使用设置的输出上限", all(payload["max_output_tokens"] == 10240 for _, payload in server.requests if payload["stream"]))
                page.reload(wait_until="networkidle")
                page.wait_for_selector(".ast-turn:not(.is-live)")
                check("刷新重放回答与用量", "Responses 已查询数学概况。" in page.locator(".ast-turn").inner_text()
                      and "缓存" in page.locator(".ast-meter").inner_text())
                page.fill("#ast-input", "再查一次")
                page.click('[data-action="assistant.send"]')
                page.wait_for_function("() => document.querySelectorAll('.ast-turn:not(.is-live)').length === 2", timeout=30000)
                check("持久上下文支持下一次用户消息", len([body for _, body in server.requests if body["stream"]]) == 4)
                store = AgentStore(vault)
                conv_id = store.conversations()[0]["id"]
                check("原生推理和工具项保存在 agent.db", any(item.get("encrypted_content") == "完整的加密推理"
                      for msg in store.messages(conv_id) for item in msg.get("_response_items", [])))
                for width in (1440, 390):
                    page.set_viewport_size({"width": width, "height": 900})
                    check(f"{width}px 无横向溢出", page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
                context.close()
    except Exception as error:  # noqa: BLE001
        results.append((f"执行出错：{error!r}", False))
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        shutil.rmtree(vault, ignore_errors=True)
    check("合成供应商无协议拒绝", not server.errors)
    check("无页面脚本错误", not errors)
    for label, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    print(f"{sum(ok for _, ok in results)}/{len(results)} 通过")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
