## Why

当前沙箱生命周期把**两个本应独立的维度**焊死在单一 `scope` 字段上(`integrations/sandbox/manager.py`):

1. **数据隔离粒度**——容器名 key 与 workspace 宿主目录 key(谁能看到谁的文件);
2. **依赖镜像持久化**——是否把安装的依赖固化成镜像、跨会话复用。

`acquire`(:124)用单一 `key` 同时驱动容器名 / workspace 路径 / 镜像三维;`_image_for`(:190)硬编码 `scope is Scope.AGENT` 才查固化镜像;`sweep_idle`(:265)只 commit `Scope.AGENT`。这导致两条都需要修的问题:

- **`agent` scope 数据隔离是反隔离档**:它让**同一 agent 下所有用户共享一个 workspace 宿主目录与一个容器**——用户 B 直接读到用户 A 的上传/产物。`session` scope 才符合 `agent-data-isolation` 的跨归属隔离要求。一旦把"镜像持久化"这个唯一正当用途从 `agent` scope 里拆出去,`agent` scope 作为**数据隔离档**就再无存在理由,必须删除(留着就是一个随时被误配出跨用户泄露的脚枪)。
- **`docker commit`-from-running-container 是不可变性与封闭性的双重漏洞**:`sweep_idle` 对一个**已运行、已被用户 A 改写过 rootfs** 的容器执行 `docker commit`(`backends/docker.py:292`),把用户 A 的 site-packages、`sitecustomize.py`、临时写入**烤进**下次为同一 agent 启动的镜像——污染流向后续所有用户。更糟:`--network none` / `--read-only` 这类运行期加固对**已烤进镜像的内容**完全无效(加固管的是运行期挂载与网络,管不了镜像层里已有的字节)。"盒子封闭才免审批"这一全批安全前提,在依赖持久化形态下被 commit-from-running 悄悄掏空。

这两点都与本序列"沙箱优先执行 → 风险降级 → 免审批"的安全前提冲突,且 `agent` scope 的数据隔离语义与镜像持久化语义在当前实现里**无法分别配置**——必须做一次解耦重构。

## What Changes

把单一 `scope` 拆成两个正交维度,删掉拆解后失去理由的档,并替换危险的镜像固化机制:

- **`workspace_scope`(数据隔离维度)**:新增/正名一个**只管数据隔离**的粒度选择 `workspace_scope`(`session` 默认 | `agent`),决定容器名 key 与 workspace 宿主目录 key、以及容器存活归属(进程隔离边界)。**删除 `agent` 作为数据隔离档**——`acquire` / `workspace_host_path` / 容器名派生不再接受 `agent` 数据隔离 key(拆出镜像维度后它只剩"同 agent 跨用户共享一个目录"这一反隔离效果)。**多用户场景下 `workspace_scope` 经校验强制为 `session`**(配 `agent` 数据隔离 = 跨用户泄露,启动期拒绝/纠正并告警)。
- **per-agent 镜像持久化(依赖维度,独立开关)**:把"同一 agent 跨会话复用已装依赖"这一正当需求从 `agent` 数据 scope 里**独立出来**,改用**声明式离线 build 不可变镜像**:
  - 依赖经 `setup_command`(agent 预声明)在**离线构建阶段**装进一个**不可变镜像**(deps 层),运行期容器以**只读** rootfs 从该镜像启动;
  - **禁用 `docker commit`-from-running-container**——`sweep_idle` 不再对运行容器 commit,`_image_for` 不再查"上次 commit 的镜像",改为查"声明式构建产出的不可变镜像";
  - 按后端能力分级:`persist_workspace=True`(Docker)支持构建并复用不可变镜像 + 秒级热启动 deps 层;`persist_workspace=False`(microsandbox)**声明**热启动不成立(无 image-commit 原语)——运行期从基础镜像 + setup 重新就绪,且 MUST 在文档/日志明示该后端不享受秒级热启动。
