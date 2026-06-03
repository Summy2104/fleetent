## Why

蓝图迁移序列**第五包**（sandbox✅ → session → skills → model → **tools** → runtime）：把 7 个平铺工具域模块收进 `tools/` 能力包。本包有两个特殊点，决定它必须单独、靠后执行：

1. **旧 `tools.py` 与新包 `tools/` 同名**——Python 不允许共存，旧模块路径**无法留 shim**，所有调用方必须在本 change 内原子改完；
2. **内置工具靠 import 副作用注册**（CLAUDE.md gotcha）——迁移后注册触发链必须保持，否则 `get_schemas()` 返回空。

## What Changes

- **迁移 7 文件**到 `src/fleetent/tools/`（`git mv` 保留 blame）：
  `tool_registry.py`→`registry.py`、`tools.py`→`builtin_tools.py`、`tool_result_truncation.py`→`result_truncation.py`、`plugin_loader.py`→`plugin_loader.py`、`vision_client.py`→`vision_client.py`、`image_gen_client.py`→`image_gen_client.py`、`multimodal.py`→`multimodal.py`。
- **建 `tools/__init__.py`**：re-export 公共 API，**并 import `builtin_tools` 以在包级保留注册副作用**——任何 `import fleetent.tools` 仍触发内置工具注册，与旧行为兼容。
- **旧路径 shim**：`tool_registry.py`、`tool_result_truncation.py`、`plugin_loader.py`、`vision_client.py`、`image_gen_client.py`、`multimodal.py` 6 个留 shim；**`tools.py` 不留**（同名冲突），其兼容性由包 `__init__.py` 承担。
- **原子改完 `fleetent.tools` 的全部调用方**：`agent_loop.py`（副作用 import + registry/truncation/multimodal）、`session/manager.py`（lazy `_get_manager`）、`im_gateway/normalizer.py`（lazy）、`server.py`、`integrations/mcp/client.py`（lazy `tool_registry`）。
- **迁移直接相关测试**：patch `tools._get_manager` 等必须改 patch `fleetent.tools.builtin_tools`（lazy import 在调用点解析真实模块，patch 包属性不生效）。
- 行为不变、无 schema 变更。

## Capabilities

### Modified Capabilities
- `package-architecture`: 记录 tools 域**已完成包化**——`tools/` 成包、注册副作用在包级保留、除 `tools.py` 外旧路径仅 shim、契约/行为不变。

## Impact

- **代码**：新增 `src/fleetent/tools/`（7 模块 + `__init__.py`）；6 个旧文件变 shim、`tools.py` 删除；agent_loop / session.manager / normalizer / server / mcp.client 改 import。
- **测试**：约 16 个测试文件触及 `fleetent.tools` / `tool_registry`——`from fleetent.tools import X` 形式靠包 `__init__` 兼容；patch 模块属性的（`_get_manager` 等）必须随迁到 `builtin_tools`。
- **关键回归点**：`get_schemas()` 非空（注册副作用存活）；MCP 工具 `{server}__{tool}` 注册路径不变。
- **依赖**：**硬依赖 session 已迁**（session/manager.py 的 lazy import 在本 change 改），其余为序列约定。
- **分支**：基于并 PR 合回 `main`。
