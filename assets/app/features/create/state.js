/** 录入题目工作区的导航定义；前三项按上传到写入题库的顺序排列。 */
export const STAGES = Object.freeze([
  { id: 'upload', title: '上传', hint: '手机 / 电脑投进收件箱', number: '1', count: 'ib-c-pending', countLabel: '待处理' },
  { id: 'process', title: '处理', hint: '框题目 / 答案，转文本或留图', number: '2', count: 'ib-c-boxed', countLabel: '已框选' },
  { id: 'create', title: '录入', hint: '核对题卡，写入题库', number: '3', count: 'ib-c-ready', countLabel: '待创建' },
  { id: 'train', title: 'AI 训练', hint: '框选与转文本的人工数据', icon: 'sparkle' },
  { id: 'quick', title: '快速录入', hint: '单题表单，剪贴板一贴即录', icon: 'edit' },
]);

export function stageOf(value) {
  return STAGES.some(stage => stage.id === value) ? value : 'upload';
}
