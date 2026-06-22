## ADDED Requirements

### Requirement: node IM-edge 识别 /link 并经平台 confirm

绑定是平台侧操作（写 im_users），agent 不参与；因此 `/link <code>` 命令 SHALL 在 **node IM-edge** 识别（不下发给 agent normalizer），由 node 经 `POST /nodes/{node_id}/link-confirm`（**node service key 鉴权**）把 `(platform, platform_user_id, code)` 交给平台校验 + 绑定。平台据 code 找到对应 pending-link 的 user_id 后做 attach-only 绑定（见 im-user-mapping）。

web 侧的 link 发起（出 code）与 unlink SHALL 经平台、由 **OIDC/admin session 认证**发起方。pending-link（`code → user_id`）SHALL 为短 TTL 的临时态。

#### Scenario: /link 经 node→platform 绑定

- **WHEN** 用户从 Telegram 发 `/link <code>`
- **THEN** node IM-edge 识别它、调 `POST /nodes/{id}/link-confirm`（node-key）带 `(telegram, tg_id, code)`；平台校验 code 后 attach 绑定，不经 agent

#### Scenario: link 发起需已认证

- **WHEN** 请求 web 端 link/initiate 或 unlink
- **THEN** 须经 OIDC/admin session 认证发起方；未认证拒
