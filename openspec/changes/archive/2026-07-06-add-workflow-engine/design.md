# Design: add-workflow-engine

## Context

fleetent 现有"多步骤"能力全部是隐式的：LLM 在对话中临场决定工具调用（不可复现），`sub_agent` 只支持一层并行 fan-out，`invoke_agent` 只支持单跳委派，步骤间只能传字符串，无编排级持久化。

方案定型前做了两组调研（2026-07-06 会话终审）：

- **Eino Workflow**（cloudwego/eino，源码级分析）：核心可借鉴——①控制流/数据流分离（`controlEdges` 与 `dataEdges` 两套完全独立的结构）；②声明式字段级映射（节点自洽，上下游靠显式字段接线）；③ AllPredecessor 就绪语义 + Kahn 拓扑排序禁环；④静态值注入；⑤定义期校验。不可照搬——它是 in-memory 一次 Invoke 无持久化；节点是 LLM 组件级（与 fleetent 已有 agent 抽象重叠）；Go 反射字段映射机器在 Python 中天然退化为 `getattr`/dict 访问。
- **Claude Code Workflow**：验证了 **agent 级节点粒度**可行（一个节点=一个完整 agent 跑一个 prompt）；resume 语义（已完成节点输出即缓存前缀）；`schema` 强制结构化输出的价值。其命令式 JS 编排被否决——fleetent 是企业 on-prem 强治理平台，流程必须是**可落库、可 diff、可审计的数据**，不能是代码。

硬约束（AGENTS.md）：禁 AI 框架、禁 ORM、禁云托管服务；agent 运行时严禁 import `fleetent.platform.*`；agent 侧表走 embedded forward-only 迁移；治理 fail-closed（critical 硬拒、无法降级）；异步资源 owner-task 契约。

## Goals / Non-Goals

**Goals:**

- 声明式 `workflow.yaml`（DAG）：可 git 版本化、可 review、可审计、load 期校验。
- 持久化执行：kill 进程重启后断点续跑；幂等 claim 保证 at-most-once 执行。
- step 全部复用现有原语（dispatch / loop.run / outbound），不新建执行机器。
- 治理不旁路：声明式路径与对话路径过同一道风险门。
- 无 platform、platform 表不存在的环境下全功能可用。

**Non-Goals（M1 明确不做）:**

- 循环（DAG-only，同 Eino）；条件分支（`when`/`on_reject` 留 M3）。
- 显式 `approval` step 与审批挂起-恢复接通（M2：风险触发审批 + approve-always；M3：显式 gate + 定义级预授权）。
- 跨进程多 agent 编排（node endpoint 路由，M3）。
- 流式字段映射；平台管理面/UI；cron 直触发 workflow。

## Decisions

### D1 落位：agent 侧新包 `fleetent.workflow`，引擎随 agent 进程

类比 `cron_scheduler`：引擎在 agent 进程内（`agent_app` lifespan 启停，owner-task 契约），状态落 per-agent `agent_state.db`。备选"platform 侧编排器"被否决：违反 agent→platform 单向依赖契约，且丧失"无 platform 可用"基线。

### D2 step 粒度：agent/tool 动作级，三种类型

`tool`（`tools.registry.dispatch` + `ToolContext` 带外注入）、`agent`（`loop.run(is_sub_agent=True)` + `snapshot.load_active`，即 `invoke_agent` 语义；`agent` 字段省略=宿主 agent 自身）、`notify`（outbound 主动触达，投递解析复用 cron 模式）。备选"LLM 组件级节点"（Eino 粒度）被否决：与 loop 内部抽象重叠、改动巨大；Claude Code 已验证 agent 级粒度可行。

### D3 数据流：Eino 双图分离的 Python 简化版

- `depends_on` = 纯控制边（Eino `AddDependency`）；`${steps.X.output.*}` 数据引用 = 数据边并**自动隐含控制依赖**。M1 无分支，二者运行时语义等价，Eino 三种边坍缩为两个用户概念。
- 字段映射 = 手写点路径解析器（dict key / list index），约 50 行；**不引第三方 JSONPath 库**。命名根仅 `${inputs.*}` 与 `${steps.<id>.output.*}`，无歧义。
- 字面量即静态值注入（Eino `SetStaticValue` 的退化形式，无需专门机制）。
- load 期校验 = Eino `Compile()` 的对应物：Kahn 禁环、引用存在性、tool args 对照工具 JSON schema 查必填与字面量类型。类型对齐查不到的推迟运行期；运行期路径解析失败 → step 失败（fail-closed）。

### D4 引擎：持久化 + 双路驱动 + 幂等 claim

Eino 的 DAG channel 就绪判定（AllPredecessor）照搬，但状态在 SQLite 而非内存：

- **热路径**：step 终态落库后，同进程内立即计算新就绪 step 并 claim 执行（避免纯轮询的每步 tick 延迟）。
- **冷路径**：周期 sweep 兜底——进程重启恢复、过期 claim 回收（`claimed_at` 超窗则 attempt+1 重领）。
- 两路都经**条件 UPDATE 幂等 claim**（`schedule_store.claim_next_run` 同款模式），并发安全 at-most-once。
- 并发上限：信号量默认 4（cron `_DEFAULT_MAX_PARALLEL` 先例）。

备选"纯 tick 轮询"（cron 原样）被否决：多步链路每步吃一个 tick 周期，延迟不可接受；"纯内存事件驱动"被否决：重启即丢。

### D5 治理 fail-closed（安全关键，不可协商）

