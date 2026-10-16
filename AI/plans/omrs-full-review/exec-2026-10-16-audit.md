# OMRS 全面实现检查：执行说明

执行者：Codex 主代理与三个子代理；运行模式：完整模式。先通读 `progress.md` 与 `plan.md`；目标、范围、验收和停止条件均以总纲为准。此说明执行一轮完整检查，可跨会话恢复，不包含业务修复或生产发布。

## 阶段 0：固定输入和可执行清单

1. 按根 `AGENTS.md` 开工，保留现有修改。记录 HEAD、`git status --short`、`git diff --name-status HEAD`、已跟踪及未跟踪业务文件清单。源码逐文件哈希另存仓库外；排除真实数据、凭据、`.git`、虚拟环境和缓存，同时记录删除项。后续报告同时标注 HEAD 和工作区快照，不把脏工作树叫作精确提交。
2. 复核 `plan.md` §2.2 所有事实。文档／测试计数只引用本轮运行值。确认服务工作目录与真实数据分离；不要通过读取凭据文件、打印环境变量全集来探测环境。
3. 下列命令从当前仓库根执行；若使用其他 checkout，先改为其实际根目录。所选 Python 必须能运行当前功能的可选依赖；需要换解释器时将下方 `OMRS_REVIEW_PY` 改为其绝对路径，所有验证统一使用该解释器。探测模块存在不等于浏览器能启动。

```bash
cd /root/workspace/apps/OMRS
export OMRS_REVIEW_BASE="$(git rev-parse HEAD)"
export OMRS_REVIEW_OUT="$(mktemp -d /tmp/omrs-full-review-XXXXXX)"
export OMRS_REVIEW_PY="$(command -v python3)"
unset OMRS_SYSTEMD_SERVICE OMRS_BOXDETECT_CONTROL
export TMPDIR="$OMRS_REVIEW_OUT"
export ZYB_TEST_EVIDENCE_DIR="$OMRS_REVIEW_OUT/gateway-browser"
git status --short
git diff --check
"$OMRS_REVIEW_PY" --version
node --version
"$OMRS_REVIEW_PY" tests/check_docs.py --diff "$OMRS_REVIEW_BASE"
```

4. 建立测试清单：逐脚本检查参数、是否实际执行断言、数据／端口／控制后端、外部访问、输出目录、SKIP 逻辑和退出语义。不得直接把未经核对的 `run_gates.py` 全组运行当作完整验收。升级夹具基线保留 `17d6d84`，不是本轮差异基线。

输出目录必须逐脚本核查：`TMPDIR` 无法覆盖写死路径，网关 `tests/support.py` 也在服务 `docs/` 内创建并清理临时目录。可配置的截图路径先设为本轮独立目录；固定路径先检查是否已有非本任务产物，不得覆盖。无冲突时运行后将证据归集并记录原路径；有冲突时改在隔离临时环境运行，无法安全隔离则记未运行。仓库内自建临时目录须验证 finally 清理且不触及其他内容，不能声称所有原脚本天然使用本轮输出目录。以下运行命令均以这一步核对完成为前提。

## 阶段 1：调用子代理并行核查

按总纲 §4.1 启动 A／B／C，禁止只在文档里“设想调用”。主代理保存各代理实际核查文件范围和结论；提示词统一附总纲的用户原话、默认审计边界、负责领域、禁止访问真实数据、不得修改共享源码、证据格式及返回条件。

各代理先完成全领域清单，再深读关键分支；主代理负责跨域链路：录入→审核→题库→调度→反馈→历史／导出，以及上传／任务→服务切换→迟到响应、备份恢复→旧任务失效。归并后的问题交给不同代理复核；遇到覆盖空白，用空闲代理补查。

仓库卫生先运行路径级清单，不输出敏感文件内容：

```bash
git ls-files
git ls-files --others --exclude-standard
git ls-files --others --ignored --exclude-standard
```

对明确候选使用 `git check-ignore -v <具体路径>`；盘点依赖声明、可选 import、生成物、体积异常、vendor 来源／许可／哈希、两类导出范围。敏感信息检查只输出文件／行号／类别，不把命中的秘密复制进报告；不默认安装新扫描器或联网扫描。`.venv/` 等目录先确认来源，不能删除或添加到提交。

## 阶段 2：运行验证并核对用户可见结果

### 2.1 根门禁与明确的 E2E 清单

以下命令保留原始入口，完整日志在 `--out` 目录。长命令后台执行并轮询，遵守会话沟通要求；不要并行启动整套浏览器和容量测试。每条结束后读取原日志，记录实际失败、跳过与断言数。

