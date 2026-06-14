# 集成方案：`main` × `feature/zhangyang` 两套架构合并

> 状态：方案（待执行）
> 分叉点：`3df29c5`（2026-05-30，PR #10 `feature/start`）
> 基线决策：**以 `main` 的工程规范为准**（db.py runtime 边界 + named params + schema 归 Alembic + 测试分层 + yaml-first 配置）
> 推送范围：集成在 `feature/zhangyang` 上进行，测试通过后仅推 `origin/feature/zhangyang`，由张洋手动开 PR 合 `main`

---

## 0. 背景：这不是普通合并

两条分支从 `3df29c5` 起朝**两个正交方向**独立生长，已不是「功能分支领先主干」的关系：

- `feature/zhangyang`：210 个领先提交，**Agent 运行时硬化**方向。
- `main`：223 个领先提交（raw34 199 / Randy Chang 12 / Romanzhang 10 / liang.zhang 2），**智能层 + 管理平台 + 工程化重构**方向。

直接 `git merge` 会产生 **34 个冲突文件**，且因为 main 做了整体包结构重组（`governance/`、`integrations/`、`intelligence/`、`observability/`、`platform/`），merge 后树里会出现**两套并行的模块结构**（如 `mcp_client.py` 与 `integrations/mcp/client.py` 并存），import 自相矛盾、无法通过测试。**这是把两套架构合二为一的集成工程，不是解冲突。**

---

## 1. 谁做了什么（互补全景）

两边重叠极少，绝大多数能力是**互补**而非竞争。

| 子系统 | 更完整的一方 | 关系 | 集成动作 |
|---|---|---|---|
| 终止框架 `termination.py` | **张洋独有，main 空白** | 净增量 | 整体移入；循环检查点插入 |
| 用量预算 `budget.py` + `layered-budget.py`（五层，cost 已砍） | **张洋独有，main 空白** | 净增量 | 移入；新表收编 Alembic |
| 循环检测 `loop_detector.py` | **张洋独有，main 空白** | 净增量 | 移入（依赖 LoopState） |
| 取消传播 `cancellation.py`（CancelToken + parent） | **张洋独有，main 空白** | 净增量 | 移入；牵动 dispatch 签名 |
| 错误分类 `error_classifier.py` | **张洋更强**（main 仅硬编码 503 fallback） | main 弱内联 | 用张洋查表替换 main 硬编码 |
| 消息卫生 `message_hygiene.py` | **张洋独有，main 空白** | 净增量 | 移入；LLM 调用前 sanitize |
| 子 agent 状态机 `sub_agent_lifecycle.py` | **张洋独有，main 空白** | 净增量 | 移入；新表收编 Alembic |
| 上下文压缩 `context_mgr.py`（713 行 vs main 103 行） | **张洋压倒性超集** | 单向演进 | 全量用张洋，迁 config + schema |
| sandbox（7 文件 vs main 单文件 MVP） | **张洋压倒性超集** | API 超集 | 弃 main 单文件，全用张洋 |
| MCP `mcp_client.py`（998 行：streamable/session/健康/降级/oauth2） | **张洋大幅超集** | | 弃 main，回收 startup 上报 |
| 模型 fallback 熔断 `provider_health.py` | **张洋独有，main 空白** | 净增量 | 移入，接 model_router |
| 工具系统（guardrails/截断/connector/plugin/超时） | **张洋超集** | | 留张洋，**回收 main async dispatch 语义** |
| skill 运行时引擎（YAML/嵌套/热加载/审计/作用域） | **张洋超集** | | 留张洋引擎 |
| 治理 `governance/`（agent_policy/permission_gate/quota/blocklist/audit_log） | 逻辑等价，main 工程质量略胜 | **行为零差异** | 用 main 的包结构 |
| skill 后台管理 `skill_admin_{store,api}` | **main 独有** | 与张洋引擎正交 | 移植 main，写适配层桥到引擎 |
| `intelligence/`（KB/记忆/向量库/反思 ~2500 行，**可跑**） | **main 独有** | 零 agent_loop 耦合 | 全量保留为基底 |
| `observability/`（traces/usage/性能/诊断/结构化日志） | **main 独有** | 单向被依赖 | 全量保留为基底 |
| 后台管理（8 API + 9 store + admin_cli + admin.html ~3000 行） | **main 独有** | 占位 seam 隔离，零 agent_loop 耦合 | 全量保留为基底 |

