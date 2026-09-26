/**
 * gallery 第二部分：浮层与反馈。浮层给出静态预览（便于截图审阅）加可点的真实演示（demos，见 gallery-demos.js）。
 */
import { html } from './core/html.js';
import { button } from './ui/button.js';
import { field, input } from './ui/field.js';
import { menuMarkup } from './ui/menu.js';
import { toastMarkup } from './ui/toast.js';
import { empty } from './ui/empty.js';
import { skeleton } from './ui/skeleton.js';
import { status, dot } from './ui/status.js';
import { progress, spinner } from './ui/progress.js';
import { kbd } from './ui/kbd.js';
import { filedrop } from './ui/filedrop.js';
import { select } from './ui/select.js';
import { switchControl } from './ui/switch.js';
import { icon } from './ui/icon.js';
import { LONG, cell } from './gallery-sections.js';

const row = (...items) => html`<div class="gl-row">${items}</div>`;
const stack = (...items) => html`<div class="gl-stack">${items}</div>`;
const narrow = content => html`<div class="gl-narrow">${content}</div>`;
const closeBtn = () => button({ label: '关闭', icon: 'x', iconOnly: true, variant: 'ghost', size: 'sm' });
const panel = ({ title, hint, body, ok = '确定', danger = false }) => html`<div class="ui-dialog__panel"><header class="ui-dialog__head"><h2 class="ui-dialog__title">${title}</h2>${closeBtn()}</header>${hint ? html`<p class="ui-dialog__hint">${hint}</p>` : ''}${body ? html`<div class="ui-dialog__body">${body}</div>` : ''}<footer class="ui-dialog__foot">${button({ label: '取消', state: danger ? 'focus' : undefined })}${button({ label: ok, variant: danger ? 'danger' : 'primary' })}</footer></div>`;
export const MENU_ITEMS = [
  { value: 'open', label: '打开详情', icon: 'external', hint: 'Enter' },
  { value: 'copy', label: '复制 UID', icon: 'copy', hint: 'C' },
  { value: 'board', label: '加入展示板', icon: 'bookmark' },
  { divider: true },
  { value: 'disable', label: '停用（本题已停用）', icon: 'eye-off', disabled: true },
  { value: 'delete', label: '删除', icon: 'trash', danger: true },
];

