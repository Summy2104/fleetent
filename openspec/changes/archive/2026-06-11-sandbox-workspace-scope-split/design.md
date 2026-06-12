# Design: sandbox-workspace-scope-split

## Context

沙箱生命周期(`integrations/sandbox/manager.py`)目前用单一 `scope: Scope`(`session`|`agent`)字段同时承载两个本质正交的维度:

1. **数据隔离粒度**:`acquire`(:124)以 `key = session_id if scope is SESSION else agent_name` 派生容器名(`_container_name`)与 workspace 宿主目录(`workspace_host_path`)——决定"谁能看到谁的文件"。
2. **依赖镜像持久化**:`_image_for`(:190)硬编码 `scope is Scope.AGENT` 才查 `_agent_image_tag(key)`;`sweep_idle`(:265)对 `Scope.AGENT` 容器在销毁前 `commit_workspace`(`backends/docker.py:292`,`docker commit` 一个运行中、已被会话改写的容器),`build_resources_by_scope` 又据此给 `agent` tier 强制 `read_only=False`(可写 rootfs,好让 commit 捕获依赖)。

两维焊死带来两个安全缺陷(见 proposal Why):`agent` 数据隔离 = 同 agent 跨用户共享一个目录/容器(跨用户泄露);`docker commit`-from-running = 把用户 A 的 rootfs 烤进用户 B 镜像,且运行期 `--read-only`/`--network none` 对 baked 内容无效。本 change 做一次**高风险解耦重构**:把两维拆开、删掉拆解后失去理由的 `agent` 数据隔离档、用声明式离线 build 不可变镜像替换 commit-from-running。

地基 `sandbox-isolation-foundation` 已落地命名/碰撞修复(完整 key 哈希后缀)、containment 门控、workspace GC。本 change 建在其上,**不碰它已改的 `sandbox-lifecycle`「命名/碰撞」块与 `sandbox-workspace-mount` 的 key 派生无碰撞条款**,只改「scope 粒度/镜像选择」块。

## Goals / Non-Goals

### Goals
- 把 `scope` 收敛为 `workspace_scope`,语义**只剩数据隔离**(容器名 key + workspace 目录 key + 容器存活归属)。
- per-agent 依赖镜像持久化成为**独立开关**,实现改为**声明式离线 build 不可变镜像 + 运行期只读启动**。
- **禁用** `docker commit`-from-running-container 作为生命周期热路径的依赖固化手段。
- **删除** `agent` 作为数据隔离档(多用户强制 `session`,启动期校验纠正 + 告警)。
- 按后端 `persist_workspace` 能力分级,`persist_workspace=False` 显式声明热启动不成立。
- 充分回归:解耦后镜像选择不随 `workspace_scope` 改变;回收/重建不带入上次会话写入;同 agent 异 session 相互隔离。

### Non-Goals
- 不翻任何工具默认免审批、不改 registry risk 常量、不改 `action_gate.resolve_action_mode` 契约(归"放松管制" change)。
- 不碰 `sandbox-lifecycle`「命名/碰撞」块、`sandbox-workspace-mount` key 派生无碰撞条款(地基已改)。
- 不实现完整的镜像构建编排 UI / 调度;离线 build 的**触发时机**(启动期 / 显式命令)细节留实现期定,本 change 锁定"声明式 + 不可变 + 运行期只读 + 禁 commit-from-running"契约。
- 不改 agent/platform 解耦方向。

## Decisions

### D1: `Scope` 收敛为 `WorkspaceScope`,语义只剩数据隔离
`manager.Scope`(`session`|`agent`)正名为 `WorkspaceScope`,语义文档与所有派生收敛到"只决定容器名 key / workspace 目录 key / 容器存活归属"。`acquire` 的 `key` 推导(`session_id` vs `agent_name`)保留,但**仅用于容器名与路径**;镜像选择从 `acquire` 主路径里拆到独立分支。

- **备选**:新增一个全新字段 `data_isolation` 与保留 `scope` 并存。**否决**:两个字段都谈"粒度"会再造混淆;正名 + 收敛语义最干净,且 `Scope = WorkspaceScope` re-export 别名可保外部 import 兼容。
- **配置兼容**:`SandboxLifecycle.scope` 正名为 `workspace_scope`;旧 `sandbox.scope` 键在加载层映射到 `workspace_scope`(读旧键、warn 一次、按新语义生效),避免存量 `platform.yaml` 失效。

### D2: per-agent 镜像持久化独立于 `workspace_scope`
`_image_for` 不再看 `scope is AGENT`,改为看 **per-agent 镜像持久化开关**(新增配置)+ 后端 `persist_workspace` 能力。镜像选择与容器名/路径派生在 `acquire` 里走**两条独立分支**:
- 容器名/路径:`workspace_scope` → key → `_container_name` / `workspace_host_path`(不变式:同 key→同名→同目录)。
- 镜像:持久化开关 && `persist_workspace` && 不可变镜像存在 → 该镜像;否则基础镜像。

这样 proposal 的核心断言"镜像选择不随 `workspace_scope` 改变"由结构保证,而非约定。

### D3: 声明式离线 build 不可变镜像替换 commit-from-running
依赖固化机制整体替换:
- **旧**:运行期可写 rootfs → 用户装依赖 → `sweep_idle` 销毁前 `docker commit` 运行容器 → 下次 `_image_for` 查该 commit 产物。
- **新**:agent 预声明 `setup_command` → **离线构建阶段**在封闭环境(无终端用户会话数据)执行 setup → 产出**不可变**依赖镜像 → 运行期容器**只读** rootfs 从该镜像启动 → `_image_for` 查该声明式镜像。
- `sweep_idle` 移除 `commit_workspace` 调用,纯按 `idle_hours` 销毁。
- `commit_workspace`(running-container commit)从生命周期热路径退役;`BackendCapabilities.persist_workspace` 语义由"能 commit 运行容器"收敛为"能构建并复用不可变 deps 镜像"。

