## Why

MCP 冒烟测试中,knowledge-bridge 大结果触发工具结果溢出,但 agent 随后无法读回:`error: path escapes workspace: '/home/ec2-user/.fleetent/data/tool_spillover/<uuid>.txt'`。

根因:`result_truncation._spillover` 把完整结果写到 `data_dir()/tool_spillover/<uuid>.txt`(**workspace 围栏之外**),并在 hint 里让 LLM `read_file(path='<该绝对路径>')`。但 `read_file` 围栏在该 session 的 `/workspace`(容器)/ 宿主 workspace 目录内 → 溢出文件读不了 → 「分段读完整结果」这一溢出功能形同虚设(数据本身在首 100 行 preview 里仍可见,故不阻断,但 paging 失效)。

## What Changes

- `truncate_tool_result` / `_spillover` 增加可选 `workspace_dir: Path | None`:
  - **提供时**(主循环按 run 的 `scope_key` 传入 session 宿主 workspace 目录):溢出写入 `<workspace>/.fleetent_spillover/<uuid>.txt`,hint 用 **workspace 相对路径** `.fleetent_spillover/<uuid>.txt` —— 容器 `resolve_ws_path` 与宿主 `resolve_host_path` 都能解析,`read_file` 可正常读回。
  - **未提供时**(无 scope_key 的边角路径、或既有测试)：回退旧全局 `SPILLOVER_DIR` + 绝对路径(向后兼容,行为不变)。
- `runtime/loop.py` 两处 finalize 调用 `truncate_tool_result(content, workspace_dir=host_workspace_dir(scope_key))`(`scope_key` 为空则传 None)。

不动:截断阈值/头尾 breadcrumb/self_truncates 豁免/多字节安全/`cleanup_spillover` 清理;全局 `SPILLOVER_DIR` 作为无 workspace 时的回退保留。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `tool-result-truncation`：溢出文件在有 session workspace 时 SHALL 写入该 workspace 的 `.fleetent_spillover/` 子目录,且分段读取提示中的路径 SHALL 为 **workspace 相对路径**,使 `read_file` 能读回完整结果(修复溢出文件落在 workspace 围栏外、无法读回的缺陷);无 session workspace 时回退全局 `data_dir()/tool_spillover/`(向后兼容)。

## Impact

**owning package**：agent runtime —— `src/fleetent/tools/result_truncation.py`（`truncate_tool_result` / `_spillover` 增 `workspace_dir`）、`src/fleetent/runtime/loop.py`（两处 finalize 传 `workspace_dir`）。不 import `fleetent.platform.*`。

**public API surface**：`truncate_tool_result(result, max_bytes=None, self_truncates=False, workspace_dir=None)` 新增可选末位参数（默认 None 保持既有行为）。

**owned tables**：无。 **config namespace**：无。

**cross-module dependencies**：loop.py 惰性 import `integrations.sandbox.manager.host_workspace_dir`（同既有 #280 用法）；不触碰 agent↔platform 边界。

**migration / shim plan**：无（全局 SPILLOVER_DIR 回退保留）。

**受影响代码**：`tools/result_truncation.py`、`runtime/loop.py`；测试 `tests/unit/test_tool_result_truncation_spillover.py`（新增 `workspace_dir` 路径 + 相对 hint 用例;既有全局用例不动）。