- **生命周期解耦**:`acquire` 的容器名/路径 key 只由 `workspace_scope` 派生;镜像选择(`_image_for`)只由 per-agent 镜像持久化开关 + 后端能力派生;`sweep_idle` 改为**纯按容器存活/闲置回收**,不再 commit;`_Entry` 的 key 派生中心不变式(同 key→同名→同目录)保持,但 key 来源收敛到 `workspace_scope`。

- **本 change 明确不做**:
  - 不翻任何工具默认免审批、不改 registry risk 常量、不改 `action_gate.resolve_action_mode` 契约(归"放松管制"change);
  - 不碰 `sandbox-lifecycle` 的「命名/碰撞」requirement 块(地基 `sandbox-isolation-foundation` 已改,本 change 只改「scope 粒度/镜像选择」块);
  - 不碰 `sandbox-workspace-mount` 的 key 派生无碰撞条款(地基已改);
  - 不改 agent/platform 解耦方向(运行时模块仍 MUST NOT import `fleetent.platform.*`)。

## Capabilities

### New Capabilities
- `sandbox-workspace-scope`: `workspace_scope`(`session` 默认 | `agent`)**只控制数据隔离**粒度(容器名 key + workspace 宿主目录 key + 容器存活归属),与镜像持久化解耦;多用户场景经校验强制 `session`;**删除 `agent` 作为数据隔离档**——拆出镜像维度后 `agent` 数据隔离只余跨用户共享一个目录的反隔离效果,故只保留 `session` 数据隔离 + 独立 per-agent 镜像开关。
- `sandbox-image-persistence`: per-agent 依赖镜像持久化改用**声明式离线 build 不可变镜像**(`setup_command` 离线构建 deps 层、运行期只读启动),**禁用 `docker commit`-from-running-container**(会把用户 A 的 rootfs/sitecustomize 烤进用户 B 镜像,且 network/read_only 对 baked 内容无效);按后端 `persist_workspace` 能力分级(`False` 时秒级热启动不成立,须显式声明、运行期重新就绪)。

### Modified Capabilities
- `sandbox-lifecycle`: 只改「scope 粒度/镜像选择」requirement 块——容器存活粒度(进程隔离)由 `workspace_scope` 决定、依赖镜像(共享)由独立 per-agent 镜像持久化开关决定,二者解耦;`acquire`/`_image_for`/`sweep_idle`/`_Entry` 的 key 派生中心不变式(同 key→同名→同目录)不变但 key 来源收敛到 `workspace_scope`;镜像复用改为声明式不可变镜像,回收不再固化运行容器。**不碰地基已改的「命名/碰撞」块。**

## Impact

- **代码**:
  - `integrations/sandbox/manager.py`:`Scope`→`WorkspaceScope` 语义收敛;`acquire`(单 key 仅派生容器名/路径,镜像走独立分支)、`_image_for`(改查声明式不可变镜像、不再查 commit 产物)、`sweep_idle`(纯按闲置回收、移除 commit-then-destroy)、`_Entry` key 派生中心。
  - `integrations/sandbox/config.py`:`SandboxLifecycle` 的 `scope` 正名为 `workspace_scope`(只剩 `session`/`agent` 两值,且 `agent` 仅作 single-tenant 数据隔离;多用户校验强制 `session`);新增 per-agent 镜像持久化与 `setup_command` 配置加载(per-field 校验、缺省安全)。
  - `integrations/sandbox/backend.py` + `backends/docker.py` + `backends/microsandbox.py`:`commit_workspace`(running-container commit)从生命周期热路径退役;新增/改用声明式 build 原语(Docker:从 setup 构建不可变镜像;microsandbox:`persist_workspace=False`,声明热启动不成立、运行期重新就绪)。`BackendCapabilities.persist_workspace` 语义由"能 commit 运行容器"收敛为"能构建并复用不可变 deps 镜像"。
  - `agent_config.py`:`SandboxSettings` 新增 per-agent 镜像持久化开关 + `setup_command`(schema-only 校验,extra=forbid)。
