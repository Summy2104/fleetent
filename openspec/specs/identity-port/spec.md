# identity-port Specification

## Purpose

基座 Identity 端口：统一定义 `Principal` 契约、提供可插拔的 `凭证 → Principal | 拒绝` 解析接口，使核运行时与 edge 只依赖端口类型而不依赖具体认证实现。解决 agent 运行时反向依赖 platform 的根因。

## Requirements

### Requirement: Principal 契约

系统 SHALL 定义 `Principal{user_id, tenant_id}` 作为核消费的身份对象。`user_id` 为内部 user id（与 `memory_items.user_id` 等同值，核用它 scope 记忆/会话）；`tenant_id` 为主体（单机 = `default`）。Principal MUST 刻意精瘦——`role` / 密码 / `scopes` / `display_name` / team **不**进 Principal（属 edge / governance / platform）。

#### Scenario: Principal 携带 user_id 与 tenant_id
- **WHEN** edge 解析出一个已认证身份
- **THEN** 得到的 `Principal` 含 `user_id` 与 `tenant_id` 两字段，不含 role/scopes/team

### Requirement: Identity 端口在基座、核不认证

系统 SHALL 提供基座 `Identity` 端口：`凭证 → Principal | 拒绝`。核与 edge MUST 只依赖端口类型，不依赖其具体实现；**核自身 MUST NOT 执行认证**，只消费已解析的 `Principal`。authn 实现按部署可插拔（单机本地 / platform / 将来 OIDC）。

#### Scenario: 核只消费 Principal
- **WHEN** 一次请求进入核运行时
- **THEN** 核收到的是已解析的 `Principal`，核内部不调用任何认证函数

#### Scenario: 端口实现可插拔
- **WHEN** 部署形态从单机切到 platform
- **THEN** 仅注入的 `Identity` 端口实现不同，核与 edge 调用代码不变

### Requirement: agent 侧解析器不依赖 platform

agent 运行时的身份解析（含其 bearer 适配器）MUST NOT `import fleetent.platform.*`。platform 专属的凭证解析（如 `api_keys` 表查询）SHALL 仅存在于 platform 侧适配器。系统 SHALL 提供依赖护栏断言此约束，并保证 standalone agent（无 platform、platform 表不存在）能完成鉴权。

#### Scenario: standalone 鉴权不触达 platform
- **WHEN** 在无 platform、platform DB 表不存在的环境运行 `fleetent agent run`
- **THEN** bearer / 渠道担保解析正常工作，全程不 import 或查询 platform

#### Scenario: 护栏捕获反向依赖
- **WHEN** agent 运行时的解析路径出现 `import fleetent.platform.*`
- **THEN** 依赖护栏测试失败

### Requirement: 验活凭证解析器（bearer 与 渠道担保）

系统 SHALL 提供两类验活凭证解析器：① **bearer**——`ma-` API key 与登录 session **同类合一**解析为 `Principal`；② **渠道担保**——IM 的 `(platform, platform_user_id)` 映射为 `Principal`，信任渠道、无密钥。OIDC/Google 将来折进 bearer 类（验完发 session 或当 bearer 验），不新增第三类解析器。

#### Scenario: bearer 解析
- **WHEN** edge 收到合法 `Authorization: Bearer ma-...`（或有效登录 session）
- **THEN** 解析出对应 user 的 `Principal`

#### Scenario: 渠道担保解析
- **WHEN** IM edge 收到平台用户消息（如 slack `U123`）
- **THEN** 经渠道担保解析器得到 `Principal`，不读 platform user_store

### Requirement: 非凭证身份获取路径

系统 SHALL 支持三条非凭证身份路径：② **继承**——sub-agent / 回合内内部调用沿用父/会话已解析的 `Principal`，不重认；③ **存档复检（按域）**——cron 从 `scheduled_tasks.user_id` load 后，复检 MUST 在该身份**所属的域**内执行：`user_id` 为平台用户（`users` 表中存在）→ 复检状态，已 block / 删 / 移出主体则拒；任务带 IM origin 的**渠道担保身份**（不在 `users` 表中，由 IM edge 准入）→ MUST NOT 经 `user_store` 复检，凭存档身份放行执行；既无平台用户记录、又无 IM origin → 拒。部署中不存在用户管理（`users` 表缺失）时 MUST 信任存档身份放行（agent 独立运行基线）；`user_id` 为 `default` 占位时放行；④ **纯基础设施**——无人类 owner 的任务用显式 `system` 标识，MUST NOT 冒充 user，审计如实记 `system`。

#### Scenario: sub-agent 继承
- **WHEN** 核派生 sub-agent 或做回合内内部调用
- **THEN** 沿用父/会话的 `Principal`，不重新认证

#### Scenario: cron 存档复检（平台用户）
- **WHEN** 定时任务触发，`scheduled_tasks.user_id` 是 `users` 表中的平台用户且状态为 blocked
- **THEN** 拒绝执行

#### Scenario: cron 存档复检（IM 渠道担保身份）
- **WHEN** 定时任务触发，`user_id` 不在 `users` 表中，但任务的 `origin` 带 IM 平台来源
- **THEN** 视为渠道担保身份，不经 `user_store` 复检，按存档 `user_id` 构造 Principal 执行

#### Scenario: cron 存档复检（未知非 IM 身份）
- **WHEN** 定时任务触发，`user_id` 不在 `users` 表中且任务无 IM origin
- **THEN** 拒绝执行（平台域"已删用户的任务不再执行"语义）

#### Scenario: 无用户管理部署放行
- **WHEN** 定时任务在 `users` 表不存在的 standalone 部署中触发
- **THEN** 信任存档身份构造 Principal 执行，不因缺少平台用户管理而拒绝

#### Scenario: 基础设施用 system 标识
- **WHEN** 无 owner 的基础设施任务（如 TTL 清理）运行
- **THEN** 以显式 `system` 标识运行、不构造冒充某 user 的 Principal，审计记 `system`
