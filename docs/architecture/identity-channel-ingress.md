# 身份模型与渠道 Ingress 架构（车道 D 设计输入）

> 状态：**已落地**（设计定稿 2026-06-22；切片 #1–#5 全部实现并归档 2026-06-22~23——#1 OIDC web login、#2 email 并号、#3 forwarder 统一入站 Principal、#4a/#4b IM-edge 下沉 node 进出站、#5 manual channel link）。本文固化 2026-06-22 一轮跨渠道身份/IM-gateway 设计探索的结论，现作为已实现架构的设计权威。出站定向触达（按 user_id 主动触达用户）是本线在出站方向的延伸，见 `directed-reach.md`。
> 关联：`docs/architecture/data-model.md`（5 物理库 + 管理表权威）、`docs/architecture/target-architecture.md`、`AGENTS.md`（agent↔platform 解耦契约、异步资源生命周期契约）。

## 1. 问题

当前 IM gateway（Slack/Telegram adapter + 连接 supervisor）跑在 **agent 进程**（`im_gateway/`，agent boot `im=True`），身份解析靠 `set_im_identity_resolver` 注入——而它**只在 platform 进程（server.py）注入**。身份绑定（`im_users`/`users`）在管理库 = **平台侧写**（`platform/im_gateway_management/identity.py::get_or_create`）。

→ managed 拓扑下 agent 是 node 上的独立进程：(1) 平台 resolver 没注入进 agent 进程 → `resolve_identity` 退化返回原始 `platform_user_id`；(2) agent **禁止写管理库**；(3) **platform→agent 单向**，agent 不能反调平台。**结果：IM 终结在 agent、身份却必须在平台绑，跨不过这条边界。** 单进程部署能跑通，分布式 managed 下断。

同时一个产品决定推高了身份的目标：**同一员工从 Slack 和 web 找同一 agent，要被当成同一个人**（共享记忆/审批/历史）——即需要**跨渠道把一个真人并成一个唯一 ID**，这是两个参考实现（openclaw / hermes）都刻意没做的（它们单用户/单租户、不需要）。

## 2. 已定决策

### 2.1 身份基线（沿用既有，本文不改）
- **一切是 User**；规范唯一身份 = `users.id`（uuid，管理库，带 `tenant_id`）。
- **agent 侧与平台侧同一个 id**：`Principal{user_id, tenant_id}` 的 `user_id` 就是 `users.id`（`identity.py`）。agent 运行时按 `Principal.user_id` scope 记忆/会话/审批。
- **认证属 edge，核心只消费 Principal**：每个渠道在 edge 解析出已认证 User，递给核心；核心从不认证。

### 2.2 跨渠道唯一身份
- **email = 租户内跨渠道 join key**：`UNIQUE(tenant_id, email)`（partial，email 非空时）。
- **自动并号**：渠道给出 verified email（Slack workspace email / OIDC verified email）时，按 `(tenant, email)` lookup-or-link 到同一 `users.id`。**信任模型 = 自动并**（限 verified email + 同租户；靠"只信 workspace/IdP 验证过的 email + 限 tenant"兜安全）。
- **fleetent 从不靠"用户输 email/手机再验证"**：身份属性只从已验证它的渠道取（Slack/OIDC/…）。→ **不接 SMTP/SMS**，契合数据不出内网。

### 2.3 无 verified email 的渠道（Telegram/WhatsApp）
- 没法 email 并号 → 首次接触先建**渠道独立 User**；要并成同一个人走 **手动 `/link`（双向控制）**：已登录（email-keyed）用户发起 → 一次性 code → 从目标渠道账号回发 code → 绑定。要同时握住登录态 + 目标渠道账号才绑得成，误绑到别人被结构性堵死。
- **可逆 + 审计**：unlink（用户自助 / admin 强制）撤销映射，未来消息回落独立身份；link/unlink 全程审计。
- **错绑窗口期数据**：**不自动迁移**——标记可疑，admin 手动清理。自动重归属 **post-v1**。

### 2.4 web 登录 = OIDC（进 v1）
- 产品决定（2.1 末）要 web 终端用户 + 企业规模 → 必须接公司 SSO。**OIDC 进 v1**。
- 形态：**edge 适配器，折进现有 session 解析器**（验完发 session），**不新增第三种认证路径**。
- 目标 IdP：**通用企业 OIDC**（自托管 Keycloak 首选 / Okta / Azure AD / Google Workspace）——**不是消费级"用 Google 账号登录"**。OIDC 只交换身份令牌、不传业务数据，不违数据主权。

