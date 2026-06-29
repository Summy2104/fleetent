## ADDED Requirements

### Requirement: per-user api-key/bearer 凭据按三元组隔离并 per-request 注入

配置为 per-user api-key/bearer 的 MCP server SHALL 按 `(user_id, agent_id, server_id)` 三元组隔离每个用户的 key，且 per-request 注入当前用户的 key（`Authorization: Bearer <key>` 或 `X-API-Key`，按 server header 配置）。同一 server 不同用户的 key MUST 互不可见、互不复用。token 解析 MUST 复用统一入口（与 per-user OAuth 同一 `resolve_user_token`/注入路径）。静态 `api_key`（`key_env`）服务行为 MUST NOT 改变。

#### Scenario: 不同用户各用各自 key
- **WHEN** 两个用户分别对同一 per-user api-key 的 MCP server 发起工具调用，各自已存了不同的 key
- **THEN** 每个调用以该用户的 key 注入请求头，互不串用

#### Scenario: 静态 api_key 不回归
- **WHEN** 一个 `auth_type=api_key`（`key_env`）的静态 server 被调用
- **THEN** 其鉴权行为与现状一致（从 env 取机器 key，全用户共享），不受 per-user 改造影响

### Requirement: 缺凭据时触发提交流程而非失败

当 per-user api-key server 被某用户调用而该三元组无已存 key 时，系统 SHALL 不抛异常、不卡住，而 MUST 返回明确的「需凭据」结果（挂在既有 degradation 链上），并 SHALL 按 server 配置的提交方式触发用户提交流程。已有 key 的调用 MUST 正常执行，不触发提交。

#### Scenario: 无 key 调用返回需凭据
- **WHEN** 用户调用一个 per-user api-key server 且其三元组无已存 key
- **THEN** 返回明确「需凭据」结果（不抛异常、不卡住），并触发提交流程（按 server 配置:表单链接 / 工具提示）

### Requirement: 安全表单提交，身份来自一次性 state、零平台登录

默认提交方式 SHALL 为安全表单:系统 SHALL 经 IM **私信（DM）** 向发起用户投递一条链接，链接携带**不可猜、一次性、短 TTL 的 `state`**，`state` 在服务端绑定 `(user_id, agent_id, server_id)`。链接指向 fleetent 自托管的凭据提交表单（standalone=agent 自托管 / managed=platform）。提交端点 MUST 凭 `state` 反查三元组完成存储，MUST NOT 依赖请求中的任何登录态（终端用户无 fleetent 平台账号）。提交的 key MUST 密文存储，MUST NOT 进入对话历史。`state` 提交后即作废。

#### Scenario: 表单提交存储且不需登录
- **WHEN** 用户点开 DM 链接、在表单填入自己的 api-key 并提交
- **THEN** 服务端校验 `state`（存在、未过期、未消费）→ 反查三元组 → 密文存储该 key;全程无需登录 fleetent 平台;`state` 随即作废

#### Scenario: 非法或过期 state 被拒
- **WHEN** 提交携带未知 / 过期 / 已消费的 `state`
- **THEN** 拒绝提交,不存储任何 key

#### Scenario: key 不进对话历史
- **WHEN** 用户经表单提交 key
- **THEN** key 从用户浏览器经 HTTPS 直达提交端点并密文落库,不出现在对话消息 / trace 中

### Requirement: 对话内工具提交为可选、限私信

当且仅当 server 配置允许工具提交（`credential_input ∈ {tool, both}`）时,系统 SHALL 暴露 `set_mcp_credential` 工具供用户在对话内直接提供 key,并 MUST 仅在**私信（DM）**上下文受理(频道内 MUST 拒绝并引导走 DM 或表单),提交的 key 存入该用户三元组。form-only 配置下该工具 MUST NOT 可用。

#### Scenario: 工具在 DM 提交成功
- **WHEN** server 配 `credential_input=tool` 或 `both`,用户在私信里用 `set_mcp_credential` 提供 key
- **THEN** key 存入该 `(user,agent,server)` 三元组,后续该用户调用即用之

#### Scenario: 频道内工具被拒
- **WHEN** 用户在群频道里调用 `set_mcp_credential`
- **THEN** 拒绝受理并提示改用私信或安全表单(防频道泄密)

#### Scenario: form-only 时工具不可用
- **WHEN** server 为默认 `credential_input=form`
- **THEN** `set_mcp_credential` 对该 server 不可见/不可用,只能经表单提交

### Requirement: 提交方式 per-server 可配,默认安全表单

每个 per-user api-key server SHALL 可配置允许的提交方式 `credential_input`,取值至少 `form`（默认）/ `tool` / `both`。未显式配置 SHALL 默认 `form`(仅安全表单)。

#### Scenario: 默认 form-only
- **WHEN** 一个 per-user api-key server 未配 `credential_input`
- **THEN** 仅安全表单可用,工具提交不可用

### Requirement: standalone 与 managed 两态;managed 下 key 不出 platform 边界外的对话/agent

per-user api-key 凭据 SHALL 在 standalone（agent 自托管表单 + 本地加密库）与 managed（platform 表单端点 + 管理库,agent 经 node loopback 登记 pending / 取 key）两态均可用,经既有注入缝并存。managed 下提交的明文 key MUST 密文存管理库;agent runtime MUST NOT import platform,MUST NOT 直连 platform(经 node 中转)。

#### Scenario: standalone 无 platform 也能提交并用
- **WHEN** 无 platform 的 standalone 部署,用户经 agent 自托管表单提交 key
- **THEN** key 密文存 agent 本地库,后续调用注入成功;全程不依赖 platform

#### Scenario: managed 经 node 中转、agent 不碰 platform
- **WHEN** managed 部署下用户提交 key、随后调用该 server
- **THEN** 提交存管理库;agent 经 node loopback 取该用户 key 注入;模块边界守护确认 agent 未 import platform

### Requirement: per-user 凭据存储类型感知,静态凭据不被当作可刷新 token

per-user 凭据存储(三元组键)SHALL 区分凭据类型 `credential_kind`(`oauth` / `static`),api-key/bearer 存为 `static`(只存注入密钥密文,refresh/expiry/scope 等 OAuth 字段为空)。注入时 header 风格 SHALL 由 server 配置 `header_style` 决定,MUST NOT 存于 per-user 凭据(同一 server 所有用户一致)。平台透明刷新路径 MUST 跳过 `static` 凭据(静态密钥无刷新,吊销则用户重交)。

#### Scenario: static 凭据只存密钥、不被刷新
- **WHEN** 一个 per-user api-key/bearer 凭据以 `kind=static` 存储,随后被取用
- **THEN** 直接返回该密钥(按 server `header_style` 注入);**不触发任何刷新逻辑**,refresh/expiry 字段为空且不被读取

#### Scenario: header 风格由 server 配置而非凭据决定
- **WHEN** 同一 `static` server 配 `header_style=x_api_key`,两个用户各存了自己的 key
- **THEN** 两用户调用均以 `X-API-Key` 注入各自 key;凭据本身不携带 header 信息
