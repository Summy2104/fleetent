## Context

`governance/blocklist.py` 同时承担两类职责:
1. **注册封禁存储**——`is_registration_blocked` / `_ban_registration` / `blocked_registrations` 表,被 agent 侧 `user_store.create_web_user` 在注册时读取。纯本地,无 platform 依赖。
2. **admin 级联编排**——`block_user` / `unblock_user` / `batch_block`,协调 `user_store` 状态、`platform.user_management.api_key_store` 吊销密钥、`platform.im_gateway_management` 禁用 IM 账号、写审计。这里产生了对 `fleetent.platform` 的两处 import。

调用方:`platform/user_management/user_admin_api.py` 调级联(`block_user`/`unblock_user`);agent 侧 `user_store` 仅调 `is_registration_blocked`。

## Goals / Non-Goals

**Goals:**
- governance/blocklist 对 `fleetent.platform` 零 import。
- 级联编排移到 platform 层,职责归位(协调 platform stores 的逻辑住在 platform)。
- 行为零变化:级联效果、unblock 语义、batch 共享 id、注册封禁拦截完全保持。

**Non-Goals:**
- 不改封禁的可观察行为或 API 契约。
- 不引入 platform→agent 的推送/触发机制(那是独立的更大架构,另行立项)。
- 不动 `blocked_registrations` schema、不加新依赖。
- 不处理 `user_store` 自身对 `api_key_store` 的 top-level 依赖(属共享身份层,本变更范围外)。

## Decisions

- **新模块 `platform/user_management/block_service.py`** 承接 `block_user` / `unblock_user` / `batch_block`。它 import `user_store`、`governance.audit_log`、`governance.blocklist`(调 `ban_registration`)、`platform.user_management.api_key_store`、`platform.im_gateway_management`。方向合规:platform(高层)→ governance(低层),允许。
- **`_ban_registration` 提升为 public `ban_registration`**:跨模块调用必须走 public API(module-boundaries 规则),故去掉前导下划线。`blocked_registrations` 表 owner 仍是 governance,platform 通过 governance public API 写入,不直接发 SQL。
- **governance/blocklist 保留** `is_registration_blocked`、`ban_registration`、`_init_db`、`DB_PATH` re-export(测试 monkeypatch 用)。删去 `block_user`/`unblock_user`/`batch_block`/`_disable_im_accounts`。
- **`user_admin_api`** 把 `blocklist.block_user`/`blocklist.unblock_user` 改成 `block_service.*`;不再 import governance.blocklist(它已 import `im`、`api_key_store`)。
- **测试归位**:级联相关断言移到调用 `block_service`;`is_registration_blocked` / 重复注册拦截仍走 `blocklist`。`test_governance_imports.py` 的 blocklist 公共 API 集合更新为 `{DB_PATH, is_registration_blocked, ban_registration, _init_db}`。

## Risks / Trade-offs

- **测试 monkeypatch 目标**:现有 fixture 在 `blocklist` 上 monkeypatch `DB_PATH`。block_service 无自有表,委托给被 patch 的 store/governance,故 DB 隔离仍有效;但需确认 `block_service` 内对 `blocklist.ban_registration` 的调用命中被 patch 的 `blocklist.DB_PATH`(同模块,成立)。
- **公共 API 收窄是 break**:任何外部对 `blocklist.block_user` 的引用会断。已 grep 确认 src 内仅 `user_admin_api` 一处调用方,无其他引用,风险可控。
