## Context

`agent.yaml` 与 `.env` 故意分离：前者只含 `*_env` 引用（密钥**名**），后者含密钥**值**，满足「密钥不 inline、数据不出内网」。但平台今天既不能从已存定义生成可部署的 `agent.yaml`（导出层丢字段），也没有让运维舒服地维护密钥的交互（手敲变量名、人肉比对两个文件）。

本 change 在不破坏「`agent.yaml` 纯引用」前提下，补齐 DB→file 导出，并引入**混合密钥模式**：默认运维在部署主机填值，单个密钥可选由平台加密注入。

```text
authoring (平台 DB)                materialize (DB→file)            runtime
  agent 定义 + 密钥槽元数据   ──▶   agent.yaml (纯 *_env 引用)   ──▶  fleetent agent run
  inject 槽: 加密密文              .env (inject 已填/operator 留空)
```

## Goals / Non-Goals

**Goals:**

- 从平台已存的 agent 定义生成**可真实部署**的 `agent.yaml`（真实 model 路由、MCP、bindings、knowledge）。
- 运维在 console 编辑时**不手敲 env 变量名**、不对两个文件人肉比对；一眼看到「这个 agent 需要哪些密钥、设了没」。
- 平台默认**不持有**密钥值（operator 模式）；inject 模式下密文加密落库，密钥由运维 env 提供，无外部 KMS。
- `agent.yaml` 始终是纯引用，mode/value 只在平台侧。

**Non-Goals:**

- 不设计完整 `platform.yaml` 的字段集；只声明平台进程 env 与 Agent env 的边界。
- 不引入外部 secret manager（Vault/KMS）——本 change 用进程 env 主密钥 + 对称加密。
- 不重做 providers / KB / bindings 的业务存储；只接它们到导出层。
- 不在本 change 落 governance/deployment 旋钮（context_*/agent_*/session_* 等）的 per-agent authoring——它们继续走 schema 默认（后续 change）。

## Decisions

### D1 — 导出层补齐：从「8 字段」到「完整定义」

[agent_file_from_store](../../../src/fleetent/platform/agent_lifecycle/materialize.py) 扩展为回填平台已存的全部字段：

| agent.yaml 段 | 平台来源 | 处理 |
|---|---|---|
| `tenant_id` / `team_id` / `skills_dir` | `agents` 行 | 直接回填（今天被丢） |
| `models.targets` / `routes` | `agent_versions.model_overrides` + providers store | D2 展开 |
| `mcp_servers` | `mcp_server_ids` + `mcp_servers` 表 | 按 id 装配 inline server 列表 |
| `bindings.channels` / `users` | `channel_agents` / `user_agents` | 映射为 `platform:channel` / user id |
| `knowledge.bindings` | `agent_kbs` | 映射 `{tenant_id, kb_id, default}` |

`default_models()` 仅在 agent 无任何 model_overrides 时作为 fallback，不再无条件覆盖。

### D2 — model 密钥复用 provider，不在 agent 重复维护

用户在 console 为 agent 选 provider（已有 providers store + `AG_PROVIDERS`）。展开 `models.targets[*]` 时，`api_key_env` **直接复用 provider 自己的 `api_key_env`**。即：模型密钥在 provider 级 author 一次，多个 agent 复用同一 `*_env`。agent 的 model 槽不再单独出现密钥输入。

### D3 — 密钥槽元数据：mode + env_name，存平台、不进 agent.yaml

每个需要 `*_env` 的槽，平台侧记一条元数据：

```text
slot = {
  env_name : 自动派生 "FLEETENT_AGENT_<NAME>_<SLOT>"，高级里可改
  mode     : "operator" (默认) | "inject"
}
```

- `env_name` 进 `agent.yaml` 的对应 `*_env` 字段（纯引用，不变）。
- `mode` 决定 `.env` 由谁填，**不出现在 `agent.yaml`**——保证 agent.yaml 仍是纯引用、可审计、无平台耦合。
- 存储位置：复用 `agent_versions` 的 JSON 列承载槽元数据（与 model_overrides 同位），避免新增表；密钥**值**单独进 D4 的 `agent_secrets`。

