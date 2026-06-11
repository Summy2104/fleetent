# Design: pluggable-sandbox-backend

## Context

`integrations/sandbox/` 当前是 Docker 单后端：`client.py`（`SandboxClient`）是唯一直接调 `docker` CLI 的层，`manager.py` 持有 client 做 scope→tier 生命周期，消费方仅 4 处（`builtin_tools.run_code`、`file_sandbox_io`、`agent_app` 启动探测+孤儿清理、`server.py` health）。部分客户内网无 Docker 或禁止 docker.sock，需要 microsandbox（自托管 msb server，microVM）作为平等并存的后端。`SandboxClient` 的公开面里有 4 个 Docker 概念泄漏（`docker_available` / `commit_workspace` / `image_exists` / `inspect_config_hash`），`SandboxResources` 里混有 Docker 专属硬化字段。`openspec/specs/sandbox-client/spec.md` 还是项目早期 microsandbox 时代的陈旧版本（技术债）。

## Goals / Non-Goals

**Goals:**

- 后端抽象缝落在现 `SandboxClient` 的位置，Docker 与 microsandbox 平等并存
- Capability 声明 + 优雅降级，manager/cleanup/probe 全部按 capability 决策，零 isinstance
- 后端选择可配置：agent.yaml > platform.yaml > 默认 docker；单体 agent 独立运行时 agent.yaml 配全
- 消费方调用面不变（`run_code` / `file_sandbox_io` 的 exec 调用形状不动）
- 还清 `sandbox-client` 陈旧 spec 技术债

**Non-Goals:**

- 不做第三种后端（gVisor / Firecracker 直驱）——只保证缝的形状容得下
- 不做 microsandbox 与 Docker 的依赖固化能力对齐（volume 装依赖方案明确放弃，选优雅降级）
- 不改变 enablement 三态 mode 语义、资源配置文件结构（只新增 backend 选择键）
- 不改 trace/eval 日志 schema（backend 字段进日志列为未来工作）

## Decisions

### D1：抽象缝位置与 ABC（而非 Protocol）

缝放在现 `SandboxClient` 处——它已是唯一碰 Docker 的层。用 ABC 基类 `BaseSandboxBackend` 而非 Protocol：session-snapshot 连续性（env/cwd 跨 exec）的包装逻辑与状态（`_snap_ready`/`_cwd`）后端无关（只要求后端能 exec shell），放基类 `exec(session_id=...)` 模板方法，子类只实现执行原语 `_run_exec()`。两后端零重复，消费方调用面不变。Protocol 无法承载共享实现，被否。

```
integrations/sandbox/
  backend.py              ← BaseSandboxBackend(ABC) + BackendCapabilities + ExecResult
  backends/docker.py      ← DockerBackend（现 client.py 整体迁移，行为不变）
  backends/microsandbox.py ← MicrosandboxBackend（官方 SDK）
  factory.py              ← create_backend(...) 读配置选型
  client.py               ← re-export shim：SandboxClient = DockerBackend
  manager.py              ← backend: BaseSandboxBackend（原 client 字段）
  session_snapshot.py     ← 纯函数不动
```

接口核心面（两后端必须实现）：`available()` / `create_workspace(name, resources, image, env, workspace_host_path, config_hash)` / `find_workspace(name)` / `exec(workspace_id, command, session_id, stdin)` / `destroy_workspace()` / `kill_workspace()`。capability 门控面：`commit_workspace` / `image_exists`（persist_workspace）、`list_workspaces(prefix)`（orphan_cleanup）、`inspect_config_hash`（无 capability，msb 恒返 None 走既有保守复用路径）。

### D2：Capability 模型与降级矩阵

```python
@dataclass(frozen=True)
class BackendCapabilities:
    persist_workspace: bool   # commit→镜像依赖固化
    workspace_mount: bool     # 宿主目录绑定挂载
    orphan_cleanup: bool      # 按前缀枚举遗留实例
```

| capability 缺失 | 决策点 | 行为 |
|---|---|---|
| persist_workspace | `manager.sweep_idle` / `_image_for` | sweep 跳过 commit 直接 destroy + warn 一次；`_image_for` 恒返 None（下次重装依赖） |
| workspace_mount | `manager.acquire` / 文件工具路由 | acquire 不传挂载；文件工具降级宿主围栏执行（见 D3） |
| orphan_cleanup | `cleanup_orphans` | 静默跳过 + log 一条，启动不受阻 |

