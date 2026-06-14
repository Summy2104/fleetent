# unify-agent-state-id

> **Provisional**：agent 身份模型迁移**阶段 3**（依据 `docs/architecture/agent-identity-model.md`）。排在阶段 2（`unify-agent-binding-id`）之后；alembic 版本号/代码行号不在此 pin，apply 时以实际为准。阶段 2 落地后回校。

## Why

`agent_admin_state`（agent 控制台生命周期态：status / provenance / drift）以 **`agent_name` 为主键**，`session_meta`（playground/chat 治理元数据）带 **`agent_name` 列**——二者是平台侧"除 agents 表外用 agent name 标 agent"的偏离者，违反身份模型 R1（平台侧除 agents 表外全用 `agent_id` INTEGER）。后果：与 `agents`（按 id）键空间不一致、无 FK、agent 删除留孤儿（admin_state/session_meta 行）。

## What Changes

- **`agent_admin_state`**：主键 `agent_name` → **`agent_id`（INTEGER）+ FK→agents.id ON DELETE CASCADE**（Alembic 新迁移，append after head、不硬编码）。数据迁移：经 `agents` 解析 name→id 重建。
- **`session_meta.agent_name`** → **`agent_id`（INTEGER）+ FK→agents.id ON DELETE CASCADE**（同迁移或同阶段）。`user_id` 列**不动**（用户身份，不在本范围）。数据迁移：name→id 解析。
- **代码**：`agent_admin_store` / `session_admin_store` 的键/列改 id；调用方（`server.py` 的 agent status 查询、`agent_management_console` API、`chat_management` API、`askit_console` apply API）改为先解析 name→id 再调 store；HTTP 路由对外仍按 `{name}` 寻址，内部解析。
- **文档**：`data-model.md` §3.2 这两表描述（admin_state 键、session_meta.agent_name）改为 agent_id + FK；引用 identity-model 阶段 3。

不碰 agent_kbs/agent_skills（阶段 2）、其余绑定表 FK（阶段 4）、agent 侧/traces 与翻译边界（阶段 5）。

## Capabilities

### Modified Capabilities

- `agent-provenance`: `agent_admin_state` 以 `agents.id`（INTEGER）为键 + FK→agents.id ON DELETE CASCADE（status/provenance/drift 行为不变，仅键规整 + 孤儿保护）
- `chat-playground`: `session_meta` 的 agent 引用列为 `agent_id`（INTEGER）+ FK→agents.id ON DELETE CASCADE（playground/治理行为不变；`user_id` 不变）

## Impact

- **owning package**：`platform`（Alembic + `agent_management_console`/`chat_management`/`askit_console` stores+APIs）、顶层 `server.py`（status 查询解析）
- **public API surface**：admin/chat store 的 agent 键参数 int 化（内部）；HTTP 路由按 `{name}` 寻址不变（内部解析 name→id）
- **owned tables**：`agent_admin_state`（PK 改 id + FK）、`session_meta`（agent_name→agent_id + FK）
- **cross-module dependencies**：全平台侧；不碰 agent 零 platform import
- **migration / shim plan**：Alembic 迁移（name→id 解析重建 + 加 FK）；forward-only；带升级路径测试；无 shim
- **相邻切片**：依赖阶段 2 先落地（同走 Alembic 单链，串行）；apply 前 pull 确认无并行 change 碰这两表