- **复用而非新建**:免审批仍复用 `action-gate`(`resolve_action_mode` SANDBOX→fail-closed→APPROVAL 契约不变,本 change 不喂它新真值);镜像不可变性是对既有 `read_only`/`network` 加固的**补强**(运行期只读启动),不引入新加固原语。
- **模块边界声明**:
  - owning package:`integrations/sandbox`(scope 语义收敛、镜像构建/选择、生命周期解耦)、`agent_config`(per-agent 镜像/`setup_command` schema)。
  - public API surface:`SandboxManager.acquire` / `workspace_host_path` / `container_name` / `invalidate` / `release_session` / `sweep_idle`(签名保持兼容,scope 实参语义收敛为 `WorkspaceScope`);后端 `BackendCapabilities`(`persist_workspace` 语义收敛)与新构建原语为 `integrations/sandbox` 内部 public,`_image_for`/`_container_name`/`_sanitise`/`_agent_image_tag` 为 internal。
  - owned tables:无(workspace 为文件系统、镜像为容器运行时产物,均不落 DB)。
  - config namespace:复用 `sandbox.*`(`workspace_scope` 正名自 `scope`;新增 `sandbox.image_persistence.*` / `sandbox.setup_command` 等子键,均归 `sandbox` 命名空间)、`agent.yaml` 的 `sandbox.*` 子树;**无新增顶层命名空间**。
  - cross-module dependencies:`tools`(`builtin_tools._get_manager` / `init_sandbox_manager`)与 `runtime` 经 `integrations/sandbox` public API 调用,语义收敛后调用点同步;**不 import `fleetent.platform.*`**,保持 agent/platform 单向解耦;agent 须仍能在无 platform、platform 表不存在环境 `fleetent agent run`。
  - migration / shim plan:这是**高风险重构**,迁移与兼容处理:
    - **配置兼容**:旧 `sandbox.scope: agent` 在单租户下等价新 `workspace_scope: agent`;多用户部署若残留 `scope: agent`,启动期校验**纠正为 `session` 并告警**(不静默接受)。`Scope` 枚举若被外部 import,保留 `Scope = WorkspaceScope` re-export 别名(shim 不承载逻辑)。
    - **存量镜像**:旧 `fleetent-sandbox-agent-<key>:latest`(commit 产物)成孤儿,不再被 `_image_for` 查找;由一次性运维清理或既有镜像 GC 兜底(低危,可重建)。`_image_for` 改查声明式不可变镜像标签;无声明式镜像时回退基础镜像(行为安全)。
    - **存量 workspace**:`agent` 数据 scope 目录在拆除后不再被 `agent` 数据 key 命中;single-tenant 沿用、multi-tenant 由 `sandbox-workspace-gc`(地基)兜底。
- **测试**:
  - unit:`workspace_scope` 只派生容器名/路径(镜像选择走独立分支、与 `workspace_scope` 解耦);多用户校验强制 `session`(配 `agent` 被纠正 + 告警);`_image_for` 只看镜像持久化开关 + 后端能力、不看 `workspace_scope`;`sweep_idle` 不调用 `commit_workspace`(纯闲置回收);`persist_workspace=False` 后端声明热启动不成立。
  - integration:声明式离线 build 产出**不可变**镜像、运行期只读启动且复用不重装;**回收不污染**——回收/重建后新容器不含上一会话写入容器层的内容(不可变性回归);删除 `agent` 数据隔离后同一 agent 不同 session 取得**相互隔离**的容器与目录(原 `agent` scope 跨用户共享的行为消失)。
- **依赖**:`sandbox-isolation-foundation`(已完成:命名/碰撞修复 + containment 门控 + workspace GC);并基于已合并 main 的 `sandbox-lifecycle`、`sandbox-workspace-mount`、`sandbox-backend-abstraction`、`microsandbox-backend`、`agent-data-isolation`。