```bash
"$OMRS_REVIEW_PY" tests/run_gates.py --ref "$OMRS_REVIEW_BASE" --upgrade-ref 17d6d84 \
  --groups unit,ui,release --out "$OMRS_REVIEW_OUT/core"
```

该组包含根 unittest、pytest 报告导出、Node、组件浏览器、两种打印、UI／对比度、合成升级回归。它不涵盖独立服务，缺依赖时不改断言、不得把失败当通过。

当前 E2E 的兼容执行清单如下；阶段 0 若发现新增特殊参数或辅助模块，先更新临时清单并记录依据。这里排除的纸面辅助模块必须确认仍由 `zuoyebang.py` 调用；boxdetect 因外部冻结材料单列未运行，网关联调及两个共用截图环境变量的作业帮脚本在下节显式执行。

```bash
OMRS_REVIEW_E2E_IDS="$("$OMRS_REVIEW_PY" - <<'PY'
from pathlib import Path
separate = {'boxdetect', 'zuoyebang_gateway_integration', 'zuoyebang_paper',
            'zuoyebang', 'zuoyebang_service'}
print(','.join('e2e-' + p.stem for p in sorted(Path('tests/e2e').glob('*.py'))
               if p.stem not in separate))
PY
)"
"$OMRS_REVIEW_PY" tests/run_gates.py --ref "$OMRS_REVIEW_BASE" --groups e2e \
  --only "$OMRS_REVIEW_E2E_IDS" --out "$OMRS_REVIEW_OUT/e2e"
```

统一入口的 `results.json` 只记录退出码，主代理须逐项读取日志，把 `SKIP`、零断言、未执行脚本单列到最终 `validation.json`；不能原样复制后宣称全绿。失败项仅在有新定位／环境修正后定向重跑，并同时保留首次失败证据。

### 2.2 两个独立服务及双服务联调

在独立进程与各自工作目录运行，避免同名 `tests` 包互相污染：

```bash
(cd services/zuoyebang && "$OMRS_REVIEW_PY" -m unittest discover -s tests -t . -q)
(cd services/boxdetect && "$OMRS_REVIEW_PY" -m unittest discover -s tests -t . -q)
node --check services/zuoyebang/zyb_gateway/assets/panel.js
OMRS_ZYB_SHOTS="$OMRS_REVIEW_OUT/zyb-main" \
  "$OMRS_REVIEW_PY" tests/e2e/zuoyebang.py
OMRS_ZYB_SHOTS="$OMRS_REVIEW_OUT/zyb-service" \
  "$OMRS_REVIEW_PY" tests/e2e/zuoyebang_service.py
"$OMRS_REVIEW_PY" tests/e2e/zuoyebang_gateway_integration.py \
  --out "$OMRS_REVIEW_OUT/integration-direct"
"$OMRS_REVIEW_PY" tests/e2e/zuoyebang_gateway_integration.py --with-prefix \
  --out "$OMRS_REVIEW_OUT/integration-prefix"
```

两个作业帮脚本都会写 `checks.json`，不能共用截图目录；失败重跑也须使用新的独立目录，保留首次结果。显式单跑项的命令、退出码和断言数由主代理写入最终验证记录。

网关独立浏览器使用 `ZYB_TEST_CDP_URL`，与主站的 `OMRS_TEST_CDP_URL` 不同。仅在已确认的可信本机 Chromium 可用时设置两个变量，连接后只关闭自己的 context，不能关闭共享浏览器：

```bash
(cd services/zuoyebang && "$OMRS_REVIEW_PY" tests/browser_acceptance.py)
```

此入口当前依赖 CDP；不可用时先尝试在隔离环境启动自己的 Chromium，仍不能运行则标明缺口。证据必须由 `ZYB_TEST_EVIDENCE_DIR` 写到仓库外；核查脚本其他临时文件最终清理情况。

另检查两个服务 README 中的安装包独立运行合同。网关 `package_smoke.py` 硬编码服务目录的 `.venv`，应在临时源码副本及独立环境安装后运行，不写现有环境。检测服务 `package_smoke.py` 需要 `--model-dir`；仅提供冻结副本时运行，可用 `--wheelhouse` 离线安装。没有模型或构建依赖时明确“未验证安装／真实推理”，保留单测和协议验证结果。不得为满足脚本去读取在线模型、真实私有目录或修改当前解释器。

### 2.3 真实浏览器、视觉与人工核对

