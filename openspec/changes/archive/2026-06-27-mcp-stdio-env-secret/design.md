## Context

修复点收敛在 platform 下发渲染的一处：`materialize.desired_state_payload_from_agent_file`。需在「保留 `env:` 引用」与「绝不下发明文 secret」之间精确切分，且不与并行的 headers 改动在同一函数冲突。其余链路（node 收名、运行时解析、secret 值通道）经调研确认已就绪。

## Goals / Non-Goals

**Goals**
- MCP `env` 字典里的 `env:VAR` 引用完整贯通到 stdio 子进程（托管模式）。
- 明文 secret 绝不进 `agent.yaml` / 下发载荷。

**Non-Goals**
- 不改运行时 `_resolve_env_ref` / `_subprocess_env`（已能解析 `env:`，整值替换、从 `os.environ` 取）。
- 不改 `collect_env_var_names` / node `reconcile` / `ensure_env_scaffold`（已能从 config 收集 mcp env 引用并由 secrets 填值）。
- 不动 HTTP `headers` 的 `env:` 引用（`headers` 不被 `_strip_secret_plumbing` 剥离，本就保留；且 headers 同步由并行 change 处理）。
- 不改 secret 值下发通道 `_agent_secrets`（inject credential slot，已贯通）。

## Decisions

### 决策1：定向保留，而非放宽通用 `_strip_secret_plumbing`
`_strip_secret_plumbing` 是通用递归剥离器，对所有 `key == "env"` 与 `*credential_ref` 生效。若改它去「按值区分 `env:` vs 明文」，会影响**所有** env 字段（含未来新增），扩大影响面与回归风险。改为在 `desired_state_payload_from_agent_file` 内**仅针对 MCP server** 捕获并回挂 `env:` 引用，通用剥离器语义保持不变。

### 决策2：捕获在 strip 前、回挂在 map 渲染后
现有顺序：`_strip_secret_plumbing(dump)` → `_mcp_payload_to_map`。env 在 strip 阶段即被删，故须在 strip **前**从 dump 出的 `mcp_servers` list 捕获每个 server 的 `env:` 引用；`_mcp_payload_to_map` 把 list 改写为按 id 键控的 `mcpServers` map 后，再按 id 回挂。两个模块级 helper：
- `_mcp_env_refs_by_id(dumped) -> {server_id: {VAR: "env:VAR"}}`：只保留 `str` 且以 `env:` 开头的值，其余（明文、非字符串）丢弃。
- `_restore_mcp_env_refs(payload, refs)`：把 refs 写回 `payload["mcpServers"][id]["env"]`（仅当该 id 存在于已渲染的 map 中）。

### 决策3：明文 / 引用的判定口径
仅当 env 值为 `str` 且 `value.startswith("env:")` 视为「引用」予以保留；其余一律不保留——交由通用剥离器剥除。此口径与 `agent_config._is_env_reference` 对 `env:` 的处理、`_resolve_env_ref` 对 `env:` 的解析一致，全链路对齐。

### 决策4：与并行 headers 改动解耦
改动不进入 `_mcp_servers_for_agent()`（对方在该函数补 `headers=row["headers"] or {}`）。本 change 只在 `desired_state_payload_from_agent_file` + 2 个模块级 helper 内活动，合并时两函数互不重叠。

## Risks / Trade-offs

- **风险**：若 operator 误把明文 secret 写进 MCP `env`（而非用 `env:` 引用 + inject slot），则该明文被剥离、且无 inject slot 兜底 → 该 secret 不下发。**取舍**：这是有意的安全姿态（禁止明文下发）；正确用法是 `env: {VAR: "env:VAR"}` + 配套 inject credential slot。
- **回归面**：仅 `desired_state_payload_from_agent_file` 的 MCP env 子树；非 MCP、无 env、纯明文 env 的载荷行为不变。

## Migration Plan
无 schema / 数据迁移。纯行为细化，向前兼容。
