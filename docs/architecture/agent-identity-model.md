# Agent 身份模型与迁移设计

> **状态：阶段 2–5 已全部落地**。本文锁定 agent 标识在平台侧 / agent 侧的统一模型，并给出完整迁移详设。阶段 2（`unify-agent-binding-id`）已于 2026-06-13 落地 `agent_kbs` / `agent_skills` 的 INTEGER+FK 规整与 `agent_skills` 控制台绑定 bug 修复；阶段 3–5 随后完成平台关系表归一、FK 完整性、`traces.agent_name` 正名、读写翻译边界收口与守护测试。`data-model.md` 已回填最终 as-built 状态。
> 背景与往返论证（为何不是 slug-everywhere、为何不用 UUID、rename 安全性）见本文 §1 + `records/decision-logs/`。

## 1. 问题与目标

### 1.1 现状的乱（实测）
agent 在系统里没有统一标识符，跨表、跨平面各行其是：
- `agents.id` 是 **INTEGER 自增主键**；但 `agents.name` 是 **UNIQUE** 的人类可读标识，且曾同时被拿来当物理目录 `agents/<name>/`、`agent_admin_state` 主键、`session_meta.agent_name`、`traces.agent_id`、agent.yaml `name`、channel 路由 的实际键。
- 平台关系表引用 agent 时**三种写法混用**：多数存 INTEGER `id`；`agent_kbs`/`agent_skills` 曾存**字符串化的 agent id**（TEXT）；`agent_admin_state`/`session_meta` 存 `name`。
- 后果：① 跨表 JOIN 要 CAST（TEXT vs INTEGER）；② `agent_skills` 出现**真 bug**——控制台按 name 写、materialize 按字符串 id 读，控制台设的 skill 绑定运行时静默失效；③ 多数绑定表无 FK、agent 删除留孤儿。

### 1.2 rename 的脆性（设计动机）
迁移前"`agents.name` 不可变"只靠"删了 rename 代码 + 守护测试 + spec 一行"撑着——是**政策不是不变量**。产品迟早要 rename（打错字/改品牌/重组）。若 name 是全系统 FK 键 + 物理目录名，rename 回来就是灾难级级联（重写所有绑定表键 + 搬物理目录）。本模型落地后关系键全挂 `id`，name 已成可变标签——rename 不再有关系级联（见 §2.3）。

### 1.3 目标
- agent 标识在两个平面各自**内部一致**，翻译收口到少数边界点（不再满地字符串化 id 包装）。
- 关系完整性**不依赖任何可变标识**——rename 廉价、零关系级联。
- 物理目录保持**可读**，不引入 UUID。
- 修掉 `agent_skills` 的 name/id 混写 bug；补齐绑定表 FK。

## 2. 模型

把 `agents.name` 现在揉在一起的两个概念拆开：**身份**（不可变、做关系键）与 **可读标签**（可变、做物理/显示）。

| 概念 | 载体 | 性质 | 谁引用 |
|---|---|---|---|
| **身份** | `agents.id`（整数代理键） | 不可变、**永不暴露给人/物理层** | 平台所有关系表 FK → `agents.id` |
| **可读标签** | `agents.name`（slug） | 可变、可由 id 重新派生 | 物理目录、agent 侧（traces / agent.yaml）、显示 |

关系完整性只挂在 `id` 上（真正的不可变代理键，从不暴露）。`name` 变不变都不影响完整性——**这就是 rename 安全性的结构保证：不需要保证 name 不变**。

### 2.1 两条规则（规范）
- **R1（平台侧）**：agent name **只存在于 `agents` 表一列**；其余所有跟 agent 有关的平台表存 **`agent_id`（INTEGER，FK→agents.id）**，永不存 name。
- **R2（agent 侧）**：所有需要 agent 标识的地方用 **name**；agent 侧不出现 agent id（含 DB 列名）。

### 2.2 两个翻译边界（name↔id 只在这两处发生）
- **写边界 = materialize / boot**：平台内部全程用 id 解析；落地 agent 产物时把 **name 盖到** 物理目录 / agent.yaml / agent 侧 traces。平台 id 永不进 agent 侧。
- **读边界 = platform 读侧投影 / observability**：平台读 agent 侧数据（traces/sessions，按 name）关联回平台 agent（按 id）时，用 `agents` 表做一次 **name→id 解析**。

