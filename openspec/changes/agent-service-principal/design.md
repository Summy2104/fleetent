## Context

`external-credential-vault`（P0）把凭证主键统一为 `user_id`，并确立「principal 即 User」。Case 3 要让 agent 以自身身份持凭证。地基已验证可行：`users.id` 是 TEXT，已有 `SYSTEM_OWNER_ID = "__system__"` 这种非人类 principal 用 User id 表达的先例；`users.role` 为自由文本（已有 `viewer`/`built_in_admin`）。本变更据此为 agent 铸造 service-principal User，并接通 `run_as=agent` 的凭证解析。

## Goals / Non-Goals

**Goals:**
- 让 agent 拥有稳定的 service-principal `user_id`，幂等铸造/解析。
- `run_as=agent` 的工具调用解析为 agent principal 的凭证，与 per-user 共用 `external_credentials`。

**Non-Goals:**
- 不做 agent 的 INBOUND 鉴权（agent 调内部服务的 `ma-` key 是 `api_keys` 机制，另议）。
- 不做多 agent 共享外部账号。
- 不改 `external_credentials` / `users` 表结构（倾向零迁移，见 D2）。

## Decisions

### D1. service-principal id 形态：`agent:<agent_id>`
- **决定**：service-principal 的 `users.id` = `agent:<agent_id>`（稳定、可逆推、与人类 UUID 命名空间不撞）。
- **为什么**：`__system__` 已证非 UUID id 合法；前缀形态便于审计辨识与反查；agent 删除时可定向清理其 principal 凭证。
- **备选**：随机 UUID + 侧表映射 agent_id↔user_id —— 多一张映射表与一次 join，无收益，弃。

### D2. service 类型用 `users.role="service"`，不新增列
- **决定**：以 `role="service"`（或等价既有字段）标注 service-principal，避免给 `users` 加 `kind/type` 列触发迁移与 FK 影响。
- **为什么**：零迁移、零 schema 风险；`role` 本就自由文本。
- **权衡**：`role` 同时承载权限语义，需确保 service principal 不被误授予人类角色权限——铸造时固定 `role=service` 且不可经常规 set_role 提权。
- **备选**：加 `users.kind` 列 —— 更显式但需迁移 + 触碰已 CASCADE 的 users 重建链，弃（除非后续有强需求）。

### D3. run_as 解析点在 dispatch 之前的凭证解析层
- **决定**：dispatch 读取 grant 的 `run_as`：`user`→调用用户 `user_id`；`agent`→该 agent 的 service-principal `user_id`；以该 principal 调 `connectors.get_credential`。
- **为什么**：run_as 是绑定级策略（P0 D5 已定），解析集中一处，不污染工具签名、不暴露给 LLM。

## Risks / Trade-offs

- **[role 复用致提权风险]** service principal 走 `users.role` → 铸造固定 `role=service`、禁止经 set_role 改它、且认证路径不为 service principal 签发人类会话/INBOUND key。
- **[principal 凭证的生命周期]** agent 删除后其 service-principal 与凭证需清理 → 铸造采用 `agent:<id>` 便于定向删除；具体清理接入 `delete_agent`（best-effort，舱壁化）。
- **[谁触发铸造]** 倾向「首次需要时惰性铸造」+ 幂等，避免给所有 agent 预建 principal。

## Migration Plan

1. 身份层加「get-or-create service-principal user for agent」幂等 helper（`role=service`，id=`agent:<agent_id>`），无 schema 迁移。
2. dispatch 凭证解析读 `run_as`，agent 分支用 service-principal user_id。
3. `delete_agent` 清理路径补 best-effort 删除该 principal 的 `external_credentials`（舱壁化，不改退出码）。
- **Rollback**：不铸造 + run_as 解析回退为仅 user 分支；已铸造的 service principal 行保留无害。

## Open Questions

- service-principal 是否需要 `tenant_id` 归属（多租户下 agent 属某 tenant）？倾向继承 agent 的 tenant，留实现时定。
- agent 删除时 service-principal User 行是删还是留档（与人类 user 的删除语义对齐）？留实现时与 user 删除策略对齐。