manager 按 `backend.capabilities` 字段分支，禁止 isinstance——第三后端进入时只填 capability，不改决策点。

### D3：mount 缺失时的文件视图取舍

mount 缺失时两条降级路线都有洞：(A) 文件工具降级宿主围栏——与 IM 附件暂存（写宿主 workspace）视图一致，附件可读、文件工具全功能，但 `run_code` 容器内 `/workspace` 与文件工具视图分歧；(B) 文件工具仍走容器 exec——与 `run_code` 视图一致，但 IM 附件对 agent 完全不可见。**选 A**：附件+文件工具是更高频路径，且宿主围栏机制已存在（`file-tools-sandbox-execution` 的 docker 不可用降级路径直接复用）。`run_code` 与文件工具的视图分歧记录为已知限制；未来可用 exec+base64 copy-in 桥接（不在本 change）。

### D4：后端选择配置与优先级

> spike 后修订（DECISIONS.md D-spike-1）：microsandbox 0.5.x 为本地嵌入式 microVM，无 server/API key，删除 `server_url` 与 `MSB_API_KEY`。

- `platform.yaml`：`sandbox.backend: docker | microsandbox`（缺省 docker）、可选 `sandbox.microsandbox.image`（基础镜像，缺省由后端定）
- `agent.yaml`：新增 `sandbox:` 嵌套节（pydantic 子模型，沿用 `vector_store:` 等既有模式），字段同上；单体 agent 独立运行（无 platform.yaml）时靠它配全
- 优先级：agent.yaml 显式值 > platform.yaml > 默认 docker；解析在 factory 一处完成
- microsandbox 无需任何连接 secret；runtime 由运维预装，后端只探测（见 D6）。`agent-scoped-runtime-config` spec 里陈旧的 `microsandbox_url` 旋钮表述随本 change 更正为 `sandbox` 节
- 非法 backend 值：log warn + 回退 docker（沿用资源配置「非法不静默接受、回退默认」惯例）

### D5：SandboxResources 不拆类，字段按后端归属

通用字段（`memory` / `cpus` / `network` / `exec_timeout` / `read_only`）为接口契约，两后端必须映射；Docker 专属硬化字段（`pids_limit` / `tmpfs_size_mb` / `cap_drop_all` / `cap_add` / `no_new_privileges` / `init` / `run_as_user`）仅 DockerBackend 渲染，MicrosandboxBackend 忽略——microVM 边界天然提供隔离，无对应概念。docstring 标注归属。拆成两个类被否：配置加载、scope tier 构建、调用面全要跟着拆，收益只是名义纯度。

### D6：MicrosandboxBackend 实现要点

> spike 后修订（DECISIONS.md D-spike-1）：基于实测 `microsandbox==0.5.6`（Apache-2.0，本地嵌入式）API。

- 官方 `microsandbox` SDK：create→`Sandbox.create(name, image=, cpus=, memory=, network=, volumes=)`，exec→`sandbox.exec("sh", ["-c", cmd], stdin=, env=, timeout=)` 返回 `ExecOutput{stdout_text, stderr_text, exit_code}`，kill→`sandbox.stop(timeout=)`（优雅，SDK 内建 SIGTERM→SIGKILL）。Docker 的 `docker kill` 信号序列是 Docker 后端实现细节，msb 用原生 stop
- **可用性探测**：`microsandbox.is_installed()`（runtime 未装时安全返 False 不抛）→ `available()`；无 server 概念。SDK 延迟导入，后端未选定时进程不 import `microsandbox`
- **stdin**：SDK `exec(..., stdin=...)` 原生支持 → base64 分块方案作废
- **host 挂载**：`Volume.bind(host_path, *, readonly, noexec, nosuid, nodev)` 支持 host 绑定挂载 → `workspace_mount=True`；`read_only` 映射 `Volume.bind(readonly=)`
- **实例枚举**：`Sandbox.list()` → `orphan_cleanup=True`；`Sandbox.remove(name)` 销毁
- **env 注入**：后端层重跑 `is_sensitive_name` 防御过滤（SB5 D3 纵深防御对两后端一致），经 `exec(env=)` 注入
- **network**：`NetworkPolicy.NONE/ALLOW_ALL/PUBLIC_ONLY` 1:1 映射 `Network.none()/allow_all()/public_only()`
- **config_hash**：msb 无 label 机制，`inspect_config_hash` 恒返 None → manager 既有「absent → 保守复用」路径，配置变更不触发重建（已知限制，与 pre-label Docker 容器一致）
- **capability 取值（spike 已回填）**：`persist_workspace=False`（无 image-commit；`Snapshot` 语义不同，列未来工作）、`workspace_mount=True`、`orphan_cleanup=True`
- **部署前提**：需宿主硬件虚拟化（Linux KVM / macOS HVF）+ 预装 microsandbox runtime（libkrunfw）。不满足时 `is_installed()` 返 False → mode 降级 OFF（与 Docker 不可用同路径）。单测全程 mock SDK，不依赖真实 microVM

