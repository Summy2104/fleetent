# Agent IM 接入与访问控制模型（as-built 行为）

> **状态：as-built 行为参考（阶段 1–4 + 3b 全落地，2026-06-14）**。讲 agent 在 IM 平台的 bot 接入身份 + 三层访问控制 + "平台配置→部署 materialize→agent 侧零-platform-DB 强制"的同步契约。命名采用 **S2（`im` 命名空间）**。
> **schema 真相源是 [data-model](data-model.md)**（`im_users`/`user_agents`/`agent_im_groups`/`agents.supports_*` + erDiagram），本文不复述列。**分阶段落地过程、已 resolved 的设计取舍**见 [`records/decision-logs/`](../records/decision-logs/) 与本文 git 历史。配套 [agent-identity-model](../records/decision-logs/agent-identity-model.md)、[[identity-auth-model]]。

## 1. runtime 模型：一个 Agent 一个 bot

agent 在 agent.yaml 声明自己的 bot 凭据，**连接器连接即 agent 身份**；消息发给哪个 bot 就是哪个 agent。没有"共享 bot 按频道路由"（旧 channel 路由表已 descope，runtime 不读）。

> 历史：早前审计发现三处缺陷（用户准入关系表 `user_agents` 不接 materialize 是死表 / 闸不看 `chat_type` / 群默认放行相反）——均已在阶段 2–4 修复（接通 materialize、加能力闸、翻转群默认关）。

## 2. 实体模型

| 实体 | 含义 | 载体 |
|---|---|---|
| **User** | 内部统一身份 | `users` + `im_users`（平台身份→内部 user 映射） |
| **Agent** | —— | `agents` |
| **IM Platform** | slack / telegram / (whatsapp 见 §8) | `platform` 字段 |
| **Agent IM Binding** | **某 agent 在某平台的 bot 接入**：凭据 + 平台级访问（= 旧 "connector"，正名为 `im`） | agent.yaml `im.<platform>` |
| **Group / DM** | 多人会话 / 1:1 私信（由 `chat_type` 区分） | `channel_id` + `chat_type` |
| **Thread** | 群内回复串 | `thread_root` |
| **Session** | 会话实例 = binding + group/dm + thread | `session_id` |

> 关键：Agent IM Binding 是**必要的一等概念**——IM bot 的凭据**就是** agent 在平台上的身份。User↔Agent、Group↔Agent 在 runtime 不是 DB 关系，而是从"binding 配置 + 访问策略"涌现。

## 3. 三层访问控制 + 粒度

| 控制 | 粒度 | 为什么 | 载体 |
|---|---|---|---|
| **能力**：`supports_dm` / `supports_groups` | **Agent 级** | 能力是 agent 行为设计内禀、跨平台不变；bot 级=过度设计 | `agents` 列 → agent.yaml `im.*` |
| **用户准入**：哪些 User 能用此 Agent | **Agent 级**（判**内部 User**） | 内部身份跨平台一致；平台身份映射归 `im_users` | `user_agents`（跨平台、非 IM 专属故不加 im 前缀）→ `im.allow_users` |
| **群白名单**：此 bot 准在哪些群 | **Bot 级**（per 平台） | 群 id 平台特定、无跨平台抽象，被迫 | `agent_im_groups` → `im.<platform>.allow_groups` |

> 不做 bot 级能力开关（同 agent 跨平台能力差异罕见，YAGNI；真需要时按平台 override 或拆 agent）。用户准入判**内部 User**（非平台原始身份）。

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

## 5. 配置与同步契约（解耦骨架）

保留 **平台配置 → 部署 materialize → agent 侧零-platform-DB 强制**（与 `agent_kbs`/`agent_mcp_servers` 同模式）：

```
平台侧（管理库，admin 配）          materialize（平台侧）          agent 侧（runtime）
─────────────────────────          ──────────────────          ──────────────────
agents.supports_*(能力)     ┐
user_agents(用户准入)       ┼──→  写 agent.yaml `im` 块  ──→  本地读 agent.yaml 判闸
agent_im_groups(群白名单)   ┘                                  （不查 platform DB）
```

agent runtime MUST NOT import platform（边界契约不变）；platform 单向写 agent 产物，agent 只读自己的 agent.yaml。

## 6. agent 侧 `im` 块形态（S2 命名）

```yaml
im:
  supports_dm: true
  supports_groups: true
  slack:
    bot_token_env: SLACK_BOT_TOKEN
    app_token_env: SLACK_APP_TOKEN
    access:
      allow_users: [alice, bob]      # agent 级（内部 User），按平台 binding materialize
      allow_groups: [C0123]          # 平台级群白名单
  telegram:
    bot_token_env: TG_BOT_TOKEN
    access:
      allow_users: [alice, bob]
      allow_groups: ["-100456"]
```

Python 模型：`ImBinding`（顶层）+ per-platform `SlackBinding`/`TelegramBinding` + `ImAccess`。
> "connector" 一词在 IM 语境已退役（阶段 4 正名 `im`）；`connectors`（→已重设计为工具 OAuth Vault 的 `external_services`）/`kb_connectors`/历史 `im_connectors` 是另外的东西，不在本模型内。

## 7. 默认与安全

- **默认全关**：新建 agent 不 supports_dm/groups、无 allow_users/allow_groups → 谁都用不了、哪个群都不进。显式开启才生效。
- 群白名单默认空 = 不能被拉进任意群。
- DM 未知用户走 `require_approval` 审批流。

## 8. 范围与取舍

- **群单门 vs 双门** → 单门（见 §4）。**不做 bot 级能力开关** → agent 级（见 §3）。
- **WhatsApp：v1 缓做，owner-level 脚手架已整体 descope（2026-06-14 调研定调）**。
  - WhatsApp Cloud API 与 slack/telegram 架构差异大：webhook-push（非轮询/socket）、身份=电话号、**一个 Business 号需路由**（"连接=agent"失效）、**不支持群**（仅 `supports_dm`）、出站受 24h 窗口+模板约束。
  - 共性扩展缝**已就位**（`NormalizedMessage` 平台无关 + `im_users(platform, platform_user_id)` 电话号即 platform_user_id + supports_dm 闸）；whatsapp 独有部分（webhook 入站/共享号路由/模板出站）形态差异大、**不预抽象**。空的 owner-level connector 脚手架（`im_connectors` 表 + `connector_manager` + owner-level admin）是错方向，已 descope（= owner→tenant 塌缩第三刀，owner_id 在 IM 域彻底退役）。
  - 未来 whatsapp = **增量**（webhook 端点 + 适配器 + 共享号路由 + 模板出站），届时正经设计。详见 [[persistence-redesign-roadmap]] / 决策日志。

> 现状：IM 域已无 owner 作用域残留——`im_users` 已瘦身为纯 `(platform, platform_user_id) ⇄ user_id` 身份映射（owner_id/allowed 删除、补 FK→users、provisioning 落 edge_tenant、封禁迁 `users.status`），旧渠道白名单表与 owner-level connector 机制均已整体 descope。
