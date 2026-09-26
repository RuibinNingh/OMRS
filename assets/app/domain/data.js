/**
 * 全局统计数据（/api/stats）：P6 起所有权在这里——加载、快照、发布都由本模块负责，旧代码只读镜像。
 * - reloadData()：拉 /api/stats → 设快照 → 写旧 DATA 镜像 → 跑旧代码的刷新链（过渡桥登记，见 legacy-bridge.js
 *   的 installDataBridge）→ 经 bus 发 'data'（外壳同步进 store.data）。返回 { ok, data, error }，不抛出。
 * - 并发合并：一次加载进行中再被调用时，排一次「补拉」，当前这次结束后再拉；期间再来的调用共享这次补拉。
 *   这样调用方 await 之后拿到的数据一定不早于它调用的时刻，同一时间最多两次请求在路上。
 * - 失败：保留上一份快照；还没有快照时给一份空快照。lastError() 给出原因，页面据此显示错态与「重试」。
 *   （旧 reloadData 失败时用演示数据顶替，服务重启的几秒里会闪出假数据；已去掉。）
 * - currentData() / itemsNow()：当前快照；旧 DATA 与 store.data 指向同一对象。
 */
import { get } from '../core/api.js';

const EMPTY = () => ({
  total: 0, killed: 0, attacking: 0, avg_mastery: 0, suspended: 0, items: [],
  subject_dist: {}, difficulty_dist: {}, mastery_histogram: {}, daily_trend: {}, recent_activity: {}, review_alert: {}, scatter_data: [],
});

let snapshot = null;
let error = null;
let running = null;
let queued = null;
let publish = () => {};
let legacyRefresh = null;
let fetchImpl;

/** 外壳就绪后接上发布通道（main.js）；测试可传 fetchImpl 替身。 */
export function connectData({ emit, fetch } = {}) {
  publish = typeof emit === 'function' ? emit : () => {};
  fetchImpl = fetch;
}
/** 旧代码在数据到达后要做的刷新（下拉选项、导出选题、展示板等），由过渡桥登记；P8 时为空。 */
export function setLegacyRefresh(fn) { legacyRefresh = typeof fn === 'function' ? fn : null; }

export const currentData = () => snapshot;
export const itemsNow = () => (Array.isArray(snapshot?.items) ? snapshot.items : []);
export const lastError = () => error;
export const loading = () => !!running;

function mirror(next) {
  // DATA 是旧 core.js 的 let：不是 window 属性，直接给标识符赋值才能让经典脚本读到（同 domain/sessions.js）。
  if (typeof DATA !== 'undefined') DATA = next; // eslint-disable-line no-global-assign
}

async function run() {
  const res = await get('/api/stats', fetchImpl ? { fetchImpl } : {});
  if (res.ok && res.data && typeof res.data === 'object') {
    snapshot = res.data;
    if (!Array.isArray(snapshot.items)) snapshot.items = [];
    error = null;
  } else {
    error = res.error || { code: 'unknown', message: '未知错误' };
    if (!snapshot) snapshot = EMPTY();
  }
  mirror(snapshot);
  if (legacyRefresh) {
    try { await legacyRefresh(snapshot); } catch (err) { console.error('[domain/data] 旧代码刷新出错', err); }
  }
  publish('data', snapshot);
  return { ok: !error, data: snapshot, error };
}

export function reloadData() {
  if (!running) {
    running = run().finally(() => { running = null; });
    return running;
  }
  if (!queued) {
    queued = running.then(() => { queued = null; return reloadData(); });
  }
  return queued;
}

/** 测试用：清空模块状态。 */
export function resetData() {
  snapshot = null; error = null; running = null; queued = null; legacyRefresh = null; publish = () => {}; fetchImpl = undefined;
}
