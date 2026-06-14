# unify-agent-binding-id

## Why

Agent 身份模型迁移**阶段 2**（依据 [`docs/architecture/agent-identity-model.md`](../../docs/architecture/agent-identity-model.md) §3.1/§3.2/§3.3）。`agent_kbs` 与 `agent_skills` 的 `agent_id` 现为 **TEXT 存 `str(agent.id)`**——平台侧"除 agents 表外全用 agent_id INTEGER"规则的两个偏离者。除类型不一致（无法与 `agents.id` INTEGER 干净 JOIN、无法声明 FK）外，`agent_skills` 还有一个**活 bug**：agent 控制台（`agent_admin_api`）写读绑定都用 agent **name**（控制台内自洽），而 `skill_admin_api` 写 `str(id)`、materialize 按 `str(agent.id)` 读——**经控制台设置的 skill 绑定，运行时（materialize）按 id 查不到、静默失效**。两表均无 FK，agent 删除留孤儿。

## What Changes

- **`agent_kbs.agent_id` / `agent_skills.agent_id`：TEXT → INTEGER + FK→agents.id ON DELETE CASCADE**（Alembic 新迁移，append after head、不硬编码）。数据迁移：数字串 `CAST`→int；`agent_skills` 中 `agent_id` 为 name 串的行（控制台 bug 产物）经 `agents` 解析 name→id，解析不到则丢弃（本就静默失效行）；pre-launch 窗口、存量可重置
- **修 `agent_skills` name/id 混写 bug**：规范键统一为 `agents.id`（materialize 这个消费方就按它读）。控制台 `agent_admin_api` 的 skill 绑定写/读（`set_agent_skill` + 列表）改为先解析 name→id 再调 store；`skill_admin_api` 去掉 `str()` 包装传 int。修复后**任一 admin 路径设的绑定，materialize 都能看到**
- **`agent_kbs` 调用方去 `str(agent.id)`**：`agent_admin_api`（kb bind）、`kb_admin_api`、materialize 读取一律传/用整数 `agent.id`
- **store 参数语义**：`skill_admin_store` / `agent_kbs_store` 的 `agent_id` 参数改为 int（named-param SQL 不变）
- 文档：`data-model.md` §3.2 这俩表描述从"TEXT str(id)"改为"INTEGER + FK"；引用 identity-model 阶段 2

**不在本阶段**：traces 列正名（阶段 1，等 trace-tool-spans 落地）、admin_state/session_meta 归 id（阶段 3）、其余绑定表补 FK（阶段 4）、翻译边界固化（阶段 5）。

## Capabilities

### Modified Capabilities

- `skill-agent-binding`: `agent_skills` 以 `agents.id`（INTEGER）为键 + FK→agents.id ON DELETE CASCADE；所有 admin 写路径（skill 侧 / agent 侧）一致按 id 写，使绑定对 materialize 可见（修 name/id 混写 bug）；materialize 读取键由 `str(agent.id)` 改为整数 `agent.id`
- `kb-agent-binding`: `agent_kbs.agent_id` 为 `agents.id`（INTEGER）+ FK→agents.id ON DELETE CASCADE（引用完整性 + 孤儿保护），binding 管理行为不变

## Impact

- **owning package**：`platform`（Alembic 迁移 + `skill_management` / `knowledge_base_management` stores + `agent_management_console` / `skill_management` admin API + `agent_lifecycle/materialize`）
- **public API surface**：`skill_admin_store` / `agent_kbs_store` 的 `agent_id` 参数 int 化（内部）；admin HTTP 路由签名不变（仍按 `{name}` 寻址，内部解析 name→id）
- **owned tables**：`agent_kbs`、`agent_skills` 的 `agent_id` 列 TEXT→INTEGER + 新增 FK
- **config namespace**：无
- **cross-module dependencies**：不碰 agent 零 platform import（全平台侧）；materialize 仍按 `agent.id` 读
- **migration / shim plan**：Alembic 一迁移完成类型转换 + 数据迁移（CAST / name 解析）+ 加 FK；forward-only；带升级路径测试；无代码 shim
- **相邻切片**：已核 5 个在跑 change（conversation-address / delivery-receipts / kb-standalone / trace-tool-spans / unified-file-exchange）均不碰 `agent_kbs` / `agent_skills` / skill·kb admin stores
