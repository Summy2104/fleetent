# Agent 侧目录与文件组织（FLEETENT_HOME 布局 + 生成职责）

> tenant-first layout 的 as-built 参考（2026-06-24）。描述 `FLEETENT_HOME` 下的目录树、每个路径**由谁生成、何时生成**，以及"期望态/物化产物 vs 运行时数据 vs node 状态"的职责边界。

## 生成者图例

| 标记 | 生成者 | 触发时机 |
|---|---|---|
| `[PLAT]` | 控制面（platform） | Alembic 迁移（建管理库）/ 暴露 desired-state / skill bundle API / 接收 node status |
| `[NODE]` | node（`fleetent node start`） | provision（写 `node/.env`）+ reconcile（写 agent home、部署 skill bundle、写缓存/hash、擦除停用 agent 的 .env） |
| `[AGENT]` | agent 进程（`fleetent agent run`） | 进程启动/运行时（建 `data/` 子树、写 `.fleetent.pid`、写会话/日志/向量库） |
| `[CLI]` | fleetent 脚手架 | `fleetent agent init`（standalone 模板）/ dev 脚本（`dev_node_provision.py`、`dev_secret_key.py`） |
| `[OPER]` | 运维/人工 | 手写配置（`platform.yaml`、平台 `.env`），非自动生成 |

> 当前不变量：**managed 下 node 是 agent home 唯一 writer**；platform 只生成 desired-state 与 skill bundle。standalone/dev 下由 **[CLI] agent init** 建初始 home，随后仍由 agent 进程自己写运行时数据。

## 路径解析（`paths.py`）

`base_dir()` = `FLEETENT_HOME` 环境变量 > 仓库根（含 `platform.yaml.example`）> `~/.fleetent`。其余全部派生：

```
management_db_path()               = base/management.db
tenant_dir(tenant)                 = base/tenants/<tenant>
tenant_kb_dir(tenant)              = base/tenants/<tenant>/kb
tenant_agent_home_dir(tenant, name)= base/tenants/<tenant>/agents/<name>
tenant_agent_data_dir(tenant, name)= base/tenants/<tenant>/agents/<name>/data
agent_home_dir(name)               = base/tenants/default/agents/<name>   # standalone shim
agent_data_dir(name)               = base/tenants/default/agents/<name>/data
platform_yaml                      = base/platform.yaml
platform_env                       = base/.env
```

## FLEETENT_HOME 顶层

```
FLEETENT_HOME/
├── platform.yaml                      [OPER]  平台配置（手写）
├── .env                               [OPER]  平台级 env（手写）
├── management.db                      [PLAT]  管理库 · 控制面权威（Alembic 维护）
├── logs/                              [PLAT]  platform structured logs 默认目录
├── diagnostics/                       [PLAT]  platform diagnostics export 默认目录
├── node/                              [NODE]  节点身份与状态（仅 agent 宿主）
│   ├── .env                           [CLI/NODE] provision：service key + 平台 URL + node id
│   ├── desired-state-cache.json       [NODE]  reconcile/provider 缓存（剥除 secret，仅保留 manifest 元数据）
│   └── applied-config-hashes.json     [NODE]  reconcile 的 config-hash 记账
└── tenants/<tenant>/                  [PLAT/NODE/AGENT] 一个租户的完整足迹
    ├── kb/                            [AGENT/NODE/OPER] tenant 级 KB 配置 home
    │   ├── kb-service.yaml
    │   ├── .env
    │   └── data/                      [AGENT/NODE] node 只把这一层 RO 挂进 agent（含 -wal/-shm）
    │       ├── kb.db
    │       └── kb_vectors.db
    └── agents/<id>/                   per-agent home（详见下）
```

## 单个 agent home（`tenants/<tenant>/agents/<id>/`）