### 2.5 开户/注册
- **平台侧、agent 永不注册任何人**。
- 推荐 **B 为主 + A 兜底**：B = 从同一 IdP/目录**预置花名册**（全员预先 email-keyed user，Slack/OIDC 一来精确命中、并号零歧义）；A = 花名册外的人 **lazy 首次接触建户**。
- 受**访问闸**门控（per-agent IM access / allowlist / `users.status`）：不是谁 DM 就开户。

## 3. 架构：统一 edge 契约 + forwarder 单一脊柱

### 3.1 两层不对称，只消除一层
- **放置层不对称**（连接终结点：chat@平台 / IM@node）：**保留且合理**——浏览器只够得到平台；IM 是出站连接、放 node 有本地性。不可约。
- **抽象层不对称**（chat 与 IM 两套管线）：**消除**——统一 edge 契约 + forwarder 单一入站。

### 3.2 edge 契约（host-agnostic）
一个 **channel edge** 实现：
- 入站：终结 transport + 解析出 `Principal` → 产出 `(Principal, message)`；
- 出站：把 agent 的回复/出站送回本渠道。
- **依赖注入**：`identity-resolver` + `outbound-sink` 由 host 注入（沿用 openclaw `outbound-send-deps` 范式），使同一 edge 在不同 host 上接线不同：
  - host=平台/独立 gateway → 注入"直连管理库"resolver + "本地连接"sink；
  - host=node → 注入"node→平台"resolver + "本地 agent 出站队列"sink。
- → **placement 从永久选择降级成部署接线选择**，不重写适配器可换 host。

### 3.3 forwarder 单一脊柱
```
edge ──产出 {Principal, message}──▶  forwarder: POST /forward/agents/<name>/message  ──▶  agent
                                                  （唯一入站，恒载 Principal+message）
agent 流式回复 / 异步出站 ──▶  由「调用方那个 edge」送回各自渠道
```
- **agent 只见一个入站接口**，不管来源是 chat 还是 IM。
- chat ingress（既有 ④，平台→forwarder→agent）与 IM 共用这条脊柱。

### 3.4 三侧落点（方案 B）
- **平台**（身份权威）：管理库（`users`/`im_users` + `UNIQUE(tenant,email)` + link 审计）；`chat-edge`（operator session→Principal）；web OIDC；身份解析 API（供 node 调）+ `/link` 绑定（node 上报 code → 配 web 会话 → 写 `im_users`）。
- **Node**（agent 的本地 edge）：`IM-edge`（持 Slack WS / Telegram poll，调平台解析身份，可缓存）；forwarder 统一入站；**drain 本机 agent 出站队列**（读本地 `agent_state.db`，非 RPC）。
- **Agent**：唯一入站收 `{Principal, message}`；**不持连接、不解析、不绑定**；`agent_state.db` 加 **outbound 队列表**；按 `user_id` scope。

### 3.5 异步出站（审批 DM / 主动通知）
- **同步回复**走那次请求的流式响应回传（同 chat ingress）。
- **异步出站**走 **delivery-queue**：agent 把出站意图写自己侧 `agent_state.db` outbound 表 → **node drain 本机文件**后发出。沿用 openclaw `outbound.send()` + delivery-queue 范式；node 读 agent 产物（本地文件）= 符合「平台/host 读 agent 产物、agent 只写自己侧」。

### 3.6 解耦校验
node→平台解析/绑定走**既有合法通道**（node 本就有 service key、拉 desired state）；node 读本机 agent 出站队列 = 读 agent 产物；agent **只写自己侧、不调平台、不持连接**。**全程无 agent→platform。** 与 AGENTS.md 异步资源生命周期契约一致（连接的 owner task 在持连接的那侧）。

## 4. 通用化：这是一个「agent ingress edge」模型，不止 chat+IM

| 入口 | transport | 身份来源 | edge host |
|---|---|---|---|
| operator web chat | HTTP/SSE·WS | operator session | 平台前门 |
| IM（Slack/TG/WhatsApp） | Socket Mode WS / poll | 渠道担保 | node |
| CLI / TUI | WS / stdio | API key `ma-` | 远程→平台；本地 dev→直连 agent |
| 开放 API / 程序化 | HTTP/SSE | API key / service principal | 平台前门 |
| webhook 入站 | 公网 HTTP POST | source 配置 | 平台前门 / DMZ |
| email / SMS / 语音 | IMAP-poll / webhook | email / 手机号 | 平台 / node |
| 嵌入式 SDK / widget | HTTP/WS | host app token | 平台前门 |

