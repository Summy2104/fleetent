# 自动执行日志 — 定时任务 & MCP 稳定性三件套

> 操作者代理记录。用户全自动授权（不中途介入），最终审批依据此文档。
> 起始 main：`b89a51d2`（2026-06-12）。执行者 git 身份 r.intern.dev / PR 经 bb-pr（yang.zhang 建、admin 合）。

## 计划（6 阶段串行）
- A. `fix-cron-fire-outbound-connectors` — 消 Jira AAA-8039 根因
- B. `mcp-session-lifecycle-and-shutdown-bulkheads` — MCP 纳编 + 关停舱壁
- C. 第一轮部署验收（A+B）：8039 复测关单、20×优雅重启、armada 断网
- D. `typed-scheduled-task-delivery` — 任务分型 + 投递契约 + 创建时定稿
- E. 第二轮部署验收：三型任务 Slack 实测 + 8039 回归
- F. 总结报告

## 最终总结报告（Phase F）

### 交付物：3 个 change，全部 TDD + 门禁通过 + 推送，待合并
| Change | 分支 | 修复 | 门禁 |
|---|---|---|---|
| `fix-cron-fire-outbound-connectors` | `feat/fix-cron-fire-outbound-connectors` | **AAA-8039** 定时任务投递不到 Slack（fire 时连接器未传入 run） | test-pr 2886✅ / integ 1934✅，净新增 0 |
| `mcp-session-lifecycle-and-shutdown-bulkheads` | `feat/mcp-session-lifecycle-and-shutdown-bulkheads` | MCP teardown 崩溃整个进程（关联 **AAA-8050** 静默失败）+ 关停舱壁 + owner-task 契约护栏 | test-pr 2893✅ / integ 1934✅，净新增 0 |
| `typed-scheduled-task-delivery` | `feat/typed-scheduled-task-delivery`（基于 A） | 任务分型 notify/generate/action + 投递契约 + 创建时定稿 + 意图级状态 | test-pr 2889✅ / integ 1942✅，净新增 0 |

三者均：proposal/design/specs/tasks 四件套 → worktree+分支 → 严格 TDD（红→绿）→ `make test-pr` + `tests/integration` 对照 main 基线无新增失败 → archive+spec 同步 → 推送。`make test-pr` 唯一 1 失败 `test_config.py::test_observability_logging_defaults` 与 integration 唯一 `test_pilot_readiness_admin` 均为 **main 上 pre-existing**（本机 config 泄漏，非本批改动）。

### 实测验收（组合 A+B+D 部署 dev-intern）
- B：SIGUSR1 优雅排水 **exit 0、零崩溃**（MCP DELETE 握手生效），原 6/11 崩溃消除。
- A+D：bot 自动建 notify 任务、冻结文案、06:08:20 准点 verbatim 投递到频道（8039 场景端到端修复）。

### Jira
- 本会话早先已关：AAA-8033 / 8037 / 8052（RESOLVED，Cause=无，附 Slack 实测证据）。
- AAA-8039：加验证评论，**待 PR 合并后关闭**。
- AAA-8050（静默失败）：根因之一（MCP 进程崩溃）已由 B 修；待合并部署后可复核关闭。
- 其余（8034/8035/8036/8051/8053/8054）：用户指示「其余不管」，未改。

### ⚠️ 需用户处理的事项（审批清单）
1. **合并 3 个 PR**（顺序：先 A，再 D〔基于 A，stacked〕；B 独立任意序）。**当前阻塞**：Bitbucket REST API 被 IP 白名单挡（403），本环境无法经 API/bb-pr 创建合并 PR。需：放行本机出口 IP，或在 Web UI 手动合并已推送的 3 个分支。
2. 合并后：拉 main → `uv tool install --reinstall .` → 重启 dev-intern（当前跑的是未合并组合分支 binary，功能优于 main 但非正式）。
3. 关闭 AAA-8039（合并后）；复核 AAA-8050。
4. 次要遗留（非阻塞，见下方记录）：aiohttp 关停 GC 告警、SIGUSR1 发送者审计、`typed-scheduled-task-delivery` 团队评审（动 schema + 用户可感知行为）。

## 决策点与问题记录（按时间）

