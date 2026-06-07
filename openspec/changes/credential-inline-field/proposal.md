## Why

凭据授权链路已可用（[agent-credential-authoring](../archive/2026-06-05-agent-credential-authoring/)），但交互暴露了**三层间接**，新人填不对：

1. **填值与填名分散两处**。Provider 表单同时有「API Key」(inline 值, `pv-api-key`) 和「API key env var」(引用名, `pv-api-key-env`) 两个框，含义重叠、谁覆盖谁不直观；KB connector 表单只有 `*_env` **名**字段（access_token_env / api_token_env …），完全没有填值的地方。
2. **值要去第三个地方填**。真正输密钥值的入口是 agent 编辑弹窗里的「所需密钥」面板（`ag-secrets`），先在 Provider/KB 填好 `*_env` **名**，再回到 agent 面板对每个槽选 operator/inject、inject 才出现 password 框。一条链路跨 3 个表单 + 要懂 operator/inject 概念。
3. **默认值反直觉**。新槽默认 `operator`（运维去主机 `.env` 填），所以新人在 console 填完一切、面板里却看不到能输值的框，误以为「坏了」。

市面友好范式（Railway/Render「就地输值，引用隐藏」；Vercel「字段上 值/引用 开关」）把它压成**一跳**：在需要密钥的字段就地输值，变量名/加密/注入由平台自动办；引用现有变量是可选高级项。

## What Changes

把凭据输入**搬到需要它的字段上**，引用降级为高级选项，面板降级为只读总览。不新增任何密钥原语，复用现有加密 secret store / credential API / 自动 env 名派生。

- **inline CredentialField 控件**：需要密钥的字段（Provider「API Key」、KB connector 的 token 字段）统一换成一个控件：
  - **默认「输入值」**：password 输入，写后不回显；值经现有加密 secret store 落库（`inject` 语义）；平台自动派生稳定 env 名并把该字段的 `*_env` 引用指向它。用户**不见 env 名、不开面板**。
  - **高级「引用现有变量」**（折叠）：切到 operator/引用模式，只填/选 env 名，值由运维在主机 `.env` 填，平台不存值（数据主权路径）。
  - 编辑态显示 set/unset chip；inline 值永不回显。
- **Provider 表单收敛**：把 `pv-api-key` + `pv-api-key-env` 两个框合并成上面这一个 CredentialField，消除「两个填 key 的地方」。
- **「所需密钥」面板降级为只读总览**：列 `ENV VAR / SOURCE / status(set·unset)`，保留「复制 .env 模板」「校验缺失」，**移除** per-slot 的 operator/inject 单选与 inject password 框（输值已上移到来源字段）。面板回答的是「部署前还缺哪些」，不再是输入入口。
- **共享密钥作用域**：Provider / KB connector 是跨 agent 的共享实体。其 inline 值需要一个非 agent 维度的密钥作用域（design 定：secret store 增加 shared/owner 作用域，或按实体键），避免把共享 provider key 绑死到单个 agent。`agent.yaml` 仍只含 `*_env` 引用，值不 inline。

部署链路不变（bootstrap→materialize→主机补 operator 空值→run）；变的只是**值在哪输**：从「面板」上移到「字段」，默认就地加密存而非默认让运维去主机填。

## Capabilities

### Modified Capabilities

- `agent-credential-authoring`: 凭据值在引用它的字段就地输入（inline-first）；inline 输值默认走加密注入并自动派生 env 名；「引用现有变量」为可选高级模式；「所需密钥」契约从「输入入口」收窄为「只读部署就绪总览」；新增共享（非 agent）密钥作用域以承载 provider/connector 的 inline 值。

## Module Boundary Impact

- **owning package**：console 静态资源拥有 CredentialField 控件 + 面板降级；`platform` secret store 拥有共享作用域扩展与自动 env 名派生；provider/KB connector 表单复用控件，不新建密钥原语。
- **public API surface**：复用现有 write-only 凭据 API（PUT 值不回显 / status / required-env）；如引入共享作用域，secret store 的 key 维度从 `(agent_id, env_name)` 扩展到含 owner 维度（design 定，向后兼容现有 per-agent 槽）。
- **owned tables**：复用 `agent_secrets`；共享作用域若需新增列/键由 design 决定（优先复用现表 + nullable owner 列，Alembic 迁移，named params）。
- **config namespace**：`agent.yaml` 仍只含 `*_env` 引用，inline 值只进加密 store；不引入新 env。
- **cross-module dependencies**：provider/KB 表单 → 凭据 API；materialize resolver 不变（按 mode resolve）。
- **migration / shim plan**：MVP 未上线，面板旧的 operator/inject 输入入口直接移除（无运行期 shim）；现有 per-agent inject 槽数据继续可读。

## Impact

- **代码**：`src/fleetent/static/admin.html`（CredentialField 控件 + Provider 表单合并 + KB connector 字段 + `ag-secrets` 面板降级）；`platform/secret_management/`（共享作用域 + 自动 env 名派生）；可能 `provider_admin_*` / KB connector store（接受 inline 值经 secret store）。
- **数据库**：复用 `agent_secrets`，共享作用域若需迁移则一条 Alembic。
- **测试**：`tests/integration/test_admin_console_ui.py`（控件/面板只读断言 + `node --check`）、secret store 共享作用域 integration、凭据 API 回归。
- **删除**：`ag-secrets` 面板的 per-slot operator/inject 输入控件；Provider 表单的独立 `pv-api-key-env` 框（并入控件）。
- **分支**：基于 `feature/impl`，worktree + 功能分支实施。
