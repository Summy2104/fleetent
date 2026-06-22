# Directed Reach：按 user_id 主动触达内部用户

> 状态：设计定稿（2026-06-23），待切片为 OpenSpec change。
> 关联：[identity-channel-ingress.md](identity-channel-ingress.md)（车道 D 身份/渠道线）、车道 A 的 A4b。

## 背景与问题

agent 有时需要**主动**联系一个内部用户，而该用户**不在任何对话里**、地址也没法预先配置——只知道他的内部 `user_id`。首个真实需求是车道 A 的 **A4b**：reflection 在用户记忆上生成需本人审批的维护提案（如"删掉『偏好简短』这条已过期的记忆？"），定时跑、无对话上下文，只有 `proposal.user_id`。

当前"找审批人/找人"是围绕**两个都绕开反查的寻址模型**设计的：

- **M1 静态配置地址**：运营者在 `agent.yaml` 的 `approval.by_tool/by_risk` 写死 approver 地址（`platform:target_id`，如 `slack:U123`）。`resolve_approvers` → `_notify_approvers` → `outbound.send_to`。地址是人事先写死的。
- **M2 requester 哨兵**：`REQUESTER_SENTINEL="requester"` 把提示回发到发起者当前对话（`reply_func`）。回复"正在说话的那个人"，无需知道他是谁。

两者都**从不需要"内部 user_id → 渠道地址"的反向解析**。A4b 第一次需要这个第三模型。

## 核心模型：M3 定向触达

```
agent 侧:   notify_user(user_id, message)        ── 只发意图、不解析地址（守 agent↔platform 解耦）
平台/node:  user_id ──[反查 im_users WHERE user_id=X]──> [(platform, address), …]
            ──[逐地址 fan-out]──> im_outbound_queue（platform + address + payload，#4b 已有）
node IM-edge: drain 队列 → connector 投递到各渠道
回复（如需）: 入站 identity resolver（渠道 → user）+ 既有 `approve <id>` 关联挂起项  ── 复用、不新建
```

**数据已存在**：渠道绑定表 `im_users(id, platform, platform_user_id, user_id, created_at, meta_json)`（#2 email 并号 / #5 `/link` 写入；迁移 089 已瘦身为纯身份映射）。`WHERE user_id=X` 即可反查该用户所有渠道地址。缺的不是数据，是**反查 API + 定向出站 + 它跑在哪**。

**分层很干净**：`im_outbound_queue` 载的已是解析好的 `platform + address_json + payload`。所以反查发生在它**上游**：directed-reach = (user_id→地址反查) + (逐地址 fan-out 进既有出站队列)。底层出站脊柱（#4b）与回复关联（审批链）都已具备，**真正新增的只在出站方向的"反查 + fan-out"这一层**。

与既有 `send_im_message` 工具的关系：后者是 agent 主动发到**已知地址**（approval-gated、recipient≠当前对话）；directed-reach 是它的"**按 user_id**"版本——多一层 user_id→地址解析。

## 决策

**D1 · 通用原语，非 reflection 私有**。做成通用 **directed-reach** 能力，A4b 只是首个消费者。理由：任何"agent 主动触达某内部用户"场景都要它（长任务完成通知、审批升级、主动提醒…），不该把反查逻辑埋进 reflection。→ 独立设计线 + 新 capability。

**D2 · 寻址 = 全发所有绑定渠道（v1）**。`im_users` 无 `last_seen`（只有 `created_at`），"最近用"需新加列 + 每次入站写它，性价比低。"全发所有绑定渠道"零新增 schema、最可达；对审批语义（批准一次、resolve 去重）**重复 DM 无害**。降噪留后做 **per-agent 平台优先序**（小配置、便宜）；per-user 优先级 / 最近用最贵、暂不做。

**D3 · agent 只发意图、不碰地址**。`notify_user(user_id, message)` 在 agent 侧只产生"通知某 user_id"的意图；user_id→地址反查 + 投递在**平台/node 侧**（持 `im_users` + connector）。守 agent 运行时不得 import/读 platform 表的解耦铁律——反查表在 platform（`im_gateway_management`）。