**关键事实**：main 的 `intelligence/` / `observability/` / 后台管理三大层**完全不反向依赖 `agent_loop`**（通过 injectable seam 通信）。所以张洋的运行时改动再大也不会破坏它们 —— 它们可以作为基底直接保留。

---

## 2. 集成基线（已定）

**以 `main` 为骨架，把张洋的运行时能力迁入对应包。**

理由：

1. main 多出 ~6200 行的智能层 + 管理平台 + 可观测性是**纯增量**且已成熟可跑；
2. 张洋的运行时模块大多是**独立新文件**，迁入成本低于反向改写 main 的整套后台；
3. 架构宪法已选 main 规范（db.py / Alembic / 测试分层 / yaml-first），骨架自然落在 main。

---

## 3. 分阶段执行路线

### 阶段 0 — 锁定架构宪法 ✅（已决策）
采用 main 的 `CLAUDE.md` 规范。张洋分支的「直接 sqlite3 / 平铺测试 / .env」做法在集成后让位给「db.py runtime 边界 / 测试分层 / yaml-first」。

### 阶段 1 — 零冲突净增量（低风险，先合）
将 main 以下层整体接纳为基底，张洋分支无对应物，**纯新增、零冲突**：
- `intelligence/`（knowledge_base / memory / vector_store / long_term_ctx / reflection）
- `observability/`（traces / usage / performance / structured_logging / diagnostics / startup_diagnostics）
- `platform/admin_cli/`（7 命令模块）
- 8 个 `*_admin_api.py` + 9 个 `*_store.py` + `db.py` + `static/admin.html`
- `agent_templates.py`、`alerting.py`、`monitoring_store.py`、`connector_config_store.py`
- `governance/` 包（治理逻辑与张洋等价，直接用 main 的包结构）

### 阶段 2 — 运行时模块迁入（中风险）
张洋的独立模块作为新文件迁入，**统一适配 main 规范**：
- 移入文件：`termination` / `budget` / `layered budget` / `loop_detector` / `cancellation` / `error_classifier` / `message_hygiene` / `sub_agent_lifecycle` / `provider_health` / `tool_guardrails` / `tool_result_truncation` / `connectors` / `plugin_loader` / `skill_audit` / `multimodal` / `vision_client` / `image_gen_client` / `sandbox_*`（7 文件）/ `mcp_client` / `context_mgr`（替换 main 版）/ `skill_registry`（替换 main 版）。
- **import 路径全仓改写**（扁平 → 包路径）：
  | 概念 | 张洋（扁平） | main（包，集成目标） |
  |---|---|---|
  | agent_policy | `fleetent.agent_policy` | `fleetent.governance.agent_policy` |
  | permission_gate | `fleetent.permission_gate` | `fleetent.governance.permission_gate` |
  | sandbox | `fleetent.sandbox_client` | 决定保留扁平或迁 `integrations.sandbox`（见注） |
  | mcp client | `fleetent.mcp_client` | 同上 |
  | trace 日志 | `fleetent.eval_logger` | `fleetent.observability.traces` / `usage` |
