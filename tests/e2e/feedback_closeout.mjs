/** 反馈结单开发回归。Node 与本机 Chromium，独立 Vault 和随机回环端口。 */
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const work = await mkdtemp(join(tmpdir(), 'omrs-feedback-closeout-'));
const env = { ...process.env, PYTHONDONTWRITEBYTECODE: '1' };
delete env.OMRS_SYSTEMD_SERVICE;
delete env.OMRS_BOXDETECT_CONTROL;
const python = process.env.OMRS_TEST_PYTHON || 'python3';
const executable = process.env.OMRS_TEST_CHROMIUM || 'chromium';
const processes = [];
const checks = [];
const scriptErrors = [];
let socket;

function start(command, args) {
  const child = spawn(command, args, { cwd: root, env, stdio: ['ignore', 'ignore', 'pipe'] });
  child.details = '';
  child.stderr.on('data', data => { child.details = (child.details + data).slice(-4000); });
  child.once('error', error => { child.details += error.message; });
  processes.push(child);
  return child;
}

async function poll(probe, label, timeout = 12000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    try {
      const result = await probe();
      if (result) return result;
    } catch (error) {
      if (!(error.cause || error.code === 'ENOENT')) throw error;
    }
    await sleep(75);
  }
  throw new Error(label);
}

function check(value, label) {
  assert.ok(value, label);
  checks.push(label);
  console.log('通过', label);
}