- 以上**全部 fit 同一 edge 契约**，差异仅在 `(transport, 身份来源, host)` 三参数。
- **cron / 定时**：无 live 连接，Principal 来自**存档引用**（`scheduled_tasks.user_id` + 触发时复检），仍走同一脊柱（脊柱对 Principal 怎么来的无所谓）。
- **内部正确出局**：sub-agent / 回合内调用（继承父 Principal）、系统任务（`system` principal）——不走 edge、不该走。

## 5. 模块边界影响（进 implementation 前声明）
- **owning packages**：`im_gateway`（adapters/连接/normalizer 当前在此，需劈分）、`runtime`（agent_app 入站接口 + 出站队列）、`node`（IM-edge 宿主 + forwarder 统一入站 + drain）、`platform`（OIDC adapter + 身份解析 API + `/link` 绑定 + im_users 变更）。
- **public API surface**：新增 forwarder 统一入站 `/forward/agents/<name>/message`；edge 契约接口（resolver/sink 注入）；平台身份解析 API（供 node）。
- **owned tables**：`im_users`（加 `UNIQUE(tenant,email)` + link 审计列/表）；`users`（email 唯一约束）；`agent_state.db` 新增 outbound 队列表（agent 侧）。
- **config namespace**：OIDC（IdP 配置）；node 的 IM-edge 连接配置（从 agent.yaml 的 `im` 块迁移/投影）。
- **cross-module deps**：node→platform（身份解析，既有合法）；node→本机 agent store（读出站队列）。**不得新增 agent→platform。**
- **migration / shim**：im_users（管理库 alembic）；agent_state outbound 表（嵌入式-Y 迁移）；im_gateway 从 agent 搬 node 期间留 re-export shim。
- **⚠ 与 AGENTS.md 张力**：现契约把 `im_gateway` 列为 agent runtime 模块；本方案把 IM-edge（连接+解析）下沉 node、normalizer+loop 留 agent。**需更新 AGENTS.md 模块归属**（IM-edge ≠ agent runtime；normalizer/loop 仍是）。

## 6. Deferred 前沿（显式标注，不在本设计实现）
- **A2A 委托身份**：agent→agent 调用是唯一没被 ingress 模型覆盖的——它复用出站 delivery-queue/reverse 机制，但带出**委托身份**新维度（被调 agent 看到的 Principal 是发起 agent 还是原始用户）。超近期 scope。**唯一现在要做的便宜事：Principal/脊柱载荷形状预留 `on_behalf_of`/委托链口子，不实现**，避免将来改契约。
- **CLI 远程形态**：已被 edge 契约覆盖（API-key 身份、远程走平台前门、本地直连）；local-vs-remote 是实现期部署细节，非阻塞分叉。关联 agent-mgmt 多渠道 deferred 项。
- **错绑数据自动重归属**：见 2.3，post-v1。
- **Telegram/WhatsApp 无-email 渠道**：v1 经 `/link` 支持（2.3），形态在切片时定。

## 7. 参考实现对照（openclaw / hermes）
- **openclaw**（单进程 daemon，渠道=plugin 各自持连接 + 回调 core）：`session.identityLinks`（`canonical-id(email形态) → [channel:peer]` 手动配置）= 本文 email-join 的**手动祖型**；`outbound.send()` + delivery-queue = 3.5 出站范式。
- **hermes**（独立 gateway 服务，多平台 adapter hub，gateway 进程内调 agent）：`BasePlatformAdapter` = edge 契约的印证；pairing 码 = 无-email 渠道授权的一种。
- **两者都没有**：自动跨渠道并号、多租户、agent 独立进程的跨边界解耦——**这三点是 fleetent 特有、net-new，须自研**（本文即其设计）。

## 8. 切片提示（供后续 opsx:propose）
本设计偏大，建议切成独立 change（与 KB/记忆车道 A/B/C **并行不阻塞**，因后者只消费 `user_id`）：
1. **OIDC adapter**（web 登录，折进 session 解析器）。
2. **email-join + im_users 演进**（`UNIQUE(tenant,email)` + 自动并号 + provisioning 改 lookup-by-email；吸收既有 im_users 收敛计划）。
3. **统一 forwarder 入站 + edge 契约**（`/forward/agents/<name>/message`，resolver/sink 注入）。
4. **IM-edge 下沉 node**（im_gateway adapters/连接搬 node，normalizer/loop 留 agent，出站 delivery-queue + node drain）。
5. **`/link` 双向控制 + unlink + 审计**（无-email 渠道）。

顺序建议：3（脊柱/契约地基）→ 1∥2（可并行）→ 4 → 5；每个独立 change/TDD。
