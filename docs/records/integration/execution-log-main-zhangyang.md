# 集成执行日志：`main` × `feature/zhangyang`

> 配套文档：`docs/records/integration/plan-main-zhangyang.md`（方案）
> 执行方式：自主执行，决策与问题记录于此，全部完成后由张洋逐个审核
> 回退锚点：`feature/zhangyang` 起点 `b7395b4`（方案文档提交后为 `5376d39`）
> main 基线：`7182767`

本日志按阶段记录：**做了什么 / 遇到的问题 / 我的决策 / 待审核点**。

---

## 执行状态总览

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 锁定架构宪法（采用 main 规范） | ✅ 已决策 |
| 1 | 启动合并 + 零冲突净增量（intelligence/observability/后台/governance 包） | ⏳ |
| 2 | 运行时模块迁入 + import/trace 接线 | ⏳ |
| 3 | 核心三方合并（tool_registry / agent_loop / config / server / store） | ⏳ |
| 4 | Alembic 迁移链重排 + 新表收编 | ⏳ |
| 5 | 测试归位 + conftest 合并 | ⏳ |
| 6 | docs / openspec 并集 + CLAUDE.md 统一 | ✅(CLAUDE/docs 已处理；openspec 取并集自动完成) |

**最终测试**：合并初始 2064 passed / 15 failed / 4 errors → **逐条解决后 2079 passed / 1 failed / 16 skipped**。collection 干净，核心 import 正常，alembic 单一 head（029）。

**唯一剩余失败** = `test_trace_events::test_legacy_eval_logger_..._not_public`，即 C2（trace 统一）—— 张洋已决定**单独立项**，eval_logger 暂与 observability 共存，故该断言预期失败。

**逐条处置结果（与张洋逐条过完）**：
- **类 A**（D5 智能层未接入，6）→ ✅ 已接线（build_context + observability trace 进 run/run_stream）。
- **类 B**（D6 S3 会话绑定，6）→ ✅ 在 main db.py 调度器上重做（按需 session_id 绑定，迁移 029）；yaml cron 加载按 main 规范弃用。
- **类 C1**（记忆双系统）→ ✅ 统一到 intelligence/memory，删 memory_layer.py。
- **类 C2**（trace 双系统）→ ⏸️ 单独立项（天级重构，100+ 测试触点）。eval_logger 暂共存。
- **类 D**（webhook 设计）→ ✅ 留 yaml 源模型 + 加 main 的安全门控（enabled/body-size）。

---

## 决策记录（Decision Log）

### D0 — 架构基线
采用 main 的工程规范（db.py runtime 边界 / named params / schema 归 Alembic / 测试分层 / yaml-first 配置），以 main 包结构为骨架。张洋已确认。

### D1 — 扁平模块的去留边界（降低 churn 的关键决策）
观察：main 自己也把 `agent_loop.py` / `tool_registry.py` / `model_router.py` / `session_mgr.py` / `config.py` / `user_store.py` 等**保留为顶层扁平模块**，只对 5 个领域分包（`governance/` `integrations/` `intelligence/` `observability/` `platform/`）。
决策："采用 main 规范"≠"所有文件进包"。因此：
- 张洋的净新增运行时模块（termination / budget / layered budget / loop_detector / cancellation / error_classifier / message_hygiene / sub_agent_lifecycle / provider_health / tool_guardrails / tool_result_truncation / connectors / plugin_loader / skill_audit / multimodal / vision_client / image_gen_client / session_index）**保持顶层扁平**，与 main 留 agent_loop 扁平一致。
- 仅 main 已分包领域中重叠的 mcp / sandbox，把张洋的超集实现**放进 `integrations/mcp/`、`integrations/sandbox/`**。
- governance：git 改名检测已自动删除扁平版、保留 `governance/` 包（行为等价，零风险）。

