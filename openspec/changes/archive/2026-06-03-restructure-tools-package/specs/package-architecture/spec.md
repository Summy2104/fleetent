## ADDED Requirements

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
