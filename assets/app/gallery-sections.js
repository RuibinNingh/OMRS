/**
 * gallery 第一部分：基础控件与数据展示。每节 cells 覆盖 design-system §4.5 的状态矩阵
 * （默认、悬停、按下、焦点、禁用、加载中、空、错误、骨架、长文本溢出；浅深色与密度由页头切换）。
 * 悬停 / 按下 / 焦点用 is-hover / is-active / is-focus 类固定展示，真实交互同样可用鼠标键盘试。
 */
import { html } from './core/html.js';
import { button } from './ui/button.js';
import { icon, ICON_NAMES } from './ui/icon.js';
import { field, input, textarea } from './ui/field.js';
import { select } from './ui/select.js';
import { switchControl } from './ui/switch.js';
import { segmented } from './ui/segmented.js';
import { tabs } from './ui/tabs.js';
import { tag } from './ui/tag.js';
import { badge } from './ui/badge.js';
import { card } from './ui/card.js';
import { stat } from './ui/stat.js';
import { table } from './ui/table.js';
import { empty } from './ui/empty.js';
import { skeleton } from './ui/skeleton.js';

export const LONG = '这是一段特别长的文字，用来检查溢出时省略或换行，而不是把布局撑破 OMRS-MATH-2026-000123';
export const cell = (label, content, opts = {}) => ({ label, content, ...opts });
const row = (...items) => html`<div class="gl-row">${items}</div>`;
const stack = (...items) => html`<div class="gl-stack">${items}</div>`;
const narrow = content => html`<div class="gl-narrow">${content}</div>`;
const VARIANTS = [['default', '次要'], ['primary', '主要'], ['ghost', '幽灵'], ['danger', '危险']];
const SUBJECTS = ['全部科目', '数学', '物理', '化学', '英语'];
const seg = (name, extra = {}) => segmented({ name, label: '视图', value: 'table', options: [{ value: 'table', label: '表格', icon: 'table' }, { value: 'grid', label: '画廊', icon: 'grid' }, { value: 'list', label: '列表', icon: 'list' }], ...extra });

const ROWS = [
  { id: 'MATH-001', title: '二次函数的最值', subject: '数学', due: 3, rate: '62%' },
  { id: 'PHY-014', title: LONG, subject: '物理', due: 0, rate: '88%' },
  { id: 'CHEM-007', title: '苯的同系物命名', subject: '化学', due: 12, rate: '41%' },
];
const COLS = [
  { key: 'id', label: 'UID', render: r => html`<code>${r.id}</code>` },
  { key: 'title', label: '题目' },
  { key: 'subject', label: '科目', render: r => tag({ label: r.subject }) },
  { key: 'due', label: '逾期天数', num: true },
  { key: 'rate', label: '正确率', num: true },
  { key: 'act', label: '操作', render: () => html`<span class="ui-table__actions">${button({ label: '打开', icon: 'external', iconOnly: true, variant: 'ghost', size: 'sm' })}${button({ label: '更多', icon: 'more-h', iconOnly: true, variant: 'ghost', size: 'sm' })}</span>` },
];

