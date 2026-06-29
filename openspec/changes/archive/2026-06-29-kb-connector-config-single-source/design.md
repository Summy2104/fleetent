## Context

connector 配置存在双源:YAML（`knowledge_base/config.py` 的 `load_knowledge_config`）与 DB（`kb_connectors` 表，`kb_connector_store`）。`knowledge-base-boundaries` spec 已定 DB 为单一真相源、要求移除 agent 侧 `_kb_config` 的 connector 读取,但 `operations.py` 的 connector 入口在 `settings=None` 时仍 `_kb_config(None)` → `load_knowledge_config()` 回落 YAML,造成 drift。

## Goals / Non-Goals

**Goals:**
- connector 列举/查找/检查/同步/状态只反映注入的、源自 `kb_connector_store` 的 settings。
- 移除 operations 对 YAML 的隐式 connector 发现回落。
- 修订 `knowledge-base` "Connector configuration registry" 与 `knowledge-base-boundaries` 一致。

**Non-Goals:**
- 不改 `kb_connectors` 表结构或 `kb_connector_store` API。
- 不改 sweep/worker/admin 既有 DB 读取路径。
- 不改 connector 的 secret 解析（`credential_ref` / `FLEETENT_KB_*`）—— secret 跨机问题属簇 A，另行处理。
- YAML `knowledge.*` 仍可承载非 connector 的 KB 定义/索引配置,本 change 只移除 connector 发现。

## Decisions

### 决策:store 为唯一源,operations 要求显式注入 settings
- **为什么**:`knowledge-base-boundaries` 已决定,本 change 是补合规,不重开选型。
- **实现**:`operations` 的 connector 函数把 `settings` 从"可选(缺省读 YAML)"改为"必需/显式来源";调用方(platform admin/sweep/worker)始终传 `as_knowledge_base_settings()`;单机 CLI 显式从本地来源构造 settings 注入。
- **替代方案**:让 YAML 作 bootstrap-seed 写入 DB。否决:增加同步复杂度且 boundaries 未要求;直接显式注入更简单。

### 决策:保持 `knowledge_base` ✗→ `platform` 护栏
- operations 仍不 import platform;由 platform 调 store 取 settings 再注入 operations。依赖方向不变。

## Risks / Trade-offs

- **[隐式调用方遗漏注入]** 若有调用方依赖旧的 YAML 缺省行为 → 移除后报错。**Mitigation**:实现前 grep 所有 `list_configured_connectors` / `get_connector_config` / `run_connector_sync` / `get_connector_status` 无参或 `settings=None` 调用点,逐一改为显式注入;integration 覆盖。
- **[单机/CLI 路径回归]** 无 platform 时 connector 入口需要本地 settings。**Mitigation**:CLI 注入路径加测试,确认无 platform 时仍可列举/同步本地定义。

## Migration Plan

- 纯实现+spec 对齐,无 schema 变更。部署即生效。回滚还原代码即可。

## Open Questions

- 无。决策已由 `knowledge-base-boundaries` 锁定。