- **备选 A**:保留 commit-from-running,但每次 commit 前 `docker export | docker import` 抹层。**否决**:仍无法阻止会话写入被捕获,治标;且额外开销。
- **备选 B**:运行期可写 + 会话结束 diff 出依赖再 build。**否决**:diff 难精确、仍把会话痕迹带入,违背不可变初衷。
- **选定**:声明式离线 build——依赖来源是 agent 预声明(可审计),与运行期会话数据物理隔离,天然满足"不可变 + 封闭"。

### D4: 多用户强制 `session`,启动期校验纠正
拆出镜像维度后 `agent` 数据隔离只余"同 agent 跨用户共享一个目录"的反隔离效果。多用户部署 MUST 强制 `workspace_scope=session`:配置声明 `agent` 时启动期纠正为 `session` 并 warn,不静默接受。single-tenant standalone agent(单用户)保留 `agent` 数据隔离(无跨用户泄露面,且配合 per-agent 镜像可获跨会话依赖复用)。

- **多用户判定来源**:复用运行形态既有信号(platform 托管的共享 IM 入口 vs standalone 单用户 `fleetent agent run`)。判定细节实现期定,契约锁定"多用户 → 强制 session + warn"。
- **备选**:彻底删除 `agent` 枚举值。**否决**:single-tenant 跨会话依赖复用仍是合法用例,保留 `agent` 数据隔离档但加多用户护栏更稳。

### D5: 后端能力分级与 `persist_workspace=False` 的诚实声明
- `persist_workspace=True`(Docker):支持离线 build 不可变镜像 + 运行期 deps 层只读热启动。
- `persist_workspace=False`(microsandbox,无 image-commit 原语):热启动**不成立**,运行期从基础镜像 + setup 重新就绪;`_image_for` 对该后端永远返回基础镜像(None),并记录一条说明日志。MUST NOT 让调用方误以为已持久化为可热启动镜像。

### D6: 不变式与 key 派生中心
`_Entry(workspace_id, scope, key, last_used)` 的 key 仍是容器名/路径派生中心;`scope` 字段类型改为 `WorkspaceScope`。`release_session` / `invalidate` / `container_name` / `forget` 的 key 推导逻辑随 `workspace_scope` 语义收敛同步,但**同 key→同名→同目录**不变式不变。`acquire` 的 verify-on-reuse、config-hash re-adopt、死容器自愈路径(归 `sandbox-liveness-reacquire`,本 change 不碰)保持。

## Risks / Trade-offs

- **高风险重构**:`scope` 是 `acquire` / `workspace_host_path` / `_image_for` / `sweep_idle` / `release_session` / `invalidate` / `container_name` 与 `tools/builtin_tools.py`、`tools/file_tools.py`、`im_gateway/normalizer.py` 多处调用点的共享语义。**缓解**:语义收敛后调用点语义不变(仍传 scope 实参),`Scope = WorkspaceScope` 别名保 import 兼容;充分回归覆盖镜像/数据两维解耦。
- **存量镜像孤儿**:旧 `fleetent-sandbox-agent-<key>:latest`(commit 产物)不再被查找。**缓解**:低危(可重建),由一次性运维或既有镜像 GC 兜底;`_image_for` 无声明式镜像时回退基础镜像,行为安全。
- **microsandbox 无热启动**:`persist_workspace=False` 下每次运行期重装依赖,慢。**缓解**:这是后端固有限制,本 change 只要求**诚实声明**(日志 + 文档),不假装持久化。
- **离线 build 触发时机未定**:启动期 build 会拉长启动;显式命令 build 需运维介入。**缓解**:契约只锁"声明式 + 不可变 + 运行期只读 + 禁 commit-from-running",触发时机实现期按最小可行选型,不阻塞契约落地。
- **配置兼容回归**:旧 `sandbox.scope: agent` 在多用户下被纠正为 `session`,可能改变部分部署的既有(危险)行为。**缓解**:这正是修复目标;纠正时 warn 明示,文档说明迁移。

## Migration

- **配置**:旧 `sandbox.scope` → `workspace_scope`(读旧键映射 + warn);多用户残留 `agent` → 启动期纠正 `session` + warn。`Scope` 枚举保留 `Scope = WorkspaceScope` re-export 别名(shim 不承载逻辑)。
- **存量镜像**:旧 commit 产物成孤儿,运维一次性清理或镜像 GC 兜底;`_image_for` 改查声明式镜像、无则回退基础镜像。
- **存量 workspace**:single-tenant `agent` 数据目录沿用;multi-tenant 由 `sandbox-workspace-gc`(地基)兜底。
- **agent.yaml**:新增 per-agent 镜像持久化开关 + `setup_command`(schema-only,`extra=forbid`,缺省关闭/空,默认行为不变)。

## Open Questions

- 离线 build 的触发时机:agent 启动期自动 build vs 显式 `fleetent-admin` 命令 build vs 首次 acquire 惰性 build?(契约不依赖此项,实现期定;倾向显式命令 + 启动期检测缺失镜像告警,避免启动期长阻塞。)
- `setup_command` 的失败处理:build 失败时该 agent 是回退到"无依赖镜像 + 运行期基础镜像"还是拒绝启动?(倾向回退 + 告警,保持 agent 可用性;运行期工具按需在容器内临时装,只是无热启动。)
- 是否需要为不可变镜像引入显式版本/内容哈希标签以支持 `setup_command` 变更后的重建检测?(可复用既有 config-hash 思路,实现期评估。)