### D2 — 合并机制：rename 检测的影响
git 把 main 对 `mcp_client.py→integrations/mcp/client.py`、`sandbox_client.py→integrations/sandbox/client.py` 的移动识别为 rename，张洋的超集内容落在这两个**包路径的冲突 stage 2(ours)**，未丢失。解冲突时 `--ours` 即取张洋超集。

### D3 — trace 系统暂时共存（送审后续项）
张洋代码重度依赖扁平 `eval_logger.py`（JSONL，log_compression/log_sandbox_exec 等），main 用 `observability/traces.py`（SQLite）。整体改接风险高、工作量大。
决策：**两者共存**——保留 `eval_logger.py`，main 的 `observability/traces.py` 也保留各自被依赖。trace 系统统一**列为后续项**，不在本次合并内完成。⚠️ 送审点。

### D4 — mcp / sandbox 保持扁平，移除 main 的 integrations/ 包（覆盖 D1 该点）
证据：合并后统计导入方——张洋侧 `agent_loop`/`tools`/`server`/`plugin_loader`/`normalizer`/6 个 sandbox helper + ~15 个测试**全部 import 扁平路径**(`fleetent.sandbox_*`、`fleetent.mcp_client`)；引用 `integrations.*` 的只有 `server.py`/`tools.py`(本就解析为张洋版) + 包内 `__init__.py`。
决策：**mcp、sandbox 保持顶层扁平**(张洋超集 `mcp_client.py` + `sandbox_*.py` 7 文件)，**删除 main 的 `integrations/` 包**(其内容是被丢弃的劣版)。
- 解 rename 冲突：从 stage2(ours) 抽出张洋内容写回扁平路径，`git rm -r integrations/`。
- 收益：避免重写 ~25 个文件(含 15 测试)的 import；功能零损失。
- ⚠️ 送审点：若要严格归入 `integrations/` 包，是后续纯机械任务。这是跑通合并的最低风险路径。
- 注：governance 由 git 自动归包(内容等价、零风险)，故保留 `governance/` 包；张洋侧 import 扁平 governance 模块处需改写为 `governance.*`(下一步处理)。

### D5 — 运行时核心文件取张洋超集 + 智能层/可观测接线列为后续
`agent_loop.py` 张洋版已正确处理 async 工具（`agent_loop.py:386` `inspect.iscoroutine(result)` → `await asyncio.wait_for`），故原 I1「async dispatch 语义冲突」**实为不存在**——dispatch 返回协程、loop 侧 await，MCP 工具可用。
决策：以下取张洋版（`--ours`）：`agent_loop.py`、`tool_registry.py`、`tools.py`、`session_mgr.py`、`im_gateway/{normalizer,slack,telegram}.py`。
⚠️ 送审/后续项：
- main 的 `intelligence/long_term_ctx.build_context()`（KB+记忆注入）与 `observability` trace 埋点**尚未接进 agent_loop**——智能层已存在但未在循环中调用。列为后续接线任务。
- session_mgr 新增表（元数据索引/TTL）仍用裸 sqlite3，未收编 db.py，后续迁移。

### D6 — 调度器取 main 版（db.py + admin 集成），S3 会话绑定后续再补
`cron_scheduler.py`/`schedule_store.py`：main 版走 `db.py` + `SchedulingSettings`，且被 main 的 `server.py`(`CronScheduler(settings=settings.scheduling)`)、`platform/admin_cli/schedules.py`、`stats_admin_api.py` 依赖。张洋版走裸 sqlite3 + S3 会话绑定。
决策：**取 main 版**（`--theirs`），保住 main 较大的后台/admin 调度面。张洋的 S3「定时任务绑定 session」作为**后续单点 feature 重新嫁接**。符合「main 为骨架」。

