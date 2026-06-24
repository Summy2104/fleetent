## Context

`agent-memory-rescope` 已把原 `shared_memory` 收敛为 per-agent `agent_memory`，但物理布局仍保留旧形态：

- `FLEETENT_HOME/data/management.db` 混在全局 data 根下。
- agent home 在 `FLEETENT_HOME/agents/<name>/`。
- agent runtime DB 经 `SQLiteTenantBackend(data_dir=<agent_home>/data)` 再落到 `<tenant>/<agent>/agent_state.db`，在 agent home 内重复嵌套 tenant/agent。
- KB 是 tenant 级资源，但仍通过 `<data_dir>/<tenant>/kb.db` 这套后端语义表达。
- managed 下 platform materialize 与 node reconcile 都可能写 agent home；skill drift/backflow 还依赖 platform 从本机 `paths.agent_home_dir(name)` 读取 agent skill 副本。

这与当前架构契约冲突：managed agent home 的实际 owner 应该是拉起 agent 的 node；platform 是控制面，应该声明期望态、维护公共 skill 池和治理表，而不是写真实运行 home。

## Goals / Non-Goals

**Goals:**

- 建立 tenant-first canonical layout：`tenants/<tenant>/` 是租户完整足迹，`tenants/<tenant>/agents/<name>/` 是 agent home。
- 将 `management.db` 提到 home 根目录，取消 canonical `data/` 全局运行时根。
- 将 agent-side DB 拍平到 agent home 的 `data/` 目录，KB 固定为 tenant-level 文件。
- managed 下 node 成为 agent home 唯一 writer；platform 只生成 desired-state payload。
- 将 skill 文件部署从 platform 写 home 改为 platform bundle cache/API + node 下载部署。
- 将 skill drift/backflow 从 platform 读取本机 home 改为 node 观测真实 home 并按需提供 bundle。
- 保持 agent runtime 对 platform 零反向依赖；agent 仍只读/写自己的 home。

**Non-Goals:**

- 不做旧布局自动迁移；dev/pilot home 重建，生产迁移另立 change。
- 不接通 `agent_memory` 到 `build_context` 的读注入。
- 不让 node 成为 Git client；node 不需要 Git URL、分支或凭据。
- 不做通用文件同步系统；skill bundle 是专用分发机制。
- 不承诺 standalone agent 的 platform backflow 治理闭环。
- 不处理 dev-noise-cleanup；该项已结案为 no-op。

## Decisions

### D1: tenant-first layout 是唯一 canonical 布局

目标布局：

```text
FLEETENT_HOME/
├── platform.yaml
├── .env
├── management.db
├── node/
│   ├── .env
│   ├── desired-state-cache.json
│   └── applied-config-hashes.json
├── skill-bundles/
└── tenants/<tenant>/
    ├── kb.db
    ├── kb_vectors.db
    └── agents/<agent_name>/
        ├── agent.yaml
        ├── .env
        ├── .fleetent.pid
        ├── skills/
        ├── exchange/
        └── data/
            ├── agent_state.db
            ├── agent_vectors.db
            ├── agent_memory.db
            ├── agent_memory_vectors.db
            ├── sessions/
            ├── logs/
            ├── diagnostics/
            ├── workspaces/
            └── im_approvals.json
```

Rationale: 根目录只放跨租户资源；租户资源全部在 `tenants/<tenant>/`；agent home 自带运行时数据，避免全局 data 混入 agent 侧产物。

Alternatives considered:

- 继续 `agents/<name>` + `data/<tenant>/<agent>`：改动小，但无法解决三层路径与 owner 混乱。
- 只移动 DB、不移动 home：会让 KB/DB 与 agent home 分裂，node-owned home 仍不完整。

### D2: managed home writer 归 node

platform managed lifecycle 不再写真实 `agent.yaml/.env/skills`。platform 只做：

- 从管理库构造 agent desired-state payload。
- 维护公共 skill 池与治理表。
- 为 node 提供 bundle API。
- 接收 node 上报的运行与 skill drift 观测。

node reconcile 写入 tenant-aware agent home，并用该 home 拉起 `fleetent agent run`。

Rationale: managed 多机下只有 node 拥有真实文件系统。platform 本机 materialized home 会成为假副本，drift/backflow 都会误判。

Alternatives considered:

- platform 继续写新路径：仍是双写，不能支持远端 node。
- platform 远程挂载 node 文件系统：引入部署假设，不符合 self-hostable 简单部署。

### D3: skill 分为公共池与 agent 部署副本

