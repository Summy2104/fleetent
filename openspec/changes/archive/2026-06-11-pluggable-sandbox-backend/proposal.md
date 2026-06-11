# Proposal: pluggable-sandbox-backend

## Why

当前代码执行沙箱只有 Docker 一种后端，但部分客户内网没有 Docker 或不允许暴露 docker.sock，需要 microsandbox（本地嵌入式 microVM 隔离，无需 Docker daemon）作为平等并存的替代后端。同时 `sandbox-client` 主 spec 仍停留在项目早期 microsandbox 时代的陈旧表述（多个归档 change 标注的技术债），本次重构一并还清。

> microsandbox SDK 的实际架构（0.5.x 本地嵌入式，非 client-server）与初始假设有出入，spike 后据实调整，详见 `DECISIONS.md` D-spike-1。

## What Changes

- 新增 `BaseSandboxBackend` ABC + `BackendCapabilities` + 后端工厂：`integrations/sandbox/backend.py`、`backends/docker.py`（现 `client.py` 整体迁移为 `DockerBackend`）、`backends/microsandbox.py`（新增 `MicrosandboxBackend`）、`factory.py`
- session-snapshot 连续性（env/cwd 跨 exec）的包装逻辑与状态上移到 ABC 基类模板方法 `exec(session_id=...)`，子类只实现执行原语；消费方调用面不变
- `client.py` 退化为 re-export shim（`SandboxClient = DockerBackend`），现有 import 兼容
- Capability 声明 + 优雅降级：`persist_workspace`（缺失时 sweep 跳过 commit 直接销毁）、`workspace_mount`（缺失时不挂载、文件工具走宿主围栏降级）、`orphan_cleanup`（缺失时启动清理静默跳过）；manager 按 capability 决策，不用 isinstance
- 后端选择配置：`platform.yaml` 的 `sandbox.backend: docker | microsandbox`（缺省 docker）+ 可选 `sandbox.microsandbox.image`（基础镜像）；`agent.yaml` 新增 `sandbox:` 节可覆盖（优先级 agent.yaml > platform.yaml > 默认）。microsandbox 0.5.x 本地嵌入式，无 server_url / API key
- 启动探测、健康报告、孤儿清理、周期回收全部改为后端无关：`available()` 取代 `docker_available()`；**BREAKING**（诊断面）：`/health` 的 sandbox 块由 `{mode, docker_available}` 改为 `{mode, backend, backend_available}`
- 新依赖：`microsandbox`（Apache-2.0，官方 microVM 沙箱 SDK，本地嵌入式 libkrunfw 运行时；可自托管、数据不出内网，非 AI 框架）
- `sandbox-client` 主 spec 从 microsandbox 历史版本重写为后端中立的权威表述，删除过时的 `host.docker.internal` 连接需求

## Capabilities

### New Capabilities

- `sandbox-backend-abstraction`: 后端抽象契约——ABC 接口面、capability 声明、工厂选型、配置优先级、各 capability 缺失时的统一降级行为
- `microsandbox-backend`: microsandbox 后端——本地嵌入式 SDK（`is_installed()` 探测）、生命周期映射（create/exec/stop）、资源字段映射与 Docker 专属字段忽略、stdin 原生、host 绑定挂载（`Volume.bind`）、实例枚举（`Sandbox.list`）、config-hash 保守复用

### Modified Capabilities

- `sandbox-client`: 陈旧 microsandbox 时代需求重写为后端中立的执行面表述；删除 `host.docker.internal` 主机连接需求
- `sandbox-lifecycle`: agent scope 依赖固化从「必经 docker commit」改为 capability 门控——后端不支持 `persist_workspace` 时 sweep 跳过 commit 直接销毁并告警，下次 acquire 回退基础镜像
- `sandbox-enablement-control`: 「Docker 不可用降级 off」泛化为「选定后端不可用降级 off」；可用性探测改为后端接口 `available()`
- `sandbox-orphan-cleanup`: 按前缀枚举成为 capability 门控能力；后端不支持时清理静默跳过并记录
- `sandbox-runtime-lifecycle-wiring`: 启动清理与周期回收的触发前提从「Docker 可用」泛化为「选定后端可用」
- `sandbox-resource-limits`: 新增字段归属需求——通用字段（memory/cpus/network/exec_timeout/read_only）各后端必须映射，Docker 专属硬化字段仅 Docker 后端消费、其他后端忽略
- `sandbox-workspace-mount`: 挂载映射限定到支持 `workspace_mount` 的后端；不支持时不挂载并降级
- `sandbox-exec-timeout`: 超时强制终止改经后端 `kill_workspace`；SIGTERM-宽限-SIGKILL 序列收敛为 Docker 后端实现细节
- `file-tools-sandbox-execution`: 文件工具走容器执行的条件从「sandbox 可用」收紧为「sandbox 可用且后端支持 workspace_mount」；不支持挂载时降级宿主围栏执行
- `agent-scoped-runtime-config`: 进程级旋钮清单中陈旧的 `microsandbox_url` 更正为 `sandbox` 节（backend 选择）

## Impact

- **代码**：`integrations/sandbox/**`（重组为 backend.py / backends/ / factory.py）、`tools/builtin_tools.py`、`tools/file_sandbox_io.py` / `file_tools.py`（mount capability 判定）、`runtime/agent_app.py`（探测与清理改后端无关）、`server.py`（health 块）、`agent_config.py`（`sandbox:` 节）、sandbox `config.py`（backend 选择加载）
- **依赖**：新增 `microsandbox`（PyPI，Apache-2.0，平台原生 wheel）；microVM runtime（libkrunfw）由运维预装，需宿主硬件虚拟化（Linux KVM / macOS HVF），数据不出内网
- **部署**：默认 `backend: docker`，未配置 microsandbox 的现有部署零行为变化（health 字段名除外）；选 microsandbox 的部署需预装 microsandbox runtime 且宿主支持虚拟化，否则 `is_installed()` 探测失败 → mode 降级 OFF（不阻断启动）
- **测试**：现有 sandbox 单测 patch 目标从 `integrations.sandbox.client` 迁至 `backends.docker`（shim 上 patch 不生效）；新增基类模板 fake-backend 单测、MicrosandboxBackend SDK-mock 单测（不需真实 microVM/KVM）、factory/配置优先级 integration 测试；真实 microVM smoke 进 e2e 显式开启，不进 PR 门禁