env_name 派生需稳定 + 防撞：`<NAME>` 取 agent name 的 upper-snake、`<SLOT>` 取 `slack_bot` / `mcp_<id>` / `kb_<id>` 等槽标识。运维改名后 env_name 不自动变（避免 silent 漂移），改名走显式「重算 env 名」动作。

### D4 — 加密 secret store（仅 inject 模式用值）

新表（Alembic 迁移，统一 DB runtime / store 边界，named params）：

```text
agent_secrets(
  agent_id    INTEGER,
  env_name    TEXT,
  ciphertext  TEXT,        -- 对称加密后的密文，base64
  updated_at  TEXT,
  updated_by  TEXT,
  PRIMARY KEY (agent_id, env_name)
)
```

- 加密：对称 AEAD（Fernet 或 AES-GCM），主密钥从进程 env **`FLEETENT_SECRET_KEY`** 读取。无 key → inject 写/读 fail loud（operator 模式不受影响）。
- 密文落 `users.db`，内网自托管，无外部 KMS——守住数据主权。
- store API：`set(agent_id, env_name, plaintext)`（加密存）、`get_decrypted(agent_id, env_name)`（仅 materialize 内部调用）、`status(agent_id, env_name) -> set|unset`（永不返回明文）、`delete`。

### D5 — write-only 凭据 API

| 方法 | 路径 | 行为 |
|---|---|---|
| `PUT` | `/admin/agents/{name}/secrets/{env_name}` | 收 plaintext，加密存；**响应不回显值**，只回 `{env_name, status: "set"}` |
| `DELETE` | `/admin/agents/{name}/secrets/{env_name}` | 清除 inject 值 |
| `GET` | `/admin/agents/{name}/secrets` | 列每个槽 `{env_name, mode, status: set\|unset}`，**永不含明文** |
| `GET` | `/admin/agents/{name}/required-env` | 复用 [`_env_var_names`](../../../src/fleetent/platform/agent_lifecycle/materialize.py) 扫当前定义，返回 required `*_env` + 来源标签（Models/MCP/Connectors/Knowledge）+ mode + status |

`required-env` 是面板的数据源；它扫的是 materialize 出的 `AgentFile`，所以依赖 D1 导出层先补齐。

### D6 — materialize resolver：按 mode 写 .env

[`_seed_env`](../../../src/fleetent/platform/agent_lifecycle/materialize.py) 增加 secret resolver 入参：

```text
for env_name in required_names:
    if slot.mode == "inject" and secret_store.status == "set":
        line = f"{env_name}={secret_store.get_decrypted(...)}"
    else:                              # operator 模式 或 inject 未设
        line = f"{env_name}={existing.get(env_name, '')}"   # 保留运维已填值
```

- operator 槽永远只写 `NAME=`（已填则保留），平台不碰值。
- inject 槽解密写真值。
- `agent.yaml` 生成与 mode 无关，永远纯引用。

### D7 — Platform ENV 与 Agent ENV 分离

`FLEETENT_SECRET_KEY`、`DATABASE_URL`、`MICROSANDBOX_URL`、`LOG_FORMAT` 等跨 agent 的平台进程变量属于 Platform ENV 模板。它们不进入 Agent `.env`，也不应放在任何 Agent 模板目录下。

```text
FLEETENT_SECRET_KEY=        # 新增；secret store 主密钥，inject 模式必需
DATABASE_URL=
LOG_FORMAT=
MICROSANDBOX_URL=
```

Agent `.env` 是 materialize 写到 `<agent-home>/.env` 的部署产物。agent 引用的密钥（`FLEETENT_MODEL_*` / `SUPPORT_SLACK_*` / MCP / KB）不放入平台 env 模板，改由 materialize 按实际配置生成 + console 面板 `[复制 .env 模板]` 提供。可选保留一个「完整 Agent env example」由示例 agent 跑 materialize 自动生成，标注「自动生成，勿手改」。

### D8 — console CredentialField 控件 + 「所需密钥」面板

每个密钥槽渲染统一控件（不显示裸变量名输入）：

