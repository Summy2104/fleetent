## Context

现状：7 个平铺模块构成工具域。调用边（已扫描）：
- `agent_loop.py:16`：`import fleetent.tools  # noqa: F401  # side-effect: register built-in tools`——**注册触发点**
- `agent_loop.py`：`from fleetent.tool_registry import (...)` + `:190` lazy `_registry`（私有）+ `multimodal.{build_message_with_images, has_image_block}` + `tool_result_truncation.truncate_tool_result` + `:1300` lazy `plugin_loader.load_plugins`
- `tools.py` 自身：`from fleetent import eval_logger, image_gen_client, vision_client` + `tool_registry.{ToolContext, tool}`
- `server.py`：`plugin_loader.{expand_plugin_patterns, load_plugins}`
- `session/manager.py:402`（session 迁移后路径）：lazy `from fleetent.tools import _get_manager`
- `im_gateway/normalizer.py:75`：lazy `from fleetent import tools, vision_client`
- `integrations/mcp/client.py:210`：lazy `from fleetent import tool_registry`
- 测试：`tests/integration/test_session_mgr.py:716` `monkeypatch.setattr(tools, "_get_manager", ...)`；约 16 个文件触及本域

## Goals / Non-Goals

**Goals**：7 文件迁入 `tools/`、注册副作用在包级保留、6 shim + 1 原子改、调用方全改、全量绿、行为不变。
**Non-Goals**：不改任何工具实现 / schema 构建 / dispatch / 访问控制逻辑；不改 MCP 命名约定；不改 plugin 加载语义。

## Decisions

### D1 — 文件映射
```
tool_registry.py          → tools/registry.py
tools.py                  → tools/builtin_tools.py   # 避免与 Python builtins 概念混淆（蓝图已决）
tool_result_truncation.py → tools/result_truncation.py
plugin_loader.py          → tools/plugin_loader.py
vision_client.py          → tools/vision_client.py
image_gen_client.py       → tools/image_gen_client.py
multimodal.py             → tools/multimodal.py
```
`git mv` 保留历史。

### D2 — 包 `__init__.py` 承载注册副作用（本包核心决策）
`tools/__init__.py` 顶部 `from fleetent.tools import builtin_tools  # noqa: F401  # side-effect`。效果：
- `import fleetent.tools`（agent_loop 现有写法）触发注册，**一行不用改语义**；
- import 包内任意子模块也先执行 `__init__` → 副作用比平铺时代**更难被绕过**；
- 旧 `from fleetent.tools import _get_manager`（session/manager lazy）继续可用——`__init__` 显式 re-export `_get_manager`（私有名不进 `__all__`，仅作兼容属性）。

### D3 — shim 矩阵
6 个旧路径留 shim（registry/result_truncation/plugin_loader/vision_client/image_gen_client/multimodal）；**`tools.py` 物理删除**（同名冲突），兼容由 D2 的包 `__init__` 承担。

### D4 — 私有符号跨界调用的处置
- `agent_loop:190` lazy `from fleetent.tool_registry import _registry`：改 `from fleetent.tools.registry import _registry`（保持私有直引，不进公共 API——runtime 迁移时再评估是否立正式接口）。
- `normalizer` 的 `from fleetent import tools, vision_client`：改 `from fleetent import tools` + `from fleetent.tools import vision_client`。

### D5 — patch 目标随迁（lazy import 语义）
`session/manager._release_sandboxes` 在**调用点** lazy import `builtin_tools._get_manager`——patch 包 `__init__` 属性不影响真实模块。`test_session_mgr.py:716` 等 patch 改为 `monkeypatch.setattr(fleetent.tools.builtin_tools, "_get_manager", ...)`。全量 grep `setattr(tools` / `patch("fleetent.tools` 核对。

### D6 — 公共 API 收口
`tool, dispatch, get_schemas, ToolContext`（registry）、`truncate_tool_result`、`load_plugins, expand_plugin_patterns`、`build_message_with_images, has_image_block`、vision/image_gen 的公共入口。`__all__` 显式；`_registry` / `_get_manager` 不进 `__all__`。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 注册副作用断链 → `get_schemas()` 空 | D2 包级触发 + 回归断言：import 包后 `get_schemas()` 非空（现有测试已覆盖，确认保留） |
| `tools.py` 无 shim，外部调用漏改 | 调用方均已枚举（见 Context）；全量 pytest + `grep -rn "fleetent\.tools\b\|fleetent import tools"` 收尾核对零残留旧语义 |
| 循环 import：`__init__` import builtin_tools，builtin_tools import registry | 包内子模块间用**子模块直引**（`from fleetent.tools.registry import tool`），不经过包 `__init__`，无环 |
| lazy patch 漂移 | D5 全量核对 |
| MCP 注册路径（mcp/client lazy import tool_registry） | 改走 shim 或新路径均可，统一改新路径 `from fleetent.tools import registry as tool_registry` |

## 验收

- `tools/` 成包；`import fleetent.tools` 后 `get_schemas()` 非空。
- 6 个旧路径仅 re-export；`src/fleetent/tools.py`（文件）不存在。
- 全部调用方改新路径；`grep` 无残留对旧 `fleetent.tools` 模块语义的依赖。
- 全量 pytest 绿；ruff 干净；mypy 不新增错误模式。
- 自检：`from fleetent.tools import tool, dispatch, get_schemas`、`from fleetent.tools.builtin_tools import _get_manager`、旧路径 `from fleetent.tool_registry import tool` 均成功。