workflow 不得成为审批门旁路：`tool` step 执行前照走 `evaluate_risk_level → resolve_action_mode`；M1 解析为非 `DIRECT`（APPROVAL/SANDBOX/REJECT）一律 step 失败并报明确错误（提示"包进 agent step 或等 M2 审批接通"）。`agent` step 内部工具由 loop 现有门控自动覆盖，`run()` 返回 `awaiting_approval` 时 M1 同样按 step 失败处理（M2 接通挂起-恢复，需持久化 messages 快照）。critical → REJECT 硬编码，任何声明都无法降级。

### D6 冻结快照：可复现、可审计

run 启动时把定义 JSON 冻结进 `workflow_runs.definition_json`（`AgentSnapshot` 思路），principal 一并冻结（cron `_resolve_cron_principal` 先例）。在跑的 run 不受定义文件编辑影响；事后可精确还原"哪个流程版本、以谁的身份执行了什么"。

### D7 失败/取消/超时语义

step 失败 → 后继级联 `skipped`（Eino cascade-skip）→ run `failed`；可选 per-step `retry.max_attempts`（默认 0，副作用工具自担幂等）与 `timeout_seconds`（默认 300，`SUB_AGENT_TIMEOUT_SECONDS` 先例）；取消经 CancelToken 父子级联（`runtime/cancellation.py` 复用）。run 终态按 origin/deliver 投递通知发起人。

### D8 触发面（M1 仅二）

内置工具 `run_workflow(name, inputs)` / `workflow_status(run_id)`（对话内 LLM 可发起，principal 取自 ToolContext）；CLI `fleetent workflow run/list`（dev/验证）。cron 直触发、HTTP、平台面后置。

### 数据模型

```sql
CREATE TABLE workflow_runs (
  id TEXT PRIMARY KEY,                -- wfr-<hex>
  workflow_name TEXT NOT NULL,
  definition_json TEXT NOT NULL,      -- 冻结快照
  status TEXT NOT NULL,               -- pending/running/succeeded/failed/cancelled
  inputs_json TEXT, principal_json TEXT,
  origin_json TEXT, deliver_json TEXT,
  error TEXT, created_at TEXT, started_at TEXT, ended_at TEXT
);
CREATE TABLE workflow_step_runs (
  run_id TEXT NOT NULL, step_id TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL,               -- pending/running/succeeded/failed/skipped/cancelled
  output_json TEXT, error TEXT,
  claimed_at TEXT,                    -- 幂等 claim + 过期回收
  started_at TEXT, ended_at TEXT,
  PRIMARY KEY (run_id, step_id, attempt)
);
```

经 `runtime/agent_state_migrations.py` `MIGRATIONS` append（版本闸前向迁移）；SQL 全 named parameters；retention 裁剪照 `scheduled_task_runs.record_run` 模式。M1 状态机不含 `waiting_approval`（M2 加，届时 append 迁移补 `approval_id` 列）。

### 模块布局

```
src/fleetent/workflow/
  __init__.py     # public API: load_definition / start_run / get_run / list_runs / engine 启停
  definition.py   # yaml 解析 + load 期校验（禁环/引用/schema 对照）
  mapping.py      # ${} 点路径解析 + 输入渲染
  store.py        # workflow_runs / workflow_step_runs SQL（set_state_db 注入）
  engine.py       # 双路驱动 + claim + 信号量 + 终态投递（owner-task）
  steps.py        # tool/agent/notify 执行器 + 治理门控
```

接线：`agent_app._init_agent_db_schema` 处 `workflow.store.set_state_db(db)` 注入（`artifact_exchange` 同款，避免未接线台账休眠）；引擎在 agent_app lifespan 启停。工具注册加在 `tools/builtin_tools.py`；CLI 子命令挂现有 CLI 入口。

## Risks / Trade-offs

- [workflow 成为治理旁路] → D5 非 DIRECT 即失败；护栏：单测覆盖 APPROVAL/SANDBOX/REJECT 三模式全部拒绝；`workflow/` 纳入 module-dependency 护栏（禁 platform import）。
- [`output_schema` LLM 遵从度不稳] → 解析失败重试一次；仍失败落 `{text}`，下游字段映射解析不到路径即 step 失败（fail-closed，不静默给错数据）。
- [claim 过期误回收：step 仍在执行但被 sweep 判过期重领] → claim 窗口 = step `timeout_seconds` + 余量；attempt 递增留痕；条件 UPDATE 保证同一 attempt 不被双跑。
- [tool step 副作用与重试冲突] → 默认 `max_attempts=0`（不重试），重试显式 opt-in，文档注明幂等自担。
- [output_json 过大膨胀 agent_state.db] → 单 step 输出设上限（超限截断并标记）；runs 表 retention 裁剪。
- [sweep 与热路径竞态双跑] → 全部经同一条件 UPDATE claim，输了的一方放弃；集成测试覆盖并发 claim。
- [agent step 无独立 session，长对话不可续] → M1 接受（输出落 step_runs 即够用）；M2 审批接通时引入 messages 快照。

## Migration Plan

- 仅新增两表：`agent_state_migrations.MIGRATIONS` append 一个版本，migrate-on-open 自动生效；无既有表变更、无数据回填、无 shim。
- 功能开关：agent.yaml `workflow.enabled`（默认关闭或按需，实现时定）；关闭时引擎不启动、工具不可用，表存在但休眠。
- 回滚：forward-only 不回滚 schema；关闭 `workflow.enabled` 即完全停用，空表无副作用。
- 分支策略：全部开发在 `.worktrees/add-workflow-engine`（分支 `feat/add-workflow-engine`），**暂不合入 main**（用户明确要求，2026-07-06）。

## Open Questions

- 无阻塞项。两个实现期再定的小口子：①`workflow.enabled` 默认值（建议默认开，工具可用性低风险）；②单 step 输出截断上限数值（建议对齐现有 tool-result-truncation 常量）。