### D7：探测、health 与启动接线

- `agent_app._start_infra` 的探测从 `SandboxClient().docker_available()` 改为 `create_backend(...).available()`，不可用照旧降级 OFF；启动清理与周期回收的触发前提同步泛化为「选定后端可用」
- `server.py` health 的 sandbox 块 `{mode, docker_available}` → `{mode, backend, backend_available}`。诊断面、无外部契约，直接改不留 alias

### D8：兼容与测试迁移

- `client.py` 留 shim（项目 runtime 扁平路径同款惯例）；`__init__.py` 继续导出 `SandboxClient` 名
- 测试 patch 目标从 `integrations.sandbox.client` 迁到 `backends.docker`——shim 复制引用，patch shim 不生效（CLAUDE.md 已知 gotcha）
- 基类 continuity 模板逻辑用 fake backend 测一次覆盖两后端；MicrosandboxBackend mock SDK 对象；factory 选型 + 配置优先级进 integration；真实 microVM smoke 进 e2e 显式开启

## Risks / Trade-offs

- [msb SDK 能力（volumes/枚举/网络）spike 前不确定] → 已由 spike 回填（DECISIONS.md D-spike-1）：均可用，`workspace_mount=True`/`orphan_cleanup=True`；capability 降级矩阵仍保留，供未来不支持挂载的第三后端复用
- [microsandbox 需硬件虚拟化（KVM/HVF）+ 预装 runtime] → 不满足时 `is_installed()` 返 False → mode 降级 OFF（与 Docker 不可用同路径，不阻断启动）；部署前提写入文档
- [msb 配置变更不触发重建（config_hash 恒 None）] → 与 pre-label Docker 容器同一保守复用语义；运维侧重建 sandbox 即可消除
- [shim 上 patch 不生效导致存量测试静默假绿] → 迁移任务显式逐文件改 patch 目标并跑该层全量对照
- [新依赖 microsandbox 的供应链/维护风险] → Apache-2.0、平台原生 wheel、仅 `backends/microsandbox.py` 一处 import；后端不选 msb 时不加载（延迟 import），Docker 部署零暴露

## Migration Plan

1. 重组目录 + shim（行为不变，存量测试绿）
2. capability 门控接入 manager/cleanup/probe（Docker capability 全 True，行为仍不变）
3. spike 回填 msb capability → MicrosandboxBackend + factory + 配置
4. 部署：默认 `backend: docker` 零变化；切 msb 的部署配 `sandbox.backend: microsandbox`，预装 microsandbox runtime 且宿主支持虚拟化
5. 回滚：配置改回 `backend: docker` 即回滚，无数据迁移

## Open Questions（spike 后已无阻塞项）

- ~~msb SDK 的 volumes 挂载、sandbox 枚举、网络策略映射是否可用~~ → **已解决**（DECISIONS.md D-spike-1）：`Volume.bind` 支持挂载、`Sandbox.list` 支持枚举、`Network.*` 干净映射；`workspace_mount=True` / `orphan_cleanup=True` 回填完毕
- （未来）`Snapshot`/`SnapshotHandle` 是否可承载 microsandbox 的依赖固化（实现 `persist_workspace=True`）——本 change 不做，保持 False + 优雅降级
