## Why

持久层 roadmap **#4**：把认证（authn）抽成基座 `Identity` 端口，结构性根除 **#1 泄漏**——今天 `user_store.authenticate`（user_store.py:61）懒导入 `fleetent.platform.user_management.api_key_store`，使 agent 运行时的 bearer 认证路径反向依赖 platform，违反 agent/platform 解耦契约（standalone agent 鉴权"够进"了 platform）。

设计已定稿（`docs/architecture/target-architecture-proposal.md §6` + memory `identity-auth-model`）：**一切身份落 User；认证是 edge 的事、核从不认证、只消费已解析的 `Principal`；authn 实现按部署可插拔。** 本 change 把这套落地。与 #3 物理库无硬依赖（#3 路由按 *agent* 主体、#4 解析 *请求者* Principal，两个 tenant_id 不同）；前置 `tenants`/`users.tenant_id` 已由 #2.5 提供。

## What Changes

- **新增 `Principal` 契约**：`Principal{user_id, tenant_id}`（精瘦——`role`/密码/`scopes`/`display_name` 挡在端口外；不带 team）。
- **新增基座 `Identity` 端口**：`凭证 → Principal | 拒绝`；核与 edge 只依赖端口类型，不依赖其实现。
- **两个解析器（验活凭证）**：① bearer（`ma-` key 与登录 session 同类合一）；② 渠道担保（IM `(platform, platform_user_id)` → user）。**OIDC/Google 适配器折进 bearer 类、本切片不实现**（后续适配器）。
- **根除 #1**：bearer 解析拆成可插拔适配器——**agent 侧（standalone）适配器 MUST NOT import platform**（本地 token / agent 侧 key 解析）；platform 的 api_key 解析变成 **platform 侧适配器**。`user_store.authenticate` 不再无条件 import platform。
- **核消费 Principal**：edge（server/agent_app/im/cron/tui）在入口解析出 `Principal` 后传入核；`loop.run`/`run_stream` 由 `user_id: str` 改为接收 `Principal`（核内部用 `principal.user_id` scope 记忆/会话，`tenant_id` 备 routing/审计）。
- **非凭证获取路径成文**：③ 继承（sub-agent / 回合内调用 ← 父/会话 Principal，不重认）；④ 存档复检（cron ← `scheduled_tasks.user_id`，触发时 load + 复检状态）；⑤ 纯基础设施用显式 `system` 标识、不冒充 user。

不在本切片：OIDC/Google 适配器实现（后续）；platform 只读投影、#3 物理 fan-out（属 #3）；现有 edge 机制（TUI token、IM allowlist、密码登录）的重写——它们**变成端口后的适配器，行为不变**。

## Capabilities

### New Capabilities
- `identity-port`: `Principal{user_id, tenant_id}` 契约 + 基座 `Identity` 端口（凭证→Principal）+ bearer/渠道担保两解析器 + 继承/存档复检/system 三条非凭证路径 + 「核只消费 Principal、edge 解析、agent 侧解析器不 import platform」的依赖约束。

### Modified Capabilities
- `user-store`: 「Key resolution enforces validity」——key→user 解析改为经 `Identity` 端口适配器暴露；**agent 侧解析器 MUST NOT import `fleetent.platform.*`**（platform 的 api_key 解析下沉为 platform 侧适配器），根除 #1。语义（有效性/吊销/过期/blocked 拒绝）不变。

## Impact

- **代码**：新增基座 `Identity` 端口 + Principal 类型 + 解析器适配器；改 `user_store.authenticate`（去 platform 无条件 import）；`runtime/loop.py`（`run`/`run_stream` 收 Principal）；edge 接线（`server.py`/`agent_app.py` 的 `_authenticate`、`im_gateway/access.py`、`cron_scheduler`、`_validate_tui_token`→system/local Principal）。
- **约束遵守**：agent 运行时（含其 bearer 解析适配器）不得 `import fleetent.platform.*`；统一经基座端口类型;不得新增反向依赖。
- **验证基线**：standalone agent（无 platform、platform DB 表不存在）能完成 `fleetent agent run` 的鉴权与对话。
- **apply 可分阶段**（见 design / tasks）：端口+Principal → bearer 适配器拆分（#1 修复）→ 渠道担保 → 核签名改 Principal → cron/system 路径。
- **依赖文档**：target-architecture-proposal.md §6（全段）、memory `identity-auth-model`。
