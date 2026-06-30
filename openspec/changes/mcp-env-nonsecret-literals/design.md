## Context

修复点收敛在前序 change `mcp-stdio-env-secret` 已确立的一处：`materialize.desired_state_payload_from_agent_file` 的捕获-剥离-回挂三步。前序按「仅 `env:` 前缀的值可保留、其余明文一律剥离」切分，并把「明文绝不下发」立为刻意安全姿态（含测试）。本 change 重新确立 MCP `env` 的下发口径：**用写法表达密/非密**——`env:VAR` 是 secret 指针，明文是 operator 声明的非密配置。这同时修好 email/site 贯通，并去掉了「需要逐个变量名维护白名单」的负担。

## Goals / Non-Goals

**Goals**
- MCP `env` 中 operator 手写的明文非密钥值（email/site 等）完整贯通到 stdio 子进程。
- 口径**通用**：任何非密配置写明文即可，无需改代码 / 维护清单。
- 真 secret 仍有明确通道：`env:VAR` 引用 + secret 存储；`credential_ref` 仍剥离。

**Non-Goals**
- 不改 `_strip_secret_plumbing` 对 `credential_ref` 的剥离、不改回挂逻辑。
- 不改运行时 `_resolve_env_ref` / `_subprocess_env`（对非 `env:` 值已整值透传）。
- 不改 `collect_env_var_names` / node `reconcile` / `ensure_env_scaffold`（明文非 `env:` 引用 → 不当 referenced env name → 不进 `.env` scaffold，作为字面量留在 `agent.yaml`）。
- 不引入新 secret 通道。

## Decisions

### 决策1：用写法切分密/非密——`env:` = secret 指针，明文 = 非密配置
email/site 与误填的明文 secret 在**值层面**不可区分，但在**写法**上可区分：secret 在本系统本就要求走 `env:VAR` 引用 + secret 存储；因此「写成明文」即 operator 对该值非密的显式声明。`_mcp_env_refs_by_id` 的保留判定改为「值为 `str` 即保留」（`env:` 引用与明文一并捕获、回挂）：

```python
kept = {str(k): v for k, v in env.items() if isinstance(v, str)}
```

`_strip_secret_plumbing`（仍剥 `credential_ref` 及通用 `env` 键，由回挂补回）与 `_restore_mcp_env_refs` 不动。影响面只在 MCP env 子树。

### 决策2：安全姿态反转（显式记录）
前序 change `mcp-stdio-env-secret` 的 design 把「明文 secret 绝不下发」列为有意取舍并写测试。本 change **反转**为：真 secret 必须 `env:VAR`；明文 env 视为非密、照常下发。对应安全测试 `test_serialize_desired_state_payload_still_strips_secret_values` 重写为新契约：`credential_ref` 仍被剥、MCP env 内明文 SHALL 保留。该反转是有意的、经评审记录于此。

### 决策3：为何不选白名单 / 显式标注
- **变量名白名单**（`{ATLASSIAN_USER_EMAIL, ATLASSIAN_SITE_NAME}`）：能保住旧安全测试，但需逐项人工维护、每加一个非密 MCP env 都要改代码，且语义隐晦。否决（保留为「若需在不反转姿态下小步修」的备选）。
- **显式非密标注**（值写 `public:...` 或新增 `env_public` 字段）：要改 config schema + 平台 UI + operator 习惯，存量明文不受益。否决。
- **本方案（写法即声明）**：零维护、通用、与「secret 走 `env:` + 存储」的既有设计自洽。取舍是放弃「对误填明文的防御性剥离」。

### 决策4：与既有链路对齐
明文值非 `env:` 引用，`collect_env_var_names`（只收 `env:` 前缀）不会把它当 referenced env name → 不进 `.env` scaffold、不被空值覆盖；原样写入 `agent.yaml`，运行时整值透传给 stdio 子进程（与 standalone agent 行为一致）。无需改下游。

## Risks / Trade-offs

- **风险**：operator 误把真 secret 写成明文 env（而非 `env:` 引用）→ 该明文进 desired-state 载荷与 `agent.yaml`（不再被剥）。**取舍/缓解**：这是本 change 有意接受的姿态变更；secret 的正确写法（`env:VAR` + 存储）在文档/契约中明确；platform→node 为鉴权信道；该值本就明文存于平台 DB（`mcp_servers.env`）。自托管单租户场景下可接受。
- **回归面**：仅 `desired_state_payload_from_agent_file` 的 MCP env 子树。`credential_ref` 剥离、`env:` 引用保留、非 MCP 载荷均不变；新增/重写测试覆盖明文保留与 `credential_ref` 仍剥。

## Migration Plan

无 schema / 数据迁移。行为细化，向前兼容。change 落地后 platform 重新物化（或下次配置变更触发 reconcile）把明文 env 写入各 managed agent 的 `agent.yaml`；node 重起对应 agent 后 stdio MCP 子进程获得这些值。