### Phase C/E — 部署验收（组合 A+B+D，未合并分支）
- 因 IP 白名单无法合并 PR，按 route-around：建 `verify/combined-abd`（D 分支并入 B，含 A），`uv tool install --reinstall .` 部署到 dev-intern（test agent），重启后 health 200、无 slack 报错。组合 17 关键测试本地全过。
- **B 验证（优雅关停不崩）✅**：`kill -USR1` 触发排水 → 日志 `Scheduler has been shut down` → MCP 会话 `DELETE .../mcp`（aclose_all 生效）→ `agent_drain_started active_runs=0` → `agent_drain_completed` → 进程退出 **`Result=success` / `ExecMainStatus=0`**，崩溃特征（cancel-scope-diff-task / BaseExceptionGroup / status=1）计数 **0**。对比 6/11 原崩溃（exit 1）彻底消除。残留：一条 aiohttp `__del__` "Unclosed client session / Event loop is closed" GC 期良性告警，不改退出码（次要遗留，见下）。
- **A+D 验证（定时投递 + 分型）✅**：Slack 让 bot 建「2 分钟后频道发提醒」→ bot 自动选 **task_type=notify**、冻结 `notify_text='定时验证-ABD-OK-2233'`、deliver=explicit slack 频道 → 06:08:20 `Running job ... executed successfully`、频道 **verbatim 收到该消息**、last_status=completed。即 8039 报障场景端到端修复，且 notify 走调度器直发不跑 agent。
- Jira：AAA-8039 加验证评论，**暂不关单**（修复在未合并分支，待 PR 合并后关闭）。
- **dev-intern 现状**：运行**组合分支代码**（verify/combined-abd 的 binary），功能优于 main（修了崩溃+定时投递）。待 PR 合并后由部署方从 main 重新部署。
- 次要遗留（非阻塞）：①SIGUSR1 关停期 aiohttp `__del__` GC 告警（exit 0 不受影响，疑似 SDK streamable-http 内部 aiohttp session 未在 loop 关闭前释放，可后续单独收口）；②bot 对建任务请求的**线程文字回复**偶发空/迟（任务实际已正确创建+触发，属 Slack 回显问题非功能问题）；③SIGUSR1 发送者审计（6/11 谁触发 drain）仍建议单独排查。



### Phase A — fix-cron-fire-outbound-connectors
- 分支 `feat/fix-cron-fire-outbound-connectors`，从 main `b89a51d2` 出发。
- 实现：`_agent_run` 增 `connectors` 形参 → `loop.run(outbound_connectors=connectors or {})`；`_fire` 传入 fire 时快照。2 个新 unit 测试红→绿。
- **决策/连带**：签名变更使 `tests/integration/test_scheduled_task_session_binding.py` 的 3 个 `fake_run` stub（`_agent_run` 替身）撞挂——按契约给 stub 补 `connectors=None` 形参修复（不改其 session-binding 测试意图）。
- **门禁**：`make test-pr` = 2886 passed，1 failed = `test_config.py::test_observability_logging_defaults`（**pre-existing**，本机 config 泄漏，main 同样红，非本改动）；`tests/integration` = 1934 passed，1 failed = `test_pilot_readiness_admin`（**pre-existing**，main 同样红）。**本改动净新增失败 0**。
- archive：spec 同步进 `openspec/specs/cron-scheduled-tasks/spec.md`，change 移入 `archive/2026-06-12-fix-cron-fire-outbound-connectors`；实现 commit `1e0662d3`。
- 分支已推送：`origin/feat/fix-cron-fire-outbound-connectors`。

### 🚧 BLOCKER（全局，影响所有 PR 合并）— IP 白名单
- **现象**：Bitbucket REST API（bb_get/bb_post，user 与 admin 两套凭据均试）返回 **403 "To access this repository, an admin must whitelist your IP."**
- **影响**：本环境**无法经 API 创建/审批/合并 PR**。SSH `git push` 正常（分支可上远端），但不能直接推保护分支 main（违反 branch-first 规则，且 main 受保护）。
- **不可自主绕过**：需 Bitbucket 管理员将本机出口 IP 加入白名单，或由人工在 Web UI 合并已推送的分支。
- **应对决策（route-around）**：
  1. A/B/D 三个 change 全部完成代码 + TDD + `make test-pr`/integration 门禁 + **推送到 remote 分支**，使其「一键可合」；
  2. **合并到 main = 人工门**，列入最终审批清单（你放行 IP 后可用 bb-pr 重跑，或 Web UI 直接合并 3 个分支）；
  3. **部署验收（Phase C/E）改为对未合并的组合分支代码做本地部署**到 dev-intern（test agent，可逆），跑真实 Slack 测试取证——验收价值不依赖 main 合并。