公共 skill 池仍由 platform 管理，可以是 `FLEETENT_SKILLS_DIR` 指向的独立 Git checkout；builtin skills 随 fleetent 代码发布。agent 本地副本位于 `tenants/<tenant>/agents/<agent>/skills/<skill>/`，由 node 部署，agent runtime 只读/修改自己的副本。

Rationale: 公共池是治理与版本源；agent 副本是 self-contained runtime 输入。两者混为一个目录会破坏独立部署和 drift 判断。

### D4: node 通过 bundle API 获取 skill 内容

desired-state 只下发 skill manifest：

- `name`
- `base_version`
- `base_commit`
- `bundle_url`
- `bundle_sha256`

platform bundle API 返回按版本寻址的 immutable `tar.gz`。platform 默认懒生成 bundle cache：cache 命中直接返回，cache miss 从公共池目录打包到临时文件，校验后原子 rename 到 `skill-bundles/<skill>@<version>.tar.gz`。

node reconcile 仅在本地版本缺失或不同且未 drift 时下载 bundle，校验 hash，解压到临时目录，再原子替换 `skills/<skill>/`。

Rationale: node 不需要 Git 凭据，也不需要理解公共池来源；复杂目录、多级文件通过压缩包自然支持。

Alternatives considered:

- desired-state 内嵌全部文件：payload 大，重复传输，难支持大目录。
- node 直接 `git clone/pull`：每台 node 都要 Git 权限和策略，职责外扩。

### D5: node 观测 skill drift，platform 做治理决策

node 扫描真实 agent home 的 skill 副本，计算 `home_hash`，检测 runtime provenance，与 `base_version` 对比后上报 drift 摘要。platform 将该状态写入治理表或只读投影字段。backflow nomination 不再从 platform 本机路径读文件，而是根据 placement 找 owning node，通过受控 endpoint 拉取真实 `skills/<skill>` bundle。

Rationale: drift 的事实在 node 文件系统上。platform 可以治理，但不应该假装拥有 runtime home。

Alternatives considered:

- agent runtime 直接写 platform proposal：违反 agent→platform 禁止反向依赖。
- platform 调 node 任意文件读取：边界过宽；bundle endpoint 必须限定 skill 目录。

### D6: 不做旧布局自动迁移

本 change 是 breaking layout change。旧 dev/pilot home 需要重建；生产迁移和备份策略单独立项。

Rationale: 旧布局涉及多 SQLite 文件、WAL sidecar、sessions/workspaces、agent home、skills 和管理库。自动迁移会显著扩大风险并遮蔽本 change 的核心目标。

## Risks / Trade-offs

- **Risk: change 横跨路径、node、runtime、platform、skill，范围大。** → tasks 必须按依赖顺序拆分：路径/路由主干先落，再接 node/platform/skill，最后做 guardrails 与全量相关验证。
- **Risk: old docs/spec 仍写 `agents/<name>` 或 `data/management.db`。** → 本 change 更新关键 OpenSpec contracts；长尾 docs 只更新直接引用的能力文档，非阻塞文档可后续 cleanup。
- **Risk: bundle 解压存在路径逃逸风险。** → platform 打包和 node 解包都必须拒绝绝对路径、`..`、`.git`、symlink/hardlink 逃逸。
- **Risk: drift agent 被 reconcile 覆盖。** → node 本地部署必须先检测 drift；drift 时跳过覆盖并上报，直到 reject/accept/fork 决策。
- **Risk: platform read projection 找不到新路径。** → read projection 统一经 tenant-aware `TenantRouter` 和 management DB registry 发现，不拼旧路径。

## Migration Plan

1. 引入 tenant-aware path API 与 router 新布局，保持 default-tenant shim 让部分旧调用可过渡。
2. 修改 runtime boot 与 standalone init/run，使新 home 能独立启动并创建拍平数据文件。
3. 修改 node desired-state/reconcile/backend/forwarder/im-edge 使用 tenant-aware home。
4. 修改 platform lifecycle：managed 写 home 路径退役，保留 payload builder；platform 只读新位置。
5. 增加 skill bundle cache/API、node bundle 下载部署、node drift observation 与 backflow bundle 拉取。
6. 更新 specs/docs 中直接冲突的路径描述。
7. 不迁移旧文件；测试环境和 dev home 重建。

Rollback: 因不做旧数据迁移，回滚代码即可回到旧布局；已用新布局生成的 dev/pilot home 可删除重建。生产自动迁移不在本 change 范围，因此不提供 mixed-layout 回滚。

## Open Questions

无。已确认：

- 使用完整切片。
- skill bundle 由 platform 懒生成 immutable tar.gz cache。
- node 不依赖 Git。
- 不做旧布局自动迁移。
