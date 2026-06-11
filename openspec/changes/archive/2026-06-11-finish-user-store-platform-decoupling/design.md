## Context

反向依赖扫描:agent 运行时 + 独立组件模块**零 platform import**;唯一残留是 `user_store`(护栏 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 棘轮 pin 着)。#4 修了 `authenticate`(注入 resolver),漏了 `user_store` 另两处懒加载:
- `get_or_create_im_user`(:345)→ `platform.im_gateway_management`:冗余死 wrapper(全仓无调用);真能力在 `platform/im_gateway_management/identity.py:get_or_create`(由 `im-user-mapping`/`im-module` 拥有)。
- `migrate_api_keys`(:146)→ `platform.user_management.api_key_store`:写 platform 的 `api_keys` 表的一次性迁移,仅一个 integration 测试调,本属 platform 域。

护栏棘轮设计:pin 已知泄漏 + 任何模块"不再泄漏"也 fail(逼集合收缩)。清掉这两处即可让棘轮归零。

## Goals / Non-Goals

**Goals:**
- `user_store` 零 `fleetent.platform` import(直接 + 懒加载)。
- `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 棘轮清空。
- #1 反向依赖根除从"认证路径"扩到整个 user_store。

**Non-Goals:**
- 改 `users` / `api_keys` 表结构(不动)。
- 改 IM 身份解析行为(platform 的 get_or_create + 渠道担保已覆盖)。
- 移动其它管理侧 store。

## Decisions

### D1：删 get_or_create_im_user（死 wrapper）
全仓无调用方(仅护栏注释提及);能力归 `platform.im_gateway_management.get_or_create`。直接删 user_store 的 wrapper + user-store「Look up user by platform identity」requirement。**为何不留**:留着就是个委派 platform 的死泄漏点;真要用走 platform 侧或渠道担保。

### D2：migrate_api_keys 移到 platform.user_management
该迁移读 user_store 的 legacy `users.api_key`(`platform → user_store` 读,方向允许)+ 写 platform 的 `api_keys`(api_key_store)。移到 `platform.user_management` 后:platform 侧 import user_store(允许)+ 写自己的表,`user_store` 不再 import platform。读 legacy 列经 user_store 公开读函数(或最小只读查询),不反向依赖。其 integration 测试改导入路径。**为何移而非删**:迁移工具仍有价值(存量 legacy key),只是放错了侧。

### D3：棘轮清零 + 更新 stale 注释
D1/D2 后 user_store 零 platform import → 护栏的 ratchet 会因"pin 模块不再泄漏"而 fail,**必须**从 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 移除 `fleetent.user_store`(集合变空)。同时更新注释(它仍说 `authenticate` hard-import,实际 #4 已修)。

## Risks / Trade-offs

- [get_or_create_im_user 真有隐藏调用方] → 已全仓 grep(src+scripts+tests)确认仅护栏注释提及;删前再 grep 一次。
- [migrate_api_keys 移动后读 legacy 列的方式] → 用 user_store 公开读(或最小查询),不让 platform 侵入 user_store 内部;integration 测试覆盖迁移行为不变(scope `["*"]`/无 expiry/同 user)。
- [护栏棘轮空后,将来真需要临时 pin] → 棘轮本就允许"新泄漏先 fail";真有正当临时泄漏再按设计加回并写明,不在本 change。

## Migration Plan

1. 删 `user_store.get_or_create_im_user`（死码）。
2. `migrate_api_keys` 移到 `platform.user_management`(读 legacy 经 user_store 公开读、写 api_key_store);改 `test_api_key_auth.py` 导入路径。
3. 确认 `user_store` 零 platform import(grep)。
4. 从 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 移除 `fleetent.user_store` + 更新 stale 注释;跑护栏测试见绿(棘轮空)。
5. 回滚:还原函数位置与棘轮集合(纯结构调整,无数据/schema 变更)。

## Open Questions

- 无（删死码 + 移工具 + 清棘轮，范围明确）。
