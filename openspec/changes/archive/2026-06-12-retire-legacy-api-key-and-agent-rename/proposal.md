# retire-legacy-api-key-and-agent-rename

## Why

platform 侧实体关系审计（2026-06-12）确认两个"上线前清最便宜"的结构问题：① **API key 双轨制是活的**——`create_user` 至今给每个新用户往 `users.api_key` 列写**明文** key（user_store.py:77），认证走"先查 `api_keys`（哈希、带生命周期）、查不到 fallback 明文旧轨"双路径；明文凭证落库与新轨哈希设计自相矛盾，吊销级联对旧轨 key 存在死角；且 standalone agent 的整个 bearer 认证（`identity.LocalBearerAdapter`）就建在旧轨列上。② **agent 改名是半接线的炸弹**——`agent_store.rename_agent()` 与 `agent_admin_store.rename()` 存在，console 入口 `rename_agent_def` 是 `return None` 死桩；一旦接通，改名会让 `session_meta.agent_name` 历史行失联，**且 per-agent 物理数据目录以名字为键**（`agents/<name>/data/`），改名后 agent 解析到空目录、全部会话/记忆/审批/定时任务被孤儿（"失忆"）。两者都在"上线前不迁移数据"窗口内，现在清成本最低。

## What Changes

**A：API key 单轨化（哈希 `api_keys` 表为唯一真相源）**
- Alembic 新迁移：把存量 `users.api_key` 明文值哈希回填进 `api_keys` 表（scope `["*"]`、无过期、幂等、跳过 NULL），随后 drop `users.api_key` 列
- `user_store.create_user`：不再写旧轨列；建 key 直接落 `api_keys`（哈希入库，明文仅在创建时返回一次）；admin CLI 输出行为不变（打印一次明文）
- `user_store.authenticate`：删 legacy fallback 与 `_get_by_legacy_key`；resolver 未注入时改为**本地直查 `api_keys` 表哈希比对**（同库本地读，不 import platform）
- `identity.LocalBearerAdapter`：从 legacy 列查找改为经 user_store 的本地 `api_keys` 哈希查找（standalone bearer 行为不变：有效 key→Principal）
- 一次性工具 `platform.user_management.migrate_api_keys()` 使命完成（被 Alembic 回填取代），删除
- **BREAKING（内部）**：`User` dataclass 的 `api_key` 字段与 `users.api_key` 列移除；消费方全在本仓一次改净

**B：agent 名锁定为不可变标识（拆掉半接线的 rename）**
- 删除 `agent_store.rename_agent`、`agent_admin_store.rename` 与 console 死桩 `rename_agent_def`；改名诉求 = 建新 agent + 按需迁数据（显式、有审计）
- 守护测试：全仓无 agent rename 写路径
- 文档：data-model §3.2 `agents` 描述注明 **name 为不可变标识**（admin_state/session_meta/物理目录均以其为键）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `user-store`: "API keys move to a dedicated table" 修订为单轨终态（Alembic 回填完成迁移、`users.api_key` 列与一次性工具退役）；"Key resolution enforces validity" 修订 standalone 路径——agent 侧适配器经 user_store **本地读 `api_keys` 表**做哈希比对（边界约束从"不查询该表"修正为"不 import platform"，与读 `users` 表同级）；"Expanded users schema" 对齐 Alembic 权威措辞并移除 `api_key` 列
- `api-key-management`: ADDED "单轨与明文禁令"——`api_keys` 为唯一 key 真相源，明文凭证 MUST NOT 落库（仅创建时返回一次）
- `agent-definition`: ADDED "Agent name 为不可变标识"——rename 不受支持，satellite（admin_state/session_meta/物理目录）以名字为键的前提由此约束保护

## Impact

- **owning package**：`platform`（Alembic 迁移、user_management 工具退役、console 死桩删除）、顶层 `user_store.py` / `identity.py`（共享 store / 基座适配器）、`agent_store.py`
- **public API surface**：`User` dataclass 去 `api_key` 字段；`create_user` 返回形态调整（明文 key 单独返回一次）；`authenticate` 签名不变；`rename_agent` / `agent_admin_store.rename` / `rename_agent_def` 删除
- **owned tables**：`users` drop `api_key` 列（Alembic，含回填前置）；`api_keys` 无 schema 变更
- **config namespace**：无
- **cross-module dependencies**：`identity.LocalBearerAdapter` 仍仅依赖 `user_store` 本地读（零 platform import，护栏不变）
- **migration / shim plan**：Alembic 回填+drop 二步（或一迁移两步骤，design 定）；无代码 shim
- **相邻切片**：无在跑 change 触碰 user_store / identity / agent_store（knowledge-base-standalone-service 不相干）