- **trace 接线改造**：张洋大量调用 `eval_logger.log_*`（压缩追溯 `log_compression`、sandbox `log_sandbox_exec`、工具脱敏等）。main 已用 SQLite `observability.traces` 取代 JSONL `eval_logger`。需把这些调用点改指 `observability.traces`，并核对函数签名；签名不一致处补适配。
- **sandbox / mcp 归属**：张洋是功能超集，直接用张洋实现。但 main 把它们放在 `integrations/` 包下。建议沿用 main 包路径把张洋实现迁入 `integrations/sandbox/`、`integrations/mcp/`（符合 main 规范），而非保留扁平。回收 main MCP `register_all` 里的 `startup_diagnostics` 上报钩子。
- **skill 引擎 ↔ 管理面适配层**：用张洋的 `skill_registry` 作引擎，移植 main 的 `skill_admin_{store,api}` 作管理面。写适配层：main 的 `agent_skills.enabled` / `global_enabled` 喂进张洋 `match()` 的 `disabled_skills` 入参；桥接 `engine_audit`/`engine_reload`/`engine_list_skills`。明确禁用语义优先级（张洋四级 + main 的 global/per-agent）。

### 阶段 3 — 核心文件三方合并（高风险，最费工）
- **`tool_registry.py`（最高风险，第一件做）**：main 支持 async 工具（dispatch 返回 `str | Coroutine`），张洋是同步 `str` 签名 + 出带参数注入（cancel_token/tool_context/client）。需合并出：既支持 async 工具、又保留张洋的 timeout/connector/schema-visibility-filter 钩子的 dispatch。`set_schema_visibility_filter` 是 MCP4 降级的依赖，必须保留。
- **`agent_loop.py`**：以**张洋的循环结构为基底**（终止检查点 + 三阶段并行派发 `_plan_run_slots`/`_execute_pending`/`_backfill_slots` + budget + sanitize + anti-flap 压缩 + 多模态路由），把 main 的 `_record_*` trace 埋点 + `build_context`（长期上下文注入）+ permission 审批逐个织回。3 处硬冲突：`_call_with_fallback`、工具派发段、`run()` 签名。逐事件移植 trace，**不要反向**。
- **`config.py` / `settings.yaml`**：保留 main 的 yaml-first + 嵌套 BaseModel 框架，把张洋的扁平调参字段（sandbox / compression `tmax_ratio`+`tretained_ratio` / budget / loop-detect / provider_health 阈值）**重建为嵌套 section**。注意张洋的旧 `compress_threshold` 单值已被双阈值取代，迁移时同步所有 `.env`/`settings.yaml`。
- **`server.py`**：合并两边 lifespan —— main 的 admin/console router 挂载 + 张洋的 sandbox 启动钩子（`cleanup_orphans` 启动、`sweep_idle` 周期、enablement 探测）+ plugin/webhook 运行时。
- **`cron_scheduler.py` / `schedule_store.py` / `session_mgr.py`**：统一走 main 的 `db.py` 边界（named params、`transaction()`），把张洋的 TTL/磁盘配额/进程内周期维护（session_mgr +308 行）和 cron 会话绑定（S3）逻辑**改写为经 db.py 的实现**。

### 阶段 4 — 数据库迁移链（硬门槛，不解决跑不起来）
两边 `002~004` 用了**相同 revision id 但不同含义**（main `002_add_scheduled_tasks` vs 张洋 `002_add_agent_features`，都 `down_revision="001"`）。main 已到 `025`，张洋只到 `004`。Alembic 线性历史撞车。
- 给张洋的迁移**重新分配 revision id**，接到 main `025` 之后（`026`/`027`/…），修正 `down_revision` 串成单链。
- 张洋的新表（`budget usage` / `sub_agent_runs` / `session_anti_flap` / 压缩相关 / `agent_skills` 等）从裸 `CREATE TABLE IF NOT EXISTS` **收编进 Alembic 声明**（符合 main 规范）。

### 阶段 5 — 测试归位（机械但量大）
- 张洋的 ~80 个平铺 `tests/test_*.py` 归位到 main 的 `tests/{unit,integration,e2e,evaluation}/` 分层目录（main ~130+ 文件）。
- 两个 `conftest.py` fixture 合并（main 的 `isolated_schedule_db` + 张洋的 `_reset_provider_health_cache` autouse，无语义冲突）。
- `test_eval_logger.py` 随 eval_logger 弃用而改写/废弃（main 用 `test_trace_events.py`）。

