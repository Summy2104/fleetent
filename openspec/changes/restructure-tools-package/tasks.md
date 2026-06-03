> 纯结构重构，但**无 shim 兜底**（tools.py 同名冲突）：调用方原子改完。注册副作用是本包的命门，每步跑 `get_schemas()` 非空自检。**前置：session 包已迁移**（session/manager.py 路径）。

## 1. 基线

- [ ] 1.1 记录基线：`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 全绿；`mypy src` 现有错误数；记录 `import fleetent.tools; get_schemas()` 当前工具数

## 2. 移文件 + 建包

- [ ] 2.1 `git mv` 7 文件入 `tools/`（registry/builtin_tools/result_truncation/plugin_loader/vision_client/image_gen_client/multimodal.py）
- [ ] 2.2 改包内模块间 import 为**子模块直引**（`from fleetent.tools.registry import tool` 等，不经包 `__init__`，避免环）；逐模块 import 自检
- [ ] 2.3 建 `tools/__init__.py`：顶部 `from fleetent.tools import builtin_tools  # noqa: F401  # side-effect` + re-export 公共 API（tool/dispatch/get_schemas/ToolContext/truncate_tool_result/load_plugins/expand_plugin_patterns/build_message_with_images/has_image_block 等）+ 显式 `__all__` + 兼容属性 `_get_manager`、`_registry`（不进 `__all__`）；**自检：`uv run python -c "import fleetent.tools; from fleetent.tools import get_schemas; assert get_schemas()"` 工具数与基线一致**

## 3. 旧路径 shim（6 个，tools.py 除外）

- [ ] 3.1 `tool_registry.py`、`tool_result_truncation.py`、`plugin_loader.py`、`vision_client.py`、`image_gen_client.py`、`multimodal.py` 改为 shim（re-export + `__all__`，不含逻辑）；旧路径 import 自检通过
- [ ] 3.2 确认 `src/fleetent/tools.py` 已随 `git mv` 消失（不可留任何同名文件）

## 4. 原子改 src 调用方

- [ ] 4.1 `agent_loop.py`：副作用 import 语义不变（`import fleetent.tools` 即可）；`tool_registry` 系、`multimodal`、`tool_result_truncation`、lazy `plugin_loader`、lazy `_registry` 全改新路径
- [ ] 4.2 `session/manager.py` lazy `_get_manager` 改 `from fleetent.tools.builtin_tools import _get_manager`；`server.py` plugin_loader 改新路径；`im_gateway/normalizer.py` lazy 改 `from fleetent.tools import vision_client` 等；`integrations/mcp/client.py` 改 `from fleetent.tools import registry as tool_registry`
- [ ] 4.3 收尾核对：`grep -rn "fleetent\.tools\b\|from fleetent import tools" src/` 仅剩新语义用法；`uv run python -c "import fleetent.server, fleetent.agent_loop"` 成功

## 5. 测试 import + patch 目标随迁

- [ ] 5.1 `grep -rn "fleetent.tools\|tool_registry\|plugin_loader\|vision_client\|multimodal" tests` 全量核对：`monkeypatch.setattr(tools, "_get_manager", ...)`（test_session_mgr:716 等）改 patch `fleetent.tools.builtin_tools`；直接相关测试 import 改新路径，其余靠 shim/包兼容
- [ ] 5.2 跑 tools 相关测试子集绿（test_tools、test_tool_registry、test_plugin_loader、test_session_mgr sandbox 释放用例等）

## 6. 全量门禁 + 文档

- [ ] 6.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 绿（与基线一致）；`get_schemas()` 工具数与基线一致
- [ ] 6.2 `uv run ruff format` 本 change 文件 + `ruff check src tests` 干净；`mypy src` 不新增错误模式
- [ ] 6.3 更新 `docs/architecture.md`：tools 域改记为 `tools/`；更新 CLAUDE.md gotcha 中 `tools.py` 的表述为 `tools/builtin_tools.py`
