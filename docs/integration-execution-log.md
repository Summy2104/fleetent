# 集成执行日志：`main` × `feature/zhangyang`

> 配套文档：`docs/integration-plan-main-zhangyang.md`（方案）
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
| 6 | docs / openspec 并集 + CLAUDE.md 统一 | ⏳ |

---

## 决策记录（Decision Log）

### D0 — 架构基线
采用 main 的工程规范（db.py runtime 边界 / named params / schema 归 Alembic / 测试分层 / yaml-first 配置），以 main 包结构为骨架。张洋已确认。

### D1 — 扁平模块的去留边界（降低 churn 的关键决策）
观察：main 自己也把 `agent_loop.py` / `tool_registry.py` / `model_router.py` / `session_mgr.py` / `config.py` / `user_store.py` 等**保留为顶层扁平模块**，只对 5 个领域分包（`governance/` `integrations/` `intelligence/` `observability/` `platform/`）。
决策："采用 main 规范"≠"所有文件进包"。因此：
- 张洋的净新增运行时模块（termination / budget / layered_budget / loop_detector / cancellation / error_classifier / message_hygiene / sub_agent_lifecycle / provider_health / tool_guardrails / tool_result_truncation / connectors / plugin_loader / skill_audit / multimodal / vision_client / image_gen_client / session_index）**保持顶层扁平**，与 main 留 agent_loop 扁平一致。
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

<!-- 遇到的问题按 I1、I2… 追加，含现象 + 处置 -->

---

## 阶段执行明细

<!-- 每阶段完成后在此补写实际操作、命令、结果 -->
