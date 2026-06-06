## Context

`SandboxClient._resource_flags`（`integrations/sandbox/client.py`）当前只产出 `--memory` / `--cpus` / `[--network none]` / `[--read-only]` / `--tmpfs /tmp`。`SandboxResources`（`config.py`）已支持从 `sandbox.resources` 逐字段加载并校验，`build_resources_by_scope` 已把 session/agent 两档资源映射出来（agent 档强制 `read_only=False`）。本 change 在这套既有结构上**追加加固字段**，不动 network 三态、`read_only`、`exec_timeout` 的既有需求。

参考对标：hermes-agent 的 Docker 后端默认 `--cap-drop ALL` + 最小 `--cap-add`、`--security-opt no-new-privileges`、`--pids-limit 256`、`--tmpfs /tmp:rw,nosuid,size=512m`、`--init`、可选非 root；openclaw 默认 `--cap-drop ALL` + `no-new-privileges` + read-only + tmpfs。fleetent 当前这些全缺。

## Goals / Non-Goals

**Goals:**
- 让默认 `docker run` 命令带上业界标准容器加固，堵住 fork 炸弹、`/tmp` 撑爆宿主内存、容器内 root+全能力、僵尸进程四条敞口。
- 加固参数按 scope 分层：session 最严，agent 为 pip 安装留最小放行。
- 全部可配置、非法回退安全默认，沿用既有加载/校验模式，零新依赖。

**Non-Goals:**
- 不实现自定义 seccomp/AppArmor profile（依赖 Docker 默认 profile，留待后续）。
- 不实现磁盘配额 `--storage-opt`（仅 overlay2+XFS pquota，环境脆弱）。
- 不改 network 三态、`read_only`、`exec_timeout` 的既有行为。
- 不改 `run_code` 工具的对外输入/输出契约。

## Decisions

**D1：新建 capability `sandbox-container-hardening`，不把需求挂到 `sandbox-resource-limits`。** 加固是与「资源限额可配置」并列的独立关注点（pids/cap/user/init 不是 memory/cpus 的延伸）。既有 resource-limits 需求与行为不变，仅 `SandboxResources` 数据结构新增字段（实现细节）。替代方案：MODIFIED resource-limits——被否，会把两个关注点的 spec 混在一起，archive 时也更易丢细节。

**D2：scope 分层默认由 `build_resources_by_scope` 设定，而非在 client 里按 scope 分支。** client 保持「按次接收一份 `SandboxResources`，照单构造 flags」的无状态语义（resource-limits 已确立）。session 档用 `SandboxResources()` 的最严默认；agent 档在 `replace(base, ...)` 时覆盖 `cap_add=(CHOWN,DAC_OVERRIDE,FOWNER,SETUID,SETGID)`、`run_as_user=None`。替代方案：client 内 `if scope is AGENT` 分支——被否，会把 scope 策略泄漏进最低层、破坏 per-call 无状态。

**D3：非 root 仅用于 session scope，agent scope 留 root（可配置）。** agent scope 要 `pip install` 写系统 site-packages 并 `docker commit` 固化依赖镜像，非 root 会把依赖装到某个可写 HOME/venv、复杂且与既有 commit 流程冲突。session scope 只读+只跑代码，nobody 足矣。`run_as_user` 可配置：置 null 即回退 root（给确需 root 的 session 工作负载留出口）。替代方案：全程非 root——被否，过于脆弱且动 commit 流程。

**D4：`/tmp` 加 `nosuid,size=`，不加 `noexec`。** `nosuid` 阻断 /tmp 内 setuid 提权、`size=` 封住 RAM 耗尽，二者零副作用。`noexec` 会破坏 pip/构建工具偶从 /tmp 执行临时脚本的行为，故不加。默认 `tmpfs_size_mb=64`（保守；可配置，数据分析类 agent 可调大）。

**D5：agent cap_add 取最小依赖安装集。** `CHOWN/DAC_OVERRIDE/FOWNER` 覆盖包管理器改属主/权限/越权读，`SETUID/SETGID` 覆盖装包过程偶发的降权调用——与 hermes 的「以 root 启动时」放行集一致。session 档不补任何 cap（只跑代码不装包）。

**D6：默认值取保守安全档。** `pids_limit=256`（与 hermes 一致，足够正常并发又能挡 fork 炸弹）。这些是 dataclass 字段默认值——`SandboxResources()` 即「最严 session 档」的单一事实源。

## Risks / Trade-offs

- **[非 root 破坏个别 session 工作负载]**（需要写 HOME/`~/.cache`、或需 root 的代码）→ 缓解：`run_as_user` 可配置，置 null 回退 root；仅影响 session scope；agent scope（装依赖处）仍 root。
- **[cap-drop ALL 破坏 agent scope 的 pip]** → 缓解：agent 档显式补最小安装能力集，并由 `test_sandbox_client` 断言 agent 档命令含这些 `--cap-add`。
- **[tmpfs 64m 对大临时文件偏小]** → 缓解：`tmpfs_size_mb` 可配置。
- **[pids 256 对高并发偏低]** → 缓解：`pids_limit` 可配置；默认值已较宽。
- **[默认 docker run 命令变更=内部 BREAKING]** → 缓解：`run_code` 对外契约不变，只更新本仓 `test_sandbox_client` 既有 flag 断言；文档记录变更。
- **[`--init` 依赖 Docker daemon 支持]** → 自 Docker 1.13 起为标准能力，on-prem 部署的 Docker 均满足；不满足时该 flag 由 Docker 直接报错（显式失败而非静默降级），可经配置 `init=false` 关闭。

## Migration Plan

纯加性配置，无数据迁移。默认值即安全加固档，升级后自动生效。回退策略：将相应字段配置为关闭（`cap_drop_all=false` / `no_new_privileges=false` / `init=false` / `run_as_user: null` / 调大 `pids_limit`、`tmpfs_size_mb`），或回滚本 change。
