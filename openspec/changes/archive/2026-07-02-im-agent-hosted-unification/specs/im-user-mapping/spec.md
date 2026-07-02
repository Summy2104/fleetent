## MODIFIED Requirements

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
