# im-user-mapping Delta

## MODIFIED Requirements

### Requirement: Map platform user to internal user
The system SHALL map `(platform, platform_user_id)` to an internal `user_id` before routing to the agent pipeline **when an identity resolver has been injected**（managed 部署：platform 启动时经 `im_gateway.access.set_im_identity_resolver` 注入，resolver 归 platform 拥有、可写 platform 身份表；agent 模块 MUST NOT 感知其实现与表结构）。无 resolver 注入时（standalone 部署）`resolve_identity` SHALL 恒等返回渠道原生 `platform_user_id`，行为与注入前完全一致。

#### Scenario: Known user（managed）
- **WHEN** a Slack message arrives from `platform_user_id=U123`（already in `im_users` table）and the platform identity resolver is injected
- **THEN** the resolver returns the corresponding internal `user_id`, and that `user_id` is used as `Principal.user_id` for this message

#### Scenario: Unknown user — first interaction（managed）
- **WHEN** a message arrives from a `platform_user_id` not in `im_users` and the resolver is injected
- **THEN** a new internal user and a new `im_users` row are created（`allowed=1` 默认，准入仍由频道白名单管），and the new internal `user_id` is used for this message

#### Scenario: 同一人双入口归并（managed）
- **WHEN** 同一用户先经 IM 渠道对话、后经其映射 user 的 bearer key 调用（或反之）
- **THEN** 两条路径解析出的 `Principal.user_id` 相同，agent 侧记忆/会话/审批数据按同一 `user_id` 归并

#### Scenario: Standalone 恒等透传
- **WHEN** 无 platform 部署（resolver 未注入）下 IM 消息到达
- **THEN** `resolve_identity` 返回渠道原生 `platform_user_id`，全程不 import 或查询 platform

#### Scenario: tenant 一致性校验（managed）
- **WHEN** 注入的 resolver 映射出的 user 的 `tenant_id` 与 connector edge 配置的 tenant 不一致
- **THEN** 该消息被拒绝处理（跨主体串话防御），并记录可诊断日志
