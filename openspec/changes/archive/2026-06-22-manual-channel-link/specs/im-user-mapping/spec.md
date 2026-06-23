## ADDED Requirements

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
