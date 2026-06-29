## Why

`knowledge-base-boundaries` spec 已规定 connector 配置的**单一真相源**为 platform `kb_connector_store`（`kb_connectors` 表），并要求移除 agent 侧 `_kb_config` 的 connector 读取。但实现未完全合规:`knowledge_base.operations` 的 connector 列举/查找在**未显式注入 settings 时回落到 YAML**（`load_knowledge_config` → `_kb_config(None)`），与 DB 源并存且互不同步——admin/sweep/worker 走 DB 表,而 `list_configured_connectors()` 无参调用返回的是 YAML 定义,产生 drift(DB 新增的 connector 不出现在 YAML 列举里,反之亦然)。

同时 `knowledge-base` spec 的 "Connector configuration registry" requirement 仍把 "Platform Knowledge config"（YAML）描述为加载源,与 `knowledge-base-boundaries` 的单一真相源相矛盾。

## What Changes

- **operations connector 入口去掉隐式 YAML 回落**:`list_configured_connectors` / `get_connector_config` / `check_connector` / `run_connector_sync` / `get_connector_status` SHALL 要求显式注入的 `KnowledgeConfigSnapshot`(由 platform 经 `kb_connector_store.as_knowledge_base_settings()` 提供);**不再**在 settings 缺省时 `load_knowledge_config()` 发现 connector。
- **单机/CLI 路径显式注入**:无 platform 时由 ingest CLI 从本地来源构造 settings 注入,不走全局 YAML 隐式发现。
- **对齐 spec**:修订 `knowledge-base` 的 "Connector configuration registry",把加载源从 "Platform Knowledge config" YAML 改为"注入的、源自 `kb_connector_store` 的 connector 定义",与 `knowledge-base-boundaries` 一致。

不改变:`kb_connector_store` / `kb_connectors` 表结构;sweep / worker / admin 已有的 DB 读取路径;connector 的 check/sync/status 行为与 secret 解析(`credential_ref`)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `knowledge-base`: "Connector configuration registry" 的加载源由 YAML Platform Knowledge config 改为注入的、源自 `kb_connector_store` 的定义;connector operations 在无注入 settings 时不再隐式读 YAML。

## Impact

- **owning package**:`fleetent.knowledge_base`(operations / config 边界)+ 调用方 `platform.knowledge_base_management`(确保始终注入 store-sourced settings)。
- **public API surface**:`operations.*` 的 `settings` 参数语义收紧(由"可选,缺省读 YAML"变为"必需或显式来源");函数签名尽量保持,移除隐式 YAML 分支。
- **owned tables**:无变更(`kb_connectors` 已存在,Alembic 051/052/101)。
- **config namespace**:YAML `knowledge.*` 仍可承载 KB 定义/索引参数等非 connector 配置;仅 connector 发现从 YAML 路径移除。
- **cross-module 依赖**:无新增;保持 `knowledge_base` ✗→ `platform` 护栏(platform 注入 settings,knowledge_base 不反向 import)。
- **测试**:integration(connector 列举/查找只反映注入的 store-sourced settings,不回落 YAML)。
