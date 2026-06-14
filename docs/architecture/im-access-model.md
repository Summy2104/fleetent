# Agent IM 接入与访问控制模型（设计）

> **状态：设计（未实现）**。锁定 agent 在 IM 平台的 bot 接入身份，与三层访问控制（用户准入 / 私群能力 / 群白名单），及"平台配置 → 部署 materialize → agent 侧零-platform-DB 强制"的同步契约。命名采用 **S2（`im` 命名空间）**。与 [agent-identity-model](agent-identity-model.md)、[data-model](data-model.md) 配套。

## 1. 问题与现状（2026-06-14 审计）

**runtime 模型**：**一个 Agent 一个 bot**——agent 在 agent.yaml 声明自己的 bot 凭据，连接器连接**即** agent 身份；消息发给哪个 bot 就是哪个 agent。旧的按频道路由表是"共享 bot 按频道路由"设计的遗骸，runtime 早已不读、已死。

**访问控制现状**：agent.yaml `ConnectorAccess`（`allow_channels` / `allow_users` / `allow_all_users` / `require_approval`），platform materialize 同步、agent 侧本地强制（零 platform DB）。这套"平台配置→部署同步→agent 侧执行"骨架是对的。

**三个缺陷**：
1. **平台配置断线**：平台侧关系表 `user_agents`（用户↔agent）不接 materialize、是死表；agent.yaml 的 `allow_users` 没有平台侧关系源喂它。admin 在平台配的"谁能用这个 agent"传不到 agent 侧。
2. **无私/群能力声明**：闸不看 `chat_type`，agent 无法声明"只支持私聊"或"只支持群"。
3. **群安全默认相反**：空 `allow_channels` = 放行所有频道（**默认开**），agent 可被拉进任意群交互——安全风险。

**命名重载**：「connector」同时指 IM bot 连接 / 工具 OAuth（`connectors` 表）/ KB 数据源（`kb_connectors`）/ owner 级 IM 配置（`im_connectors`），读代码须脑内消歧。

## 2. 实体模型

| 实体 | 含义 | 载体 |
|---|---|---|
| **User** | 内部统一身份 | `users` + `im_users`（平台身份→内部 user 映射） |
| **Agent** | —— | `agents` |
| **IM Platform** | slack / telegram / (whatsapp 见 §9) | `platform` 字段 |
| **Agent IM Binding** | **某 agent 在某平台的 bot 接入**：凭据 + 平台级访问（= 旧 "connector"，本设计正名为 `im`） | agent.yaml `im.<platform>` |
| **Group / DM** | 多人会话 / 1:1 私信（conversation 种类，由 `chat_type` 区分） | `channel_id` + `chat_type` |
| **Thread** | 群内回复串 | `thread_root` |
| **Session** | 会话实例 = binding + group/dm + thread | `session_id` |

> 关键：Agent IM Binding 是**必要的一等概念**——IM bot 的凭据**就是** agent 在平台上的身份。User↔Agent、Group↔Agent 在 runtime 不是 DB 关系，而是从"binding 配置 + 访问策略"涌现。

## 3. 三层访问控制 + 粒度

| 控制 | 粒度 | 为什么 | 载体 |
|---|---|---|---|
| **能力**：`supports_dm` / `supports_groups` | **Agent 级** | 能力是 agent 行为设计内禀、跨平台不变；bot 级=过度设计 | agent 版本化配置 → agent.yaml `im.*` |
| **用户准入**：哪些 User 能用此 Agent | **Agent 级**（判**内部 User**） | 内部身份跨平台一致；平台身份映射归 `im_users` | 平台表 `user_agents`（**保留、不加 im 前缀**——用户准入跨平台、非 IM 专属）→ `im.allow_users` |
| **群白名单**：此 bot 准在哪些群 | **Bot 级**（per 平台） | 群 id 平台特定、无跨平台抽象，被迫 | 平台表 `agent_im_groups` → `im.<platform>.allow_groups` |

> 决策：**不做 bot 级能力开关**（同 agent 跨平台能力差异罕见，YAGNI；真需要时按平台 override 或拆 agent）。用户准入判**内部 User**（非平台原始身份）。

## 4. 准入闸逻辑（入站）

```
解析 agent（= 收到消息的 bot binding）+ 解析内部 User（经 im_users）
按 chat_type 分流：
  DM  → 准入 ⟺ supports_dm     ∧ user ∈ allow_users（或 require_approval 审批流）
  群  → 准入 ⟺ supports_groups  ∧ group ∈ 该 binding 的 allow_groups
         （群单门：群在白名单即视为授权，群内不再逐用户门——你审核过群、群成员在群内即可信）
默认全关：supports_* 默认 false；allow_groups 默认空=不进任何群；allow_users 默认空
```

DM 是 1:1、对端就是该 user，故必须过用户门；群是多人、群白名单本身即控制点，逐用户门不现实。

## 5. 配置与同步契约（修复"断线"）

保留 **平台配置 → 部署 materialize → agent 侧零-platform-DB 强制** 的解耦骨架（与 `agent_kbs`/`agent_mcp_servers` 同模式）。把断开的关系表接通：

```
平台侧（管理库，admin 配）          materialize（平台侧）          agent 侧（runtime）
─────────────────────────          ──────────────────          ──────────────────
agents.supports_*(能力)     ┐
user_agents(用户准入,保留)  ┼──→  写 agent.yaml `im` 块  ──→  本地读 agent.yaml 判闸
agent_im_groups(群白名单)   ┘                                  （不查 platform DB）
```

agent runtime MUST NOT import platform（边界契约不变）；platform 单向写 agent 产物，agent 只读自己的 agent.yaml。

## 6. 目标数据模型

