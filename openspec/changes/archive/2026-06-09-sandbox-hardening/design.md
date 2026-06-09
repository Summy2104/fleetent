## Context

容器 run flags 加固（`_resource_flags`）已合并。env 经 `build_sandbox_env`（黑名单 `is_sensitive_name`）过滤，注入源是 agent 声明的 `features.sandbox_env`。`manager.workspace_host_path` 派生 `paths.workspaces_dir()/{sanitised key}` 并 mkdir。`manager.acquire` 复用：registry 命中 → 直接复用；`find_workspace`（按名找到存活容器）→ re-adopt；否则 create_workspace。约束：纯 agent 运行时、不改 alembic、不破坏既有复用语义。

## Goals / Non-Goals

**Goals:**
- env 可选白名单（白名单 ∩ 非 sensitive）。
- workspace 挂载路径落在敏感宿主根时拒绝。
- 容器配置变更后复用失效（销毁重建），而非沿用旧配置容器。

**Non-Goals:**
- 不重写既有容器 run flags（已加固）。
- 不做 per-exec 路径黑名单（文件工具已锁 workspace；本黑名单只管「挂载源目录」这一道）。
- 不引入新配置文件层；新策略为纯函数 + 既有 manager/client 接缝。

## Decisions

**D1：env 白名单 = build_sandbox_env 增可选 `allowlist: set[str] | None`。**
合并三源后、黑名单过滤后，若 `allowlist` 非 None，再 `{k:v for k,v in ... if k in allowlist}`。None 保持现状。纯函数、可单测；调用方未传即不改变行为（白名单是 opt-in 加固）。

**D2：挂载路径黑名单 = 纯函数 `is_blocked_mount(path) -> bool` + manager 校验。**
`BLOCKED_MOUNT_SUBPATHS`（相对 `~` 的 `.ssh`/`.aws`/`.gnupg`/`.config/gcloud` + 绝对 `/etc`/`/root`/`/var/run`/`/proc`/`/sys`）。`is_blocked_mount` 把 path `realpath` 后判断是否等于或落在任一黑名单根内。`manager.workspace_host_path` 在 mkdir 后调用，命中 → `raise ValueError`（不返回路径、不挂载）。理由：workspace 源目录是唯一 bind mount 入口，守住它即守住「不会把宿主敏感目录挂进容器」。备选：在 create_workspace 校验——也可，但 manager 是路径派生权威，更靠源头。

**D3：config-hash = 纯函数 + 容器 label + acquire re-adopt 失效。**
`config_hash(image, resources, env, ws_path) -> str`：对 `(image or "", resources 的稳定字段元组, sorted(env keys), ws_path)` canonical 化后 sha256[:16]。`create_workspace` 增 `config_hash: str | None`，非空则 `--label fleetent.confighash=<h>`。`client.inspect_config_hash(name) -> str | None` 读 label（`docker inspect -f {{index .Config.Labels "fleetent.confighash"}}`）。`acquire`：
- registry 命中：本进程内、按当前配置创建，**视为最新**，直接复用（不额外 inspect，省开销）。
- `find_workspace` re-adopt：`desired = config_hash(...)`；`actual = await client.inspect_config_hash(name)`；`actual != desired`（含 actual 为 None 的旧容器？）→ **仅当 actual 存在且不等才重建**（None=未打 label 的历史容器，保守复用避免误杀；新建的都会带 label）。不一致 → `destroy_workspace(name)` + 落到 create 分支。

> env keys（非 values）入 hash：value 变（如 token 轮换）不应强制重建；注入的变量**集合**变才算配置变更。

**D4：env 入 hash 只取 keys 排序。**
见上：值不入 hash，避免无谓重建。

## Risks / Trade-offs

- **config-hash 增一次 docker inspect（仅 re-adopt 路径）**：registry 命中不 inspect；只有跨重启 re-adopt 才多一次 inspect + 可能重建。可接受（重建本就该发生）。
- **旧容器无 label**：保守复用（不重建），避免对历史容器误杀；新建容器都带 label，长期收敛。
- **路径黑名单 realpath 跟随符号链接**：刻意如此——防符号链接绕过；workspace 正常路径不受影响。
- **env 白名单 opt-in**：默认不启用即无行为变化；启用需调用方传 allowlist（本 change 提供能力，wiring 可后续）。

## Migration Plan

增量：三项均 opt-in 或仅在「配置变更 / 路径异常」时触发；正常路径零变化。无数据迁移、无 alembic。Rollback：移除 allowlist 分支、路径校验、config-hash 比对与 label。
