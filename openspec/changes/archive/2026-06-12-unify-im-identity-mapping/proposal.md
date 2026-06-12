# unify-im-identity-mapping

## Why

agent 侧所有 `user_id` 列的命名空间取决于入口：bearer 路径写管理库 `users.id`，IM 路径写渠道原生 id（`im_gateway/access.py` 的 `resolve_identity` 直接返回 `platform_user_id`）。同一个人从 Slack 和从 API key 进来是两个"用户"——记忆、会话、审批历史全部分裂；封禁级联也追不到该用户已写入的 agent 侧数据。`im_users` 映射表（本职就是归并）运行时无人消费、仅剩 admin 面，而 canonical spec `im-user-mapping` 本就要求"路由进 agent 管道前映射到内部 user_id"——现状实现违反既有 spec。这是 #4 Identity 端口"渠道担保解析器"留下的尾巴，R1 审批闭环（approver 用内部 user_id 反查 IM 地址）也因请求者/审批人命名空间错位而不自洽。

## What Changes

- **`im_gateway/access.py` 加模块级注入点 `set_im_identity_resolver(resolver)`**（与 `user_store.set_api_key_resolver` 同构先例）：`resolve_identity` 在 resolver 已注入时经其映射返回内部 `user_id`；resolver 为 None 时恒等返回渠道原生 id（**standalone 行为锁死，零变化**）。签名扩展可选 connector/owner 参数（映射需要 `owner_id`，slack/telegram 调用方各自知道连接器身份）
- **platform 启动时注入 resolver**（`server.py`，包装 `platform.im_gateway_management.identity.get_or_create`）：首见 IM 用户自动建 `users` 行 + `im_users` 映射行（`allowed=1` 默认、准入由频道白名单管——`identity.py` v1.0 注释既定语义，本 change 不引入新准入策略）
- **tenant 一致性校验**：映射出的 `user.tenant_id` 与 connector edge 配置的 tenant 校验一致（跨主体串话防御）
- **三个边界护栏**：注入点 docstring 声明 resolver 归属 platform、可写 platform 身份表、agent 侧不得感知其实现与表结构；守护测试锁 standalone 恒等行为；`im_gateway` 零 platform import 依赖护栏维持不变
- **文档**：`target-architecture.md` §6 补"managed 模式下 IM edge 延伸至 platform——身份注册写由注入的 platform resolver 完成，不构成 agent→platform 写"；`data-model.md` 把 `memory_items.user_id ⇢ users` 等跨库边注明语义（managed 成立 / standalone 为 opaque 渠道原生 id）
- 存量内测数据不迁移（上线前窗口；旧原生 id 行作历史数据自然沉淀）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `im-user-mapping`: "Map platform user to internal user" 恢复实现与 spec 一致（managed 经注入 resolver 在 edge 完成映射），并补 standalone 例外（无 platform 部署时恒等使用渠道原生 id）
- `identity-port`: "验活凭证解析器（bearer 与 渠道担保）" 的渠道担保路径修订——managed 下经**注入的 platform-owned 映射**得到内部 user_id 的 `Principal`（agent 模块仍不 import / 不直查 platform）；standalone 维持原生 id 透传

## Impact

- **owning package**：`im_gateway`（注入点 + resolve_identity）、`platform`（resolver 注入与 `im_gateway_management.identity` 复用）、`server.py`（启动接线）
- **public API surface**：新增 `im_gateway.access.set_im_identity_resolver`；`resolve_identity` / `resolve_principal` 签名扩展可选 connector 参数（向后兼容默认值）
- **owned tables**：无新表、无 schema 变更（复用既有 `users` / `im_users`；写者是 platform 侧 resolver）
- **config namespace**：无
- **cross-module dependencies**：依赖方向不变（platform 注入 callable 给 agent 模块，agent 零 platform import）；`get_or_create` 为 platform 既有 public API
- **migration / shim plan**：无迁移、无 shim；standalone 路径行为完全不变
- **相邻切片**：`schema-residue-cleanup` 正在 apply（blocklist / session index / 迁移文件），与本 change 无文件交集；`platform.im_gateway_management.identity` 的 `_init_db` 双权威残渣**不在本 change 修**（另立小切片）
