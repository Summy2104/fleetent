# identity-port Delta

## MODIFIED Requirements

### Requirement: 验活凭证解析器（bearer 与 渠道担保）

系统 SHALL 提供两类验活凭证解析器：① **bearer**——`ma-` API key 与登录 session **同类合一**解析为 `Principal`；② **渠道担保**——IM 的 `(platform, platform_user_id)` 映射为 `Principal`，信任渠道、无密钥。渠道担保解析 SHALL 经可注入的身份映射 resolver 工作：**managed 部署**下 platform 启动时注入 platform-owned resolver，将渠道身份映射/注册为内部 `user_id`（与 bearer 路径同一命名空间，写 platform 身份表的动作发生在注入的 platform 代码内）；**standalone 部署**无注入，恒等使用渠道原生 id。agent 模块自身 MUST NOT import 或直查 platform user_store。OIDC/Google 将来折进 bearer 类（验完发 session 或当 bearer 验），不新增第三类解析器。

#### Scenario: bearer 解析
- **WHEN** edge 收到合法 `Authorization: Bearer ma-...`（或有效登录 session）
- **THEN** 解析出对应 user 的 `Principal`

#### Scenario: 渠道担保解析（managed，经注入映射）
- **WHEN** managed 部署的 IM edge 收到平台用户消息（如 slack `U123`），platform 已注入身份映射 resolver
- **THEN** 经注入的 resolver 得到内部 `user_id` 的 `Principal`；agent 模块自身不 import、不直查 platform user_store

#### Scenario: 渠道担保解析（standalone，原生 id 透传）
- **WHEN** standalone 部署（无 resolver 注入）的 IM edge 收到平台用户消息
- **THEN** 经渠道担保解析器以渠道原生 id 得到 `Principal`，全程不触达 platform
