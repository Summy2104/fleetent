# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿** → 可选 refactor。
> 测试任务排在对应实现任务之前。基线对照 main（门禁判据＝无新增失败）。

## 1. 前置核实（不改产线代码，定 scope）

- [x] 1.1 复读 `_call_via_session_inner`（client.py ~1186-1249）确认 `server`/`args`/`scope_key` 在 `session.call_tool` 前均可用，且 `server.transport ∈ {stdio,http}`
- [x] 1.2 确认 `manager._name_key`（含 sha256 截断）与 `paths.workspaces_dir()`，及 `tool_context.scope_key == workspace_scope_key(...)`（与 `/workspace` 同源）

## 2. host_workspace_dir 派生（TDD：红 → 绿）

- [x] 2.1 **测试先行**：`tests/unit/test_mcp_exchange_injection.py`（或新文件）加 `test_host_workspace_dir_from_scope_key`——断言 `manager.host_workspace_dir(k) == paths.workspaces_dir() / manager._name_key(k)`（conftest 已钉 FLEETENT_HOME 到 tmp）。跑最窄命令 **见红**（函数不存在）
- [x] 2.2 **实现**：`integrations/sandbox/manager.py` 加模块级 `host_workspace_dir(scope_key: str) -> Path`（纯计算，不 mkdir，完整类型注解 + docstring）。跑 2.1 **见绿**

## 3. 纯函数路径翻译（TDD：红 → 绿）

- [x] 3.1 **测试先行**：`test_mcp_exchange_injection.py` 加 `test_translate_workspace_args_*`：
  - `/workspace/generated/x.png` → `<tmp_host>/generated/x.png`
  - 精确 `/workspace` → `str(<tmp_host>)`
  - 非 `/workspace` 串（`/etc/x`、`hello`、`generated/x.png` 相对）原样不变
  - dict + list 递归改写；非 str（int/None）原样
  跑最窄命令 **见红**（函数不存在）
- [x] 3.2 **实现**：client.py 加模块级 `_WORKSPACE_PREFIX` + `_translate_workspace_arg(value, host_dir)` + `_translate_workspace_args(args, host_dir)`（递归 dict/list/str）。跑 3.1 **见绿**

## 4. chokepoint 接线（TDD：红 → 绿）

- [x] 4.1 **测试先行**：新建 `tests/unit/test_mcp_workspace_arg_translation.py`——`monkeypatch.setitem(client._server_registry,(None,id),server)`（`McpServerConfig` + `_health=healthy`）、stub `_active_sessions[(None,id)]` 为 fake session（`call_tool` 记录收到的 args、返回哨兵）、`monkeypatch.setattr(client,"_result_to_text",lambda r:"ok")`。断言：
  - stdio server + scope_key：fake session 收到的 args 里 `/workspace/g/x.png` 已变 `<host>/g/x.png`
  - http server：收到的 args 原样 `/workspace/g/x.png`（不翻译）
  - stdio 但 scope_key=None：不翻译
  跑最窄命令 **见红**（现状入参零改写）
- [x] 4.2 **实现**：`_call_via_session_inner` 在 health 短路之后、`session.call_tool` 之前加：`if scope_key and server.transport == "stdio": 惰性 import host_workspace_dir; args = _translate_workspace_args(args, host_workspace_dir(scope_key))`。跑 4.1 **见绿**

## 5. 回归 + lint

- [x] 5.1 整文件回归：`uv run pytest tests/unit/test_mcp_exchange_injection.py tests/unit/test_mcp_workspace_arg_translation.py tests/unit/test_mcp_result_handling.py tests/unit/test_mcp_degradation.py -q` 全绿
- [x] 5.2 `uv run ruff check` + `ruff format --check` 受影响文件通过

## 6. spec 同步

- [x] 6.1 确认 `specs/file-exchange/spec.md` 的 ADDED 要求与实现一致（stdio 入参 `/workspace`→宿主路径翻译；http/非 workspace 不动），scenario 覆盖 stdio 翻译 / http 不翻译 / 嵌套 / 无 scope_key

## 7. 收尾验证

- [x] 7.1 `make test-pr`：3206 passed，仅 1 个**预先存在且无关**的失败 `test_config.py::test_observability_logging_defaults`（data/logs 环境断言，不引用本改动）——符合「无新增失败」判据
- [x] 7.2 模块边界自检：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；确认 `mcp/client` 仅 intra-`integrations` import manager、无 `fleetent.platform.*` 反向 import
- [x] 7.3 回归确认（人读）：结果侧改写/登记、`/exchange` 解析、http server 行为、非 `/workspace` 入参均未变；仅新增「stdio 入参 `/workspace`→宿主路径」一向
