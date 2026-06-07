## Context

凭据后端（加密 `agent_secrets`、`credential_service`、write-only API、materialize resolver、`*_env` required-env 派生）已落地且测试通过。本变更**纯 UX + 一处 store 作用域扩展**，不动加密原语、不动 materialize resolve 语义。

现状入口（[admin.html](../../../src/fleetent/static/admin.html)）：
- Provider 表单：`pv-api-key`（inline 值，写 provider store）+ `pv-api-key-env`（引用名）两个框。
- KB connector 表单：`KBC_FIELDS` 渲染的 `*_env` **名**字段，无填值处。
- Agent 弹窗 `ag-secrets` 面板：`agLoadSecrets` 拉 `/required-env` → 每槽 operator/inject 单选 + inject `PUT /secrets/{env}`（写 `agent_secrets`，per-agent）。

目标：值在字段就地输（默认加密注入），引用为高级，面板只读。

## Goals / Non-Goals

**Goals**
- 常用路径一跳：在 Provider「API Key」/ KB token 字段输值即完成（加密存 + 自动 env 名 + 引用回填）。
- 数据主权路径保留：高级「引用现有变量」= operator 模式，值不进平台。
- 面板成为只读部署就绪总览。

**Non-Goals**
- 不改 materialize 的 `.env` 生成与 mode resolve。
- 不改加密算法 / `FLEETENT_SECRET_KEY` 契约。
- 不做密钥轮换 / 版本化 / 审计 UI（超范围）。
- 不碰 MCP 表单（仍用 headers/env，无独立 `api_key_env` 框）——本轮只收敛 Provider + KB。

## Decisions

### D1 — CredentialField 控件契约（前端）
单一可复用控件，挂在任何需要密钥的字段。状态机两态：
- `value`（默认）：`<input type=password>` + 「保存」；保存 → 经凭据 API 加密存（inject 语义）；自动派生/复用 env 名并写回该字段对应的 `*_env` 引用；显示 `🟢 set` / `⚪ unset` chip；**永不回显**已存值（编辑态只显 chip + 「替换」）。
- `reference`（高级，折叠「⚙ 引用现有变量」展开）：`<input type=text>` 填 env 名（operator）；提示「值由运维在主机 .env 填，平台不存」。
- 切换 = 改该槽 mode；从 value→reference 提示已存的 inject 值将被忽略（不自动删，避免误删；由「清除」显式删）。

UI marker（供 `test_admin_console_ui.py` 断言）：控件 class `cred-field`、`data-mode`、value/ref 两输入、chip、advanced toggle。

### D2 — 自动 env 名派生（值优先路径）
inline 输值时用户不填名。复用现有派生规则（`FLEETENT_<SCOPE>_<SLOT>` 形式），按来源实体稳定派生：
- Provider key：`FLEETENT_MODEL_<PROVIDER_ID>_API_KEY`（大写、`-`→`_`）。
- KB connector token：`FLEETENT_KB_<CONNECTOR_ID>_<SLOT>`（slot = ACCESS_TOKEN / API_TOKEN …）。
派生后写入该实体配置的对应 `*_env` 字段（provider.api_key_env / connector.<key>_env），`agent.yaml` 引用即指向它。撞名仍 fail loud（沿用现有校验）。

### D3 — 共享密钥作用域（store）
Provider / connector 跨 agent 共享，其 inline 值不能键到单个 `agent_id`。现 `agent_secrets(agent_id, env_name, …)`。
**选定**：给 secret store 加 owner 维度而非新表——`agent_id` 允许 NULL 表示 shared/process 作用域（或并行 `scope` 列 `agent|shared`，design 实现时二选一，倾向 nullable `agent_id` + 唯一约束 `(coalesce(agent_id,''), env_name)`）。materialize resolver 解析顺序：agent 槽优先，回退 shared 槽。Alembic 迁移放宽 `agent_id` 非空约束 + 调唯一索引。
**理由**：复用现表/加密/API，迁移最小；shared 值天然被多 agent 复用（provider key 本就该复用）。

### D4 — 面板降级为只读总览
`ag-secrets` 面板：
- 移除 `agSecretSlotHtml` 里的 operator/inject 单选 + inject password 行 + 保存/清除按钮。
- 改为表格行：`<code>env</code> · source · chip(set/unset)`。source 链接/提示「在 <来源> 字段设置」。
- 保留 `agCopyEnvTemplate` / `agCheckMissingSecrets`。
- `agLoadSecrets` 仍拉 `/required-env`（含 mode + status）；不再绑写操作。

### D5 — Provider 表单合并
删 `pv-api-key-env` 独立框；`pv-api-key` 升级为 D1 控件。提交逻辑（`prSave`/body 组装，admin.html ~3888/3923/4048）：value 模式 → 经凭据 API 存值 + 自动名回填 `api_key_env`，**不再**把明文塞 provider body；reference 模式 → 只设 `api_key_env`。保留「编辑留空 = 不改」语义。

## Risks / Trade-offs

- **共享作用域迁移**：放宽 `agent_id` 非空有数据完整性风险 → 唯一索引用 `coalesce` 兜底；迁移加 integration 测试覆盖 per-agent 与 shared 并存。
- **provider 明文 key 去留**：现 `pv-api-key` 把明文写 provider store（既有行为）。本变更后 value 模式改走加密 store；需确认 provider runtime 读 key 路径仍能解析（经 `*_env` → resolver）。若有直读 provider.api_key 明文的旧路径，保留兼容或一并切换（apply 时核查）。
- **误切 mode 丢值**：value→reference 不自动删值，靠显式「清除」，避免误删。

## Migration Plan

MVP 未上线：面板旧输入控件直接删，无运行期 shim。新增 Alembic 放宽 `agent_secrets.agent_id` 约束（D3）。现有 per-agent inject 槽数据保持可读（agent 维度查询不变）。

## Open Questions

- D3 落地形态：nullable `agent_id` vs 显式 `scope` 列 —— 实施首个 task 据现 schema 定，二者对 API/前端透明。
- provider runtime 是否存在直读明文 `api_key`（非 `*_env`）的路径 —— apply 时 grep 核实，决定是否需兼容垫片。
