## Why

两条**默认部署即生效**的隔离缺陷,使"沙箱隔离 → 风险降级 → 免审批"这一即将落地的安全前提不成立。本 change 是后续"沙箱优先执行"序列的**前置地基——免审批不得早于它落地**。

1. **容器名与 workspace 宿主目录共用 `_sanitise(raw)[:48]` 截断**(`integrations/sandbox/manager.py:60`),被 `_container_name`(:63)与 `workspace_host_path`(:221)同时使用。超过 48 字符、仅在尾部不同的 key(如默认单管理员部署下 `<36字符 admin UUID>` 前缀 + 不同 Slack DM 标识)截断后碰撞到**同一个容器、同一个 workspace 宿主目录**——对抗评审实测 `COLLISION=True`:用户 B 的会话读到用户 A 上传的文件(P0 跨用户泄露)。这直接违反 `sandbox-lifecycle` 既有要求"scope 与归属 key 不同的请求 MUST 取得相互隔离的容器"。

2. **action gate 的 `sandbox_capable` 是静态工具名查表**(`runtime/loop.py:748` `is_sandbox_backed(name)`),不读运行时沙箱 mode。docker 不可用时 `effective_mode=OFF`、file tools 降级宿主 `_HostBackend`(宿主进程权限、normpath 围栏自承 symlink/TOCTOU 缝),但 gate 仍判该工具"已被沙箱隔离"。一旦后续放松管制让部署者把 medium 操作配成 `sandbox` 免审批,降级态会**静默放行宿主侧写/执行**——"盒子封闭才免审批"在最可能的生产形态下落空。

3. **workspace 宿主目录从不回收**:session TTL 清理管线(`session/manager.py`)只删 `SESSIONS_DIR` 下会话文件,从不触碰 `workspaces_dir`。敏感上传(如 `salary.xlsx`)明文长期滞留,agent scope 目录无限增长——on-prem 合规真实漏点。

## What Changes

- **碰撞修复**:容器名与 workspace 宿主目录的 key 派生改为**基于完整未截断 key 的哈希后缀**(可读前缀 + 短哈希),`_container_name` 与 `workspace_host_path` 同一处修复同覆盖两者;不同 key 即便共享 >48 字符前缀也 MUST 落不同容器/目录。
- **运行时封闭性门控**:喂给 action gate 的 `sandbox_capable` 改为反映**运行时封闭性**——`effective_mode != OFF` **且**该工具本次确在容器 namespace 内执行(workspace mount 可用)才为真;否则为假,gate 复用既有 fail-closed("SANDBOX 但非 sandbox-backed → APPROVAL")回升审批。等价于声明"无 docker = 盒子不封闭 = 不免审批"。
- **workspace GC**:`session` scope 会话过期时**整目录 rmtree**(`is_blocked_mount` 同源校验防误删,接入既有 session TTL 触发点);`agent` scope **按 mtime 在目录内清理**(不可整删,跨会话复用)。
- **本 change 明确不做**:不翻任何工具的默认免审批(归后续"放松管制"PR);不改 registry 的 risk 常量;不新增 agent.yaml 配置字段;不动 scope 语义(拆 scope 是后续独立高风险重构)。

## Capabilities

### New Capabilities
- `sandbox-workspace-gc`: workspace 宿主目录的按 scope 回收契约——session 粒度随会话过期整目录回收、agent 粒度按 mtime 目录内清理,回收前 `is_blocked_mount` 同源校验;与 `session-ttl-cleanup` 的会话过期触发点对接,但作用对象是 `workspaces_dir` 而非 `SESSIONS_DIR`。
- `sandbox-containment-gating`: 喂给 action gate 的 `sandbox_capable` 反映运行时封闭性(`effective_mode != OFF` 且工具确在容器内执行),非静态工具名查表;封闭性不成立则 gate fail-closed 升 APPROVAL。明确"无 docker / 无 workspace mount = 不免审批"。

### Modified Capabilities
- `sandbox-lifecycle`: 强化既有"不同 scope+key MUST 取得相互隔离的容器"要求——容器名 key 派生 MUST 对仅在截断边界之后不同的 key 保持无碰撞(哈希基于完整 key)。
- `sandbox-workspace-mount`: 强化既有"每个 scope key 维护独立宿主子目录"要求——workspace 宿主子目录 key 派生 MUST 与容器名同样无碰撞,仅尾部不同的长 key 不得映射到同一宿主目录。

## Impact

- **代码**:`integrations/sandbox/manager.py`(`_sanitise`/`_container_name`/`workspace_host_path` 的 key 派生;新增或扩展 GC sweep);`integrations/sandbox/` 维护/清理路径(workspace GC 落点,与 `internal-session-maintenance` 触发点对接);`runtime/loop.py`(`sandbox_capable` 改为运行时封闭性派生,接 `sandbox_enablement.get_effective_mode()` 与 workspace mount 能力)。
- **复用而非新建**:免审批路由复用已合并的 `action-gate`(`resolve_action_mode` 的 SANDBOX→fail-closed→APPROVAL 契约不变,仅改喂进去的 `sandbox_capable` 真值)。
- **模块边界声明**:
  - owning package:`integrations/sandbox`(命名/挂载/GC)、`runtime`(封闭性派生喂 gate)。
  - public API surface:`SandboxManager.workspace_host_path`(签名不变,返回路径派生变)、新增 workspace GC sweep 入口;`_container_name`/`_sanitise` 为 internal。
  - owned tables:无(workspace 为文件系统,不落 DB)。
  - config namespace:无新增(复用 `sandbox.*`、`governance.action_gate_*`)。
  - cross-module dependencies:`runtime` 调用 `governance.action_gate` 与 `integrations/sandbox` 的 public API;**不 import `fleetent.platform.*`**,保持 agent/platform 单向解耦;agent 须仍能在无 platform、platform 表不存在环境下 `fleetent agent run`。
  - migration / shim plan:key 派生变更使存量 `data/workspaces/<旧名>/` 与旧容器名成孤儿——旧容器由既有 `sandbox-orphan-cleanup` 回收,旧 workspace 目录低危(临时性数据),由新 GC 或一次性运维清理兜底;internal 函数无需 re-export shim。
- **测试**:unit(key 派生对 >48 字符同前缀 key 无碰撞;封闭性派生:OFF/无 mount → sandbox_capable=False;GC 纯逻辑:scope 分派、is_blocked_mount 拦截);integration(同前缀双 key 取得隔离容器+隔离 workspace 目录;effective_mode=OFF 时 medium 工具经 gate 升 APPROVAL;session 过期触发 workspace 整目录回收、agent 目录 mtime 清理)。
- **依赖**:基于已合并 main 的 `action-gate`、`sandbox-lifecycle`、`sandbox-workspace-mount`、`sandbox-enablement-control`、`sandbox-orphan-cleanup`、`session-ttl-cleanup`。
