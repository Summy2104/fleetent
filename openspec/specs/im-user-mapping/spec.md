# im-user-mapping Specification

## Purpose
Define how platform-owned IM identities map to internal users across automatic and manual attachment paths.
## Requirements
### Requirement: 身份解析可经 node→platform 端点调用

除"平台进程内经 `set_im_identity_resolver` 注入 resolver"外，身份解析（`resolve_or_provision`：按 `(tenant, email)` lookup-or-link、无 email 则 channel-keyed）SHALL 可经两条 HTTP 通道调用：既有 **node→platform 端点**（`POST /nodes/{node_id}/identity/resolve`，node service key 鉴权），以及 **agent→node loopback 端点**（`POST /agent/{name}/identity/resolve`，agent 以 `FLEETENT_TUI_TOKEN` 鉴权调 node，node 补 service key 转发到 platform）。两条通道使 IM-edge 无论运行在 node 进程还是在 agent 进程都能解析身份；`im_gateway` 在任一通道下都 SHALL NOT 直接 import platform、SHALL NOT 直写管理库、SHALL NOT 持有 node service key（agent 侧仅用 TUI token）。

该端点的解析语义 SHALL 与进程内解析**完全一致**（同一 `resolve_or_provision`、同样 attach-only 不合并、同样 tenant 校验/blocked 拒绝），仅调用通道不同（HTTP vs 进程内）。

#### Scenario: node 进程内的 IM-edge 解析身份

- **WHEN** IM-edge 在 node 进程收到入站消息，经注入的 resolver 调 node→platform 端点
- **THEN** 平台执行 `resolve_or_provision` 返回 `Principal`，结果与"平台进程内注入 resolver"一致

#### Scenario: agent 进程内的 IM-edge 经 loopback 解析身份

- **WHEN** IM-edge 在 agent 进程（managed 自持连接）收到入站消息，经注入的 `AgentIdentityResolver` 调 node loopback `/agent/{name}/identity/resolve`（TUI token 鉴权）
- **THEN** node 补 service key 转发 platform，平台执行 `resolve_or_provision` 返回，结果与 node→platform 通道一致

#### Scenario: 解析语义不因通道而异

- **WHEN** 同一渠道身份分别经进程内 resolver、node→platform 端点、agent→node loopback 端点解析
- **THEN** 得到相同的 `user_id`（attach-only 并号、blocked/tenant 校验行为一致）

### Requirement: 手动渠道绑定（双向控制 /link）

无 verified email 的渠道（如 Telegram/WhatsApp）SHALL 可经**手动 `/link`** 把渠道身份并到某真人的 email-keyed user。绑定 SHALL 要求**双向控制**：由**已认证用户**（经 OIDC web 登录）发起、平台签发一次性 code（短 TTL）；用户从**目标渠道账号**回发该 code；平台校验后才绑。要同时握住"已登录会话"和"目标渠道账号"才绑得成——单边声明不能绑。

绑定 SHALL 为 **attach-only**（与 email-join 一致）：仅当该 `(platform, platform_user_id)` **尚无映射**时，`_attach_identity` 到 code 对应的 user_id；若已映射到别的 user，**MUST NOT 合并**，拒并提示走人工。link SHALL 写审计（actor、两身份、时间、code 来源）。

#### Scenario: 双向控制绑定成功

- **WHEN** 已登录用户发起 link 拿到 code，并从目标 Telegram 账号回发 `/link <code>`（code 未过期）
- **THEN** 平台校验后把 `(telegram, tg_id)` attach 到该用户 user_id，写审计

#### Scenario: 单边/过期/错 code 拒绝

- **WHEN** code 过期、不匹配，或只有渠道侧消息而无对应的已认证发起
- **THEN** 不绑定

#### Scenario: 已映射渠道身份不被合并

- **WHEN** 该渠道身份已映射到 user A，提交的 code 属于 user B
- **THEN** 不合并、不改挂；拒并提示人工处理（attach-only）

### Requirement: 渠道解绑（可逆 + 审计）

已绑定的渠道身份 SHALL 可 **unlink**（用户自助 / admin）：删除该 `(platform, platform_user_id)` 的 im_users 映射并**写审计**。解绑后该渠道未来消息 SHALL 回落独立身份解析（`resolve_or_provision` 重新建/解析）。错绑窗口期已落在错 user_id 名下的数据 **SHALL NOT 自动迁移**——留痕，由 admin 人工清理（自动重归属为 post-v1 范围）。

#### Scenario: unlink 后回落独立身份

- **WHEN** 用户/admin 对某渠道身份执行 unlink
- **THEN** 删除其映射 + 写审计；该渠道下次来消息按独立身份解析

#### Scenario: 错绑数据不自动迁移

- **WHEN** 因错绑产生了归属错误的数据，随后 unlink
- **THEN** unlink 只改未来解析；已写错的数据保留待 admin 手动处置，系统不自动搬移

### Requirement: 管理员可经 admin API 管理 IM 身份映射

平台 SHALL 提供一组 session 认证的 admin API（前缀 `/admin/im-identities`），让管理员查看与维护 `im_users` 的"外部身份 ↔ 内部用户"映射。该 API SHALL 复用既有 `identity.py` store 与审计，并与既有 `/admin/im-users*` 路由共存、不冲突。当前管理前端把该能力内联在 Users 页（非独立页）消费。

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

