## Why

managed（node 托管）部署下，per-user MCP OAuth 的 **per-agent client_secret 无法解析**，被迫退回全局密钥兜底，且 **per-agent token 隔离形同虚设**——所有 agent 的 token 共用一格。根因是 agent 身份在两处断链：

1. **agent 侧身份传空**：IM 入站轮次里 `normalizer.route()` 不向 `loop.run()` 传 `agent_name`（这是为 workspace scope 一致性有意为之），导致 `tool_context.agent_name` 为空 → `tools/registry.py` 把空串当作 per-user 三元组的 `agent_id` → pending / token 记录 `agent_id=''`。
2. **平台侧解析只认数字 id**：`mcp_oauth_service._resolve_client_secret` 用 `int(agent_id) if agent_id.isdigit() else None`；而运行时三元组的 agent 身份是**名字**（`registry.py` 传的是 `agent_name`），`agent_secrets` 却按**数字 registry id** 存 → 名字永远映射不到 per-agent 作用域，只能落全局。

现网 bi-intern 的 Google Drive OAuth 曾因此报 `exchange_transient`（platform 取到空 client_secret → token 端点 400），只能临时补一份全局 secret 兜底。本 change 根治两处断链，使「全局连接器定义 + per-agent 密钥值」这一既定模型在 managed OAuth 下真正生效。

## What Changes

- **P2（agent 侧）**：MCP client 在公开入口 `call_tool` 归一化 per-user 三元组的 `agent_id`——当调用方未提供（managed IM 轮次的常态）时，取本进程**唯一活跃 agent** 的名字（`agent_config.active_agent().name`）。归一化只发生一次，向下游 resolve / trigger(pending) / 子进程 env 注入 / http auth 一致流转。不改 `normalizer.route()` 的 `run()` 传参，故 workspace scope 行为零改动。
- **P1（平台侧）**：`mcp_oauth_service._resolve_client_secret` 改为把**原始 agent 身份串**透传给注入的 resolver；在组合根 `server.py` 注入一个能把 **name→numeric id** 映射（经 `agent_store.get_by_name`）再查 `agent_secrets`、并保留全局作用域兜底的 resolver。resolver 契约由 `(int|None, str)` 调整为 `(str|None, str)`。
- 行为收益：per-agent client_secret 可解析（不再强制全局）、per-agent token 按真实 agent 身份隔离。

**非目标（YAGNI）**：不改 token 存储 schema（三元组键沿用文本 `agent_id`）；不改 standalone 授权/回调路径（其 client_secret 走 agent 自身 env，本就不受影响）；不改 workspace / exchange scope 归属；不引入 per-agent client_id 解析（client_id 已由 agent 侧 env:REF 正确解析）。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `mcp-managed-oauth`: 回调/刷新交换所用的 client_secret 解析，SHALL 支持运行时三元组以 agent **名字**为身份，映射到 `agent_secrets` 的 per-agent 作用域（数字 registry id），并保留全局作用域兜底。
- `mcp-per-user-oauth`: per-user 三元组的 `agent_id` SHALL 为发起调用的运行 agent 身份；当调用方未透传身份时，SHALL 回退到本进程唯一活跃 agent，避免落空串导致隔离失效。

## Impact

- **owning packages**：`integrations/mcp/client.py`（P2 归一化）、`platform/connector_management/mcp_oauth_service.py`（P1 透传）、`server.py`（P1 注入映射 resolver）。
- **public API surface**：`mcp_oauth_service.set_client_secret_resolver` 的 resolver 签名 `(int|None,str)→(str|None,str)`（仅平台内部缝，调用点在 server.py）。`call_tool` 签名不变。
- **owned tables**：无（不改 schema；`agent_secrets` / `mcp_user_tokens` 结构不动）。
- **config namespace**：无。
- **cross-module dependencies**：P1 的 name→id 映射放在 `server.py` 组合根（可 import `agent_store`），保持 `connector_management` face 不 import `agent_lifecycle`/`agent_store`（plane 边界不破）。P2 在 `integrations/mcp/client.py` 内 import agent 侧 `agent_config`（非 platform，符合解耦契约）。
- **migration / shim plan**：无迁移。既有以 `agent_id=''` 存的 token 在归一化后按新身份查不到 → 用户**一次性重新授权**（可接受，记录于 design）。
