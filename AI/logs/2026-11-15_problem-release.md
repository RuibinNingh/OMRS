# 2026-11-15 问题中心与题目弹窗生产发布

> **任务**
> - 标识：problem-release
> - 状态：进行中

## 背景

用户原话：「上线生产吧」。执行者Codex，完整模式；授权发布本聊天已验收的问题中心开发候选，以及宽屏侧栏/窄屏题后布局、备注Markdown显示。此授权取代开发阶段不得提交与部署的限制；不包含GitHub推送。

开工主仓库main为f50c6c3且干净；候选为`/root/workspace/apps/omrs-problem-center-dev-20261114-2042`，同一基线，保留全部已交付开发改动。生产当前为a9f5672精确归档、v2.10.0，三服务active/running、NRestarts=0。发布证据目录`/root/workspace/apps/releases/OMRS-problem-v2110-s4s0qpyb`为0700，保存开工源码哈希、状态与后续私有备份；不将真实数据加入Git。

## 行为变化

问题中心、快捷错因与调度首页SVG提醒按计划U1–U5发布；题目优先显示，空间足够用右侧错因栏，空间不足排在题后；答案下方备注按安全Markdown渲染。版本更新至v2.11.0。生产依赖、认证、模型与业务数据沿用当前环境，切换失败回原源码并保留最新数据。

## 影响文件

开工已用`git status --short`、`git diff --name-status`及未跟踪清单复核候选，原候选变化均属于问题中心计划和本聊天两次UI交付。发布新增版本同步涉及`omrs/version.py`、`omrs_dashboard.html`、根`README.md`、`AI/README.md`和`AI/changelog.md`；更新计划及本日志、生成索引。部署完成后同步`AI/environment.md`的实际生产事实。

## 已执行验证

已核对主仓库、开发候选、计划执行说明、历史发布流程和三服务systemd状态；生产路径及解释器与当前环境文档一致。候选发布验证已实际完成：用生产同一套Python3.13.5依赖，清除生产控制环境后执行`python -B -m unittest discover -s tests`，1176项全部通过（181.287秒，exit 0）；`node --test tests/app/*.test.mjs`587项通过；UI零违规、对比度58组通过；`check_docs.py --diff HEAD`检查165份文档、0问题和4条大小提醒；`git diff --check`通过。日志分别保存在本次证据目录的`python-full-candidate.log`、`node-candidate.log`、`ui-candidate.log`、`contrast-candidate.log`与`docs-candidate.log`。精确归档及生产验证继续进行，结果随实际执行追加。

## 未执行验证

尚未切换生产；需完成精确归档验证、备份完整性、数据库原行与正文/配置哈希比较、生产资源及浏览器只读验收。未使用真实模型或实体设备，不向生产写入合成题目、反馈或审批；未执行GitHub推送。
