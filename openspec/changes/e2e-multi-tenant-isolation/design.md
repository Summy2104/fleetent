## Context

地基 harness（`e2e-managed-stack-coverage`）已落地：`tests/e2e/conftest.py::managed_stack` 起单 tenant 单 agent 的真实多进程栈，`tests/e2e/_llm_stub.py` 提供确定性 LLM。本 change 在其上加多租户隔离覆盖。

per-tenant 物理布局由 `tenant_router.SQLiteTenantBackend` 落盘（已核实 `src/fleetent/tenant_router.py`）：
- tenant 级：`<data_dir>/<tenant>/kb.db`、`shared_memory.db`、`kb_vectors.db`、`shared_memory_vectors.db`
- agent 级：`<data_dir>/<tenant>/<agent_id>/agent_state.db`、`agent_vectors.db`

`agent_store.create_agent(..., tenant_id=...)` 已支持指定 tenant（默认 `"default"`）。

## Goals / Non-Goals

**Goals**：端到端证明两 tenant 数据物理隔离 + 跨租户读路径零串数据；fixture 以新增方式提供，零 src 改动。

**Non-Goals**：不测网络后端（Postgres/Qdrant，仍 BLOCKED）；不测 tenant 创建/计费等管理面；不重构核心 `managed_stack`。

## ⚠️ 关键可行性风险（apply 第一步必须先验）

**managed 运行时下，agent 的 KB/记忆/state 数据到底落在哪？** 需先确认：placed agent 在 node 下运行时，其 per-tenant 数据是否真的经 `tenant_router` 落到 `<data_dir>/<tenant>/<agent_id>/`，还是落到 agent home（`<home>/agents/<name>`）。**这决定隔离断言的观测点**：
- 若经 tenant_router 落 `<data_dir>/<tenant>/...` → 直接断言文件路径分离 + 跨租户检索。
- 若 agent 数据落 agent home（与 tenant 无关）→ 隔离边界实际在 tenant 级共享库（KB/shared_memory），断言点改为 tenant 级 KB/记忆，agent-state 隔离改由 per-agent home 体现。

apply 的 task 1 必须先用最小探针定位真实落盘点，再据此定断言；不得假设。

## Decisions

- **新增 `managed_stack_two_tenants`，不改 `managed_stack`**：放 `tests/e2e/_tenant_helpers.py`（本 change 独占文件），并行波 D2/D3 不碰 → 零 `conftest.py` 合并冲突。fixture 内复用既有起栈步骤，起一个 node、注册两个不同 `tenant_id` 的 agent 并各自 pin 到该 node。
- **写入与观测走真实读写路径**：写用 agent 可达的真实写入（KB ingest 或经对话产生记忆）；跨租户验证走 tenant-b 的真实检索/读取路径返回零命中，而非仅比对文件——文件级断言作为补充证据。
- **单 node 承两 tenant 足够**：隔离边界是数据层（tenant_router 落盘），不是进程；无需起两个 node。

## Risks / Trade-offs

- 落盘点不确定（见上）→ 用 task 1 探针消解。
- 起两 agent 增加栈启动时间 → e2e 在 slow lane，可接受。
