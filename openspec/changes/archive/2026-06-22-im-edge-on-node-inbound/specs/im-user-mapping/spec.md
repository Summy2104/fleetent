## ADDED Requirements

### Requirement: 身份解析可经 node→platform 端点调用

除"平台进程内经 `set_im_identity_resolver` 注入 resolver"外，身份解析（`resolve_or_provision`：按 `(tenant, email)` lookup-or-link、无 email 则 channel-keyed）SHALL 可经 **node→platform HTTP 端点**（node service key 鉴权）调用。这使 IM-edge 在 node 进程运行时仍能解析身份——node 注入一个调用该端点的 resolver，`im_gateway` 不直接 import platform、不直写管理库。

该端点的解析语义 SHALL 与进程内解析**完全一致**（同一 `resolve_or_provision`、同样 attach-only 不合并、同样 tenant 校验/blocked 拒绝），仅调用通道不同（HTTP vs 进程内）。

#### Scenario: node 进程内的 IM-edge 解析身份

- **WHEN** IM-edge 在 node 进程收到入站消息，经注入的 resolver 调 node→platform 端点
- **THEN** 平台执行 `resolve_or_provision` 返回 `Principal`，结果与"平台进程内注入 resolver"一致

#### Scenario: 解析语义不因通道而异

- **WHEN** 同一渠道身份分别经进程内 resolver 与 node→platform 端点解析
- **THEN** 得到相同的 `user_id`（attach-only 并号、blocked/tenant 校验行为一致）
