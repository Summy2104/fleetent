# Proposal: add-workflow-engine

## Why

fleetent 目前没有编排一等概念：多步骤任务只能靠 LLM 在对话中临场决定工具调用（不可复现、无流程级重试/恢复），或靠 `sub_agent`（仅一层并行 fan-out）/ `invoke_agent`（单跳委派）拼接，步骤间只能传字符串。企业场景（周报流水线、数据处理链、定时多步任务）需要**可声明、可审计、可断点续跑**的确定性工作流：流程定义是数据（可 diff、可 review、可落库），执行状态持久化（进程重启后从断点接续），同时不破坏现有治理门控。

## What Changes

- 新增 agent 侧顶层包 `src/fleetent/workflow/`：声明式 workflow 编排引擎（M1 核心）。
- 新增 `workflow.yaml` 声明格式：DAG（无环）步骤定义，load 期校验（拓扑禁环、引用存在性、tool args 对照工具 schema 查必填与类型）、`${...}` 点路径字段映射（`${inputs.*}` / `${steps.<id>.output.*}`）、字面量即静态值注入。
- 新增三种 step 类型，全部复用现有原语：`tool`（`tools.registry.dispatch`）、`agent`（`loop.run(is_sub_agent=True)` + `snapshot.load_active`，可选 `output_schema` 强制 JSON 结构化输出）、`notify`（outbound 主动触达）。
- 新增持久化执行引擎：`workflow_runs` + `workflow_step_runs` 两表落 per-agent `agent_state.db`（embedded forward-only 迁移 append）；热路径步进直推 + 冷路径周期 sweep 兜底；条件 UPDATE 幂等 claim（at-most-once）；信号量并发上限（默认 4）；kill 进程重启后断点续跑（已成功 step 输出即缓存前缀）。
- 治理 fail-closed（不旁路契约）：`tool` step 执行前照走 `evaluate_risk_level → resolve_action_mode`，解析为非 `DIRECT`（APPROVAL/SANDBOX/REJECT）即 step 失败并报明确错误；`agent` step 内部撞审批（`awaiting_approval`）同样按失败处理。审批挂起-恢复接通留 M2。
- run 启动时冻结 `definition_json` 与 principal（可复现、可审计，在跑的 run 不受定义文件编辑影响）。
- run 到达终态（succeeded/failed/cancelled）按 origin/deliver 投递通知发起人（复用 cron 投递解析模式）。
- 触发面（M1 仅两个）：内置工具 `run_workflow(name, inputs)` / `workflow_status(run_id)`；CLI `fleetent workflow run/list`。
- 明确不做（M1）：循环、条件分支、显式 approval step、跨进程多 agent 编排、流式字段映射、平台管理面、cron 直触发。

## Capabilities

### New Capabilities

- `workflow-definition`: workflow.yaml 声明格式与 load 期校验——步骤/依赖/字段映射语法、DAG 禁环（Kahn）、引用存在性、tool schema 对照校验、定义目录解析（`FLEETENT_WORKFLOWS_DIR`，默认 `<config_dir>/workflows`）。
- `workflow-engine`: 持久化执行引擎——run/step 状态机、就绪判定（全部控制前驱成功 + 数据引用可解析）、幂等 claim、双路驱动（步进直推 + sweep 兜底）、级联 skip、断点续跑、并发上限、超时与取消（CancelToken）、定义/principal 冻结快照、终态投递、运行历史 retention。
- `workflow-steps`: 三种 step 执行器（tool/agent/notify）——输入渲染与输出规约（tool 输出尝试 JSON 解析、agent 可选 output_schema 强制结构化）、治理 fail-closed 门控（非 DIRECT 即失败、agent step 内 awaiting_approval 即失败）。
- `workflow-triggers`: 触发面——`run_workflow` / `workflow_status` 内置工具（对话内 LLM 可发起）、CLI `fleetent workflow run/list`（dev/验证）。

### Modified Capabilities

（无——不改变任何现有 capability 的 spec 级行为：embedded 迁移机制、工具注册机制、治理门控语义均按现状复用，仅新增消费方。）

## Impact

- **owning package**: `fleetent.workflow`（新增：`definition.py` / `mapping.py` / `store.py` / `engine.py` / `steps.py`）。
- **public API surface**: `load_definition`、`start_run`、`get_run` / `list_runs`、engine 启停；内置工具注册加在 `tools/builtin_tools.py`；CLI 子命令挂在现有 CLI 入口。
- **owned tables**: `workflow_runs`、`workflow_step_runs`（per-agent `agent_state.db`，经 `runtime/agent_state_migrations.py` 的 `MIGRATIONS` append，版本闸前向迁移）。
- **config namespace**: `workflow.*`（agent.yaml 可选：`enabled` / `max_parallel`）；env `FLEETENT_WORKFLOWS_DIR`（经 `paths.py` 统一解析）。
- **cross-module dependencies**: `tools`（dispatch / get_schemas / ToolContext）、`runtime`（loop 公开入口、cancellation、snapshot、agent_state_migrations、agent_app 接线）、`governance`（action_gate 只读判定）、`structured_logging`。**严禁 import `fleetent.platform.*`**（护栏测试保障）；无新第三方依赖（无 AI 框架、无 ORM、无 JSONPath 库）。
- **migration / shim plan**: 仅新增表（append 迁移），无表变更、无 shim；`agent_app._init_agent_db_schema` 处 `set_state_db` 注入接线（`artifact_exchange` 同款模式，避免未接线台账休眠）。
- **验证基线**: 无 platform、platform 表不存在的环境下 `fleetent agent run` + workflow 全功能可用；kill 进程重启后 run 断点续跑。
- **分支策略**: 开发在独立功能分支（`.worktrees/add-workflow-engine` + `feat/add-workflow-engine`），**暂不合入 main**。
