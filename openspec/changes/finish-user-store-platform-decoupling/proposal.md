## Why

agent→platform 反向依赖扫描结论:**所有 agent 运行时 + 独立组件模块零 `fleetent.platform` import**——解耦守住。唯一残留是 `fleetent.user_store`(被 `test_module_dependency_guardrails` 的 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` **棘轮 pin 着**:agent 运行时 import user_store → user_store 懒加载 platform = 传递泄漏)。

#4 只修了 `authenticate`(改注入 resolver、不再 import platform),**漏了 user_store 的另两处懒加载**:
- `get_or_create_im_user`(:345)→ `platform.im_gateway_management`:**冗余死 wrapper**(全仓无调用;真能力已在 `platform/im_gateway_management/identity.py:get_or_create` + 由 `im-user-mapping`/`im-module` 拥有)。
- `migrate_api_keys`(:146)→ `platform.user_management.api_key_store`:一次性 key 迁移工具(只有一个 integration 测试调),写的是 **platform 的 `api_keys` 表**,本属 platform 域却长在 user_store。

护栏注释也 stale(仍说 `authenticate` hard-import,实际 #4 已修)。把这两处清掉,user_store 零 platform import,**棘轮收缩到空**——agent/platform 解耦直接 + 传递都干净,#1 泄漏彻底收尾。

## What Changes

- **删 `user_store.get_or_create_im_user`**(死 wrapper):IM 身份→内部 user 的能力由 `platform.im_gateway_management.get_or_create` 拥有(platform 侧);agent 侧 IM 身份走 #4 的渠道担保 Identity 端口(构造 `Principal`,不创建/不查 user_store)。
- **`migrate_api_keys` 移到 `platform.user_management`**(连同其 integration 测试):它读 user_store 的 legacy `users.api_key`(platform→user_store 读,方向允许)+ 写 platform 的 `api_keys` 表,本属 platform 域。迁移行为不变。
- **user_store 零 platform import**:移除后 `user_store` 不再 `import fleetent.platform.*`。
- **棘轮清零**:从 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 移除 `fleetent.user_store`(棘轮设计本就要求"不再泄漏则必须移除"),更新 stale 注释。

## Capabilities

### New Capabilities
<!-- 无;清理 + 落实既有解耦 -->

### Modified Capabilities
- `user-store`: 移除「Look up user by platform identity」(`get_or_create_im_user` 删,能力归 platform `im_gateway_management` / `im-user-mapping`);legacy api_key 一次性迁移函数移到 `platform.user_management`(user_store 不再托管写 platform 表的迁移);**user_store MUST NOT `import fleetent.platform.*`**(把 #1 根除从"认证路径"扩到"整个 user_store")。
- `module-dependency-guardrails`: 顶层共享模块 `user_store` 的传递 platform 泄漏清零;`_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 棘轮集合为空(任何模块新引入 platform 传递泄漏即 fail)。

## Impact

- **代码**:`user_store.py`(删 `get_or_create_im_user` + 移走 `migrate_api_keys`,去两处 platform import)、`platform/user_management/`(新增 `migrate_api_keys`)、`tests/unit/test_module_dependency_guardrails.py`(棘轮移除 user_store + 更新注释)、`tests/integration/test_api_key_auth.py`(migrate 测试改导入路径)。
- **owned tables**:无变化(`users` 仍 user_store;`api_keys` 仍 platform)。
- **config namespace**:无;**cross-module**:消除 `user_store → platform`;新增 `platform.user_management → user_store`(读 legacy 列,方向允许)。
- **migration/shim**:`get_or_create_im_user` 无调用方(死码,直接删);`migrate_api_keys` 调用方(仅测试)改导入路径。
- **验证基线**:`fleetent agent run` 的 bearer-auth 路径不再传递触及 platform;护栏棘轮空、`grep fleetent.platform` 在 user_store 零命中。
