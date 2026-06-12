## Why

拆 scope change(sandbox-workspace-scope-split)留了两个收尾项,本 change 补齐——两者都是该 change 移除 docker-commit 后、原放松的理由已失效的"应收而未收"。

1. **multi_user 信号无来源**:`resolve_workspace_scope(configured, multi_user)` 护栏已落地(多用户配 `agent` → 纠正为 `session`),但 `SandboxManager.multi_user` 恒由唯一构造点 `init_sandbox_manager` 以默认 `False` 传入——**护栏在生产中永不触发**。后果:多用户部署若显式配 `workspace_scope: agent`,不会被纠正 → 跨用户数据共享。需要一个**显式配置信号**驱动它。

2. **agent 加固档仍可写 + root,但理由已失效**:`sandbox-container-hardening` 要求 agent 档"需在容器内装依赖(pip)故保留 caps + 以 root 运行 + 可写 rootfs"。但 sandbox-workspace-scope-split 已把依赖安装移到**声明式离线 build**(运行期不再装依赖,见 sandbox-image-persistence)。该放松的原始理由不复存在,agent 档应收紧为与 session 同档(`read_only` + 非 root + 不补 caps)。这是纵深防御收紧,核心跨用户镜像投毒已由"禁 docker-commit"根除。

## What Changes

- **multi_user 显式配置信号**:agent.yaml `sandbox.multi_user`(bool,默认 `false`)→ `init_sandbox_manager` 读取并传入 `SandboxManager.multi_user`,驱动既有护栏。standalone `fleetent agent run` 默认单用户(false);platform 生成多用户共享 agent 的 agent.yaml 时写 `true`(纯配置,无反向依赖)。
- **agent 加固档收紧**:`build_resources_by_scope` 的 agent 档不再 `read_only=False` / `cap_add=安装 caps` / `run_as_user=None(root)`——改为与 session 同档(`read_only=True`、非 root、`cap_add` 空)。依赖来自 build 期不可变镜像,运行期 `/workspace`(bind mount)仍可写,不影响 agent 工作。清理 config 中"writable rootfs for docker commit"的陈旧注释/理由。

## Capabilities

### Modified Capabilities
- `sandbox-workspace-scope`: 明确多用户信号来源——运行形态(multi_user)由显式配置 `sandbox.multi_user` 决定(默认 false=单用户),standalone 默认单用户;护栏据此驱动。
- `sandbox-container-hardening`: agent 加固档不再为运行期装依赖保留 caps/root/可写——因依赖已移至 build 期不可变镜像;agent 档收紧为与 session 同的最严档(read_only + 非 root + cap-drop ALL 不补)。

## Impact

- **代码**:`integrations/sandbox/config.py`(`build_resources_by_scope` agent 档不再放松 read_only/cap/user + 清理陈旧注释);`agent_config.py`(`SandboxSettings.multi_user` 字段);`tools/builtin_tools.py`(`init_sandbox_manager` 读 `resolved.sandbox.multi_user` 传入)。
- **模块边界声明**:owning package=`integrations/sandbox`、`agent_config`、`tools`;public API surface=`SandboxManager.multi_user`(已存在);owned tables=无;config namespace=`sandbox.multi_user`(新增 bool 字段,落 SandboxSettings extra=forbid);cross-module dependencies=`tools` 读 agent_config public 配置传 manager,**不 import platform**(multi_user 信号经 agent.yaml 配置,platform 生成配置时写入,保持单向解耦);migration/shim=无(新增字段默认 false 行为不变;agent 档收紧对存量 agent-scope 容器经 config_hash 触发重建)。
- **测试**:unit(SandboxSettings.multi_user 默认 false/解析/extra=forbid;init_sandbox_manager 传入 multi_user;build_resources_by_scope agent 档现为 read_only/非 root/无 cap);integration(multi_user=true + 配 agent scope → 纠正 session + 告警;agent 档容器以非 root + 只读 rootfs 创建、/workspace 仍可写;声明式 deps 镜像在只读运行期仍可用)。
- **依赖**:基于已落地的 sandbox-workspace-scope-split(WorkspaceScope、resolve_workspace_scope、声明式镜像)、sandbox-container-hardening、sandbox-image-persistence。
