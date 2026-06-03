# package-architecture Specification

## Purpose
TBD - created by archiving change runtime-package-blueprint. Update Purpose after archive.
## Requirements

### Requirement: 目标 package 结构为权威定义

`docs/architecture.md` SHALL 把张洋负责能力域的目标 package 结构记录为权威目标:`runtime/`、`model/`、`tools/`、`skills/`、`session/` 各为独立能力包,`sandbox` 位于 `integrations/sandbox/`。这是定义本身(本蓝图交付),不要求代码此刻已达成。

#### Scenario: 架构文档列出目标结构
- **WHEN** 查阅 `docs/architecture.md` 的目标 package map
- **THEN** 其中列出上述 7 个能力包归属,且 sandbox 明确归 `integrations/sandbox/`

### Requirement: 迁移约定为强制规范

后续逐包迁移 SHALL 遵守以下约定:每个能力域是一个 package 且公共 API 收口于 `__init__.py`;跨包只 import 公共 API、不引用另一包内部模块;迁入时去冗余前缀命名(对齐 `mcp/client.py`);迁移期旧扁平路径的 re-export shim 不承载业务逻辑。这些约定自本蓝图确立起对所有逐包迁移 change 生效,并在其 review 中被检查。

#### Scenario: 逐包迁移 change 符合约定
- **WHEN** 任一逐包迁移 change 实现完成、提交 review
- **THEN** 其新增 package 带 `__init__.py` 公共 API、无跨包内部 import、命名已去前缀、旧路径 shim 仅 re-export

### Requirement: 迁移为行为不变的纯结构搬迁

本系列每个迁移 SHALL 是纯结构搬迁,不改变运行时行为、公共契约或数据库 schema。

#### Scenario: 迁移前后行为一致
- **WHEN** 任一逐包迁移完成
- **THEN** 全量测试(`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`)在其前后均通过,且无 schema 变更


### Requirement: sandbox 域已迁入 integrations/sandbox

sandbox 能力域 SHALL 组织为 `integrations/sandbox/` package:公共 API 收口于其 `__init__.py`;原 `src/fleetent/sandbox_*.py` 平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim;迁移 SHALL 不改变运行时行为、`run_code` 工具契约或 schema。

#### Scenario: sandbox 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/integrations/sandbox/`
- **THEN** 它含 `__init__.py` + `client/config/manager/enablement/cleanup/secrets/output_truncation.py`,且 `__init__.py` 导出 `SandboxClient`、`Mode`、`cleanup_orphans`、`SandboxManager` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看任一旧路径(如 `src/fleetent/sandbox_client.py`)
- **THEN** 它只从 `fleetent.integrations.sandbox.*` re-export,不含函数/类定义

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试(`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`)通过,且无 schema 变更

### Requirement: session 域已迁入 session/

session 能力域 SHALL 组织为 `session/` package：公共 API 收口于其 `__init__.py`；原 `src/fleetent/session_mgr.py`、`session_index.py` 平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim；迁移 SHALL 不改变 session 持久化格式、原子写语义或运行时行为。

#### Scenario: session 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/session/`
- **THEN** 它含 `__init__.py` + `manager.py` + `index.py`，且 `__init__.py` 导出 `load`、`save`、`session_lock`、`SESSIONS_DIR` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看 `src/fleetent/session_mgr.py` 或 `session_index.py`
- **THEN** 它只从 `fleetent.session.*` re-export，不含函数/类定义

#### Scenario: 测试 patch 目标已随迁
- **WHEN** 检索 `tests/**` 中对 session 模块属性的 monkeypatch
- **THEN** patch 目标均为 `fleetent.session.manager`（非旧 shim 路径）

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且无 schema 变更

### Requirement: skills 域已迁入 skills/

skills 能力域 SHALL 组织为 `skills/` package：公共 API 收口于其 `__init__.py`；原 `src/fleetent/skill_registry.py`、`skill_audit.py` 平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim；`BUILTIN_SKILLS_DIR` SHALL 在迁移后仍指向真实的 `builtin_skills/` 目录；迁移 SHALL 不改变扫描、匹配、审计或热重载行为。

#### Scenario: skills 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/skills/`
- **THEN** 它含 `__init__.py` + `registry.py` + `audit.py`，且 `__init__.py` 导出 `scan`、`match`、`available_skills_prompt`、`SkillIndex` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看 `src/fleetent/skill_registry.py` 或 `skill_audit.py`
- **THEN** 它只从 `fleetent.skills.*` re-export，不含函数/类定义

#### Scenario: builtin_skills 路径解析正确
- **WHEN** import `fleetent.skills.registry`
- **THEN** `BUILTIN_SKILLS_DIR.exists()` 为真（指向 `src/fleetent/builtin_skills/`）

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且无 schema 变更

### Requirement: model 域已迁入 model/

model 能力域 SHALL 组织为 `model/` package：公共 API 收口于其 `__init__.py`；原 `src/fleetent/model_router.py`、`provider_health.py` 平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim；迁移 SHALL 不改变路由解析、fallback 链、routes.yaml 契约或 provider 熔断语义。

#### Scenario: model 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/model/`
- **THEN** 它含 `__init__.py` + `router.py` + `provider_health.py`，且 `__init__.py` 导出 `get_client_and_config`、`RouteConfig`、`get_health_cache` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看 `src/fleetent/model_router.py` 或 `provider_health.py`
- **THEN** 它只从 `fleetent.model.*` re-export，不含函数/类定义

#### Scenario: 可变全局的 patch 目标已随迁
- **WHEN** 检索 `tests/**` 中对 `ROUTES_PATH`、`ROUTES` 等模块属性的 monkeypatch
- **THEN** patch 目标均为 `fleetent.model.router`（非旧 shim 路径）

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且无 schema 变更

### Requirement: tools 域已迁入 tools/

tools 能力域 SHALL 组织为 `tools/` package：公共 API 收口于其 `__init__.py`，且 `__init__.py` SHALL 通过 import `builtin_tools` 保留内置工具注册副作用（`import fleetent.tools` 即触发注册）；原平铺路径中除 `tools.py`（与包同名、物理删除）外 SHALL 仅保留为不承载逻辑的 re-export shim；迁移 SHALL 不改变工具 schema、dispatch、访问控制或 MCP 注册行为。

#### Scenario: tools 成包且注册副作用保留
- **WHEN** 执行 `import fleetent.tools` 后调用 `get_schemas()`
- **THEN** 返回的内置工具列表非空且与迁移前数量一致

#### Scenario: 旧扁平路径处置正确
- **WHEN** 查看 `src/fleetent/`
- **THEN** `tools.py` 文件不存在；`tool_registry.py`、`tool_result_truncation.py`、`plugin_loader.py`、`vision_client.py`、`image_gen_client.py`、`multimodal.py` 只从 `fleetent.tools.*` re-export，不含函数/类定义

#### Scenario: 包内无循环 import
- **WHEN** import `fleetent.tools` 包及其任一子模块
- **THEN** 导入成功（子模块间用直引，不经包 `__init__`）

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且无 schema 变更