两个边界都在平台侧、都手握 `agents` 行、都是廉价 join——翻译收口于此，不散落。

### 2.3 rename 语义
rename = 改 `agents.name` 一行（全系统唯一存 name 处）→ 平台 FK 全挂 id、**零级联**；下次 re-materialize 重刷 agent 产物（目录搬迁 + agent.yaml 重写）；`traces` 历史行保留旧 name（日志不改史，合理）。改名罕见、且不碰关系完整性。

## 3. 迁移详设（完整）

> 当前 alembic head = 081；agent_state 嵌入式 Y 最新 = v34。所有版本号落地时 append、以实际为准。处于"上线前不迁移数据"窗口——存量可重置，迁移仍按对存量友好写。

### 3.1 平台侧（管理库 · Alembic）→ 全部归一到 agent_id INTEGER + FK

| 表 | 现状 | 目标 | 数据迁移要点 |
|---|---|---|---|
| `agent_kbs.agent_id` | TEXT 存 `str(id)` | INTEGER + FK→agents.id ON DELETE CASCADE | `CAST` 数字串→int |
| `agent_skills.agent_id` | TEXT 存 `str(id)` **或 name（bug）** | INTEGER + FK→agents.id ON DELETE CASCADE | 数字串→`CAST`；**name 串→经 agents 解析 name→id，解析不到则丢（本就静默失效行）** |
| `agent_admin_state` | 主键 = `agent_name` | 主键/键 → `agent_id` + FK | 经 agents 解析 name→id 重建 |
| `session_meta` | `agent_name` 列 | `agent_id` 列 + FK | 经 agents 解析 name→id；`user_id` 列不动（用户身份，不在本范围） |
| `user_agents` / `channel_agents` / `agent_versions` / `mcp_servers`（原 `agent_mcp_servers`，见下「MCP 表改名」） / `agent_secrets` | 已 INTEGER id、**无 FK** | 补 FK→agents.id ON DELETE CASCADE | 无值变更，仅加约束（FK 已全局启用，见 data-model §2） |
| `agent_mcp_servers`（原 `agent_mcp_server_bindings`，见下「MCP 表改名」） / `agent_oauth_bindings` | 已 INTEGER + 已有 FK | 改名（FK 不变） | — |
| `connectors.agent_id` | INTEGER、休眠列（never written） | 维持现状（休眠），**不强加 FK**；文档注明 | — |

> **MCP 表改名（阶段 4 并入，方案 A）**：当前两张 MCP 表命名与 skills/kbs 不一致、且角色反着——`agent_mcp_servers` 其实是**定义/注册表**（存 transport/url/auth，含全局 `agent_id=NULL` 行），却长得像绑定表；真正的绑定是 `agent_mcp_server_bindings`。阶段 4 一并正名，对齐 `agent_skills`/`agent_kbs`（绑定 = `agent_<物>`）与 `connectors`（注册表无 `agent_` 前缀）两条既有惯例：
> - `agent_mcp_servers`（定义/注册表）→ **`mcp_servers`**（注册表去 `agent_` 前缀；同批补 FK）
> - `agent_mcp_server_bindings`（绑定）→ **`agent_mcp_servers`**（沿用既有 FK）
> - 终态：`mcp_servers`（注册）+ `agent_mcp_servers`（绑定），与 skills/kbs 完全并行。
> - **换名顺序避碰**：先 `agent_mcp_servers`→`mcp_servers` 腾名，再 `agent_mcp_server_bindings`→`agent_mcp_servers`，两步顺序换、**无需临时名**。
> - 代码面：`agent_mcp_server_store.py`（注册表 SQL→`mcp_servers`）、`agent_store.py` 的 bind/unbind/list（绑定 SQL→`agent_mcp_servers`）、索引 `idx_agent_mcp_servers_agent`→`idx_mcp_servers_agent`；store 文件/函数名建议随动以免「表名已正、代码名仍反」。

### 3.2 agent 侧（agent_state.db · 嵌入式 Y）→ 全部 name、列名也不出现 id

| 落点 | 现状 | 目标 |
|---|---|---|
| `traces.agent_id`（TEXT，**已存 slug**） | 列名误导（叫 id 实存 name） | **列改名 → `agent_name`**（内容不动；嵌入式 Y `RENAME COLUMN`） |
| 物理目录 `agents/<name>/` · agent.yaml `name` | 已 name | 不变 |
| `sub_agent_runs.name`（子任务标签）· `scheduled_tasks.name`（任务名） | 不是 agent slug | 不动（排除，勿误判） |

