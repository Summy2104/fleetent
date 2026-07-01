# Design — managed-oauth-agent-identity

## 背景与根因（代码坐实）

per-user MCP OAuth 的授权归属三元组是 `(user_id, agent_id, server_id)`。agent 侧 `tools/registry.py` 在 dispatch MCP 工具时传：

```python
agent_id=getattr(tool_context, "agent_name", None)   # 设计上 = 运行 agent 名字
```

两处断链使该值在 managed 下落空 / 无法映射：

1. **agent 身份传空**：`im_gateway/normalizer.py` 主轮次 `agent_loop.run(...)`（约 L768）**不传 `agent_name`**，且这是有意的——`_save_file_to_workspace` 用 `agent_name=None` 对齐 workspace scope 的 `"default"`（见 normalizer.py L325-341 注释）。于是 `loop` 内建的 `tool_context.agent_name` 为空 → registry 传空串 → pending / token 记录 `agent_id=''`（本地 zy-bot 与 claw1 bi-intern 均实测为空）。
2. **平台解析只认数字 id**：`platform/connector_management/mcp_oauth_service.py::_resolve_client_secret`：

```python
scoped = int(agent_id) if agent_id.isdigit() else None   # 名字非数字 → None → 只查全局
value = _client_secret_resolver(scoped, client_secret_env)
```

而 `agent_secrets` 按**数字 registry id** 存（`get_decrypted(agent_id:int|None, env)` 的 `WHERE agent_id IS :agent_id`）。名字身份永远映射不到 per-agent 行，只能命中全局（agent_id NULL）。

**现网表现**：bi-intern 的 Google Drive 授权回调 `exchange_transient`——platform 解析出空 client_secret → token 端点 400。zy-bot 之所以「没事」，仅因其密钥恰好也配了一份**全局** `GDRIVE_OAUTH_TEST_CLIENT_SECRET`（agent_id NULL），命中全局兜底。

## 方案总览

两处各修一刀，互相独立、都可单测：

```
[agent 进程]                                  [platform 进程]
call_tool(agent_id=None/'')                    /oauth/callback  (managed)
   │  _effective_agent_id():                     │ complete_callback(state)
   │  空 → agent_config.active_agent().name       │ _resolve_client_secret(pending.agent_id, env)
   ▼                                              │   透传原始身份串 → 注入 resolver
resolve/trigger/subprocess-env/http-auth         ▼
   （三元组 agent_id 一致 = 真实 agent 名）      server.py 注入 resolver:
                                                   name.isdigit()? int : get_by_name(name).id
                                                   get_decrypted(id, env)  or  全局兜底
```

### P2 — agent 侧身份归一化（`integrations/mcp/client.py`）

在**公开入口** `call_tool`（唯一 chokepoint，向下 `_call_via_session` 一致分发 `agent_id` 给 resolve / trigger / `_subprocess_env` token 注入 / http auth）归一化一次：

```python
def _effective_agent_id(agent_id: str | None) -> str | None:
    """per-user 三元组的 agent 身份：调用方未提供时（managed IM 轮次不透传 agent_name），
    回退到本进程唯一活跃 agent。多 agent dev/platform index 下 active_agent()=None，保持原值。"""
    if agent_id:
        return agent_id
    from fleetent import agent_config
    active = agent_config.active_agent()
    return active.name if active is not None else None
```

`call_tool` 在取到 `server` 后、调 `_call_via_session` 前：`agent_id = _effective_agent_id(agent_id)`。

- managed 单 agent 进程（`agent run bi-intern`）：`active_agent()` = bi-intern → 身份补全。
- standalone 单 agent：同样补全（token 隔离也随之正确；其 client_secret 走自身 env，本就 OK）。
- 多 agent dev/platform index：`active_agent()` 返回 None → 保持调用方原值（不回归）。
- `/chat` 等已透传 `agent_name` 的路径：`agent_id` 非空 → 原样返回（不改）。

**为何不改 `normalizer.route()` 传 `agent_name`**：那会改变 workspace scope key（AGENT scope 下 `default`→agent 名），并与上传路径 `_save_file_to_workspace(..., None)` 失配，属真实回归面。身份补全只服务 per-user 三元组，与 workspace 解耦，放在 MCP client 内最小且安全。

### P1 — 平台侧 name→id 映射（`mcp_oauth_service.py` + `server.py`）

`_resolve_client_secret` 不再自己 `int()` 判定，把**原始 agent 身份串**透传给注入 resolver（作用域映射 + 兜底逻辑下沉到组合根）：

```python
def _resolve_client_secret(agent_id: str, client_secret_env: str) -> str:
    if not client_secret_env or _client_secret_resolver is None:
        return ""
    return _client_secret_resolver(agent_id or None, client_secret_env) or ""
```

resolver 契约：`Callable[[int|None,str],str|None]` → `Callable[[str|None,str],str|None]`。

`server.py` 组合根注入映射 resolver（此处允许 import `agent_store`，face 边界不破）：

```python
def _resolve_agent_client_secret(agent_ref: str | None, env_name: str) -> str | None:
    agent_id: int | None = None
    if agent_ref:
        if agent_ref.isdigit():
            agent_id = int(agent_ref)
        else:
            agent = agent_store.get_by_name(agent_ref)
            agent_id = agent.id if agent is not None else None
    value = _secret_store.get_decrypted(agent_id, env_name)
    if value is None and agent_id is not None:
        value = _secret_store.get_decrypted(None, env_name)   # 全局兜底
    return value
_mcp_oauth_service.set_client_secret_resolver(_resolve_agent_client_secret)
```

两个调用点（`complete_callback` 换 token、`fetch_access_token` 刷新）自动受益。

## 边界与契约

- **plane 边界**：name→id 映射只在 `server.py`（组合根）；`connector_management` 仍不 import `agent_lifecycle`/`agent_store`。resolver 缝语义不变（可注入、未注入=无 secret）。
- **agent⊥platform**：P2 只 import agent 侧 `agent_config.active_agent()`，无 platform 反向依赖；护栏 `test_module_dependency_guardrails` 应保持绿。
- **owner-task 契约**：无活资源改动。

## 迁移影响

既有以 `agent_id=''` 存的 `mcp_user_tokens`（bi-intern 试授权残留、zy-bot 现有 token）在归一化后按新身份（agent 名）查不到 → 触发**一次性重新授权**。无 schema 迁移；旧行留存无害（可后续清理）。属可接受的一次性用户动作。

## 备选方案（未采纳）

- **A：`normalizer.route()` 向 `run()` 传 `agent_name`**——最"正统"但会动 workspace scope 归属 + 与上传路径失配，回归面大，弃。
- **B：平台侧在 `mcp_oauth_service` 内直接 import `agent_store` 做映射**——破 face→agent_store 边界，弃；改在组合根注入。
- **C：仅补全局密钥（现状兜底）**——无法支持 per-agent 独立 client（用户明确要 per-agent 密钥模型），非根治，弃。

## 测试策略（分层）

- **unit**（`tests/unit/`）：
  - `_effective_agent_id`：空→active agent 名；非空→原样；无活跃 agent→None（patch `agent_config.active_agent`）。
  - `_resolve_client_secret`：透传原始 agent_id 给注入 resolver（名字不被 int 门挡掉）；空 env→""；无 resolver→""。
- **integration**（`tests/integration/`）：
  - `server.py` 注入的映射 resolver：真实 `agent_store` + `agent_secrets`，以 agent **名字** 命中 per-agent client_secret；per-agent 缺失时命中全局兜底；未知名字→None。