### D7 — 测试解析：保留「与所留实现匹配」的测试 + 扁平测试迁入 subdir
- 解析原则：留张洋实现的模块→留张洋测试、删 main subdir 重复版；留 main 实现的→反之。
  - 留张洋测试：`test_agent_loop`、`test_eval_logger`、`test_server_lifespan`、`test_server`、`unit/test_tools`、`unit/test_sandbox_client`、`unit/test_model_router`。
  - 留 main 测试：`integration/test_admin`(用 platform/admin_cli)、`unit/test_config`(config 以 main 为基底)、`integration/test_migrations`(迁移链以 main 为准)。
- `conftest.py`：合并两个 fixture(`_reset_provider_health_cache` autouse + `isolated_schedule_db`)。
- ⚠️ **关键**：main 的 `pytest.ini` 仅收集 `tests/{unit,integration,e2e,evaluation}`，张洋的 34 个扁平 `tests/test_*.py` 默认**不被收集**→ 留扁平等于没覆盖。故**全部迁入 `tests/unit/`**(无 basename 冲突)。unit/integration 归类为近似(对收集无影响)，精确归类列为后续项。
- 注：main 自身在 `tests/unit/` 与 `tests/integration/` 存在 8 对同名测试(vector_store 等)，靠 `__init__.py` 包路径区分，是 main 既有状态，未改动。

### D8 — 全局 import 改写
张洋侧保留代码中所有 `from fleetent.{agent_policy,audit_log,blocklist,permission_gate,quota} import` 改写为 `from fleetent.governance.* import`（agent_loop / tool_registry / normalizer / 迁入的测试）。mcp/sandbox 保持扁平（D4）故无需改写。

<!-- 后续决策按 D9… 追加 -->

---

## 问题记录（Issue Log）

- **I1 — `memory_layer.py` 被合并误删**：main 的 "shim cleanup" 删了它，张洋 agent_loop 仍 import。处置：从 5376d39 恢复扁平版（D3 共存）。
- **I2 — `integrations.*` 结构断言测试**：3 个 main 测试断言 integrations 包存在 / 扁平 mcp/sandbox 不可导入，与 D4 矛盾。处置：删除（test_integrations_imports、test_legacy_shim_cleanup、integration/test_mcp_client）。
- **I3 — 全局 ValidationError（曾 ~450 处）**：`Settings.anthropic_api_key` 必填，合并后无全局测试 env。处置：conftest 加 autouse fixture 设 `ANTHROPIC_API_KEY`（修复 ~200+ 测试）。
- **I4 — alembic 多 head/重复 revision**：两边 002/003/004 撞号。处置：张洋 002→026 / 003→027 / 004→028，链接 main head 025（阶段4）。
- **I5 — `no such table: scheduled_tasks`（曾 36 处）**：main CronScheduler（D6）需迁移表，张洋 server 测试未建表。处置：server lifespan `cron.start/shutdown` 改 best-effort（与 sandbox/IM 同款容错）。
- **I6 — `webhook_router.load_sources` 缺失**：合并取了 main 的 webhook_router（无 load_sources），但张洋 server.py 启动调用它。处置：恢复张洋 webhook_router（唯一消费者是 server.py）。
- **I7 — `session_mgr.clear/inject_message` 缺失**：main chat_admin_api 依赖，张洋 session_mgr 无。处置：从 main 嫁接两函数。**踩坑**：首次嫁接误插入 `save()` 体中段，把 save 的 metadata/maintenance 尾巴孤立进 inject_message → test_session_mgr 4 挂；已重做为干净独立函数修复。
- **I8 — skill_admin_api `_validate_frontmatter` 崩 None**：张洋 `_parse_frontmatter` 对非法 frontmatter 返回 None（main 返回 {}）。处置：`or {}` 兜底。

---

## 剩余 15 failed + 4 errors —— 全部为已记录决策的预期后果（待张洋审核）

> 这些**不是意外破坏**，而是合并取舍/延后接线的直接体现。保留为失败状态是刻意的——它们正是后续工作的"规格信号"，请逐条决定如何处置。

