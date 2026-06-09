## Why

sandbox 容器加固已大量落地（`--init`、`--cap-drop ALL`、`no-new-privileges`、`--pids-limit`、`--read-only`、`--network none`、tmpfs nosuid、非 root uid）。还差三道纵深防御：

1. **env 注入仍是黑名单**（`is_sensitive_name` 子串匹配）——无法表达「只允许这几个明确命名的变量进容器」的白名单，benign 名字仍可能被注入。
2. **workspace 挂载路径无黑名单**——若部署把 `FLEETENT_HOME` 指到敏感目录（如 `~`），`data/workspaces/{scope}` 可能落在 `~/.ssh`、`/etc` 等附近并被 bind mount，扩大暴露面。
3. **容器复用无 config 失效**——`acquire` 按名复用存活容器（重启后 re-adopt），但若 sandbox 配置（镜像/资源档/env 策略）已变，旧容器仍被沿用，配置变更静默失效。

## What Changes

- **env 白名单**（`secrets.build_sandbox_env` 增可选 `allowlist`）：提供白名单时，仅白名单内的变量名可注入（叠加既有 sensitive 黑名单）；不提供保持现状。
- **挂载路径黑名单**（`integrations/sandbox` 新增 `BLOCKED_MOUNT_SUBPATHS` + `is_blocked_mount`）：`manager.workspace_host_path` 在派生 workspace 目录后校验其规范化路径不落在黑名单根（`~/.ssh`、`~/.aws`、`~/.gnupg`、`/etc`、`/root` 等）内，命中即拒绝（raise），不创建/挂载。
- **config-hash 复用失效**（`manager` + `client`）：`config_hash(image, resources, env_keys, ws_path)` 纯函数；create_workspace 给容器打 `--label fleetent.confighash=<h>`；`acquire` re-adopt 存活容器时比对其 label 与期望 hash，**不一致 → 销毁重建**（配置变更生效），一致或无 label（旧容器）按现状复用。

无 BREAKING：env 白名单默认关；路径黑名单对正常 repo 内 `data/workspaces` 零影响；config-hash 仅在配置变更时触发重建，否则复用不变。

## Capabilities

### New Capabilities
- `sandbox-hardening`: 三道纵深防御契约——env 注入可选白名单（白名单 + sensitive 黑名单双过滤）；workspace 挂载路径黑名单（敏感宿主根拒绝挂载）；容器复用 config-hash 失效（配置变更则销毁重建而非沿用旧容器）。

### Modified Capabilities
<!-- 无：sandbox-secret-injection / sandbox-workspace-mount / sandbox-lifecycle 的既有契约保留，本 change 叠加白名单 / 路径黑名单 / config-hash 三项加固。 -->

## Impact

- **代码**：`integrations/sandbox/secrets.py`（build_sandbox_env allowlist）；`integrations/sandbox/`（路径黑名单 + config_hash 纯函数，可放 `config.py` 或新 `hardening.py`）；`integrations/sandbox/manager.py`（workspace_host_path 路径校验 + acquire config-hash 失效）；`integrations/sandbox/client.py`（create_workspace 打 label + 读 label 的 inspect 辅助）。
- **约束**：纯 agent 运行时（integrations/sandbox），不依赖 platform；不改 alembic。
- **测试**：unit（白名单过滤；is_blocked_mount 命中/不命中；config_hash 稳定/敏感；manager 在 hash 不一致时销毁重建、一致时复用——mock client）；integration 可选（真实 docker label roundtrip）。
- **依赖**：基于已合并 main 的 sandbox-workspace / sandbox-secret-injection / sandbox-container-hardening / sandbox-lifecycle。
