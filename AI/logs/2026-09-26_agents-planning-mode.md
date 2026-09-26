# 2026-09-26 AGENTS 规划模式与前端重构执行者切换

## 背景

**运行模式：** 受限模式（CCW）。基线是导出包 `OMRS-source-sanitized-20260926T140037Z.zip`，解压后 `git init` 提交为基线。

**用户原话：**
- 「剩下的交给Codex执行,去掉交接文档环节」
- 「这是实际导出的代码,应该是合并了」
- 「我准备写一个提示词,让Claude制作详细的计划」
- 「我每次会提要求,但是要求往往没有那么具体.Codex执行的不是很好」
- 「作为Claude,你需要理解需求,制定详细的执行计划」
- 「每次我上传完项目说明你是CCW,启动规划模式的时候触发」
- 「建议弄到AGENT.md吧,对了优化一下AGENT.md」
- 「然后把这次执行文档放AI文件夹里面合适目录就行」
- 「返回我全部zip文件」

用户另外给过一份规划提示词。它的方法和输出格式已并入 `AGENTS.md`「规划模式」的流程和执行说明模板。

**所属计划：** `frontend-rearch`（执行者切换部分）。

## 行为变化

产品行为不变：没有改业务代码、测试和配置。协作规则的变化如下。

**`AGENTS.md`：**
- **新增内容：**
  - 开头加了按角色找章节的导航；
  - 新增默认分工：CCW 规划，Codex 执行，Hermes 合入、部署和运维；
  - 模式判定加入规划模式：用户说「你是 CCW」并要求「规划模式」时触发。
- **新增「规划模式」一节：**
  - 流程：抄原话 → 实测 → 想清需求 → 写执行说明 → 自检 → 入库交付；
  - 执行说明模板，共十节；
  - 写给执行者的要点；
  - 存放与交付；
  - 规划模式不做的事。
- **新增「按执行说明执行」一节：** 规定 Codex 怎样开工、不改目标、按粒度提交、连续执行、中断后恢复、汇报。
- **受限模式的交付改了：** 不再写 UPGRADE、HANDOFF 和包外交接清单。补丁怎么应用、要补做哪些步骤，写在任务日志的「合入」一节。
- **完整模式补充了三点：**
  - 保护未提交改动；
  - 测试实例启动前去掉 `OMRS_SYSTEMD_SERVICE`；
  - 合入流程改为按「合入」一节执行。
- **共同约定：** 加上「用中文」。
- **强制收尾第 9 条：** 改为「执行说明放在计划文件夹，不写包外交接文档」。
- **映射表：** 加入 `tests/browser_runtime.py`。
- 防漂移、文档写法两节和映射表的其余各行不变。`check_docs` 和 `check_ui` 解析的表头格式保持原样。

**前端重构计划：**
- **新增执行说明** `AI/plans/frontend-rearch/exec-2026-09-26-codex.md`：Codex 按它从本机基线执行到 P6 剩余、P7、P8 和终检，部署另等用户授权。
- **`plan.md`：** 更新执行者；§6 通用约定改为按提交交付；§9 交接清单模板停用。
- **`progress.md`：**
  - 状态块改为指向执行说明；
  - 新增 U15；
  - §2 改写为流程与生产现状，并入了原 `AI/rearch-plan.md` 里仍然有效的事实；
  - §4 的 unittest 预期改为 159；
  - §5b 写入截图审计「44 处行内样式」的定位结论；
  - §7 标注只适用于 CCW 的条目；
  - §8 改写终检和部署两行；
  - §9 登记这次变更。

**其它文档：**
- 删除 `AI/rearch-plan.md`：它与本计划文件夹重复，内容停在「P5 待开始」。删除后用 `--write-routes` 重新生成了 `AI/routes.md`。
- `AI/plans/README.md`：新增执行说明 `exec-*.md` 的约定；删掉包外交接文档的说法。
- `AI/README.md`：
  - 修复日志模板没闭合的代码块（原来从模板开始到文件末尾都被渲染成代码），补上模板正文；
  - 「按任务找文档」加上规划模式一行；
  - 已迁页面清单更新到 P6。
- `AI/environment.md`：
  - 维护者表加上规划模式；
  - §5 新增「测试实例会重启生产服务」一条；
  - §6 改写接手配方，加入按执行说明开发。

## 规划前的实测（写进执行说明的依据）

**导出包内容：** 与 p6r5 完整包相比，只多出本机浏览器测试的 CDP 适配、`AI/rearch-plan.md`，以及 `AI/routes.md` 里的一处引用。P1–P6 删除的文件都已不在。

**门禁：**

| 门禁 | 结果 |
|---|---|
| unittest | 159 OK |
| node | 220 / 220 |
| `check_ui` | 0 处问题 |
| `check_contrast` | 58 组 0 不达标 |
| `check_docs --diff HEAD` | 0 处问题，1 条提醒 |
| `tests/e2e/schedule.py` | 45 / 45 |
| `smoke_schedule_workbench` | OK |

以上在独立 Chromium 下运行。

**截图审计「44 处行内样式」：** 用 `visual/run.py --audit-only` 复现出来了。原因是整页截图之后，所有 `<input>` 都带上了空的 `style=""`，而审计用 `hasAttribute('style')` 计数。截图前数，复习调度和题库页都是 0。

**`/api/restart`：** 进程环境里有 `OMRS_SYSTEMD_SERVICE` 时，它会执行 `systemctl restart`。

## 影响文件

| 状态 | 文件 |
|---|---|
| M | `AGENTS.md` |
| M | `AI/README.md` |
| M | `AI/environment.md` |
| M | `AI/plans/README.md` |
| M | `AI/plans/frontend-rearch/plan.md` |
| M | `AI/plans/frontend-rearch/progress.md` |
| A | `AI/plans/frontend-rearch/exec-2026-09-26-codex.md` |
| D | `AI/rearch-plan.md` |
| M | `AI/routes.md`（脚本生成：`/api/status` 去掉已删的 `AI/rearch-plan.md`，`/api/restart` 加上 `AI/environment.md`） |
| A | `AI/logs/2026-09-26_agents-planning-mode.md` |

## 验证

**已执行：** 见文末「合入」一节的门禁计数，全部在本次交付的最终文件上运行。

**未执行：**
- 浏览器 E2E：本次没有改代码。
- `--write-log-index`：受限模式不运行。

## 合入

- **补丁基线：** 导出包 `20260926T140037Z`。
- **补丁：** `changes-2026-09-26-ccw-plan.patch`，只改文档。
- **应用命令：** 在本机工作区执行 `git apply --3way changes-2026-09-26-ccw-plan.patch`。时机按执行说明阶段 0.4 第 3 步：先做基线提交，再应用这个补丁并单独提交。
- **预期门禁：** unittest 159 OK；node 220 / 220；`check_ui` 0 处问题；`check_contrast` 58 组 0 不达标；`check_docs --diff HEAD` 0 处问题、2 条提醒。两条提醒是：
  - `AI/api.md` 53KB，原有的；
  - 执行说明 48KB。它是计划文档，不受模块文档 40KB 的限制；为了让执行者一次读完，不拆分。
- **完整模式要补做的步骤：**
  - 运行 `python3 tests/check_docs.py --write-log-index`。验收标准：`AI/logs/log.md` 里有本日志。
  - 之后按 `AI/plans/frontend-rearch/exec-2026-09-26-codex.md` 执行，这一步由 Codex · 完整模式负责。
