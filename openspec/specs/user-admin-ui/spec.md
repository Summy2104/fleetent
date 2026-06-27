# user-admin-ui Specification

## Purpose
TBD - created by archiving change complete-user-mgmt-ui. Update Purpose after archive.
## Requirements
### Requirement: 管理员经 UI 创建服务主体

用户管理面 SHALL 提供创建服务主体(service principal)的入口,调用既有 `POST /admin/service-principals`。提交成功后 UI SHALL 一次性展示新发放的凭证(`ma-` key)并提供复制,复用现有 API key 弹窗的"仅此一次可见"模式;凭证 MUST NOT 在后续列表中再次以明文展示。

#### Scenario: 创建服务主体并展示一次性凭证

- **WHEN** 管理员在用户管理面填写名称并提交创建服务主体
- **THEN** 调用 `POST /admin/service-principals` 成功,UI 弹窗一次性展示 `ma-` 凭证与复制按钮
- **AND** 关闭弹窗后该明文凭证不再可见

#### Scenario: 创建失败给出可见错误

- **WHEN** 创建服务主体的请求返回非 2xx
- **THEN** UI 展示错误信息,不关闭表单、不伪报成功

### Requirement: IM 身份管理收敛为单一面

管理 SPA SHALL 在用户管理面的 "IM Identities" 标签内提供 IM 身份的**全生命周期**操作:新建映射、绑定/重绑到内部用户、禁用、恢复、删除、编辑平台元数据。新建映射 SHALL 调用既有 `POST /admin/im-identities`;生命周期操作 SHALL 调用既有 `/admin/im-users/*` 端点(block/restore/bind/PATCH/DELETE)与 `GET /admin/im-users/fields`。独立顶级路由 `/im-identities` 及其导航项 SHALL 被移除。

#### Scenario: 单面内新建 IM 映射

- **WHEN** 管理员在 "IM Identities" 标签内选择平台、填写 platform_user_id、选择目标内部用户并提交
- **THEN** 调用 `POST /admin/im-identities` 创建映射,列表刷新展示该映射

#### Scenario: 单面内完成生命周期操作

- **WHEN** 管理员对某条 IM 身份执行禁用 / 恢复 / 重绑 / 编辑元数据 / 删除
- **THEN** 分别调用对应 `/admin/im-users/*` 端点并刷新该行状态

#### Scenario: 独立路由被移除后深链回落

- **WHEN** 浏览器访问已移除的 `/admin/ui/im-identities` 深链
- **THEN** 不再渲染独立映射页面(该路由不存在),管理员经用户管理面的 IM 标签完成同等操作

### Requirement: 管理员经 UI 手动绑定/解绑渠道身份

用户管理面 SHALL 提供手动渠道绑定与解绑入口。发起绑定 SHALL 调用 `POST /admin/link/initiate` 并展示返回的一次性 code 及其有效期(TTL),以便目标渠道账号回发完成双向控制;解绑 SHALL 调用 `POST /admin/link/unlink`。

#### Scenario: 发起绑定展示一次性 code

- **WHEN** 管理员对某用户发起渠道绑定
- **THEN** 调用 `POST /admin/link/initiate`,UI 展示一次性 code 与 TTL 提示

#### Scenario: 解绑渠道身份

- **WHEN** 管理员对某已绑定渠道身份执行解绑
- **THEN** 调用 `POST /admin/link/unlink` 成功后刷新该用户的渠道绑定展示

