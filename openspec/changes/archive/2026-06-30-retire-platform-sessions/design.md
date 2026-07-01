## Context

会话治理（sessions）功能横跨前端 SPA、platform 后端、管理库三层，是一个接线完整但生产不可用的半成品（详见 proposal.md）。移除涉及：整包删除、`server.py` 解线、Alembic drop 表、前端目录/路由/i18n 清理、多个 guardrail 与单元测试调整。本 change 是纯减法重构，不新增任何外部行为，但跨多个模块且含 schema 变更与边界护栏调整，故需 design 固化"删什么/留什么"的边界判断与删除顺序。

当前事实（调查已确认）：

- 后端 `platform/chat_management/` 共 4 文件：`chat_admin_api.py`（9 endpoint + 占位 seam）、`session_admin_store.py`（管理库 `session_meta` 存储）、`transcript_export.py`（纯渲染，仅自身测试引用）、`__init__.py`。
- `chat_admin_api` 的唯一生产消费方是 `server.py`（`:41` import、`:234-244` seam 注入、`:282` include_router）。
- `session_admin_store` 的唯一消费方是 `chat_admin_api`；其 `list_unpinned_playground` / `delete_meta` 是零消费死方法。
- 管理库 `session_meta` 表（Alembic 022 建，054-059 增删列，当前 head 113）唯一读写者是 `session_admin_store`，`upsert_meta` 生产零调用，表恒空。
- `_CONTROL_FACE_PREFIXES`（`test_module_dependency_guardrails.py:368`）列了 `fleetent.platform.chat_management`。

## Goals / Non-Goals

**Goals:**

- 删干净 sessions 治理 feature 的前端、后端、管理库三层，使 `make test-pr` + `make test-integration-ci` 全绿。
- drop 恒空的 `session_meta` 表，不留孤儿表。
- 保持 agent 验证基线：无 platform、platform DB 表不存在时 `fleetent agent run` 仍可对话（本 change 只删 platform 侧，agent 侧 session 模块零触碰，天然满足）。

**Non-Goals:**

- 不触碰 `GET /admin/stats/sessions/{session_id}/trace`（`agent_statistics`，独立 capability，被 `features/stats/` 消费）。
- 不触碰 agent 侧 `session/` 模块（`manager.py` / `index.py`、per-agent `agent_state.db` 的 `sessions` 表、`session-metadata-index` capability）——core runtime。
- 不重构、不"顺手"改 sessions 之外的任何 platform 代码。

## Decisions

### D1：整包删除 `platform/chat_management/`，而非保留瘦身

`transcript_export.py` 虽是无害纯函数，但只被自身测试引用、未接任何 endpoint，是 sessions feature 的孤儿。三个业务文件 + `__init__.py` 一并删，整包退场，`_CONTROL_FACE_PREFIXES` 同步去掉该前缀项。
- 备选（否决）：保留 `transcript_export` 作通用 markdown 渲染——无第二消费方，留着即新孤儿，违背减法初衷。

### D2：drop `session_meta` 表用新增 forward-only Alembic 迁移（114）

管理表由 Alembic 维护（双权威铁律）。新增迁移 `114_drop_session_meta.py`：`upgrade` drop index `idx_session_meta_origin` + drop table `session_meta`；`downgrade` 按 022 当前列形态重建（forward-only 仓库的 downgrade 仅为形式完整，不依赖其精确还原数据，因表恒空）。
- 备选（否决）：留表不删——零风险但留死表，与"删干净"目标背离；且 `session-metadata-index` spec 已明确管理库 `session_meta` 仅承担 platform 跨 agent 语义，治理退场后该语义消失。

### D3：`server.py` 解线一次性删除三处

`:41` import、`:234-244` 四个 seam 注入（`load_transcript` / `clear_session` / `inject` / `reset_session`）、`:282` `include_router(chat_admin_api.router)` 同批删除。`session_mgr`（`fleetent.session.manager`）本身保留——它服务于 web chat / runtime，seam 注入只是把它"借给" admin，删注入不影响其本职。

### D4：`manager.py` admin 专用方法的清理推迟到实现阶段逐个核查

`manager.py:697` 注释称 `inject_message` 为 admin console 而设。但 `clear` / `reset` 等可能被 runtime（如 `/new` 指令、resume）复用。实现某 task 时对每个候选方法 `grep -rn` 全仓确认无 admin 之外消费方才删；有疑即留。`manager.py` 是 agent 侧 core runtime，宁可留下无害死方法也不冒误删伤运行时的险。

### D5：删除顺序——先测试见红，后删实现

按 TDD Hard Gate：每个删除 task 先改/删对应测试断言（如 `test_server_lifespan_and_wiring` 去掉 sessions seam 断言后该断言不再存在 = 见绿基线），再删实现。对"删 endpoint"类，采用"先删测试文件 → 跑确认其它测试不依赖 → 删实现 → 跑全层无新增失败"。删除型 task 的红/绿语义：删测试后相关用例消失，删实现后剩余测试仍绿即达标。

## Risks / Trade-offs

- **[迁移撞号]** 多分支并行时 114 可能与他人迁移撞号 → 实现前 `ls migrations/versions/ | tail` 复核 head，合并期撞号则顺延重命名（参见 external-credential-vault 迁移撞号教训）。
- **[误删 manager 运行时方法]** `clear`/`reset` 若被 runtime 复用而被删 → D4 强制逐个全仓 grep，有疑即留；并以 agent 验证基线（无 platform 跑 `fleetent agent run`）兜底。
- **[guardrail 漏改导致 collect error]** `_CONTROL_FACE_PREFIXES` 删项、`test_platform_admin_api_unit` 去用例若漏改 → 整包删除后 import 失败会在 collect 阶段直接报错，跑 `make test-pr` 即暴露，低风险。
- **[残留 i18n/路由引用]** sessions 词条/路由漏删 → 前端 `routes.test.tsx` 断言与 tsc 编译会捕获；删后跑前端测试确认。
- **[漏网引用]** 其它代码隐式依赖 `/admin/sessions/*` → 已全仓 grep 确认前端是唯一消费方，无其它下游；实现收尾再 grep `admin/sessions`（排除 stats trace）兜底。

## Migration Plan

1. 后端：删 `chat_management/` 整包 → 改 `server.py` 解线 → 新增迁移 114 drop 表 → 改 guardrail/unit 测试。
2. 前端：删 `features/sessions/` → 改 `routes.tsx`/`nav.ts`/`routes.test.tsx` → 删 `i18n` 词条。
3. 验证：`make test-pr` + `make test-integration-ci` 全绿；前端测试绿；`fleetent agent run` 烟测对话正常。
4. 回滚：本 change 为单分支整体提交，回滚即 revert 分支；迁移 114 的 downgrade 可重建空 `session_meta` 表（无数据需恢复）。

## Open Questions

- 无。范围与边界已在调查阶段全部确认（trace 保留、agent 侧 session 保留、表恒空可删、整包无外部依赖）。
