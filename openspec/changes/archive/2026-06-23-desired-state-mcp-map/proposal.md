## Why

给 managed agent 绑定 MCP server 后，node 落地的 `agent.yaml` 里 `mcp_servers` 是 **list 形态**，agent 进程启动时校验直接抛 `ValueError: legacy list-of-id 'mcp_servers' is not supported; use the 'mcpServers' map`，反复崩溃起不来。任何绑了 MCP 的 managed agent 都受影响。

根因：`platform/agent_lifecycle/materialize.py` 的 `desired_state_payload_from_agent_file` 只做了 `_strip_secret_plumbing(model_dump(...))`，漏调同文件已存在的 `_mcp_payload_to_map`——后者专门把 dump 出的 `mcp_servers` list 改写成 agent 接受的 `mcpServers` map（key=server id）。另一条写 `agent.yaml` 的路径（`write_home`）有调它，desired-state 下发路径没调。

## What Changes

- `desired_state_payload_from_agent_file` 在 dump + 剥密之后、返回之前调用 `_mcp_payload_to_map(payload)`，使 desired-state 载荷的 MCP 配置以标准 `mcpServers` map 形态下发，与 `write_home` 一致。
- 顺序保证：先 `_strip_secret_plumbing`（剥离 `env` 字典与 `*credential_ref`），再 `_mcp_payload_to_map`（list→map），密钥值仍被剥除。
- 不改 agent 运行时、不改 `agent_config.py`；只补 platform 侧下发载荷形态。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `node-desired-state-api`: desired-state 配置载荷新增一条 requirement——MCP server 配置 SHALL 以标准 `mcpServers` map 形态下发（非 legacy `mcp_servers` list），使 node 写出的 `agent.yaml` 能被 agent 运行时 `load_agent_file` 成功加载。

## Impact

- **owning package**: `platform/`（`agent_lifecycle/materialize.py` 单函数补一行调用 + 理顺顺序）
- **public API surface**: `materialize.desired_state_payload_from_agent_file` 行为修正（返回 `mcpServers` map 而非 `mcp_servers` list）；签名不变。
- **owned tables**: 无
- **config namespace**: 无
- **cross-module dependencies**: 不触碰 agent 运行时与 `agent_config.py`；仅消费同文件已有的 `_mcp_payload_to_map`。
- **migration / shim plan**: 无 schema/迁移；行为纯修正，已有非 MCP agent 下发不受影响（`_mcp_payload_to_map` 对无 MCP 载荷 no-op）。
- 受影响代码：`src/fleetent/platform/agent_lifecycle/materialize.py`；现有断言 list 形态的测试 `tests/unit/platform/node_management/test_node_config_payload.py` 同步更新为 map 形态（原断言编码了 bug 行为）。
