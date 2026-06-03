## ADDED Requirements

### Requirement: 能力域按 package 组织

张洋负责的每个能力域(runtime / model / tools / skills / session / sandbox)SHALL 组织为一个 package(目录 + `__init__.py`),其公共 API SHALL 收口于该 package 的 `__init__.py`。sandbox SHALL 位于 `integrations/sandbox/`(与 mcp / connectors 同属工具执行后端);其余各域为 `src/fleetent/` 下的独立顶层 package。

#### Scenario: 每个能力域对应一个 package
- **WHEN** 检视 `src/fleetent/` 的目录结构
- **THEN** runtime / model / tools / skills / session 各为一个带 `__init__.py` 的目录,sandbox 位于 `integrations/sandbox/`

#### Scenario: 公共 API 收口
- **WHEN** 外部模块需要某能力域的功能
- **THEN** 它从该 package 的 `__init__.py` 导出的公共 API 导入,而非从内部实现模块导入

### Requirement: 跨包只使用公共 API

跨 package 的调用 SHALL 只引用目标 package 的公共 API(其 `__init__.py` 导出的符号),不得 import 另一个 package 的内部实现模块。

#### Scenario: 不存在跨包内部引用
- **WHEN** 审查某 package 对另一 package 的 import
- **THEN** 只出现对 `fleetent.<pkg>`(公共 API)的引用,不出现对 `fleetent.<pkg>.<内部模块>` 的跨包引用

### Requirement: 命名去冗余前缀

模块迁入 package 时 SHALL 去掉与 package 同义的冗余前缀,对齐既有惯例(`mcp_client.py` → `mcp/client.py`)。

#### Scenario: 迁移后的命名
- **WHEN** `sandbox_client.py` / `tool_registry.py` / `session_mgr.py` 迁入各自 package
- **THEN** 分别成为 `integrations/sandbox/client.py` / `tools/registry.py` / `session/manager.py`

### Requirement: 迁移期 shim 不承载逻辑

迁移期间,旧扁平路径 SHALL 保留为 re-export shim 以维持向后兼容;该 shim SHALL 只做 re-export,不得承载任何业务逻辑。所有 package 迁移完成且调用方改至新路径后,shim SHALL 被统一删除。

#### Scenario: shim 仅 re-export
- **WHEN** 检视某旧扁平路径(如 `src/fleetent/sandbox_client.py`)在迁移期的内容
- **THEN** 它只包含从新位置的 import / re-export,不含函数体或类定义等业务逻辑

### Requirement: 结构迁移不改变行为与契约

本系列的 package 迁移 SHALL 为纯结构搬迁:不改变任何运行时行为、公共契约或数据库 schema。

#### Scenario: 迁移前后行为一致
- **WHEN** 完成任一 package 的迁移
- **THEN** 全量测试套件(`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`)在迁移前后均通过,且无 schema 变更
