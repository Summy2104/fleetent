## Context

run_code 经 `SandboxManager` 在常驻容器（`sleep infinity`）里通过 `docker exec` 执行代码。两个现状限制：

1. `create_workspace`（`client.py`）不挂载任何宿主目录——容器内产物随容器销毁丢失，宿主也无法与容器共享工作区。
2. 每次 `docker exec` 是独立 `sh -c` 进程，`PATH`/虚拟环境/`cwd` 的修改不跨命令保留。

本 change 是「危险操作沙箱治理方案」的基础设施层，为后续 `file-tools-in-sandbox`（文件工具走容器、堵住读宿主任意文件的泄露通道）提供 workspace 统一边界。约束：纯 agent 运行时（不依赖 platform）；fleetent 是 asyncio，所有子进程走 `asyncio.create_subprocess_exec`；借鉴 hermes 的 `init_session`/`_wrap_command` 机制但改为异步。

## Goals / Non-Goals

**Goals:**
- 宿主 `data/workspaces/{scope}` bind mount 进容器 `/workspace`，scope 对齐 `SandboxManager`，容器销毁不丢宿主数据。
- session snapshot 使 `PATH`/venv/`cwd` 跨 exec 连续；失败可降级。
- 为 `file-tools-in-sandbox` 备好「容器与宿主共享、且锁定边界」的工作区。

**Non-Goals:**
- 文件工具（read/write/edit/search）走容器本身——下一个 change。
- workspace 的清理 / 配额 / TTL——后续 hardening。
- config-hash 容器配置失效——后续 hardening change。
- 任何宿主侧路径围栏（O_NOFOLLOW 等）——本方案靠 namespace 边界，不在宿主重做。

## Decisions

**D1：workspace 路径从 `paths.py` 派生，新增 `workspaces_dir()`。**
复用既有 `data_dir()` 派生链，常量可 monkeypatch 注入隔离测试。备选：在 sandbox 模块内自读环境变量——否决，违反 CLAUDE.md「禁止各模块自读家目录」。

**D2：固定挂载点 `/workspace`，scope key 复用 `SandboxManager.acquire` 的 session/agent 粒度。**
`acquire` 已按 scope 解析 key 与容器名，workspace 子目录用同一 key，保证容器复用时映射稳定。备选：每 exec 临时挂载——否决，常驻容器模型下挂载在 create 时一次性确定。

**D3：session snapshot 采用「首次捕获 + 逐命令 wrap」，在 `client.exec` 内组装。**
首次 exec 跑 `bash -l` 捕获 `export -p`/`declare -f`/`alias -p` 到 `/tmp/snap-<session>.sh`；后续每条命令包装为 `source 快照 → cd 持久化 cwd → eval 命令 → 重新 export-p → 打印 cwd marker`。备选：每次都 `bash -l`（hermes 的降级路径）——否决，登录 shell 每次重载 profile 慢且仍丢非 profile 的运行期修改。

**D4：cwd 经 stdout marker 持久化并从输出剥离。**
命令尾部 `printf '\n<MARKER>%s<MARKER>\n' "$(pwd -P)"`，用唯一 per-session marker，提取后从返回文本剥离，避免泄露给 agent/trace。备选：写容器内临时文件再读——否决，多一次 exec 往返。

**D5：全异步实现，不照搬 hermes 的同步 poll 循环。**
用 `asyncio.create_subprocess_exec` + `communicate()`；snapshot 包装只改命令字符串组装，不引入阻塞轮询。理由：fleetent 是 FastAPI/asyncio，阻塞 poll 会卡 event loop。

**D6：snapshot 文件放容器内 `/tmp`，随容器销毁，无需额外清理。**
session 隔离用 `/tmp/snap-<session>.sh`，容器生命周期天然回收。

## Risks / Trade-offs

- **挂载点 uid 写权限**：session tier 以 `nobody`(65534) 运行 + 只读 rootfs，`/workspace` 是可写挂载，但 `nobody` 能否写宿主 workspace 目录取决于该目录权限 → 缓解：创建 workspace 目录时确保对容器运行 uid 可写（如 0777 或与运行 uid 对齐）；apply 阶段用 integration 测试验证 session/agent 两个 tier 都能写。
- **cwd marker 被命令输出伪造**：恶意/巧合输出包含 marker 文本可能干扰提取 → 缓解：marker 含 per-session 随机/uuid 片段，提取取最后一对 marker 之间内容。
- **snapshot 被容器内代码篡改**：代码可写 `/tmp/snap-*.sh` → 缓解：篡改至多破坏自己 session 的环境连续性（snapshot 在容器内、随容器销毁），且 D-降级路径保证命令仍能跑；不构成跨 session 或宿主风险。
- **首次 exec 增加一次捕获开销**：每 session 首条命令多一次 `bash -l` 捕获 → 接受：一次性、且换来后续连续性。

## Migration Plan

增量、对现有 run_code 调用方透明：未挂载/未 snapshot 的旧行为是新行为的子集。无数据迁移。Rollback：还原 `create_workspace` 不挂载、`exec` 不包装即可，无残留状态（snapshot 在容器内 /tmp，workspace 目录留存但不影响旧路径）。
