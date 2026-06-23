## ADDED Requirements

### Requirement: 管理员可经 admin API 管理 IM 身份映射

平台 SHALL 提供一组 session 认证的 admin API（前缀 `/admin/im-identities`），让管理员查看与维护 `im_users` 的"外部身份 ↔ 内部用户"映射。该 API SHALL 复用既有 `identity.py` store 与审计，并与既有 `/admin/im-users*` 路由共存、不冲突。

- **列表**（`GET /admin/im-identities`）SHALL 返回全部映射，并 **join users 带出该映射所绑内部用户的用户名与邮箱**（`user_name` / `user_email`），使管理员无需二次查询即可知道某外部身份对应谁。读权限放行 viewer 与 admin。
- **新增绑定**（`POST /admin/im-identities`，body `{platform, platform_user_id, user_id}`）SHALL 仅限 admin；目标内部用户不存在时返回 404；该 `(platform, platform_user_id)` 已存在映射时（唯一约束冲突）返回 409；成功写审计并返回新映射行。
- **删除绑定**（`DELETE /admin/im-identities/{im_user_id}`）SHALL 仅限 admin，删除该映射行并写审计；映射不存在时返回 404。删除只移除映射，所绑内部用户本身不受影响。

写操作 SHALL 写审计（actor、身份、动作）。鉴权语义 SHALL 对齐既有 admin router（`Authorization: Session <token>`，过期/缺失→401，权限不足→403）。

#### Scenario: 列出映射带出内部用户名与邮箱

- **WHEN** 管理员（或 viewer）GET `/admin/im-identities`
- **THEN** 返回全部 `im_users` 映射，每行含 `platform` / `platform_user_id` / `user_id` 及所绑用户的 `user_name` / `user_email`

#### Scenario: 新增绑定到已存在用户

- **WHEN** 管理员 POST `/admin/im-identities` 提交 `{platform, platform_user_id, user_id}`，且该 user_id 存在、该 `(platform, platform_user_id)` 尚无映射
- **THEN** 创建映射、写审计 `create_im_user`，返回含内部用户信息的新映射行

#### Scenario: 新增绑定的目标用户不存在

- **WHEN** 管理员 POST `/admin/im-identities` 提交的 `user_id` 在 users 表中不存在
- **THEN** 返回 404，不创建映射

#### Scenario: 新增绑定的渠道身份已被占用

- **WHEN** 管理员 POST `/admin/im-identities` 提交的 `(platform, platform_user_id)` 已映射到某用户
- **THEN** 返回 409（唯一约束冲突），不覆盖既有映射

#### Scenario: 删除映射

- **WHEN** 管理员 DELETE `/admin/im-identities/{im_user_id}`
- **THEN** 删除该映射、写审计 `delete_im_user`；所绑内部用户保留

#### Scenario: 非管理员不可写

- **WHEN** viewer 调 POST 或 DELETE `/admin/im-identities*`
- **THEN** 返回 403，状态不变
