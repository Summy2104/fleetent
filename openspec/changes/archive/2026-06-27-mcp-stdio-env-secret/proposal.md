## Why

托管模式（platform + node）下，stdio 类 MCP server（jira / slack-mcp / confluence / bitbucket）在 `mcpServers` 的 `env` 字段里用 `env:XXX` 声明的变量，**进不了 MCP 子进程**，导致这些 server 在托管部署下拿不到 token、连不上。

根因是 platform 下发渲染**剥离过宽**，级联出两个断点（都在托管下发路径上）：

- **断点1（过度剥离）**：`platform/agent_lifecycle/materialize.py` 的 `_strip_secret_plumbing()` 对任意 `key == "env"` **整段删除**。schema 中字面名为 `env` 的 dict 字段**只有** `McpServerSettings.env`（`config.py:243`），其余皆为 `*_env` 字符串指针（不受影响）。于是 desired-state 下发载荷里 MCP 的 `env` 被整删——**连 `env:XXX` 这种纯变量名引用也一并删掉**。而 `env:XXX` 并非 secret，只是「去 `.env` 取哪个变量」的指针，与已被保留的 `api_key_env` 同类。
- **断点2（断点1的级联）**：node 的 `reconcile._write_home()`（`reconcile.py:155`）用 strip 后的 config 重算 `referenced_env_names()` → `collect_env_var_names()`（`agent_config.py:846`，本就会扫 mcp `env`/`headers` 里的 `env:` 引用）。因 env 已被删，扫不到这些名字 → `ensure_env_scaffold()` 既不 scaffold 也不填值。同时 agent 运行时 `client.py:_subprocess_env()`（`client.py:952`）读到的 `server.env` 为空，stdio 子进程拿不到任何变量。

下游本就就绪、无需改动：`parse_mcp_servers(expand_env=False)`（`config.py:327`）在 map↔list 往返保留 `env` 且不展开 `env:`；运行时 `_resolve_env_ref()`（`client.py:897`）从 `os.environ`（由 `.env` 经 `load_dotenv` 填充）取值；真实 secret 值经 `_agent_secrets()`（`node_desired_state_api.py:237`）的 inject credential slot 通道下发。**因此只要让下发载荷保留 `env:` 引用、仍剥明文，断点2 与运行时即自动级联打通**。

## What Changes

- `desired_state_payload_from_agent_file` 在 `_strip_secret_plumbing` 删 env **之前**，先按 server 捕获每个 MCP `env` 字典中「`env:` 开头的引用」（明文值不捕获）；在 `_mcp_payload_to_map` 渲染出 `mcpServers` map **之后**，把这些 `env:` 引用回挂到对应 server 条目的 `env` 字段。
- 明文 env 值仍被 `_strip_secret_plumbing` 剥离（保持「禁止明文下发」的安全意图不变）；`_strip_secret_plumbing` 保持通用不动——其它/未来的 `env` 字段、`*credential_ref` 照旧全剥。
- **不改** agent 运行时、**不改** `agent_config.py`、**不改** node `reconcile`；断点2 与子进程注入均为断点1 修好后的自动级联。
- 与并行改动解耦：改动落在 `desired_state_payload_from_agent_file` + 两个模块级 helper，**不触碰** `_mcp_servers_for_agent()`（另一窗口在该函数补 headers 同步），合并冲突面最小。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `node-desired-state-api`: 细化「保留非密指针、仅剥密钥值」——MCP `env` 字典内 `env:VAR` 形态的值属**非密变量名指针**（语义同 `api_key_env`），SHALL 被保留下发；仅剥离 `env` 字典内的**明文值**与 `credential_ref`。使绑定 stdio MCP 的 managed agent 在 node 写出的 `.env` 中能 scaffold 到该变量名、并由既有 secret 通道填值，最终经 `env:VAR` 解析注入 stdio 子进程。

## Impact

- **owning package**: `platform/agent_lifecycle`（唯一代码改动处：`materialize.py` 的 `desired_state_payload_from_agent_file` + 2 个新模块级 helper）
- **public API surface**: `materialize.desired_state_payload_from_agent_file` 行为细化（保留 MCP `env:` 引用），**签名不变**。
- **owned tables**: 无（无新增/变更表）
- **config namespace**: 无新增
- **cross-module dependencies**: 不变；无新增 import，**特别是无 agent→platform 反向依赖**。`node` / `runtime` 仅作为消费方被测试验证，无代码改动。
- **migration / shim plan**: 无 schema / 迁移；纯行为细化，向前兼容。无 MCP `env`、或 `env` 仅含明文的 agent 下发不受影响。
- **验证基线**: 仅改 platform 侧渲染、运行时零改动，「无 platform、platform 表不存在」下 `fleetent agent run` 基线天然不受影响。
- 受影响测试：`tests/unit/platform/node_management/test_node_config_payload.py`（既有断言编码了旧「整剥 env」语义，同步更新为「引用保留 / 明文剥离」）；新增 platform→node 级联 integration 用例。
