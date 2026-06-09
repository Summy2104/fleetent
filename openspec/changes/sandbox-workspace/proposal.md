## Why

run_code 的沙箱容器当前不挂载任何宿主目录，且每次 `docker exec` 都是一个全新 shell——上一条命令对 `PATH`/虚拟环境/`cwd` 的修改在下一条命令里全部丢失，agent 无法连续工作。同时，后续让文件工具（read/write/edit/search）走容器以堵住"读宿主任意文件"的泄露通道，前提是先有一个被容器和宿主共享的 **workspace 统一边界**。本 change 提供这两块基础设施。

## What Changes

- **新增 workspace 统一边界**：宿主 `data/workspaces/{scope}/`（scope 复用 `SandboxManager` 现有的 session/agent 粒度）通过 bind mount 映射进容器 `/workspace`。沙箱内一切文件活动锁定在该目录，宿主敏感路径（`/etc`、`~/.ssh` 等）不挂入、物理上不可达。
- **run_code 容器从"零挂载"改为"挂载 workspace"**：`create_workspace` 新增 `-v <host_workspace>:/workspace` 挂载；容器停止/重建不删除宿主 workspace 目录（持久化）。这是对现有 run_code 的能力扩展，不改变其"代码在隔离容器内执行"的既有语义。
- **新增 session snapshot 机制**：首次 exec 时用 `export -p` / `declare -f` / `alias -p` 捕获 shell 环境到容器内 `/tmp/snap-{session}.sh`；后续每条命令包装为 `source snapshot → cd 持久化的 cwd → 执行 → 重新 dump 环境 → 输出 cwd marker 并从结果剥离`，使 `PATH`/venv/`cwd` 在多次 exec 间连续。snapshot 捕获或恢复失败时降级为 `bash -l`，不影响命令正确性。

无 BREAKING：workspace 挂载与 snapshot 对现有 run_code 调用方透明（默认行为更强，不破坏既有契约）。

## Capabilities

### New Capabilities
- `sandbox-workspace-mount`: 宿主 workspace 目录 bind mount 进沙箱容器的契约——路径从 `paths.py` 派生且可注入隔离、scope 与容器生命周期对齐、容器销毁不丢宿主数据、workspace 外宿主路径不可达。
- `sandbox-session-snapshot`: 沙箱内 shell 环境快照与逐命令恢复的契约——首次捕获、每命令 source+cd+重新 dump、cwd 经 marker 持久化并从输出剥离、失败降级，使跨 exec 的环境连续。

### Modified Capabilities
<!-- 无：workspace 挂载与 snapshot 作为新增行为契约引入；实现上扩展 client/manager，但不改变 sandbox-client / sandbox-lifecycle 既有需求。 -->

## Impact

- **代码**：`integrations/sandbox/client.py`（`create_workspace` 增挂载、`exec` 增 snapshot 包装）、`integrations/sandbox/manager.py`（`acquire` 解析并传入 workspace 路径）、`paths.py`（新增 `workspaces_dir()` 派生常量）、`tools/builtin_tools.py`（run_code 串接 workspace + session）。
- **约束**：纯 agent 运行时改动，不 `import fleetent.platform.*`；异步实现（`asyncio.create_subprocess_exec`），不引入同步阻塞 poll。
- **测试**：unit（路径派生、snapshot 命令包装组装、cwd marker 剥离）；integration（真实 docker 挂载与持久化、跨 exec 环境连续）。
- **依赖**：为后续 `file-tools-in-sandbox` 提供 workspace 边界前提；与现有 `sandbox-lifecycle`/`sandbox-client`/`sandbox-resource-limits` 协同，不冲突。