```
tenants/<tenant>/agents/<id>/
├── agent.yaml          物化产物 · 完整配置（exclude_defaults=False 全字段）
│                       写者：[NODE] reconcile._write_home（managed）
│                            | [CLI] fleetent agent init（standalone 模板）
│
├── .env                物化产物 · 0600 · env-only 单一真相（materialize-complete-env 后）
│                       内容：collect_env_var_names() 收集的【全部】被引用 *_env 名
│                            + 真实 secret 值（managed 来自 desired-state.secrets；
│                              standalone 来自 operator/既有值；无值则空占位）
│                            + FLEETENT_TUI_TOKEN（保留或新生成）
│                       写者：node 或 standalone init；node 经 ensure_env_scaffold(secrets=…) 写值
│
├── .fleetent.pid       [AGENT] 进程启动自写 os.getpid()（agent_app.py）；backend 只读做探活
│
├── skills/<name>/SKILL.md
│                       [NODE] skill bundle deployer（从平台 bundle API 下载、校验、原子部署）
│                       | [AGENT] skill_manage 工具（运行时创建/编辑，过审批门）
│
└── data/               [AGENT] 进程 boot 时建并持有
                        （_redirect_agent_data_paths 把数据落点重定向到 home/data；
                         _init_agent_db_schema + tenant_router 建库；嵌入式迁移 migrate-on-open）
    ├── agent_state.db (+agent_vectors.db)                 per-agent（traces/memory/approvals/sessions 元数据…）
    ├── agent_memory.db (+vectors)                         per-agent（agent 记忆）
    ├── traces.jsonl                                        legacy JSONL trace fallback
    ├── sessions/<sid>.json (+.lock)                        会话持久化（原子写 .tmp→rename）
    ├── logs/<date>.log
    ├── diagnostics/                                        诊断导出
    ├── workspaces/                                         沙箱工作区（bind-mount 进容器）
    ├── tool_spillover/                                     大工具结果落盘
    ├── sandbox_output/                                     run_code 大 stdout/stderr 落盘
    └── im_approvals.json                                   IM 用户准入本地状态
```

## 职责边界（核心原则）

```
期望态（management.db / desired-state / bundle API）→  [PLAT]
物化产物（agent.yaml / .env / skills/）   →  [NODE]（managed） | [CLI]（standalone init）
运行时数据（整个 data/ 子树 + .fleetent.pid）→  [AGENT] 进程自己在 fleetent agent run 时建
node 状态（node/）                          →  [NODE] 自己（provision + reconcile）
管理库（management.db）                      →  [PLAT]（Alembic）
```

- secret 经 `GET /nodes/{id}/desired-state` 的独立 `secrets` 字段下发到 node（config 已 strip），node 写进 agent `.env`（0600）；**不再** spawn 时注入进程 env（materialize-complete-env D1）。
- env 名收集器全局唯一：`agent_config.collect_env_var_names()`（flatten 全 `*_env`），node 与平台共用；`agent_init.referenced_env_names` 是其薄 re-export。
- agent 运行时数据只落 agent 侧（per-agent / per-tenant 库），严禁写入平台管理表（AGENTS.md 解耦契约）。

## 已落地约束

1. **managed 下 node 是 agent home 唯一 writer**；platform 不直接写 managed agent 的真实 home。
2. **管理库在根目录**：`FLEETENT_HOME/management.db`。
3. **租户优先布局**：canonical home = `tenants/<tenant>/agents/<agent>/`。
4. **agent data 拍平**：运行时 DB 与 sessions/logs/workspaces 都落 `<agent-home>/data/`。
5. **KB 是 tenant 级**：配置 home 在 `tenants/<tenant>/kb/`，关系库/向量库/队列库在 `tenants/<tenant>/kb/data/`。
6. **KB 服务可 standalone 运行且 host config / tenant config 分层**：`fleetent kb serve --config kb-service.yaml` 与 `fleetent kb worker --config kb-service.yaml` 共用根 `kb-service.yaml`；每租户只在 `tenants/<tenant>/kb/` 保留 `connectors.yaml` 与 `.env`，而关系库/向量库/队列库继续落 `kb/data/`。node 只把 `kb/data/` RO 挂进 agent，隔离 `kb/` 根与 tenant `.env` 的 secret。

---

# 目标态（重构方向）

