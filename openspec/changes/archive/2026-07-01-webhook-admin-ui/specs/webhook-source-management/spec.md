## ADDED Requirements

### Requirement: managed webhook source 在 React SPA 中原生管理

React 管理 SPA SHALL 提供托管 webhook source 的原生管理界面，覆盖既有 admin API 的能力子集：列表、新建、删除。创建表单 MUST 要求 `id` / `user_id` / `agent_id` 必填（`agent_id` 前端强制必填，即使后端模型允许 null——入站请求在 `agent_id` 为空时会 409）。SPA SHALL NOT 提供编辑能力（后端 upsert 语义会清空未传的 secret，改配置以删除重建代替）。

#### Scenario: 管理员新建 webhook source

- **WHEN** 管理员在 SPA 中填写 id / user_id / agent_id 等字段并提交新建
- **THEN** SPA 调用 `POST /admin/webhooks/sources`，成功后列表刷新，并展示可复制的完整 webhook URL

#### Scenario: 管理员删除 webhook source

- **WHEN** 管理员对某条 webhook source 发起删除并确认
- **THEN** SPA 调用 `DELETE /admin/webhooks/sources/{id}`，成功后该行从列表消失

#### Scenario: 不提供编辑入口

- **WHEN** 管理员想修改已有 webhook source 的配置
- **THEN** SPA 不提供编辑表单，只能删除后重新新建