```text
Slack Bot Token
  来源:  ◉ 运维在主机填    ○ 平台注入
  ─ 运维填  → 显示 env 名 + [复制]，不收值
  ─ 平台注入 → [ •••••• ] 🟢已设置/⚪未设置  [替换][清除]
  ⚙ env: FLEETENT_AGENT_SUPPORTBOT_SLACK_BOT   (自动, 高级可改)
```

agent 编辑页底部「所需密钥」面板（数据来自 `GET /required-env`）：

```text
部署需要 N 个密钥:
  🟢 FLEETENT_MODEL_PRIMARY_API_KEY   Models·primary    平台注入·已设置
  ⚪ SUPPORT_SLACK_BOT                 Connectors·slack  运维填
  ...
  [复制 .env 模板]  [校验缺失]
```

write-only：inject 值只显 set/unset chip，密文永不回浏览器。

## 部署顺序

```text
0. 平台 bootstrap (一次性, 先于一切; Platform ENV)
   FLEETENT_SECRET_KEY / DATABASE_URL / MICROSANDBOX_URL …
        │
        ▼
1. console 编辑 agent 配置
   prompt / 选 provider / MCP / KB / connectors / bindings
   每个密钥槽选 mode:
     inject   → 当场输值(加密存)      ← 值在这一步就定了
     operator → 只声明 env 变量名
        │  (派生 required *_env)
        ▼
2. materialize  DB→file
   写 <home>/agent.yaml (纯引用)
   写 <home>/.env       (inject 已填 / operator 留空, 保留运维值)
   面板列出 required + set/unset
        │
        ▼
3. Agent 部署主机
   运维补 operator 槽空值到 .env      ← 唯一的手动设 env
        │
        ▼
4. fleetent agent run
```

要点：inject 的值随 config 一起设了；部署前手填只剩 operator 槽；Platform ENV（含 secret key）是前置第 0 步，不写入 Agent home；materialize 可每次保存就跑（持续 DB→file）。

## Error Handling

- inject 模式写/读但 `FLEETENT_SECRET_KEY` 未设或无效 → fail loud（明确提示缺主密钥）。
- `PUT` secret 收到空值 → 拒绝（用 `DELETE` 清除而非写空）。
- `GET secrets` / 任何响应 → 绝不含明文密文；测试断言响应体不出现值。
- materialize 时 inject 槽标记 set 但解密失败（key 轮换/密文损坏）→ fail loud，不静默写空。
- `required-env` 扫描依赖导出层；导出层未接的字段（governance 等）不产生 `*_env`，不误报。
- env_name 撞名（两个槽派生同名）→ author 时 fail loud，提示改高级 env 名。

## Observability / Operations

- 凭据写/删记审计（[audit_log](../../../src/fleetent/platform/skill_management/skill_admin_api.py) 同款）：`agent.secret_set` / `agent.secret_delete`，记 agent + env_name + updated_by，**不记值**。
- materialize 记每次导出的 required env 数 + inject/operator 拆分计数（不记值）。
- `FLEETENT_SECRET_KEY` 轮换：旧密文需重新加密——本 change 提供 fail-loud 检测，轮换工具留后续。

## Risks / Trade-offs

- [平台持有 inject 密文] → 仅 inject 模式、对称加密、key 在运维 env；operator 模式仍零持有。默认 operator，守住保守姿态。
- [复用 `agent_versions` JSON 列存槽元数据] → 避免新表，但 JSON 列语义变宽；用明确 key 前缀隔离。
- [env_name 不随改名自动变] → 避免 silent 漂移，代价是改名要显式重算；可接受。
- [导出层是面板前置依赖] → tasks 中导出层任务排在凭据 API/面板之前。
- [主密钥单点] → key 丢失则 inject 值不可恢复；文档明确 operator 模式不受此影响，关键密钥建议 operator。

## Open Questions

无。以下已关闭：

- 密钥值默认运维填，inject 可选（混合模式）。
- 主密钥来自进程 env `FLEETENT_SECRET_KEY`，无外部 KMS。
- mode/value 不进 `agent.yaml`；agent.yaml 保持纯引用。
- model 密钥复用 provider 级，不在 agent 重填。
- governance/deployment per-agent authoring 不在本 change。
