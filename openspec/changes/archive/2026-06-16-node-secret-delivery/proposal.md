> ⏳ **骨架（skeleton）**：本 change 仅 `proposal.md`。`specs/` 与 `tasks.md` 留待 JIT。
> 属**编排序列 C4/5**。依赖：[`node-desired-state-api`]（契约）+ [`node-supervisor`]（注入端）。**与 C3 紧耦合**——多数 agent 需 secret 才能连外部，故 C4 紧跟 C3，apply 时连着做（独立成 change 仅为聚焦安全评审）。

## Why

agent 要连 Slack/Telegram/模型/MCP，必须拿到 secret（IM token、模型 key、MCP/OAuth、KB 凭证）。同机时 materialize 把 secret 写本地 `.env`；分机后 secret 必须**安全地过网**到远端 node。本 change 定义 v1 的 secret 下发与注入：中心 Vault 仍是真相源，值经 TLS 推给授权 node，node 注入子进程 env、**不落 node 盘**。

## What Changes

- **desired-state 扩展携带 secret**：C2 的分区响应中加入该 node 被 pin 的 agent 所需 secret 值（仍按 node 分区——node 只拿到自己 agent 的）。
- **platform 出 secret**：从既有中心凭证库（`external_credential_store` / `vault_provider`）取值下发；中心 Vault 保持**唯一真相 + 中心轮换**（轮换后 node 下次 reconcile 重取）。
- **node 注入子进程 env**：`fleetent-node` 把 secret 作为 env 传给 `Popen(fleetent agent run, env=…)`；agent 的 `load_dotenv(override=False)` 不覆盖已存在 env → **agent 进程零改动**，且 secret **仅在 node 内存 + 子进程 env，不写 node 盘**。
- **安全基线（强制）**：TLS（mTLS 更佳）+ node 鉴权 + **按 node 分区授权**（node 取不到非自己 agent 的 secret）。
- 不做：secret 引用间接（`vault://`）、JIT fetch endpoint、短期租约——均 roadmap；**HashiCorp Vault 后端列 roadmap，不进 v1**（其动态 secret/自动轮换对 fleetent 静态外部 token 基本不适用；真有用的审计/时限 token/policy 待合规客户真要时再上）。

## Capabilities

### New Capabilities
- `node-secret-injection`: platform 经 desired-state 分区下发 per-agent secret（源自 `credential_slots`+`secret_store`，与非密 config 分离）+ node 注入子进程 env（内存不落盘、缓存只存 config 剥 secret）+ platform-down 降级 + 安全基线（TLS/分区授权）。

### Modified Capabilities
<!-- 细化（C2/C3 已落地）：secret 全部落新 capability node-secret-injection，
     含"扩展 desired-state 响应携带 secrets"作为 ADDED 要求——不 modify node-desired-state-api/
     node-supervisor/node-process-backend（同 C2 处理原则：新增行为不改既有）。
     凭证读取复用既有 secret_store.get_decrypted（读路径不变），不 modify 凭证 capability。 -->
<!-- 无 -->

> 注：本 proposal 由 skeleton 细化（C3 已 apply 落 main）。对着真实代码写：platform 侧复用
> `credential_slots.list_slots` + `secret_store.get_decrypted`（materialize 写 .env 同源）；
> config 已由 `materialize._strip_secret_plumbing` 确保非密；node 侧注入点 `node/backend.py spawn`
> + `node/reconcile.py`，⚠️ `node/provider.py` 的磁盘缓存必须剥 secret。

## Impact

**owning package**：platform（出 secret，触碰凭证库读取）+ `node/`（注入）。

**public API surface（修改）**：C2 desired-state 响应 schema 扩展 secret 字段；`node/` provider 增加 secret 解析→env 注入。

**owned tables**：无新增（用既有凭证库表）。

**config namespace**：TLS/mTLS 要求、node 授权范围相关配置，apply 时定。

**cross-module dependencies**：platform 读 `external_credential_store`/`vault_provider`；node 注入 subprocess env。无 Python import 跨边界（node 仍是 HTTP client）。

**migration / shim plan**：无 schema、无迁移、无 shim。

**安全注记**：secret 离开 platform 主机过网络是本架构的固有事实（中心 Vault + 远端 agent）；v1 靠 TLS + 分区授权 + 内存不落盘把暴露面降到最低。若客户有"secret 绝不离开使用机"的硬合规红线，则该 agent 走 node 本地自持（放弃中心轮换）——列 roadmap，非 v1 默认。

**不碰**：`data-model.md`、主 specs（delta 写 change 内）。