export const SECTIONS_B = [
  { id: 'dialog', title: '对话框 Dialog', desc: '<dialog>.showModal() 进顶层：焦点陷阱、Esc 与遮罩关闭、Enter 确认、关闭后焦点回到触发元素、锁定背景滚动。旧 uiDialog / uiPrompt / uiConfirm 已转调这里。', demos: [['dialog', '打开对话框'], ['confirm', '危险确认'], ['prompt', '输入框'], ['long', '长内容']], cells: [
    cell('默认（带表单）', panel({ title: '重命名分组', hint: '只影响展示板里的显示名称。', body: field({ label: '分组名称', id: 'gd-s1', control: input({ id: 'gd-s1', value: '第三章 电磁学' }) }), ok: '保存' }), { stage: 'gl-scrim' }),
    cell('危险确认（默认聚焦「取消」）', panel({ title: '删除这个展示板？', hint: '板上的 12 道题不会被删除，只是从板上移走。', ok: '删除', danger: true }), { stage: 'gl-scrim' }),
    cell('错误 · 长标题换行', panel({ title: LONG, body: field({ label: '名称', id: 'gd-s2', error: '名称不能为空', control: input({ id: 'gd-s2', invalid: true }) }) }), { stage: 'gl-scrim' }),
  ] },
  { id: 'drawer', title: '抽屉 Drawer', desc: '次要任务的侧边面板（筛选、详情）；窄屏变底部面板。与对话框共用焦点陷阱与关闭逻辑。', demos: [['drawer', '打开抽屉']], cells: [
    cell('静态预览', html`<div class="ui-drawer__panel"><header class="ui-drawer__head"><h2 class="ui-drawer__title">筛选条件</h2>${closeBtn()}</header><div class="ui-drawer__body">${stack(field({ label: '科目', id: 'gdr-1', control: select({ id: 'gdr-1', options: ['全部科目', '数学', '物理'] }) }), switchControl({ id: 'gdr-2', label: '只看逾期', checked: true }))}</div><footer class="ui-drawer__foot">${button({ label: '重置' })}${button({ label: '应用', variant: 'primary' })}</footer></div>`, { stage: 'gl-scrim is-drawer', wide: true }),
  ] },
  { id: 'menu', title: '菜单 Menu', desc: '↑/↓ 移动（跳过禁用项）、Enter 选择、Esc 关闭并把焦点还给触发按钮；在对话框里打开时挂进对话框。', demos: [['menu', '打开菜单']], cells: [
    cell('悬停项 · 快捷键提示 · 分隔 · 禁用 · 危险', html`<div class="gl-static">${menuMarkup(MENU_ITEMS.map((it, i) => (i === 1 ? { ...it, hover: true } : it)), { staticPreview: true })}</div>`),
    cell('长文本溢出（省略）', html`<div class="gl-static">${menuMarkup([{ label: LONG, icon: 'file' }, { label: '短项' }], { staticPreview: true })}</div>`),
  ] },
  { id: 'toast', title: '通知 Toast', desc: '全站唯一一套：右下角堆叠（窄屏底部通栏），最多 3 条，同文同类合并，悬停或聚焦暂停计时；error 用 role=alert。旧 uiToast、收件箱 ibToast 均已转调。', demos: [['toast-info', '信息'], ['toast-ok', '成功'], ['toast-warn', '警告'], ['toast-error', '错误'], ['toast-action', '带撤销'], ['toast-long', '长文本'], ['toast-many', '连发 5 条']], cells: [
    cell('四种类型', html`<div class="gl-static">${toastMarkup('已同步 3 个展示板', { kind: 'info' })}${toastMarkup('已复制题目 UID', { kind: 'ok' })}${toastMarkup('这些题已经在「考前冲刺」里了', { kind: 'warn' })}${toastMarkup('保存失败：服务暂时不可用', { kind: 'error' })}</div>`),
    cell('带操作 · 长文本', html`<div class="gl-static">${toastMarkup('已移出展示板', { kind: 'ok', actions: [{ label: '撤销' }] })}${toastMarkup(LONG, { kind: 'warn' })}</div>`),
  ] },
  { id: 'tooltip', title: '提示 Tooltip', desc: '给元素写 data-tooltip；悬停 500ms 或键盘聚焦时出现，Esc 隐藏。只放补充说明，不放必要信息。', cells: [
    cell('静态预览', html`<div class="gl-static"><div class="ui-tooltip is-static" role="tooltip">复制 UID（C）</div><div class="ui-tooltip is-static" role="tooltip">${LONG}</div></div>`),
    cell('真实目标（悬停或 Tab 聚焦）', row(html`<button type="button" class="ui-btn ui-btn--icon ui-btn--ghost" aria-label="复制" data-tooltip="复制 UID（C）">${icon('copy')}</button>`, html`<button type="button" class="ui-btn" data-tooltip="${LONG}">长提示</button>`)),
  ] },
  { id: 'empty', title: '空状态 Empty', desc: '说明为什么是空的、下一步做什么，并给一个主操作（D5）。', cells: [
    cell('默认（带主操作）', empty({ icon: 'inbox', title: '收件箱是空的', hint: '在手机上拍照上传，或把图片拖到这里。', action: { label: '上传图片', icon: 'upload' } })),
    cell('紧凑 · 描边', empty({ icon: 'search', title: '没有符合条件的题', hint: '换个关键词，或清除筛选。', compact: true, bordered: true })),
    cell('长文本', empty({ icon: 'calendar', title: LONG, hint: LONG, compact: true })),
  ] },
  { id: 'skeleton', title: '骨架屏 Skeleton', desc: '加载超过 300ms 才出现（showAfter），不再出现「加载中…」纯文字闪烁。减少动效时静止。', cells: [
    cell('文字行', skeleton({ lines: 3 })),
    cell('头像 + 文字', skeleton({ lines: 2, avatar: true })),
    cell('卡片块', skeleton({ lines: 2, block: true })),
  ] },
  { id: 'status', title: '状态 Status', desc: '局部状态写在出错的位置；全局错误才用 toast（D11）。', cells: [
    cell('行内', stack(status({ text: '上次同步：3 分钟前' }), status({ tone: 'info', text: '有 2 道题的图片还在处理' }), status({ tone: 'success', text: '已保存' }), status({ tone: 'warning', text: '题库里有 3 道题缺少答案' }), status({ tone: 'danger', text: '连接失败，稍后重试' }))),
    cell('色块', stack(status({ tone: 'info', text: '新版本已就绪，刷新后生效', block: true }), status({ tone: 'success', text: '导出完成', block: true }), status({ tone: 'warning', text: '远端离线，改动保存在本机', block: true }), status({ tone: 'danger', text: '无法读取这张图片', block: true }))),
    cell('状态点 · 长文本', stack(row(dot('success', '在线'), dot('warning', '同步中'), dot('danger', '离线'), dot('info', '新'), dot()), status({ tone: 'warning', text: LONG, block: true }))),
  ] },
  { id: 'progress', title: '进度 Progress', desc: '原生 progress：确定进度、不定进度、三种粗细；小范围等待用 spinner。', cells: [
    cell('确定进度 0 · 35 · 100', stack(progress({ value: 0 }), progress({ value: 35 }), progress({ value: 100, tone: 'success' }))),
    cell('带说明 · 色调', stack(progress({ value: 7, max: 12, label: '今日复习', meta: '7 / 12' }), progress({ value: 80, tone: 'warning', label: '存储空间', meta: '80%' }), progress({ value: 95, tone: 'danger', label: '配额', meta: '95%' }))),
    cell('不定进度 · 粗细', stack(progress({ label: '正在扫描' }), progress({ value: 60, size: 'sm' }), progress({ value: 60, size: 'lg' }))),
    cell('转圈', row(spinner({ size: 'sm' }), spinner(), spinner({ size: 'lg' }), button({ label: '保存', loading: true, variant: 'primary' }))),
  ] },
  { id: 'kbd', title: '快捷键 Kbd', desc: '键帽与组合键，用于菜单提示与帮助面板。', cells: [
    cell('单键 · 组合', row(kbd('J'), kbd('K'), kbd('Esc'), kbd('Ctrl', 'K'), kbd('Shift', '?'))),
    cell('在句子里', html`<p class="gl-note">按 ${kbd('J')} / ${kbd('K')} 切题，${kbd('空格')} 显示答案。</p>`),
  ] },
  { id: 'filedrop', title: '文件拖放 FileDrop', desc: '取代原生「Choose File」（D6）：整块可点、可拖入、键盘可达；不符合类型的文件会被滤掉并标红。', cells: [
    cell('可交互（拖入或点击）', html`<div class="gl-stack">${filedrop({ id: 'gfd-live', title: '拖入图片，或点击选择', hint: '支持 PNG / JPG，可多选', accept: 'image/*', multiple: true })}<div id="gfd-out" class="gl-note" aria-live="polite">还没有选择文件</div></div>`),
    cell('悬停 · 拖入中', stack(filedrop({ id: 'gfd-2', title: '悬停', state: 'hover' }), filedrop({ id: 'gfd-3', title: '松手即可上传', state: 'dragover' }))),
    cell('焦点 · 禁用 · 错误', stack(filedrop({ id: 'gfd-4', title: '键盘焦点', state: 'focus' }), filedrop({ id: 'gfd-5', title: '上传已关闭', disabled: true }), filedrop({ id: 'gfd-6', title: '拖入 Markdown', error: '只接受 .md 文件' }))),
  ] },
  { id: 'legacy', title: '旧类名桥接 legacy-bridge', desc: '未迁移页面的 .btn / .input / select.input / textarea.input 经 legacy-bridge 层套上新外观：高度统一为 28 / 32 两档（D2），select 不再裁字（D3）。', cells: [
    cell('.btn 系列', html`<div class="gl-row"><button class="btn">默认</button><button class="btn primary">主要</button><button class="btn ghost">幽灵</button><button class="btn danger">危险</button><button class="btn" disabled>禁用</button><button class="btn sm">小号</button><button class="btn sm toggle active">切换中</button></div>`, { wide: true }),
    cell('.input · select.input · textarea.input', html`<div class="gl-stack"><div class="gl-row"><input class="input" placeholder="旧输入框" aria-label="旧输入框"><select class="input" aria-label="旧选择框"><option>全部科目</option><option>数学</option></select><button class="btn">筛选</button></div><textarea class="input" rows="2" aria-label="旧多行">旧多行输入</textarea></div>`, { wide: true }),
  ] },
];