export const SECTIONS_A = [
  { id: 'button', title: '按钮 Button', desc: '三档高度 28 / 32 / 40；同一行只用同一档。主要按钮每个区域最多一个；危险操作用 danger，确认框里默认聚焦「取消」。', cells: [
    ...VARIANTS.map(([v, name]) => cell(`${name}（${v}）：默认 · 悬停 · 按下 · 焦点 · 禁用 · 加载中`, row(
      button({ label: '保存', variant: v }), button({ label: '保存', variant: v, state: 'hover' }), button({ label: '保存', variant: v, state: 'active' }),
      button({ label: '保存', variant: v, state: 'focus' }), button({ label: '保存', variant: v, disabled: true }), button({ label: '保存', variant: v, loading: true })), { wide: true })),
    cell('尺寸 sm 28 · md 32 · lg 40', row(button({ label: '小', size: 'sm' }), button({ label: '中' }), button({ label: '大', size: 'lg' }))),
    cell('带图标 · 仅图标（须有 aria-label）', row(button({ label: '重新扫描', icon: 'refresh' }), button({ label: '导出', iconRight: 'chevron-down' }), button({ label: '更多', icon: 'more-h', iconOnly: true, variant: 'ghost' }), button({ label: '删除', icon: 'trash', iconOnly: true, variant: 'danger', size: 'sm' }))),
    cell('切换态 aria-pressed', row(button({ label: '表格', pressed: true, size: 'sm' }), button({ label: '画廊', pressed: false, size: 'sm' }))),
    cell('长文本溢出（容器 160px，省略）', narrow(button({ label: LONG, icon: 'file' }))),
    cell('整宽 block', narrow(button({ label: '加载推荐', variant: 'primary', block: true }))),
  ] },
  { id: 'icon', title: '图标 Icon', desc: `内部自绘 ${ICON_NAMES.length} 个：24 网格、1.5 描边、跟随文字颜色。用 icon(name) 引用 sprite；替换各页 emoji 图标（D7）随页面迁移进行。`, cells: [
    cell('全部图标（20px）', html`<div class="gl-icons">${ICON_NAMES.map(n => html`<div class="gl-icon">${icon(n, { size: 'lg' })}<code>${n}</code></div>`)}</div>`, { wide: true }),
    cell('尺寸 14 · 16 · 20 · 24', row(icon('search', { size: 'sm' }), icon('search', { size: 'md' }), icon('search', { size: 'lg' }), icon('search', { size: 'xl' }))),
  ] },
  { id: 'field', title: '字段 Field · 输入框 Input', desc: 'Field 统一 label、提示、错误的位置；错误写在控件下方并由 role=alert 读出。输入框与按钮同档高度。', cells: [
    cell('默认（空，占位符）', field({ label: '题目 UID', id: 'gf-1', hint: '形如 MATH-001', control: input({ id: 'gf-1', placeholder: '输入 UID', describedBy: 'gf-1-msg' }) })),
    cell('悬停', field({ label: '题目 UID', id: 'gf-2', control: input({ id: 'gf-2', placeholder: '输入 UID', state: 'hover' }) })),
    cell('焦点', field({ label: '题目 UID', id: 'gf-3', control: input({ id: 'gf-3', value: 'MATH-00', state: 'focus' }) })),
    cell('已填写 · 必填', field({ label: '知识点', id: 'gf-4', required: true, control: input({ id: 'gf-4', value: '二次函数' }) })),
    cell('禁用 · 只读', stack(input({ id: 'gf-5', value: '禁用的输入', disabled: true, label: '禁用' }), input({ id: 'gf-6', value: '只读的输入', readonly: true, label: '只读' }))),
    cell('错误', field({ label: '题数', id: 'gf-7', error: '请输入 1–50 之间的整数', control: input({ id: 'gf-7', value: '120', invalid: true, describedBy: 'gf-7-msg' }) })),
    cell('长文本溢出', field({ label: '备注', id: 'gf-8', control: input({ id: 'gf-8', value: LONG }) })),
    cell('尺寸 28 · 32 · 40', stack(input({ id: 'gf-9', size: 'sm', placeholder: '小', label: '小' }), input({ id: 'gf-10', placeholder: '中', label: '中' }), input({ id: 'gf-11', size: 'lg', placeholder: '大', label: '大' }))),
    cell('多行 textarea · 错误', stack(field({ label: '答案', id: 'gf-12', control: textarea({ id: 'gf-12', rows: 3, value: '设 f(x)=ax²+bx+c，当 a>0 时在 x=-b/2a 处取最小值。' }) }), field({ label: '解析', id: 'gf-13', error: '解析不能为空', control: textarea({ id: 'gf-13', rows: 2, invalid: true }) }))),
    cell('行内字段', field({ label: '每页', id: 'gf-14', inline: true, control: input({ id: 'gf-14', value: '20', size: 'sm' }) })),
  ] },
  { id: 'select', title: '选择框 Select', desc: '保留原生 select（可访问性最好），统一外观与高度；上下内边距为 0、文字由行高居中，旧页 select 文字被裁切的问题（D3）由此修掉。', cells: [
    cell('默认', select({ id: 'gs-1', options: SUBJECTS, label: '科目' })),
    cell('悬停 · 焦点', stack(select({ id: 'gs-2', options: SUBJECTS, label: '科目', state: 'hover' }), select({ id: 'gs-3', options: SUBJECTS, label: '科目', state: 'focus' }))),
    cell('禁用', select({ id: 'gs-4', options: SUBJECTS, label: '科目', disabled: true })),
    cell('错误', field({ label: '分类', id: 'gs-5', error: '请选择分类', control: select({ id: 'gs-5', options: ['请选择…', '词汇', '电磁学'], invalid: true }) })),
    cell('长选项溢出（容器 160px）', narrow(select({ id: 'gs-6', options: [LONG, '短选项'], label: '长选项' }))),
    cell('同一行同一档（D2）：输入 · 选择 · 按钮 · 分段', row(input({ id: 'gs-7', placeholder: '搜索', label: '搜索' }), select({ id: 'gs-8', options: ['熟练度 ↑', '熟练度 ↓'], label: '排序' }), button({ label: '筛选', icon: 'filter' }), seg('gs-seg')), { wide: true }),
  ] },
  { id: 'switch', title: '开关 Switch', desc: 'role=switch 的原生复选框：空格切换，标签可点。', cells: [
    cell('关 · 开', stack(switchControl({ id: 'gw-1', label: '只看逾期' }), switchControl({ id: 'gw-2', label: '只看逾期', checked: true }))),
    cell('悬停 · 焦点', stack(switchControl({ id: 'gw-3', label: '悬停', state: 'hover' }), switchControl({ id: 'gw-4', label: '键盘焦点', checked: true, state: 'focus' }))),
    cell('禁用（关 · 开）', stack(switchControl({ id: 'gw-5', label: '禁用', disabled: true }), switchControl({ id: 'gw-6', label: '禁用', checked: true, disabled: true }))),
    cell('长文本溢出（换行）', narrow(switchControl({ id: 'gw-7', label: LONG, checked: true }))),
  ] },
  { id: 'segmented', title: '分段控件 Segmented', desc: '互斥的 2–5 个选项（视图切换、密度）。一组原生 radio，←/→ 切换。', cells: [
    cell('默认', seg('gg-1')),
    cell('焦点', seg('gg-2', { state: 'focus' })),
    cell('小号 28', seg('gg-3', { size: 'sm' })),
    cell('禁用', seg('gg-4', { disabled: true })),
    cell('溢出（容器 160px，横向滚动）', narrow(seg('gg-5'))),
  ] },
  { id: 'tabs', title: '标签页 Tabs', desc: '页内分区切换；←/→/Home/End 移动并激活，按 aria-controls 切换面板。', cells: [
    cell('默认（可点、可用方向键）', tabs({ label: '题目详情', idPrefix: 'gt1', value: 'q', items: [{ id: 'q', label: '题面' }, { id: 'a', label: '答案' }, { id: 'h', label: '记录', badge: 4 }] }), { wide: true }),
    cell('悬停 · 焦点 · 禁用', tabs({ label: '状态', idPrefix: 'gt2', value: 'q', items: [{ id: 'q', label: '题面' }, { id: 'a', label: '悬停', state: 'hover' }, { id: 'f', label: '焦点', state: 'focus' }, { id: 'd', label: '禁用', disabled: true }] }), { wide: true }),
    cell('溢出（横向滚动）', narrow(tabs({ label: '溢出', idPrefix: 'gt3', value: 'a', items: ['a', 'b', 'c', 'd', 'e'].map((id, i) => ({ id, label: `第 ${i + 1} 章` })) }))),
  ] },
  { id: 'tag', title: '标签 Tag', desc: '只做展示的分类与状态标记；可移除时带一个 28px 热区的按钮。', cells: [
    cell('色调', row(tag({ label: '中性' }), tag({ label: '强调', tone: 'accent' }), tag({ label: '已掌握', tone: 'success' }), tag({ label: '待复习', tone: 'warning' }), tag({ label: '顽固题', tone: 'danger' }), tag({ label: '新题', tone: 'info' }))),
    cell('带图标 · 可移除', row(tag({ label: '考前必看', icon: 'star', tone: 'warning' }), tag({ label: '计算失误', removable: true }))),
    cell('长文本溢出（省略）', narrow(tag({ label: LONG, title: LONG }))),
  ] },
  { id: 'badge', title: '徽标 Badge', desc: '计数与提醒点；数字等宽，超过上限显示 99+。', cells: [
    cell('计数 · 上限', row(badge(3), badge(12), badge(128), badge(7, { tone: 'accent' }))),
    cell('色调 · 圆点', row(badge(2, { tone: 'danger' }), badge(5, { tone: 'success' }), badge(1, { tone: 'warning' }), badge(null, { dot: true }))),
    cell('在按钮里', row(html`<button type="button" class="ui-btn">${icon('inbox')}<span class="ui-btn__label">收件箱</span>${badge(8, { tone: 'accent' })}</button>`)),
  ] },
  { id: 'card', title: '卡片 Card', desc: '表面 1 + 描边 + 轻阴影；可交互卡片可聚焦、悬停抬升。加载与空状态直接放骨架屏、空状态组件。', cells: [
    cell('默认（标题 · 操作 · 页脚）', card({ title: '今日复习', subtitle: '12 道待复习 · 预计 18 分钟', actions: button({ label: '更多', icon: 'more-h', iconOnly: true, variant: 'ghost', size: 'sm' }), body: '先做逾期最久的 3 道，再做新题。', footer: button({ label: '开始复习', variant: 'primary', size: 'sm' }) })),
    cell('可交互：悬停 · 焦点', stack(card({ title: '悬停', body: '整卡可点', interactive: true, state: 'hover' }), card({ title: '键盘焦点', body: '整卡可点', interactive: true, state: 'focus' }))),
    cell('加载中（骨架）', card({ title: '行动推荐', body: skeleton({ lines: 3 }) })),
    cell('空', card({ title: '展示板', body: empty({ icon: 'bookmark', title: '还没有展示板', hint: '在题库里选题后点「加入展示板」。', compact: true }) })),
    cell('长标题溢出 · 扁平', card({ title: LONG, subtitle: LONG, body: LONG, flat: true })),
  ] },
  { id: 'stat', title: '统计 Stat', desc: '标签 12 · 数值 28 · 变化量 12，数字等宽；display 40 全站只给仪表盘首屏一处。', cells: [
    cell('默认 · 单位 · 趋势', row(stat({ label: '待复习', value: 12, unit: '题', delta: '+3', trend: 'up' }), stat({ label: '正确率', value: '76', unit: '%', delta: '-4%', trend: 'down' }))),
    cell('首屏大数字（lg）', stat({ label: '累计掌握', value: '1,284', unit: '题', hint: '本周 +36', size: 'lg' })),
    cell('空值 · 加载中', row(stat({ label: '平均用时', value: null, hint: '还没有记录' }), html`<div class="gl-narrow">${skeleton({ lines: 2, label: '统计加载中' })}</div>`)),
    cell('长标签溢出', narrow(stat({ label: LONG, value: 3 }))),
  ] },
  { id: 'table', title: '表格 Table', desc: '表头固定；悬停、选中、行内操作三种行态；数字列右对齐。stack 模式在 ≤760px 降级为卡片列表（D4），切到手机宽度查看。', cells: [
    cell('默认 · 选中（CHEM-007）· 悬停（MATH-001）· 行内操作', table({ columns: COLS, rows: ROWS, selected: ['CHEM-007'], hover: 'MATH-001', stack: true }), { wide: true }),
    cell('空', table({ columns: COLS.slice(0, 4), rows: [], empty: empty({ icon: 'search', title: '没有符合条件的题', hint: '换个关键词，或清除筛选。', compact: true, action: { label: '清除筛选', size: 'sm' } }) }), { wide: true }),
    cell('加载中', html`<div class="ui-table-wrap gl-stack">${skeleton({ lines: 4, label: '表格加载中' })}</div>`, { wide: true }),
  ] },
];
