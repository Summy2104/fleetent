## Why

托管模式（platform + node）下，MCP server 的 `env` 字典里用**明文字面量**配置的**非密钥变量**——典型是 @aashari Atlassian MCP（jira / confluence / bitbucket）做 `email:token` Basic auth 所需的 `ATLASSIAN_USER_EMAIL` 与 `ATLASSIAN_SITE_NAME`——**进不了 node 盘上的 `agent.yaml`，也进不了 MCP 子进程**。结果：平台 DB（`mcp_servers.env`）里明明配了这些值，下游 MCP 仍因缺 email/site 报 `Authentication credentials are missing`。

根因在前序 change `mcp-stdio-env-secret` 立下的下发渲染口径：`platform/agent_lifecycle/materialize.py` 的 `desired_state_payload_from_agent_file` 经 `_mcp_env_refs_by_id` 捕获 MCP `env` 中**仅 `env:` 开头的引用**、`_strip_secret_plumbing` 整段删除 `env`、再 `_restore_mcp_env_refs` 回挂引用。该口径把**所有明文 env 值一律当 secret 剥掉**。`env:VAR` 引用得以贯通，但**明文非密钥配置（email/site）被一并剥除**——而它们既非 secret，又**无法**用 `env:VAR` + secret 通道表达。

旁证：standalone / 手写 agent（如 `dev-intern`，不过平台物化）`agent.yaml` 里把 email/site 写成明文即可正常工作——运行时 `_subprocess_env` / `_resolve_env_ref`（`integrations/mcp/client.py`）对非 `env:` 值本就整值透传给子进程。只有**平台物化的 agent** 在下发渲染处被剥。

## What Changes

确立 MCP `env` 字典的下发口径（让「写法」直接表达「密/非密」）：

- **`env:VAR` 形态值 = secret 指针**：保留下发（指针本身非密；值经既有 secret 通道 / `.env` 填充）。沿用现状。
- **其余字符串明文值 = operator 显式声明的非密配置**：原样保留下发、由 node 写进 `agent.yaml`、运行时整值透传给 stdio 子进程。**这是本 change 放开的部分**（此前被一律剥离）。
- **`credential_ref` 仍被剥离**：它是专用 secret-值字段，非 operator 手写的 `env` 表面。

实现上：`_mcp_env_refs_by_id` 的保留判定由「值以 `env:` 开头」放宽为「值为字符串即保留」（`env:` 引用与明文一并捕获、回挂）；`_strip_secret_plumbing`（含 `credential_ref` 剥离）与回挂逻辑不动。

**安全契约调整（须知）**：前序 change 把「明文一律剥离、绝不下发」立为刻意姿态并写了测试。本 change **反转该姿态**为「真 secret 必须用 `env:VAR` 引用 + secret 通道；写成明文即视为非密配置、照常下发」。对应安全测试同步重写为新契约（`credential_ref` 仍剥、env 内明文照常下发）。

不改 agent 运行时、不改 `agent_config.collect_env_var_names`（只收 `env:` 前缀名；明文不进 `.env` scaffold，作为字面量留在 `agent.yaml`）、不改 node `reconcile`。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `node-desired-state-api`: 调整 MCP `env` 的下发口径——`env:VAR` 引用与**operator 手写的明文值**均 SHALL 保留下发（前者为 secret 指针，后者为 operator 声明的非密配置）；仅 `credential_ref` 与经 secret 通道管理的密钥值 SHALL 不入载荷。真 secret 必须经 `env:VAR` 表达，明文 env 由 operator 负责其非密性。

## Impact

- **owning package**: `platform/agent_lifecycle`（唯一代码改动处：`materialize.py` 的 `_mcp_env_refs_by_id` 判定）
- **public API surface**: `materialize.desired_state_payload_from_agent_file` 行为细化（保留 MCP env 明文），**签名不变**。
- **owned tables**: 无
- **config namespace**: 无新增（沿用现有 `mcpServers.env`）
- **cross-module dependencies**: 不变；无新增 import，**无 agent→platform 反向依赖**。`node` / `runtime` 仅作为消费方被测试验证，无代码改动。
- **migration / shim plan**: 无 schema / 数据迁移；行为细化，向前兼容（已有纯 `env:` 引用 / 无 env 的载荷行为不变）。
- **安全姿态变更**: 由「明文一律剥离」改为「`env:` = secret 通道，明文 = 非密配置照常下发」。残余风险：operator 误把真 secret 写成明文 env → 进载荷/`agent.yaml`（不再被剥）。缓解：文档明确「secret 必须用 `env:`」；platform→node 为鉴权信道；该值本就明文存于平台 DB。
- **验证基线**: 仅改 platform 侧渲染、运行时零改动，「无 platform、platform 表不存在」下 `fleetent agent run` 基线天然不受影响。
- 受影响测试：`tests/unit/platform/node_management/test_node_config_payload.py::test_serialize_desired_state_payload_still_strips_secret_values` 重写为新契约（`credential_ref` 仍剥、env 内明文保留）；新增「明文 env 被保留下发」unit + platform→node 级联 integration 用例。
