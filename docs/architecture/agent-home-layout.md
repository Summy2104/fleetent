# Agent 侧目录与文件组织（FLEETENT_HOME 布局 + 生成职责）

> 现状参考（截至 materialize-complete-env 合并后）。描述 `FLEETENT_HOME` 下的目录树、每个路径**由谁生成、何时生成**，以及"物化产物 vs 运行时数据 vs node 状态"的职责边界。供理顺/重构这块时对照。

## 生成者图例

| 标记 | 生成者 | 触发时机 |
|---|---|---|
| `[PLAT]` | 控制面（platform） | Alembic 迁移（建管理库）/ `materialize_from_store` DB→file 导出（`server.py` agent 生命周期事件触发）/ server lifespan |
| `[NODE]` | node（`fleetent node start`） | provision（写 `node/.env`）+ reconcile（materialize agent home、写缓存/hash、擦除停用 agent 的 .env） |
| `[AGENT]` | agent 进程（`fleetent agent run`） | 进程启动/运行时（建 `data/` 子树、写 `.fleetent.pid`、写会话/日志/向量库） |
| `[CLI]` | fleetent 脚手架 | `fleetent agent init`（standalone 模板）/ dev 脚本（`dev_node_provision.py`、`dev_secret_key.py`） |
| `[OPER]` | 运维/人工 | 手写配置（`platform.yaml`、平台 `.env`），非自动生成 |

> 真正生成 agent home 的"物化器"有三家（按部署模式三选一）：**[NODE] reconcile**（managed）、**[PLAT] materialize_from_store**（平台 DB→file 导出）、**[CLI] agent init**（standalone 脚手架）。三者写同一套 `agent.yaml` / `.env` / `skills/`。

## 路径解析（`paths.py`）

`base_dir()` = `FLEETENT_HOME` 环境变量 > 仓库根（含 `platform.yaml.example`）> `~/.fleetent`。其余全部派生：

```
data_dir()        = base/data
agents_dir()      = base/agents
agent_home_dir(id)= base/agents/<id>
agent_data_dir(id)= base/agents/<id>/data
sessions_dir()    = base/data/sessions
workspaces_dir()  = base/data/workspaces
platform_yaml     = base/platform.yaml
platform_env      = base/.env
```

## FLEETENT_HOME 顶层

```
FLEETENT_HOME/
├── platform.yaml                      [OPER]  平台配置（手写）
├── .env                               [OPER]  平台级 env（手写）
│
├── data/                              全局数据根（平台主机）
│   ├── management.db                  [PLAT]  管理库 · 控制面权威（Alembic 维护）
│   ├── <tenant>/                      per-tenant 物理分区（tenant_router）
│   │   ├── kb.db / kb_vectors.db      [AGENT] KB 关系表 + 向量
│   │   ├── shared_memory.db (+vectors)[AGENT] 共享记忆 + 向量
│   │   └── state.db                   [AGENT/CLI] 非重定向 agent-side state（见“已知毛刺”#3）
│   ├── traces.jsonl                   [AGENT] eval logger 全局轨迹
│   ├── sessions/  workspaces/         [AGENT] 全局（非重定向）会话 / 沙箱工作区
│   └── logs/
│
├── node/                              node 身份与状态（仅 agent 宿主）
│   ├── .env                           [CLI/NODE] provision：service key + 平台 URL + node id
│   ├── desired-state-cache.json       [NODE]  reconcile/provider 缓存（剥除 secret）
│   └── applied-config-hashes.json     [NODE]  reconcile 的 config-hash 记账
│
└── agents/<id>/                       per-agent home（详见下）
```

## 单个 agent home（`agents/<id>/`）

```
agents/<id>/
├── agent.yaml          物化产物 · 完整配置（exclude_defaults=False 全字段）
│                       写者：[NODE] reconcile._write_home（managed）
│                            | [PLAT] materialize.write_home / materialize_from_store
│                            | [CLI] fleetent agent init（standalone 模板）
│
├── .env                物化产物 · 0600 · env-only 单一真相（materialize-complete-env 后）
│                       内容：collect_env_var_names() 收集的【全部】被引用 *_env 名
│                            + 真实 secret 值（managed 来自 desired-state.secrets；
│                              standalone 来自 operator/既有值；无值则空占位）
│                            + FLEETENT_TUI_TOKEN（保留或新生成）
│                       写者：同 agent.yaml 三家；node 经 ensure_env_scaffold(secrets=…) 写值
│
├── .fleetent.pid       [AGENT] 进程启动自写 os.getpid()（agent_app.py）；backend 只读做探活
│
├── skills/<name>/SKILL.md
│                       [PLAT] _copy_skills @ materialize（从 skill pool 拷入）
│                       | [AGENT] skill_manage 工具（运行时创建/编辑，过审批门）
│
└── data/               [AGENT] 进程 boot 时建并持有
                        （_redirect_agent_data_paths 把数据落点重定向到 home/data；
                         _init_agent_db_schema + tenant_router 建库；嵌入式迁移 migrate-on-open）
    ├── <tenant>/<id>/agent_state.db (+agent_vectors.db)   per-agent（traces/memory/approvals/sessions 元数据…）
    ├── <tenant>/<id>/agent_memory.db (+vectors)            per-agent（agent 记忆；原 shared_memory 已去 scope 迁至 per-agent）
    ├── <tenant>/kb.db (+kb_vectors)                        per-tenant
    ├── sessions/<sid>.json (+.lock)                        会话持久化（原子写 .tmp→rename）
    ├── logs/<date>.log
    ├── diagnostics/                                        诊断导出
    ├── workspaces/                                         沙箱工作区（bind-mount 进容器）
    └── im_approvals.json                                   IM 用户准入本地状态
```