> 2026-06-23 探索收敛。把上面 6 条毛刺收口为下面的布局 + 一条不变量 + 决策 ledger。

## 目标布局

```
FLEETENT_HOME/
├── platform.yaml / .env / .dev_secret_key   [OPER]  部署/运维配置
├── management.db                            [PLAT]  控制面 · 跨租户单库（裸放根）
├── logs/ diagnostics/                       [PLAT]  宿主级日志与诊断导出
├── node/                                    [NODE]  节点身份 · 跨租户（.env + cache + hashes）
└── tenants/<tenant>/                        ← 一个租户的完整足迹 = 一棵子树
    ├── kb/                                  租户级共享 KB home：配置在根，数据在 data/
    │   ├── kb-service.yaml
    │   ├── .env
    │   └── data/                            kb-worker 写 / 各 agent 读（node 只 RO 挂这层，含 -wal/-shm；可选 colocated kb-serve 也读同一层）
    │       ├── kb.db
    │       └── kb_vectors.db
    └── agents/<name>/                       name=不可变 handle（rename 已移除）；单一 owner
        ├── agent.yaml  .env(0600)  .fleetent.pid  skills/
        └── data/                            [AGENT]  拍平，无 <tenant>/<id>/ 冗余嵌套
            ├── agent_state.db (+vectors)        state + agent_memory_items（原 shared_memory：agent 级、去 team/tenant scope，并入 state 库 v39）；vectors = mem:* + agentmem:*
            └── traces.jsonl sessions/ logs/ diagnostics/ workspaces/
                tool_spillover/ sandbox_output/ im_approvals.json
```

## 不变量（这就是"职责边界显式表达"）

```
根目录        = 跨租户的东西（控制面 management.db + 节点身份 node/ + 运维配置）
tenants/<t>/  = 该租户的一切（KB + 它的 agents + 各 agent 的运行时数据）
全局 data/    = 取消（traces/sessions/workspaces 归各 agent 自己的 data/；KB 归租户；管理库提到根）
```

## 决策 ledger（探索已锁）

| # | 决策 | 对应毛刺 |
|---|---|---|
| A | agent home 单一 owner = 跑 agent 的那方（managed=NODE / standalone=CLI）；**平台不再写 home**（`materialize_from_store` 退役；仅显式"同机也当 node"模式可保留） | #1 #6 |
| B | `management.db` 独占根；**全局根零 agent 侧文件**（裸 CLI 默认 agent 也走一个 home） | #2 #3 |
| C | per-agent `data/` **拍平**（home 已是 agent 作用域，去掉内层 `<tenant>/<id>/`）；命名统一 `agent_state.db` | #3 #4 |
| D | KB → `tenants/<t>/kb/`，**跨 agent 共享**（kb-worker 写、各 agent 只读；node 整目录 RO 挂载） | #2 #4 |
| E | shared memory → 正名 **agent memory**，**agent 级**，**删 team/tenant scope**，**并入 agent `agent_state.db`（v39，无独立库文件）**；跨租户共享靠 promote 到 KB | （新发现：原半成品） |
| F | **租户优先**：`tenants/<t>/agents/<name>/`；name 不可变、作路径键（可读 + 稳定）；单租户接受 `tenants/default/` 一层 | #2 #4 |
| G | dev 噪音：文档钉死 canonical 集合；`make` 等 dev 产物收进非 canonical 位置（如 `.dev/`） | #5 |

## 范围提醒

1. **agent memory 的"读注入"是另一回事**：本重构只管**布局/归属/路径/命名/去 scope**（把它正名 + agent 级 + 落对位置）。让 `agent_memory` 真被 `build_context` 读进上下文 = **功能接通**，是半成品的另一半，**不在本布局重构范围**，单独立项。
2. **大重构、宜切片**：横跨 `paths.py` / `materialize` / `node/reconcile` / `tenant_router` / `agent_app` 数据重定向 / `_init_agent_db_schema` / KB 租户路径 / 全局 data 消除。利好：上线前内测窗口可**重建而非迁移** agent 侧数据（见 [[persistence-redesign-roadmap]] #3 口径），降低风险。