**D4 · 异步回复复用既有审批链**。directed-reach 用于审批类问答时（如 A4b），回复经正常入站 identity resolver（渠道→user）+ 既有 `approve <id>` 关联回挂起 approval_request——**这套已具备**（approval_router + reflection 提案审批，见 [reflection-approval-routing 已落地]）。directed-reach 本身只管"把消息送出去"，不重建回复关联。

**D5 · 不可达（无绑定）→ 留 pending + 日志**。user 没绑任何渠道时不强行投递、不回退兜底 approver：保持挂起项 pending 并记日志，等该用户将来绑定渠道后由下一轮触达。（理由：A4b 语义是"问本人"，回退给别人违背"本人审批自己记忆"的初衷；搁置 + 可观测最忠实。）

**D6 · 只面向 managed；dev agent-run 降级**。standalone 已非部署模式（platform 始终在场；`fleetent agent run` 仅 dev/test 原语，迁移 v27 已 retire standalone DB）。directed-reach 面向 managed（平台/node 持绑定表 + connector）。dev 的 `agent run` 无 `im_users` 表 → 反查降级为 no-op + 日志，不为它设计专门绑定源。

## 模块边界（切片前必须钉）

- **owning package**：
  - 反查 + fan-out + 出站 = **platform `im_gateway_management`**（持 `im_users`）+ 复用 `im_gateway` 出站脊柱（`im_outbound_queue` / node IM-edge drain）。
  - agent 侧 intent API = agent runtime 的一个薄出口（产生"通知 user_id"意图，经 forwarder/node 交给平台解析投递）——**MUST NOT** 在 agent 进程内反查 `im_users`。
- **public API surface**：`notify_user(user_id, message)`（agent 侧意图）；平台侧 `resolve_user_addresses(user_id) -> [(platform, address)]` + fan-out 投递；directed-reach 不暴露新的回复入口（复用审批链）。
- **owned tables**：读 `im_users`（既有，platform）；写 `im_outbound_queue`（既有，#4b）。**无新表**（v1 不加 last_seen）。
- **config namespace**：（可选，降噪期）`agent.<...>` per-agent 平台优先序——v1 不做。
- **cross-module dependencies**：agent→（forwarder/node）→platform 反查；**无 agent→platform 直接 import**。复用 #4a/#4b 的 node IM-edge 宿主。
- **migration / shim**：v1 无迁移。

## 切片建议

**A4b 一个 change 搞定**（下列 1-3 合一）。它们彼此**不是独立可发布的**——原语单独落地是死代码（无调用方）、agent intent 单独落地没人消费——只有三者一起才真正"提案送到本人"，拆开只制造"先建死代码再接线"的 churn。故合为一个 change：

1. **directed-reach 原语**：`resolve_user_addresses(user_id)` 反查 `im_users` + 全发 fan-out 进 `im_outbound_queue`；无绑定→不投递+日志。
2. **agent 侧 intent 出口**：`notify_user(user_id, message)` —— agent 入队 user_id-目标意图；node drain 时反查+投递；dev agent-run 降级 no-op。
3. **A4b 接入**：reflection 的 user-memory 提案（`reflection_user_memory_proposal` 路由，A4a 已落地）经 directed-reach 通知 `proposal.user_id` 本人；回复经既有审批链关联回提案。

**单独/deferred**：
4. 降噪 per-agent 平台优先序 + 可达性可观测（送达/未达指标）—— opt-in 优化，A4b 不需要它即可工作。

## 关联与现状

- **A4a 已落地**（`reflection-approval-routing`，2026-06-23）：reflection 提案已按域+目标细分路由 key（`reflection_user_memory_proposal` / `reflection_shared_memory_proposal` / `reflection_skill_proposal`）。本设计的切片 3 正是给 `reflection_user_memory_proposal` 补上"真正送到本人"的投递。
- **车道 D 身份线**（#2 email 并号 / #4a IM-edge inbound / #4b outbound queue / #5 /link）提供了：绑定表 `im_users`、node IM-edge 宿主、出站队列脊柱。directed-reach 是这条线在**出站定向**方向的自然延伸。
- A4b 之外的消费者（长任务完成通知、审批升级再触达等）后续按需接入同一原语。
