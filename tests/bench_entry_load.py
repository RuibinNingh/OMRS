"""隔离入口冷加载和持续渲染实测；包含真实 PIN 输入，不访问生产数据。

python3 tests/bench_entry_load.py --ref HEAD --runs 3 --out /tmp/entry-bench.json
统计时间不是功能门禁；软件 WebGL、CPU 节流不代表实体设备功耗。
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.browser_runtime import launch_chromium
from tests.visual.run import start_server
from omrs import security

SCENARIOS = {
    'desktop': {'viewport': {'width': 1440, 'height': 900}, 'device_scale_factor': 1},
    'mobile': {'viewport': {'width': 390, 'height': 844}, 'device_scale_factor': 3,
               'is_mobile': True, 'has_touch': True},
    'large': {'viewport': {'width': 2560, 'height': 1440}, 'device_scale_factor': 2},
}

INSTRUMENT = r"""() => {
  const s = window.entryBench = {frames: 0, atlasPixels: 0, peakPixels: 0, renderer: null, longTasks: [], events: [], authMs: null};
  performance.setResourceTimingBufferSize(1000);
  new PerformanceObserver(list => s.longTasks.push(...list.getEntries().map(e => e.duration)))
    .observe({type: 'longtask', buffered: true});
  if (PerformanceObserver.supportedEntryTypes.includes('event')) new PerformanceObserver(list =>
    s.events.push(...list.getEntries().map(e => ({name:e.name, delay:e.processingStart-e.startTime, duration:e.duration}))))
    .observe({type:'event', buffered:true, durationThreshold:16});
  const auth = () => {
    const pin = document.querySelector('#entry-form'), enter = document.querySelector('#enter');
    if (s.authMs === null && ((pin && !pin.hidden) || (enter && !enter.hidden))) s.authMs = performance.now();
  };
  new MutationObserver(auth).observe(document, {subtree:true, childList:true, attributes:true, attributeFilter:['hidden']});
  const proto = WebGL2RenderingContext.prototype;
  const targets = new WeakMap();
  const bind = proto.bindFramebuffer;
  proto.bindFramebuffer = function(target, buffer) {
    if (target === this.FRAMEBUFFER || target === this.DRAW_FRAMEBUFFER) targets.set(this, buffer);
    return bind.apply(this, arguments);
  };
  for (const name of ['drawArrays','drawElements','drawArraysInstanced','drawElementsInstanced']) {
    const draw = proto[name];
    proto[name] = function() { const result = draw.apply(this, arguments);
      if (!targets.get(this) && this.canvas.closest?.('#gravity')) {
        s.frames++; s.peakPixels=Math.max(s.peakPixels,this.canvas.width*this.canvas.height);
        if (!s.renderer) {const ext=this.getExtension('WEBGL_debug_renderer_info');
          s.renderer=this.getParameter(ext?.UNMASKED_RENDERER_WEBGL || this.RENDERER);}
      }
      return result; };
  }
  for (const name of ['texImage2D','texSubImage2D']) {
    const upload = proto[name];
    proto[name] = function() {
      const source = arguments[arguments.length - 1];
      if (source instanceof HTMLCanvasElement) s.atlasPixels = Math.max(s.atlasPixels, source.width * source.height);
      return upload.apply(this, arguments);
    };
  }
}"""


def process_times(session):
    try:
        return {row['id']: (row['type'], row['cpuTime'])
                for row in session.send('SystemInfo.getProcessInfo')['processInfo']}
    except Exception:
        return {}


def measure(browser, browser_session, base, profile, scenario, args, iteration):
    context = browser.new_context(**SCENARIOS[scenario])
    context.add_init_script(f"localStorage.setItem('omrs-entry-quality', {json.dumps(profile)});")
    context.add_init_script('(' + INSTRUMENT + ')()')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('response', lambda response: errors.append(f'HTTP {response.status}: {response.url}')
            if response.status >= 400 else None)
    session = context.new_cdp_session(page)
    session.send('Performance.enable')
    session.send('Network.enable')
    session.send('Network.emulateNetworkConditions', {
        'offline': False, 'latency': args.latency,
        'downloadThroughput': args.mbps * 1_000_000 / 8,
        'uploadThroughput': 125000, 'connectionType': 'cellular4g'})
    if args.cpu_rate != 1:
        session.send('Emulation.setCPUThrottlingRate', {'rate': args.cpu_rate})
    try:
        page.goto(base + '/', wait_until='domcontentloaded', timeout=90000)
        page.wait_for_function("window.entryBench.authMs !== null", timeout=90000)
        page.locator('#pin').focus()
        inputs = []
        for digit in '246810':
            start = time.perf_counter()
            page.keyboard.press(digit)
            inputs.append((time.perf_counter() - start) * 1000)
        page.wait_for_function("""() => {
          const d=document.querySelector('#gravity')?.dataset;
          return ['ready','fallback','custom-ready'].includes(d?.status) ||
            (d?.preference && d.status === 'static' && d.quality === 'static');
        }""", timeout=90000)
        ready_ms = page.evaluate('performance.now()')
        first_frames = page.evaluate('entryBench.frames')
        start = time.perf_counter()
        cpu_before = process_times(browser_session)
        perf_before = {m['name']: m['value'] for m in session.send('Performance.getMetrics')['metrics']}
        # 固定观察窗口用于计量实际工作量；不是功能正确性的固定等待。
        page.wait_for_timeout(args.seconds * 1000)
        perf_after = {m['name']: m['value'] for m in session.send('Performance.getMetrics')['metrics']}
        cpu_after = process_times(browser_session)
        elapsed = time.perf_counter() - start
        steady_inputs = []
        for key in ['1', 'Backspace', '1', 'Backspace']:
            input_start = time.perf_counter(); page.keyboard.press(key)
            steady_inputs.append((time.perf_counter() - input_start) * 1000)
        result = page.evaluate("""() => {
          const s=entryBench, r=performance.getEntriesByType('resource'),
            n=performance.getEntriesByType('navigation'), d=document.querySelector('#gravity').dataset,
            c=document.querySelector('#gravity canvas'), gl=c?.getContext('webgl2'),
            ext=gl?.getExtension('WEBGL_debug_renderer_info');
          return {auth_ms:s.authMs, fcp_ms:performance.getEntriesByName('first-contentful-paint')[0]?.startTime,
            frames:s.frames, atlas_pixels:s.atlasPixels, status:d.status, quality:d.quality || 'original',
            buffer_pixels:c ? c.width*c.height:0, peak_buffer_pixels:s.peakPixels,
            paused:d.paused, renderer:s.renderer || (gl ? gl.getParameter(ext?.UNMASKED_RENDERER_WEBGL || gl.RENDERER):null),
            transfer_bytes:[...r,...n].reduce((a,x)=>a+x.transferSize,0), requests:r.map(x=>new URL(x.name).pathname),
            long_task_count:s.longTasks.length, longest_task_ms:Math.max(0,...s.longTasks),
            input_event_delay_ms:Math.max(0,...s.events.filter(e=>e.name.startsWith('key')).map(e=>e.delay)),
            pin_value:document.querySelector('#pin').value};
        }""")
        cpu = sum(max(0, value[1] - cpu_before[pid][1]) for pid, value in cpu_after.items() if pid in cpu_before)
        result.update(scenario=scenario, profile=profile, iteration=iteration, ready_ms=ready_ms,
                      observed_seconds=elapsed, rendered_fps=(result.pop('frames')-first_frames)/elapsed,
                      browser_cpu_seconds=cpu if cpu_before else None,
                      browser_cpu_percent=cpu/elapsed*100 if cpu_before else None,
                      main_thread_task_seconds=perf_after.get('TaskDuration', 0)-perf_before.get('TaskDuration', 0),
                      js_heap_bytes=perf_after.get('JSHeapUsedSize'), input_roundtrip_max_ms=max(inputs),
                      steady_input_roundtrip_max_ms=max(steady_inputs), errors=errors)
        if result.pop('pin_value') != '246810':
            result['errors'].append('真实 PIN 输入丢失')
        if args.shots:
            shots = Path(args.shots); shots.mkdir(parents=True, exist_ok=True)
            # 计量结束后停发新动画帧再截图，避免软件GPU持续忙碌导致截图饥饿。
            page.evaluate('window.requestAnimationFrame = () => 0')
            try:
                page.screenshot(path=str(shots / f'{scenario}-{profile}-{iteration}.png'), timeout=30000)
            except Exception as error:
                result['screenshot_error'] = str(error)
        return result
    finally:
        context.close()


def run_tree(tree, label, browser, browser_session, args, work, record):
    vault = work / label
    (vault / '错题').mkdir(parents=True)
    security.set_pin(str(vault), '246810')
    proc, port = start_server(str(tree), str(vault), str(work / (label + '.log')))
    results = []
    try:
        profiles = ['original'] if label == 'before' else args.profiles.split(',')
        for scenario in args.scenarios.split(','):
            for iteration in range(args.runs):
                for profile in profiles:
                    try:
                        row = measure(browser, browser_session, f'http://127.0.0.1:{port}', profile, scenario, args, iteration)
                    except Exception as error:
                        row = {'scenario': scenario, 'profile': profile, 'iteration': iteration,
                               'quality': 'unavailable', 'errors': [str(error)]}
                    row['side'] = label
                    results.append(row)
                    record(row)
                    print(json.dumps({k: v for k, v in row.items() if k != 'requests'}, ensure_ascii=False), flush=True)
    finally:
        proc.terminate(); proc.wait(timeout=10)
    return results


def summarize(results):
    groups = {}
    metrics = ['auth_ms', 'fcp_ms', 'ready_ms', 'buffer_pixels', 'peak_buffer_pixels', 'atlas_pixels', 'rendered_fps',
               'browser_cpu_percent', 'main_thread_task_seconds', 'transfer_bytes', 'longest_task_ms',
               'input_event_delay_ms', 'input_roundtrip_max_ms', 'steady_input_roundtrip_max_ms', 'js_heap_bytes']
    for row in results:
        groups.setdefault((row['side'], row['scenario'], row['profile']), []).append(row)
    return [{'side': key[0], 'scenario': key[1], 'profile': key[2], 'runs': len(rows),
             **{metric: round(statistics.median(r[metric] for r in rows if r.get(metric) is not None), 3)
                for metric in metrics if any(r.get(metric) is not None for r in rows)},
             'qualities': sorted({r['quality'] for r in rows}), 'errors': [e for r in rows for e in r['errors']]}
            for key, rows in groups.items()]


def main():
    parser = argparse.ArgumentParser(description='入口资源分档前后对照实测')
    parser.add_argument('--ref', help='比较基线 Git 提交')
    parser.add_argument('--tree', default=str(ROOT), help='当前源码树')
    parser.add_argument('--out', required=True)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--seconds', type=float, default=6)
    parser.add_argument('--latency', type=int, default=100)
    parser.add_argument('--mbps', type=float, default=5)
    parser.add_argument('--cpu-rate', type=float, default=1)
    parser.add_argument('--scenarios', default='desktop,mobile,large')
    parser.add_argument('--profiles', default='auto,light,static')
    parser.add_argument('--shots', help='另存每个样本的实际入口截图')
    args = parser.parse_args()
    if args.runs < 1 or args.seconds <= 0 or args.mbps <= 0 or args.cpu_rate < 1 or args.latency < 0:
        parser.error('次数、观察窗口、带宽、CPU倍率或延迟非法')
    if set(args.scenarios.split(',')) - SCENARIOS.keys() or set(args.profiles.split(',')) - {'auto','light','full','static'}:
        parser.error('未知场景或档位')
    output = Path(args.out).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    results = []
    with tempfile.TemporaryDirectory(prefix='omrs-entry-bench-') as tmp:
        work = Path(tmp)
        baseline = None
        if args.ref:
            baseline = work / 'source'; baseline.mkdir()
            archive = work / 'source.tar'
            with archive.open('wb') as stream:
                subprocess.run(['git', '-C', str(ROOT), 'archive', args.ref], stdout=stream, check=True)
            with tarfile.open(archive) as source:
                source.extractall(baseline, filter='data')
        with sync_playwright() as p:
            browser = launch_chromium(p)
            session = browser.new_browser_cdp_session()
            environment = {'browser': browser.version, 'platform': sys.platform, 'cpu_throttling': args.cpu_rate,
                           'latency_ms': args.latency, 'download_mbps': args.mbps,
                           'seconds': args.seconds, 'ref': args.ref,
                           'cache_scope': '上下文HTTP缓存冷；复用进程，未清空着色器和系统缓存',
                           'limitations': '浏览器进程CPU与软件/硬件WebGL由本环境决定，不能推导实体设备功耗；JS堆不含GPU显存。'}
            def record(row):
                results.append(row)
                output.write_text(json.dumps({'environment': environment, 'results': results,
                    'summary': summarize(results)}, ensure_ascii=False, indent=2) + '\n')
            try:
                for tree, label in ([(baseline, 'before')] if baseline else []) + [(Path(args.tree), 'after')]:
                    run_tree(tree, label, browser, session, args, work, record)
            finally:
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
    return 1 if any(row['errors'] for row in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
