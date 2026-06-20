## Why

共享记忆是 **agent 侧数据**(per-tenant 共享记忆库),且有 **agent 侧治理生命周期**:reflection 提炼建议 → 审批门(`reflection_gate`)→ `apply_shared_memory_proposal` 落地。但当前有两个**平台侧手动入口**绕过这套治理直写:
- `fleetent admin memory shared create/update/archive` CLI(`admin_cli/shared_memory.py`)
- `/admin/memory/shared` 直写 HTTP API(`shared_memory_management/`,complete-admin-api-coverage 加的)

两者都调 `create_shared_memory(source="manual")`,无提议、无审批,且放错了层——把 agent 侧数据的编辑塞进了平台控制面。审查确认**无任何 admin UI 消费该 HTTP API**(仅 integration 测试 + server wiring)。本 change 撤掉这两个平台侧入口,让共享记忆回到"纯 agent 侧数据 + agent 侧治理"。

## What Changes

- **删 CLI**:从 `admin_cli/main.py` 的 `_COMMAND_MODULES` 移除 `shared_memory`,删 `admin_cli/shared_memory.py`。
- **删 HTTP API**:删整个 `platform/shared_memory_management/` 包,移除 `server.py` 第 48 行 import 与第 237 行 `include_router`。
- **删对应测试**:`tests/integration/test_shared_memory_admin_api.py`、`tests/integration/test_shared_memory_admin_cli.py`。
- **更新文档与文档测试**:roadmap 文档移除 `memory shared` CLI 引用;`test_deployment_docs.py::test_intelligence_roadmap_manual_uses_current_shared_memory_cli` 相应调整(不再断言 CLI 存在)。
- **spec 回收/强化**:`shared-memory-admin-api` capability 整个下线;强化 `manual-maintenance-entrypoints` 的「Shared Memory edits use proposal lifecycle」——从"仅维护面"扩到"任何平台面(CLI/HTTP)均不提供直写",共享记忆改动一律走 agent 侧 proposal/apply 生命周期。

**保留不动**:`memory.shared` 数据层、reflection proposal/apply 生命周期(agent 侧、本就是对的)、`test_coverage_memory_and_platform_logic.py`(测数据层)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `shared-memory-admin-api`:REMOVE 整个 capability(平台侧直写 HTTP API 下线)。
- `manual-maintenance-entrypoints`:MODIFY「Shared Memory edits use proposal lifecycle」——明确任何平台面(CLI/HTTP)都不提供共享记忆直写,改动走 agent 侧 proposal/apply。

## Impact

**owning package**:删 `platform/shared_memory_management/`、`admin_cli/shared_memory.py`;改 `admin_cli/main.py`、`server.py`

**public API surface(移除)**:`fleetent admin memory shared *` CLI;`GET/POST/PATCH /admin/memory/shared`、`POST /admin/memory/shared/{id}/archive` HTTP

**owned tables**:无 schema 变更(`shared_memory_items` 表与数据层不动,只撤平台侧编辑入口)

**config namespace**:无　**migration**:无

**cross-module dependencies**:移除后 platform 不再 import `fleetent.memory` 的 shared-memory 写函数(`server.py`/admin_cli 侧);数据层与 reflection 生命周期不受影响

**回退说明**:本 change 回退 complete-admin-api-coverage 中的共享记忆 HTTP API 部分(及 align 对其 201 的收紧)——当时未察觉 agent 侧已有 proposal/apply 治理,加错了层。

**Out of scope / 后续**:"agent 侧手动编辑共享记忆"(admin/用户主动手工写一条)是净新增能力,不在本 change;撤入口后手动改动的现存路径是 reflection 提议→审批。若确需主动手动编辑,另起 agent 侧 change。