### 类 A：D5 智能层/可观测未接进 agent_loop（6）—— ✅ 已解决（2026-06-03）
- 已把 main 的 `build_context`（KB+记忆注入）+ observability trace（injected_context / agent_run_completed）接进张洋 `run()` 与 `run_stream()`，调用点 best-effort（无 DB/禁用 KB 不破坏运行，159 个无 DB 单测保持绿）。契约测试 fixture 适配：`maybe_compress` mock 收 `**kwargs`、补 `extract_and_save` mock（张洋 run 有记忆提取）。
- 全量回归：**13 failed / 2070 passed / 0 errors**（A 类 6 项清零，无新破坏）。

### 类 B：D6 取 main 调度器、丢张洋 S3 会话绑定（6）—— 后续 feature 重嫁接
- `test_scheduled_task_session_binding`（6）：断言 schedule_store.DB_PATH / load_cron_yaml / session_id 列（张洋 S3）。
- **处置建议**：在 main 的 db.py 调度器上重新实现 S3 会话绑定，或确认放弃该 feature 后删除这些测试。

### 类 C：D3 trace/memory 双系统共存（3）—— 断言"已删除"与共存决策冲突
- `test_trace_events::test_legacy_eval_logger_..._not_public`
- `test_memory_legacy_import_cleanup::test_legacy_memory_layer_module_is_not_importable`
- `test_memory_package_imports::test_legacy_memory_layer_is_removed`
- **处置建议**：做 trace/memory 统一（弃 eval_logger/memory_layer 改用 observability/intelligence）后这些转绿；或确认长期共存则删除这些断言。

### 类 D：Webhook 设计分歧（4）—— 需产品/架构定夺
- `test_webhook_server`（3）：main 设计 = 拒绝 legacy `webhooks.yaml`（fail-fast）+ `webhook_settings` 开关/体积门控；张洋设计 = 从 `webhooks.yaml` 加载。**二者根本互斥**（不能既加载又 fail-fast）。
- `test_webhook_router::test_yaml_source_loader_is_removed`（1）：断言 load_sources 已删（我们恢复了它）。
- **处置建议**：定夺 webhook 走 main 的运行时 API 还是张洋的 yaml；二选一后对齐实现与测试。

---

## 后续工作清单（FOLLOW-UP，按优先级）

> 类 A/B/C1/D 已在「逐条过」中解决（见上）。以下为剩余项。

1. **[高·已立项] C2 trace 统一**：弃用 `eval_logger.py` 改用 `observability/traces`（含为 compression/sandbox 新增事件类型）。天级重构，~100+ 测试触点（test_eval_logger 42 测 + agent_loop 55 处 log_run 断言 + context_mgr 8 + tools 13）。**唯一剩余失败测试**等它落地。
2. **[中] 记忆提取的触发**：C1 把 inline 提取改为 `intelligence.memory.extract_and_update`（每次 run 后 best-effort 调用，对齐原 inline 行为）。若想完全对齐 main（提取移出热路径、交反思层），再调整。
3. **[中] DB schema 收编**：张洋裸 `CREATE TABLE`（budget usage/sub_agent_runs/session_anti_flap 等）纳入 alembic 声明。
4. **[低] mcp/sandbox 是否归 `integrations/` 包**：当前扁平（D4）。若要严格 main 规范，机械迁移 + 改 import。
5. **[低] 测试精确归类**：迁入 `tests/unit/` 的 34 个文件按 unit/integration 精确归位。
6. **[低] `reload-skills` CLI 子命令**：main admin_cli 未含，`skill_registry.reload()` 仍在。
7. **[低] CLAUDE.md / capability docs 与混合架构对齐**（扁平 mcp/sandbox + main 包结构并存的现状描述）。
8. **[低] webhook 运行时 API**：当前 yaml 源模型 + 安全门控（类 D）；main 设想的运行时来源管理 API 可后续补。

---

## 阶段执行明细

<!-- 每阶段完成后在此补写实际操作、命令、结果 -->
