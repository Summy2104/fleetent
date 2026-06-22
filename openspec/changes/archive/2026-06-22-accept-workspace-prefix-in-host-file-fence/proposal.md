## Why

MCP 冒烟测试(2026-06-22)中,playwright 截图后 `send_file('/workspace/outbound/example_com.png')` 报 `path escapes workspace: '/workspace/outbound/example_com.png'`,模型试错几次才走通。

根因:`send_file`(及 file 工具的宿主围栏)经 `resolve_host_path(root, path)`(`tools/file_sandbox_io.py:123`)解析,`root` = 该 session 的宿主 workspace 目录。模型生活在容器 `/workspace` 单根坐标系,自然会传 `/workspace/<rel>` **绝对路径**;但 `resolve_host_path` 把它当普通绝对路径,与 host `root` 前缀不符 → 判为越界拒绝。

对比:容器侧 `resolve_ws_path` 本就接受 `/workspace/<rel>`(`WORKSPACE="/workspace"`),只有宿主侧 `resolve_host_path` 不认这个前缀。这与 #280/#284 给 stdio MCP 入参做的 `/workspace`→宿主翻译是同一类缺口,只是落在 builtin 文件 I/O 的宿主围栏上。

## What Changes

- `resolve_host_path` 识别容器挂载点前缀:`path` 等于 `/workspace` 或以 `/workspace/` 开头时,**剥掉该前缀、按 root 相对路径解析**(`/workspace/<rel>` → `<root>/<rel>`,`/workspace` → `<root>`)。其余绝对路径、`..` 越界、`/workspace-evil` 仿冒前缀**仍拒绝**(围栏不放松)。
- 受益方:`send_file`(`builtin_tools.py:1135`)与文件工具宿主后端(`file_tools.py:303` read/write 的 host-degrade)都不再因 `/workspace/` 前缀误拒。

不动:容器侧 `resolve_ws_path`(已接受该前缀);`/exchange` 解析;越界/仿冒拒绝逻辑。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `sandbox-file-send`：明确 `send_file` 的 workspace 路径翻译(经 `resolve_host_path`)除 **workspace 相对路径**外,亦 SHALL 接受**容器 `/workspace[/<rel>]` 绝对路径**(剥前缀后按宿主 root 解析),与模型所见的单根 `/workspace` 坐标系一致;两根之外、`..` 越界、`/workspace` 仿冒前缀仍 MUST 拒绝。

## Impact

**owning package**：agent runtime —— `src/fleetent/tools/file_sandbox_io.py`（`resolve_host_path`）。不 import `fleetent.platform.*`。

**public API surface**：`resolve_host_path(root, path)` 签名不变（行为放宽：多接受 `/workspace` 前缀）。

**owned tables**：无。 **config namespace**：无。

**cross-module dependencies**：`send_file` / file_tools host backend 既有调用方自动受益;不新增依赖,不触碰 agent↔platform 边界。

**migration / shim plan**：无。

**受影响代码**：`tools/file_sandbox_io.py`（`resolve_host_path`）；测试 `tests/unit/test_file_sandbox_io.py`（`/workspace` 前缀映射 + 仿冒/越界仍拒）。