- 待办合并清单（最终审批）：
  - [ ] PR: `feat/fix-cron-fire-outbound-connectors` → main（Phase A，AAA-8039）
  - [ ] PR: `feat/mcp-session-lifecycle-and-shutdown-bulkheads` → main（Phase B；独立于 A）
  - [ ] PR: `feat/typed-scheduled-task-delivery` → main（Phase D；**基于 A 分支，须在 A 之后合并**）

### Phase B — mcp-session-lifecycle-and-shutdown-bulkheads
- 分支 `feat/mcp-session-lifecycle-and-shutdown-bulkheads`（从 main `b89a51d2`，与 A 文件无重叠）。commit `bec12b9a`(proposal) + 实现 commit。已推送。
- 实现：`integrations/mcp/client.py` 引入 `_SessionHost` + `_host_session`（per-session owner task，enter/exit 同 task）；`_active_sessions` 仍存 live session（消费点零改），并行 `_session_hosts` 管生命周期；删除模块级 `_exit_stack`/`get_exit_stack()`/死代码 `close()`，新增 `aclose_all()`（并发关、每宿主 5s 超时 cancel 兜底、错误遏制）。`_reopen_session` 先关旧宿主。`unregister_server`（sync）发 close_event 自销。
- 关停接线：`agent_app._stop_step`（舱壁）+ 抽 `_drain_and_close`（rt.stop→排干→`aclose_all`）；`AgentRuntime.stop` 各步舱壁化；`server.py` lifespan shutdown 调 `aclose_all`。
- 护栏：`test_module_dependency_guardrails.py` 加「模块级 AsyncExitStack 单例」扫描 + 非空性证明（绿，且证明可捕获植入违例）。AGENTS.md 加 owner-task 契约 + Gotcha。
- **门禁**：`make test-pr` = 2893 passed + 1 pre-existing(`test_observability_logging_defaults`)；`tests/integration` = 1934 passed + 1 pre-existing(`test_pilot_readiness_admin`)。MCP 套 149 unit + 73 integration 全过（消费路径未破）。**净新增失败 0**。
- spec 同步：`mcp-session-continuity`（会话宿主 + 懒重连关旧 + REMOVED AsyncExitStack 释放→ADDED aclose_all）、`agent-runtime-cli`（排水链 + 舱壁 + exit 0）、`module-dependency-guardrails`（新护栏）。已 archive。

### Phase D — typed-scheduled-task-delivery
- 分支 `feat/typed-scheduled-task-delivery` 基于 **A 分支**（含 A 的 cron 改动），实现 commit 已推送。PR 须在 A 之后合并（stacked）。
- 实现：`agent_state_migrations` v29/v30（task_type 默认 generate + notify_text）；`schedule_store.create` 按型校验；`cron_scheduler._fire` 三型分发（notify 直发不跑 agent / generate 折入投递声明并投递 / action 跑 agent 不广播）+ `_generate_delivery_statement`；`schedule` 工具加 task_type/notify_text + 校验转字符串 + 描述含判定问题与定稿流程；`create_task`(模块+方法) 透传。
- **决策/连带**：① generate 的投递声明改为**折入 task 消息内容**（非独立消息），避免固定会话历史累积污染、保持消息条数不变；② `test_scheduled_task_session_binding::test_fire_fixed_semantics_accumulates` 的 task 改用 `action` 型（session-binding 与类型正交，action 不注入声明，断言原样成立）；③ `test_agent_state_unified_migrations` 两处：列完整性集合补 task_type/notify_text；legacy fixture 补建 scheduled_tasks（忠实于 v27 态，让 v29 ALTER 有表）。
- **门禁**：`make test-pr` = 2889 passed + 1 pre-existing；`tests/integration` = 1942 passed + 1 pre-existing(`test_pilot_readiness_admin`)。**净新增失败 0**。
- spec 同步：`cron-scheduled-tasks`（Scheduled task definition 增列+校验、Cron trigger 改三型分发+意图状态、schedule tool 增参、新增 Delivery contract / Notify finalized-at-creation 两 requirement）。data-model.md 更新。已 archive。