kb.db / shared_memory.db 无 agent 标识列，不涉及。

### 3.3 代码侧改动

- **materialize**（写边界）：平台关系表写入用 `agents.id`；agent 产物（目录/agent.yaml/agent 侧 traces 上下文）盖 `agents.name`。
- **read-projection / observability**（读边界）：读 agent 侧 traces/sessions 后，按需 `agents` 表 name→id 解析关联平台 agent。
- **`agent_skills` bug 修复**：`agent_management_console.set_agent_skill` 当前传 `name` 给 `set_binding`——改为先解析 name→id 再写（与 materialize 的 id-keyed 读对齐）；`skill_admin_api` 已传 id（去 `str()` 包装，传 int）。
- **`agent_admin_store` / `session_admin_store`**：键/列从 name 改 id；调用方（server.py status 查询、console、chat admin、askit apply）改为传/解析 id。
- 全仓清理字符串化 id 包装与按 name 查平台绑定表的残留。

## 4. 分阶段落地（每阶段一个 OpenSpec change）

> 安全相关（agent 解析、删除级联），分阶段降风险；每阶段对照 main 基线零回归。

1. **阶段 2 — agent_kbs / agent_skills 归一 + 修 bug**（已完成，2026-06-13）：TEXT→INTEGER + FK；修控制台 name-写。落地 change：`unify-agent-binding-id`。
2. **阶段 3 — agent_admin_state / session_meta 归 id**：键/列 name→id + FK + 调用方改造。
3. **阶段 4 — 补齐绑定表 FK + MCP 表正名**：user_agents / channel_agents / agent_versions / agent_secrets 及 MCP 注册表补 FK→agents.id ON DELETE CASCADE；并一并执行 MCP 两表方案 A 改名（`agent_mcp_servers`→`mcp_servers` 注册表、`agent_mcp_server_bindings`→`agent_mcp_servers` 绑定，见 §3「MCP 表改名」）。
4. **阶段 5 — 翻译边界固化 + 守护（含 agent 侧列正名）**：materialize 写边界 / read-projection 读边界的 name↔id 收口；**`traces.agent_id` → `agent_name` 列正名**（纯美容 R2 合规，并入此阶段而非单列——见下）；守护测试断言"平台关系表无 name 列（除 agents）、agent 侧无 agent id 列/标识"。已完成。

> **决策（2026-06-13）**：原"阶段 1 = traces 列正名先做"已撤销。该改名纯属 R2 美容合规（列本已存 slug、零行为/完整性收益），却牵动 observability/agent-observability-view 两个 spec 的 5 条 requirement + 与彼时在跑的 trace-tool-spans 撞同一文件——性价比与时机均差。故并入阶段 5 的守护/清理一并做。Alembic 单链使阶段 2/3/4 本就串行；逐个 just-ahead propose（最多领先 applied frontier 一片）。

## 5. 风险与权衡

- [agent 解析是安全核心，改键有回归风险] → 分阶段 + 每阶段对照基线零回归 + 守护测试锁规则
- [agent_skills 存量行混入 name（bug 产物）] → 迁移时 name→id 解析、解析不到丢弃（本就静默失效）；pre-launch 窗口亦可重置
- [读边界 name→id 解析遗漏 → 平台关联错] → 收口到 read-projection 一处 + 测试覆盖"按 name 的 agent 侧数据正确关联回 id"
- [rename 后 traces 历史按旧 name] → 接受（日志不改史）；如需聚合跨 rename，按 agents 当前 name 解析时附历史别名（暂不做，YAGNI）
- [connectors.agent_id 休眠列不补 FK] → 接受（never written）；文档注明，待真实接入再规整

## 6. 守护规则（落地后长期约束）

- 平台关系表新增 agent 引用列 MUST 为 `agent_id` INTEGER FK→agents.id（除 `agents.name`，name 不得出现在其它平台表）
- agent 侧新增 agent 引用 MUST 用 name（slug），MUST NOT 出现 agent id（含列名）
- name↔id 翻译 MUST 只在 materialize（写）/ read-projection（读）两处；其它代码不得做该翻译
- 守护测试强制以上三条

## 7. Open Questions
（无——身份模型、两规则、两翻译边界、rename 语义、分阶段均已与用户敲定。）