## 职责边界（核心原则）

```
物化产物（agent.yaml / .env / skills/）   →  物化器写（[NODE] | [PLAT] | [CLI]，按模式三选一）
运行时数据（整个 data/ 子树 + .fleetent.pid）→  [AGENT] 进程自己在 fleetent agent run 时建
node 状态（node/）                          →  [NODE] 自己（provision + reconcile）
管理库（data/management.db）                 →  [PLAT]（Alembic）
```

- secret 经 `GET /nodes/{id}/desired-state` 的独立 `secrets` 字段下发到 node（config 已 strip），node 写进 agent `.env`（0600）；**不再** spawn 时注入进程 env（materialize-complete-env D1）。
- env 名收集器全局唯一：`agent_config.collect_env_var_names()`（flatten 全 `*_env`），node 与平台共用；`agent_init.referenced_env_names` 是其薄 re-export。
- agent 运行时数据只落 agent 侧（per-agent / per-tenant 库），严禁写入平台管理表（AGENTS.md 解耦契约）。

## 已知毛刺（理顺/重构候选）

1. **agent.yaml/.env 有三个 writer**（node reconcile / platform materialize_from_store / agent init）；单机 managed 时 platform 与 node 写**同一** `agents/<id>/` 路径 → 双写、权威归属不清。
2. **`data/` 在两层各出现**：全局 `FLEETENT_HOME/data/`（混 `management.db`[平台] + `<tenant>/…`、`traces.jsonl`、`sessions/`[agent 侧]）与 per-agent `agents/<id>/data/`（重定向）。平台数据与 agent-side 数据在全局 `data/` 混居。
3. **顶层 `data/<tenant>/state.db`**：命名 `state.db`，per-agent 却叫 `agent_state.db`——命名不一致 + 来源含糊（非重定向 agent-side store 的产物，如裸 CLI 默认 agent 运行）。
4. **分区层级不齐**：`data/<tenant>/<agent>/…`（三层）与顶层 `data/<tenant>/…`（两层）并存。
5. **dev 噪音散落 home 根**（非 fleetent 结构，仅 dev/会话产生）：`standalone/`、`logs/*.out`、`*.md`、`.tui-token`、`dev-env.sh`、`chat-ma-key.txt`。
6. **职责边界未在代码/文档显式表达**：上述"物化 vs 运行时 vs node"边界靠反推得出，没有单一处声明，故出现三个物化器各写一份。

---

# 目标态（重构方向）

> 2026-06-23 探索收敛。把上面 6 条毛刺收口为下面的布局 + 一条不变量 + 决策 ledger。

## 目标布局

```
FLEETENT_HOME/
├── platform.yaml / .env / .dev_secret_key   [OPER]  部署/运维配置
├── management.db                            [PLAT]  控制面 · 跨租户单库（裸放根）
├── node/                                    [NODE]  节点身份 · 跨租户（.env + cache + hashes）
└── tenants/<tenant>/                        ← 一个租户的完整足迹 = 一棵子树
    ├── kb.db (+kb_vectors)                  租户级共享：kb-worker 写 / 各 agent 读（并发只读安全）
    └── agents/<name>/                       name=不可变 handle（rename 已移除）；单一 owner
        ├── agent.yaml  .env(0600)  .fleetent.pid  skills/
        └── data/                            [AGENT]  拍平，无 <tenant>/<id>/ 冗余嵌套
            ├── agent_state.db (+vectors)
            ├── agent_memory.db (+vectors)       ← 原 shared_memory：agent 级、去 team/tenant scope
            └── sessions/ logs/ diagnostics/ workspaces/ im_approvals.json
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
| D | KB → `tenants/<t>/kb.db`，**跨 agent 共享**（kb-worker 写、各 agent 只读） | #2 #4 |
| E | shared memory → 正名 **agent memory**，**agent 级**，**删 team/tenant scope**，住 agent `home/data`；跨租户共享靠 promote 到 KB | （新发现：原半成品） |
| F | **租户优先**：`tenants/<t>/agents/<name>/`；name 不可变、作路径键（可读 + 稳定）；单租户接受 `tenants/default/` 一层 | #2 #4 |
| G | dev 噪音：文档钉死 canonical 集合；`make` 等 dev 产物收进非 canonical 位置（如 `.dev/`） | #5 |

## 范围提醒

1. **agent memory 的"读注入"是另一回事**：本重构只管**布局/归属/路径/命名/去 scope**（把它正名 + agent 级 + 落对位置）。让 `agent_memory` 真被 `build_context` 读进上下文 = **功能接通**，是半成品的另一半，**不在本布局重构范围**，单独立项。
2. **大重构、宜切片**：横跨 `paths.py` / `materialize` / `node/reconcile` / `tenant_router` / `agent_app` 数据重定向 / `_init_agent_db_schema` / KB 租户路径 / 全局 data 消除。利好：上线前内测窗口可**重建而非迁移** agent 侧数据（见 [[persistence-redesign-roadmap]] #3 口径），降低风险。

