# embedded-schema-migration Specification

## Purpose

为 agent 侧库提供共享的嵌入式 forward-only 迁移引擎（Y）。schema 以代码中的有序迁移步定义，DB 文件只存版本戳（SQLite `PRAGMA user_version`）。引擎为通用件，各 agent 侧库供自己的迁移清单与目标版本；KB 关系库为首个消费者。

## Requirements

### Requirement: 嵌入式 forward-only 迁移引擎

系统 SHALL 提供一个共享的嵌入式迁移引擎：schema 以**代码中**的有序迁移步定义（`MIGRATIONS = [(version, sql), ...]`），DB 文件只存版本戳（SQLite `PRAGMA user_version` 或等价的极小 `_schema_meta`）。引擎 SHALL 为通用件，各 agent 侧库供自己的迁移清单与目标版本。

#### Scenario: 引擎按库供的清单迁移

- **WHEN** 某库以其 `MIGRATIONS` 清单打开
- **THEN** 引擎据该清单与 DB 当前版本戳决定要执行的步

### Requirement: migrate-on-open

打开一个受 Y 管理的库时，引擎 SHALL 自动把它迁移到代码已知的当前版本：依序执行版本戳之后的迁移步，**每步在事务内执行且成功后才 bump 版本戳**。每个库文件 SHALL 各自迁移，无需中央编排。

#### Scenario: 开库即迁到当前版本

- **WHEN** 打开一个版本戳低于代码当前版本的库
- **THEN** 引擎依序执行缺失的迁移步，最终版本戳 = 代码当前版本

#### Scenario: 每步事务内 bump

- **WHEN** 某迁移步执行失败
- **THEN** 该步回滚、版本戳不前进，启动报错而非留下半迁状态

### Requirement: 版本闸（防降级）

若 DB 文件的版本戳 **大于** 代码已知的当前版本，引擎 SHALL 拒绝启动（防止旧代码打开新库导致数据损坏）；版本戳 **小于或等于** 时正常迁移/放行。

#### Scenario: 超前库被拒

- **WHEN** 打开一个版本戳高于代码当前版本的库
- **THEN** 引擎拒绝继续并明确报错

### Requirement: 空库与旧库同一路径

引擎 SHALL 用同一段代码路径处理空库（版本戳 0，执行全部迁移步）与旧库（只执行增量步）；不区分"建表"与"升级"两套逻辑。

#### Scenario: 空库执行全部步

- **WHEN** 打开版本戳为 0 的空库
- **THEN** 引擎依序执行全部迁移步，建出当前 schema

### Requirement: KB 为首个消费者

KB 关系库 SHALL 作为引擎的第一个消费者：把现 `knowledge_base/operations.py:ensure_schema()` 的 DDL 原样 lift 成 KB 的 `MIGRATIONS`（v1..vN），**保留 `tenant_id`/`kb_id` 列**，不借机改 schema。其余 agent 侧库（traces/memory/reflection 等）迁入 Y 不在本切片。

#### Scenario: KB schema 经 Y 建出且与原 DDL 等价

- **WHEN** 一个空 KB 关系库经引擎迁移
- **THEN** 建出的表/列/索引等价于原 `ensure_schema()` 的产出（含 `tenant_id`/`kb_id` 列）
