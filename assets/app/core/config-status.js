/** 配置写入已原子发布；镜像同步失败不会把已生效的修改说成失败。 */
export function configSavedStatus(data, text = '已保存，立即生效') {
  if (data?.mirror_conflict) return { text: `${text}；参数已生效，配置镜像存在第三方冲突，两份文件均已保留`, tone: 'warning' };
  return data?.mirror_pending
    ? { text: `${text}；配置已生效，配置镜像待同步`, tone: 'warning' }
    : { text, tone: 'success' };
}