自动 E2E 之外，主代理在临时实例逐行核对总纲 §3.2 主路径与边界，尤其核对成功提示后实际持久化、刷新／重启恢复和失败后的可重试状态。复用 `tests/fixtures/make_vault.py` 的 full／empty 与 `tests/browser_runtime.py` 的 `open_app`；所有实例自行选随机端口。AI 使用现有 faux fixture，网关只替换官方网络边界。

```bash
"$OMRS_REVIEW_PY" tests/visual/run.py --ref "$OMRS_REVIEW_BASE" \
  --out "$OMRS_REVIEW_OUT/visual-default"
"$OMRS_REVIEW_PY" tests/visual/run.py --audit-only --pages assistant,ai-review,zuoyebang,trainpanel \
  --out "$OMRS_REVIEW_OUT/visual-extra"
"$OMRS_REVIEW_PY" tests/visual/run.py --audit-only --fixture empty \
  --out "$OMRS_REVIEW_OUT/visual-empty"
```

默认覆盖浅／深、1440px 桌面和 390px 手机。`/annotate` 是独立页，不能当 hash 路由传给 `--pages`；按 annotate E2E 的真实入口补截图与交互检查。网关面板也独立核对；关键编辑／审核／上传操作补 320px，必要时 1024px。模拟视口不能写成实体手机验收。

空态命令仍只覆盖默认 12 页；另外用临时空库补助手、作业帮、训练面板、标注页、审核中心及网关面板的无内容／未配置状态。审核中心视觉脚本会自动 seed 提案，不能以其截图证明空队列可用，应在未注入提案的空库用真实入口核对。

视觉基线 HEAD 不含已有未提交改动，已有差异必须归属说明；本计划不改页面时不把差异归为审计引入。截图出口退出 0 不代表横溢、字体、小目标或内容无问题，必须阅读 `report.html`、`audit.json` 并逐项解释异常。默认视觉可能操作自己的基线 worktree，使用唯一全新输出目录，不能复用其他任务的目录。

### 2.4 安全、数据与错误路径

按子代理结果核对根测试是否真正覆盖总纲 §5–6；优先复用 security／http_boundaries／mcp_keys／agent_permissions／ai_review／backup_recovery／ledger_concurrency／content_integrity／question_update 等现有测试，不为覆盖数字编写镜像测试。

用合成标记检查异常／日志／公开配置是否泄露凭据；合成归档检查路径、清单、WAL 与多独立库；重复批准／反馈／入库核对事实只追加一次。必要的进程中断、并发和磁盘失败演练仅在临时环境，保留失败现场，不能杀生产进程。普通性能仅记录当前合成数据规模下的耗时／资源；万题压测等可选项不得取代这些闭环。

CLI 单独建一份合成 Vault，按 `omrs_engine.py --help` 和各子命令帮助核对 create、scan、stats、schedule、sessions、export、export-csv 的输入／输出与持久化；再核对 mcp-key 的创建／查询／变更／吊销，以及 content-audit 和 content-recover 的默认预览、显式应用、幂等和错误清单。必须每次显式传 `--vault <本轮合成库>`，HTML 导出显式传 `--output <本轮仓库外路径>`。Key 创建的输出私密捕获并脱敏后记录；正文补回只用合成且身份／哈希匹配的清单，不访问旧生产备份。

## 阶段 3：复核结论、同步文档与收尾

1. 主代理复核三个子代理实际阅读范围及动态结果，补齐每个功能域的结论。高优先级问题必须有另一代理复核；证据不足写待核查，给出下一步验证方法。
2. 生成报告和完整验证记录；真实日志与截图留在仓库外，入库摘要脱敏且能对应源码快照。未修缺陷在 `AI/optimization.md` 唯一登记，事实错误按映射更新模块文档；不修改历史日志、不修业务代码。
3. 更新 progress 的状态块、分期、实际门禁计数、限制及下一步。审计完成不等于缺陷已修复；后续修复建议明确范围、优先级、预期验收和执行者，必要时另立执行说明。
4. 完成以下门禁，审查生成器实际差异后仅纳入本任务路径。未修改路由不生成路由表，未修改页面不重复因收尾而扩大 UI 门禁。

```bash
git diff --name-status "$OMRS_REVIEW_BASE"
"$OMRS_REVIEW_PY" tests/check_docs.py --write-log-index
"$OMRS_REVIEW_PY" tests/check_docs.py --diff "$OMRS_REVIEW_BASE"
git diff --check
```

5. 逐文件核对开工快照，证明未改既有业务内容；共享文档只包含经确认的勘误，暂存时保留他人 hunk。按总纲提交粒度交付，记录通过、失败、跳过、未运行四种状态，最终中文汇报的五项见总纲 §10。