### 阶段 6 — 文档与 OpenSpec（取并集 + 人工裁决）
- `openspec/changes`、`openspec/specs`、archive 两边基本正交，**取并集**即可。
- `docs/capabilities` 三个冲突文件（`sandbox.md` / `skill.md` / `tools.md`）：统一为「Docker 路线 + main 包路径归属」叙事 —— main 文档里的 microsandbox 迁移段落删除（张洋已论证 EC2 不支持 KVM 嵌套虚拟化，确定走 Docker）。
- `CLAUDE.md`：以 main 版为准，补回张洋方向特有但仍适用的 Gotchas。

---

## 4. 风险登记（按优先级）

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| 1 | `tool_registry` async dispatch 语义冲突（str vs Coroutine） | 高 | 集成第一件解决；确保 MCP/run_code 等 async 工具在张洋路径不被当同步 str |
| 2 | `agent_loop` trace 埋点 ↔ 控制流手工三方合并 | 高 | 以张洋循环为基底逐事件织回 trace；最易出错 |
| 3 | Alembic revision id 撞车 | 高（硬门槛） | 张洋迁移重排接 main 025 后 |
| 4 | `config.py` yaml-first ↔ 扁平字段不可行级 merge | 中高 | 张洋调参重建为嵌套 section |
| 5 | `eval_logger` → `observability.traces` 全量改接线 + 签名核对 | 中 | 逐调用点改，签名不符补适配 |
| 6 | import 路径全仓改写（扁平 → 包） | 中 | 全局 grep 替换，CI 兜底 |
| 7 | 新表收编 Alembic（两套 schema 管理打架） | 中 | budget usage/sub_agent_runs/session_anti_flap 等纳入迁移 |
| 8 | Grace Call 多发的 LLM 调用被 trace 误记为正常 turn | 低中 | 移植时标记区分 |
| 9 | skill 引擎 ↔ 管理面接口契约不匹配 | 中 | 写适配层翻译 store 状态为引擎入参 |
| 10 | 测试归位量大（~80 文件改路径） | 低（机械） | 批量移动 + 路径修正 |

**无任何子系统出现「双方各有不可调和的独立逻辑」** —— 治理是等价、skill 是引擎(张)+管理(main)互补、压缩/sandbox/MCP/工具是张洋单向超集、智能层/可观测/后台是 main 独有。集成方向清晰，主要工作量在 import 改写、agent_loop 三方合并、迁移链重排、config 重建。

---

## 5. 建议的落地顺序（执行清单）

1. [ ] 在 `feature/zhangyang` 基础上，先把 main 合进来（接受其包结构为骨架），**保留两套并存的冲突态**作为起点
2. [ ] 阶段 1：删除 merge 后重复的扁平治理文件，统一用 `governance/` 包；接纳 intelligence/observability/后台 全部
3. [ ] 阶段 3-1：先解 `tool_registry` async 语义
4. [ ] 阶段 2：迁入张洋运行时模块到对应包，改 import + trace 接线
5. [ ] 阶段 3-2：`agent_loop` 三方合并（张洋循环基底 + main trace 织回）
6. [ ] 阶段 3-3：`config` / `server` / store 层改写到 db.py 规范
7. [ ] 阶段 4：Alembic revision 重排 + 新表收编
8. [ ] 阶段 5：测试归位 + conftest 合并
9. [ ] 阶段 6：docs/openspec 并集 + CLAUDE.md 统一
10. [ ] `uv run pytest` 全绿（或不引入相对基线的新失败）→ 推 `origin/feature/zhangyang` → 手动开 PR

---

*本方案由两套架构的只读对比分析得出，未对任何源码做改动。执行前建议与 raw34 对齐 agent_loop / tool_registry 两处核心合并的预期行为。*
