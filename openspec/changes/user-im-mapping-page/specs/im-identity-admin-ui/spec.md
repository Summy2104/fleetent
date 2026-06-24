## ADDED Requirements

### Requirement: 用户-IM 关系页在 React SPA 中原生渲染

React admin SPA SHALL 提供一个专属的"用户-IM 关系"页（原生路由 `/im-identities`，侧边栏入口标题"用户-IM 关系"），背靠 `/admin/im-identities` admin API，让管理员一屏管理"外部身份 ↔ 内部用户"映射。

- 页面 SHALL 以列表/表格列出全部映射，每行展示**平台**、**外部 ID**（`platform_user_id`）、所绑**内部用户**（用户名 + 邮箱）。
- 页面 SHALL 提供新增表单：选择平台、输入外部 ID、选择目标内部用户（来自 `GET /admin/users`），提交 `POST /admin/im-identities` 新增绑定，成功后列表刷新。
- 页面 SHALL 对每行提供删除操作，调 `DELETE /admin/im-identities/{id}`，成功后列表刷新。
- 数据访问 SHALL 走 TanStack Query（与既有 features 一致），并在变更后失效 `im-identities` 查询。

#### Scenario: 列出映射

- **WHEN** 管理员打开"用户-IM 关系"页
- **THEN** 经 `GET /admin/im-identities` 渲染每条映射的平台 / 外部 ID / 内部用户名+邮箱

#### Scenario: 新增绑定

- **WHEN** 管理员在表单选平台、填外部 ID、选内部用户并提交
- **THEN** 调 `POST /admin/im-identities`，成功后映射列表刷新出现新行

#### Scenario: 删除绑定

- **WHEN** 管理员点击某映射的删除
- **THEN** 调 `DELETE /admin/im-identities/{id}`，成功后该行从列表消失

#### Scenario: 侧边栏原生路由

- **WHEN** SPA 导航渲染
- **THEN** "用户-IM 关系"是指向 `/im-identities` 的原生 NavLink