### 6.1 平台侧（管理库 · Alembic）

| 表/列 | 定义 | 说明 |
|---|---|---|
| `agents`：`supports_dm` `supports_groups` | INTEGER(bool) | agent 能力——**agent 级非版本化配置**，并入 `agents` 的 allowed_skills/features/plugins 族（非 agent_versions，避免"回滚版本→IM 能力变"的耦合）；materialize 进 `im.*` |
| `user_agents`（**保留、不改名**） | 现有 `(user_id TEXT, agent_id INTEGER FK→agents.id ON DELETE CASCADE)` | 用户准入源（跨平台、agent 级，**非 IM 专属故不加 im 前缀**）；phase 3 materialize 进 `allow_users` |
| **`agent_im_groups`**（新建） | `agent_id INTEGER FK→agents.id ON DELETE CASCADE`, `platform TEXT`, `group_id TEXT`，PK(agent_id,platform,group_id) | 群白名单（req3 载体，IM 平台特定故带 im）；默认无行=不进任何群 |
| ~~旧 channel 路由表~~ | **descope** | 旧路由表（含 `bound_version_id` 死列）；一 agent 一 bot 后路由不需要 |

FK 遵循 identity-model：agent 引用 = `agent_id` INTEGER FK→agents.id ON DELETE CASCADE。

### 6.2 agent 侧（agent.yaml · S2 命名）

```yaml
im:
  supports_dm: true
  supports_groups: true
  allow_users: [alice, bob]          # agent 级（内部 User）
  slack:
    bot_token_env: SLACK_BOT_TOKEN
    app_token_env: SLACK_APP_TOKEN
    allow_groups: [C0123]            # 平台级群白名单
  telegram:
    bot_token_env: TG_BOT_TOKEN
    allow_groups: ["-100456"]
```

Python 模型：`ImBinding`（顶层）+ per-platform `SlackBinding`/`TelegramBinding` + `ImAccess`（演进自 `ConnectorAccess`）。

### 6.3 命名映射（S2，旧→新）

| 旧 | 新 |
|---|---|
| agent.yaml `connectors.*` | `im.*` |
| `ConnectorAccess` | `ImAccess`（+ `ImBinding`） |
| `allow_channels` | `allow_groups`（仅群；DM 由 supports_dm + allow_users 管） |
| `SlackConnector` / `TelegramConnector` | `SlackBinding` / `TelegramBinding` |
| `user_agents` | **保留不改名**（用户准入跨平台、非 IM 专属，不加 im 前缀；phase 3 materialize 进 `allow_users`） |
| 已删除的 channel 路由表 | descope（access 改用 `agent_im_groups`，语义不同——非路由） |

> "connector" 一词在 IM 语境退役；`connectors`（工具 OAuth）/`kb_connectors`/`im_connectors` 是另外的东西，不在本设计内。

## 7. 默认与安全

- **默认全关**：新建 agent 不 supports_dm/groups、无 allow_users/allow_groups → 谁都用不了、哪个群都不进。显式开启才生效。
- 群白名单默认空 = 不能被拉进任意群（修复 req3 的反向默认）。
- DM 未知用户走 `require_approval` 审批流（保留现有能力）。

## 8. 分阶段落地（每阶段一个 OpenSpec change，串行——都碰 data-model + materialize）

1. **阶段 1 — descope dead channel-route table**：删表 + `bound_version_id` 死列 + 相关 store/端点；ER 图/§3.2 同步。（最干净、无依赖）
2. **阶段 2 — 立访问关系表 + 能力列**：建 `agent_im_users` / `agent_im_groups`，加 `supports_dm`/`supports_groups`；admin API 配置入口。（暂不接 materialize）
3. **阶段 3 — materialize 接线 + agent.yaml `im` 块演进 + 闸按 chat_type 分流**：`ConnectorAccess`→`ImAccess`、`allow_channels`→`allow_groups`、平台表 materialize 进 `im` 块、准入闸实现 DM/群 双路 + 默认关。（核心，依赖 1/2）
4. **阶段 4（可选）— "connector"(IM 义) 全量正名 `im`**：Python 类/agent.yaml 块名/测试随动。（纯整洁，可并入阶段 3 或单列）

> 阶段顺序与 identity-model 同理：串行（Alembic 单链 + 都改 data-model/materialize）；逐个 just-ahead propose。

## 9. 范围与取舍

- **whatsapp owner-level 例外**：slack/telegram 是 per-agent bot（本设计对象）；whatsapp 走 owner 级 `im_connectors`（连接归属平台用户、非 per-agent）。本设计聚焦 per-agent-bot 平台；whatsapp 的 owner 模型如何并入本访问模型留作后续单独议题。
- **群单门 vs 双门** → 单门（见 §4）。
- **不做 bot 级能力开关** → agent 级（见 §3）。

## 10. Open Questions

- ~~能力 `supports_*` 落 `agents` 还是 `agent_versions`~~ **已定（2026-06-14）：落 `agents`**——能力是 agent 级策略立场、非版本化推理配置，并入 allowed_skills/features 族，避免版本回滚耦合。
- ~~用户准入表命名~~ **已定：保留 `user_agents`**（跨平台、非 IM 专属，不加 im 前缀）；仅群白名单 `agent_im_groups` 带 im（平台特定）。
- whatsapp owner-level 与本模型的统一（§9）——独立议题。
- **身份/租户**（随本线一起做，见 [[identity-auth-model]]）：`owner_id` 误名（im_users.owner_id 实为 agent 名）、多租户 IM 身份守卫半成品（provisioning 落 default 而非 edge_tenant）、身份域 FK 缺口——phase 3 materialize/gate 落地时一并拉直。