try {
  const seed = spawnSync(python, ['-c', `
import json, sys
from omrs.creation import create_question
from omrs.sessions import create_session_from_selection
vault = sys.argv[1]
questions = [create_question(vault, '数学', f'合成{i}', 5, question_text='求 1+1', answer_text='2') for i in range(6)]
selected = [{"question_id": q["question_id"], "source": "due"} for q in questions]
first = create_session_from_selection(vault, selected[:4])
second = create_session_from_selection(vault, selected[4:])
print(json.dumps([first["session_id"], second["session_id"], questions], ensure_ascii=False))
`, work], { cwd: root, env, encoding: 'utf8' });
  assert.equal(seed.status, 0, seed.stderr);
  const [sid, otherSid, questions] = JSON.parse(seed.stdout.trim().split('\n').at(-1));
  const listener = createServer().listen(0, '127.0.0.1');
  await once(listener, 'listening');
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  start(python, ['omrs_engine.py', '--vault', work, 'serve', '-p', String(port)]);
  const base = `http://127.0.0.1:${port}`;
  await poll(async () => (await fetch(base)).ok, '隔离 OMRS 未启动');
  const headless = ['--headless', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
    '--disable-background-networking', '--no-first-run', '--no-default-browser-check', `--user-data-dir=${join(work, 'chromium')}`];
  if (process.getuid?.() === 0) headless.push('--no-sandbox');
  start(executable, [...headless, 'about:blank']);
  const [cdpPort] = (await poll(() => readFile(join(work, 'chromium', 'DevToolsActivePort'), 'utf8'), 'Chromium 未启动')).split('\n');
  const endpoint = await fetch(`http://127.0.0.1:${cdpPort}/json/new?about:blank`, { method: 'PUT' }).then(res => res.json());
  socket = new WebSocket(endpoint.webSocketDebuggerUrl);
  await once(socket, 'open');
  let seq = 0;
  const pending = new Map();
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') {
      const error = message.params.exceptionDetails;
      scriptErrors.push(error.exception?.description || error.text);
    }
    if (pending.has(message.id)) pending.get(message.id)(message);
  });
  async function call(method, params = {}) {
    const id = ++seq;
    let timer;
    try {
      const reply = await new Promise((resolve, reject) => {
        pending.set(id, resolve);
        timer = setTimeout(() => reject(new Error(method + ' 超时')), 15000);
        socket.send(JSON.stringify({ id, method, params }));
      });
      assert.ok(!reply.error, JSON.stringify(reply.error));
      return reply.result;
    } finally {
      clearTimeout(timer);
      pending.delete(id);
    }
  }
  async function evaluate(expression) {
    const output = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (output.exceptionDetails) throw new Error(output.exceptionDetails.exception?.description || output.exceptionDetails.text);
    return output.result.value;
  }
  async function page(url) {
    await call('Page.navigate', { url });
    await poll(() => evaluate('!!globalThis.__omrs'), '页面模块未加载');
  }
  const query = selector => `document.querySelector(${JSON.stringify(selector)})`;
  const text = selector => evaluate(`${query(selector)}?.textContent || ''`);
  const click = async selector => {
    const target = query(selector);
    await poll(() => evaluate(`!!${target} && !${target}.disabled`), '控件未就绪 ' + selector);
    await evaluate(`${target}.click()`);
  };
  const action = name => `[data-action="${name}"]`;
  const rail = index => `.fbw-q[data-arg="${index}"]`;
  const dialog = 'dialog[open]:not(.is-closing)';
  const accept = () => click(dialog + ' [data-dialog-ok]');
  const setValue = (selector, value, event = 'input') => evaluate(`(() => {
    const el = ${query(selector)};
    el.value = ${JSON.stringify(value)};
    el.dispatchEvent(new Event(${JSON.stringify(event)}, { bubbles: true }));
  })()`);
  const openPlan = async plan => {
    await poll(() => evaluate(`!!document.querySelector('#fb-session-picker option[value="${plan}"]')`), '计划不在反馈列表');
    await setValue('#fb-session-picker', plan, 'change');
  };
  const feedbackSummary = () => text('.fbw-bar__info');
  const detailSummary = () => text('.schd-detail__sum');
  async function request(path, data) {
    const response = await fetch(base + path, data === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    const body = await response.json();
    assert.ok(response.ok, JSON.stringify(body));
    return body;
  }
  const suspend = index => request('/api/question/suspend', { question_id: questions[index].question_id });
  const resume = index => request('/api/question/resume', { question_id: questions[index].question_id });

  await call('Runtime.enable');
  await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await page(base + '/?unlocked=1#/feedback');
  await openPlan(sid);
  await click(action('feedback.verdict') + '[data-arg="0"]');
  await setValue('[data-input="feedback.note"]', '保留本地作答备注');
  await poll(() => evaluate(`!![...document.querySelectorAll('[data-reflections-host] button')].find(el => el.textContent.trim() === '记录本次')`), '错因编辑项未挂载');
  await evaluate(`[...document.querySelectorAll('[data-reflections-host] button')].find(el => el.textContent.trim() === '记录本次').click()`);
  await setValue('[data-reflections-host] textarea', '检查代数步骤');
  await click(action('feedback.skip'));
  check((await text(dialog)).includes('还有未保存的错因'), '跳过前出现错因守卫');
  await click(dialog + ' [data-dialog-cancel]');
  check(await evaluate(`${query('[data-reflections-host] textarea')}.value`) === '检查代数步骤', '继续编辑保留独立错因草稿');
  await evaluate(`${query('[data-reflections-host] textarea')}.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true, cancelable: true }))`);
  await poll(() => evaluate(`${query('[data-reflections-host] textarea')}?.value === ''`), '独立保存错因失败');
  await click(action('feedback.skip'));
  check((await text(dialog)).includes('本次不会提交这条反馈'), '跳过已判题明示暂不提交');
  await accept();
  await poll(async () => (await feedbackSummary()).includes('本次跳过 1'), '跳过未显示');
  check(await evaluate(`${query('.fbw-q[aria-current]')}.dataset.arg`) === '1', '跳过后落到下一待录原题');
  await click(rail(0));
  await click(action('feedback.skip') + '[data-arg="0"]');
  await poll(async () => !(await feedbackSummary()).includes('本次跳过'), '撤销跳过未生效');
  check(await evaluate(`${query('[data-input="feedback.note"]')}?.value`) === '保留本地作答备注', '撤销恢复未提交的判定与备注');

  await suspend(2);
  await click(action('feedback.refresh'));
  await poll(async () => (await feedbackSummary()).includes('不可录 1'), '刷新未显示不可录');
  const omr = { recognition_id: 'synthetic', template_id: 'synthetic', mode: 'omrs', status: 'ready', unresolved: [],
    questions: [{ seq: 3, result: 'W', level: 1 }, { seq: 4, result: 'C', level: 8 }] };
  await evaluate(`(() => {
    const data = new DataTransfer();
    data.setData('text/plain', ${JSON.stringify(JSON.stringify(omr))});
    document.body.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: data }));
  })()`);
  check((await text('.fbw-import__status')).includes('不可录 1 题（原题号 3）'), 'OMR 按原题号排除第 3 题');
  await click(rail(3));
  check(await evaluate(`${query('[data-input="feedback.score"]')}.value`) === '8', 'OMR 第 4 题仍对应原第 4 题');
  await click(rail(1));
  await click(action('feedback.verdict') + '[data-arg="1"]');
  await setValue('[data-input="feedback.note"]', '跨端停用前的判定');
  await suspend(1);
  await click(action('feedback.submit'));
  await poll(async () => (await text(dialog)).includes('2/3 条写入成功'), '混合反馈未给出逐行回执');
  await accept();
  await poll(async () => (await feedbackSummary()).includes('不可录 2'), '反馈页未同步部分成功');
  await resume(1);
  await click(action('feedback.refresh'));
  await poll(async () => (await feedbackSummary()).includes('待录 1'), '恢复后待录状态未刷新');
  check(await evaluate(`${query('[data-input="feedback.note"]')}?.value`) === '跨端停用前的判定', '部分成功后保留失效题的原草稿');
  await click(action('feedback.submit'));
  await poll(async () => (await text(dialog)).includes('1/1 条写入成功'), '重试未记录保留草稿');
  await accept();
  await click(action('feedback.finish'));
  check((await text(dialog)).includes('已录 3 · 本次跳过 0 · 不可录 1'), '结单确认列出真实处置');
  await accept();
  await poll(async () => (await feedbackSummary()).includes('已结束 · 已录 3 · 不可录 1'), '反馈页未显示结单');
  await resume(2);
  await call('Page.reload');
  await poll(() => evaluate(`!!document.querySelector('#fb-session-picker option[value="${sid}"]')`), '刷新后计划未加载');
  await openPlan(sid);
  check((await feedbackSummary()).includes('已结束 · 已录 3 · 不可录 1'), '刷新与恢复题目后结单快照保持');

  await suspend(4);
  await suspend(5);
  await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await evaluate("localStorage.setItem('omrs-theme', 'dark')");
  await page(base + '/?unlocked=1#/schedule');
  await click('#sch-tab-plans');
  await click(action('schedule.open') + `[data-arg="${otherSid}"]`);
  await click(action('schedule.finish'));
  check((await text(dialog)).includes('已录 0 · 本次跳过 0 · 不可录 2'), '全停用计划可从调度详情结单');
  await accept();
  await poll(async () => (await detailSummary()).includes('已结束 · 无反馈 · 不可录 2'), '全停用计划未显示无反馈');
  check(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), '390 像素深色页面无横向溢出');
  const second = await request('/api/session?id=' + encodeURIComponent(otherSid));
  check(second.completion.counts.recorded === 0 && second.entries.every(e => !e.feedback_submitted), '零反馈结单未生成学习回执');
  check(scriptErrors.length === 0, 'Chromium 页面脚本错误为零');
  console.log(`反馈结单 Chromium 开发回归 ${checks.length} 项通过`);
} catch (error) {
  console.error(error);
  for (const child of processes) console.error(child.spawnfile, child.exitCode, child.details);
  process.exitCode = 1;
} finally {
  socket?.close();
  for (const child of processes.reverse()) {
    if (child.exitCode === null && child.signalCode === null && child.pid) {
      child.kill();
      await Promise.race([once(child, 'exit'), sleep(3000)]);
    }
  }
  await rm(work, { recursive: true, force: true, maxRetries: 3, retryDelay: 150 });
}
