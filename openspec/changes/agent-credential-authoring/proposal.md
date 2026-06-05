## Why

`agent.yaml` 用 `*_env` 引用密钥**名**，`.env` 存密钥**值**，两者分离以满足数据主权（密钥不 inline）。但今天有两个断点让这条链路不可用：

1. **导出层丢字段**：[materialize.agent_file_from_store](../../../src/fleetent/platform/agent_lifecycle/materialize.py) 只搬 8 个核心字段（name/system_prompt/allowed_tools/allowed_skills/plugins/features/memory_namespace + 写死的 `default_models()`）。平台已存的 `model_overrides` / `mcp_server_ids` / `tenant_id` / `team_id` / `skills_dir` 被丢弃；`agent_kbs` 绑定、`channel_agents` / `user_agents` 绑定、connectors 未接。结果：生成的 `agent.yaml` 模型路由是假的（`localhost:11434` ollama 占位），`.env` 几乎为空——部署后 agent 连不上真实模型、没知识库、没 IM 入口。

2. **没有友好的密钥编辑交互**：运维要手敲 `*_env` 变量名、对着 `agent.yaml` 和 `.env` 两个文件人肉比对缺漏。变量名容易撞、容易漏，无法回答「这个 agent 部署到底需要哪些密钥、设了没有」。

## What Changes

采用**混合密钥模式**（默认运维在主机填，可选平台加密注入）：

- **导出层补齐**：`agent_file_from_store` 回填 `tenant_id` / `team_id` / `skills_dir`；`model_overrides` 结合 providers store 展开为 `models.targets[*]` + `routes`（`api_key_env` 复用 provider 级）；`mcp_server_ids` → `mcp_servers`；`channel_agents` / `user_agents` → `bindings.channels` / `bindings.users`；`agent_kbs` → `knowledge.bindings`。
- **加密 secret store**：新表 `agent_secrets(agent_id, env_name, ciphertext, updated_at, updated_by)`，对称加密（AES-GCM/Fernet），主密钥来自进程 env `FLEETENT_SECRET_KEY`，密文落 `users.db`，**无外部 KMS**。经统一 DB runtime / store 边界，named params，Alembic 迁移。
- **per-agent 密钥槽元数据**：每个 `*_env` 槽记 `{ env_name(自动派生 FLEETENT_AGENT_<NAME>_<SLOT>，可改), mode: operator | inject }`。`mode` / `value` 是平台侧元数据，**不进 `agent.yaml`**（`agent.yaml` 仍是纯引用，守住「无密钥 inline」）。
- **API**：`PUT` 写值（write-only 收值，永不回显）、`GET` status（只回 set/unset）、`GET` required env names（复用 `_env_var_names` 扫当前配置）。
- **materialize resolver**：`_seed_env` 接入 secret resolver——`inject` 槽解密写 `NAME=value`，`operator` 槽写 `NAME=` 并保留运维已填值。
- **console CredentialField + 「所需密钥」面板**：每个密钥槽一个控件（来源单选 运维填 / 平台注入；inject 显示 password + set/unset chip；高级里显示自动 env 名）；面板列出当前配置 required `*_env` + mode + 状态 + 复制 `.env` 模板 + 校验缺失。模型密钥复用所选 provider，不让 agent 重填。
- **`.env.example` 拆分**：保留**进程级**精简模板（`FLEETENT_SECRET_KEY` / `DATABASE_URL` / `MICROSANDBOX_URL` / `CONTEXT_*` / `PERMISSION_GATE_*` / `LOG_FORMAT`——`agent.yaml` 引用不到的）；agent 引用的密钥从模板删除，改由 materialize 生成 + 面板复制。

部署顺序：`0` 平台 bootstrap（含 `FLEETENT_SECRET_KEY`，先于一切）→ `1` console 配置 agent（inject 槽当场输值加密存，operator 槽只声明名）→ `2` materialize DB→file（写 `agent.yaml` 纯引用 + `.env` scaffold，inject 已填 / operator 留空）→ `3` 部署主机运维补 operator 空值 → `4` `fleetent agent run`。

## Capabilities

### New Capabilities

- `agent-credential-authoring`: per-agent 密钥槽元数据、加密 secret store、write-only 凭据 API、required-env 派生契约。

### Modified Capabilities

- `platform-agent-lifecycle`: materialize 导出完整 agent 定义（model/mcp/bindings/knowledge/tenant/team/skills_dir）并按密钥 mode resolve `.env`；`.env.example` 拆分为进程级模板。

## Module Boundary Impact

- **owning package**：`platform` 拥有 secret store、密钥槽元数据、凭据 API、materialize resolver；`agent_config` 拥有 `models.targets/routes` 的展开 schema；console 静态资源拥有 CredentialField/面板 UI。
- **public API surface**：凭据 API 暴露 write-only 写值、status 查询、required-names 查询；secret store 暴露 set / get-decrypted（仅 materialize 内部用）/ status。
- **owned tables**：新增 `agent_secrets`；密钥槽元数据复用 `agent_versions` 的 JSON 列或新增小表（design 定）。
- **config namespace**：`agent.yaml` 仍只含 `*_env` 引用；mode/value 仅在平台 DB；进程级 env 在 `config/agent/.env.example`。
- **cross-module dependencies**：materialize 依赖 secret store 解密；console 依赖凭据 API；secret store 不依赖 agent runtime 内部。
- **migration / shim plan**：MVP 未上线，无运行期兼容 shim；`.env.example` 直接拆分；新增 `FLEETENT_SECRET_KEY` 为部署必需项。

## Impact

- **代码**：`platform/agent_lifecycle/materialize.py`、新 secret store 模块、凭据 API、`agent_config.py`（model 展开）、`src/fleetent/static/admin.html`。
- **配置**：`config/agent/.env.example` 拆分 + 新增 `FLEETENT_SECRET_KEY`；`config/agent/agent.yaml.example` 注释更新。
- **数据库**：新增 `agent_secrets` 表（Alembic 迁移）+ 可能的密钥槽元数据列。
- **删除**：`.env.example` 中 agent 引用的密钥占位（移交 materialize 生成）。
- **分支**：基于并合回 `main`。
