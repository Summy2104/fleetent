## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 MCP1 `_base_headers`（mcp_client.py 行 165-174）的 `auth_type` 分支：`"api_key"` 如何从 `api_key_env` 取静态 key 附 `Bearer`、`"none"` 不附；确认该函数为**同步** `def _base_headers(server) -> dict`（`api_key` 分支仅 `os.environ.get`，无 await）。据此定 `"oauth2"` 的插入方案（D6a）：取/刷新 token 是 async，必须在请求构造前 `await` resolve token 再传入头拼装（首选保持 `_base_headers` 同步），不能在同步函数内 await；核实所有调 `_base_headers` 的请求构造点（`_post_jsonrpc` 行 189、initialize、notification）
- [ ] 1.2 核实 `McpServerConfig`（行 28-44）字段风格，确定 OAuth2 配置字段（token_url / client_id / client_secret_env / scope）的命名与默认值，与 `auth_type` / `api_key_env` 一致
- [ ] 1.3 核实自托管授权服务器（如 Keycloak）的 client_credentials token 端点请求/响应格式、错误响应（`invalid_client` / `invalid_grant` 的 HTTP 状态与错误体），据此定取 token 与认证失败判据；确认 token 端点为客户内网地址、无云依赖
- [ ] 1.4 核实 token 存储隔离方式：默认内存按 server 隔离；如持久化则参照 user_store 的 aiosqlite + 可 monkeypatch `DB_PATH` 模式，隔离到 tmp_path
- [ ] 1.5 确认默认无新依赖（手写 client_credentials 复用 httpx）；如评估需 OAuth2 库则记录必要性与自托管/纯客户端确认（design D2）

## 2. OAuth2 配置字段（mcp_client.py）

- [ ] 2.1 Write failing tests：`McpServerConfig` 支持 OAuth2 字段（token_url / client_id / client_secret_env / scope），`auth_type: "oauth2"` 合法。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement OAuth2 配置字段，看到绿

## 3. token 存储（按 server 隔离、可注入）

- [ ] 3.1 Write failing tests：token 存储按 server 隔离持有（access token + 绝对过期时刻 + 可选 refresh token）；不同 server 互不影响；存储后端可注入（默认内存）；可重置以便测试；不进模块级可变全局。如持久化则隔离到 tmp_path。看到红
- [ ] 3.2 Implement token 存储（默认内存、按 server 隔离、可注入；持久化时 aiosqlite 裸 SQL + 可 monkeypatch 路径），看到绿

## 4. client_credentials 取 token 并以 Bearer 附加

- [ ] 4.1 Write failing tests：`auth_type: "oauth2"` 服务向 token 端点按 client_credentials 取 token，解析 `access_token` / `expires_in`；`_base_headers` 为该服务附 `Authorization: Bearer <access_token>`；`none` / `api_key` 分支行为不变。respx mock token 端点，**不发真实请求**。看到红
- [ ] 4.2 Implement client_credentials 取 token；oauth2 请求路径在构造头前 `await` resolve token 再传入 `_base_headers` 拼装（D6a 方案 a，保持 `_base_headers` 同步、仅替换 Authorization 来源），看到绿

## 5. token 自动刷新（对调用透明）

- [ ] 5.1 Write failing tests：token 临近/已过期（依记录的绝对过期时刻）时，下次取 token 自动刷新——主路径重跑 client_credentials（覆盖「响应无 refresh_token」为正常情况、不判失败）；防御性覆盖「若返回 refresh_token 则优先用之」；刷新对工具调用透明，调用方拿到正常结果；刷新失败不使用过期 token。respx mock 刷新响应。看到红
- [ ] 5.2 Implement 过期前自动刷新（带安全余量，不静默用过期 token），看到绿
- [ ] 5.3 Write failing tests 边界（注入可控时钟）：无 `expires_in` 时按保守 TTL 处理；通过注入可控时钟确定性地构造「时钟余量内的临近过期」「已过期」，验证触发刷新（过期判定的当前时间源可注入，不硬编码 `time.time()`，D4）。看到红
- [ ] 5.4 Implement 过期判定边界处理（当前时间源可注入），看到绿
- [ ] 5.5 Write failing tests：同一 server 在 token 过期时并发 resolve（多个工具调用同时触发）只触发一次取 token——per-server `asyncio.Lock` 串行化 + 锁内 double-check，等锁的并发请求复用已刷新 token；锁按 server 实例隔离、不进模块级全局；不同 server 互不阻塞（D9）。respx mock 计取 token 端点命中次数 == 1。看到红
- [ ] 5.6 Implement per-server 刷新锁（锁随 server 实例持有，锁内复检后仅必要时取 token），看到绿

## 6. 认证失败标记服务认证不可用并提示重新授权

- [ ] 6.1 Write failing tests：token 获取/刷新返回认证错误（token 端点 401 / `invalid_client`）时，标记该服务认证不可用、给出「需重新授权 / 检查 OAuth2 凭据」提示，且不反复无效重试打爆 token 端点；凭据/配置更新后可恢复。respx mock token 端点认证错误。看到红
- [ ] 6.2 Implement 认证失败标记与重新授权提示、停止无效重试，看到绿
- [ ] 6.3 Write failing tests 瞬时错误不置 sticky（D5）：token 端点返回 5xx / 网络错误 / 超时时，**不**标记服务认证不可用、按可重试处理（下次调用可正常再取 token 并成功）；仅 401 / `invalid_client` / `invalid_grant` 才置 sticky。respx mock 先返回 5xx/超时、再返回成功。看到红
- [ ] 6.4 Implement 瞬时错误（5xx/网络/超时）与真认证错误区分：仅真认证错误置 sticky，瞬时错误按可重试处理，看到绿
- [ ] 6.5 Write failing tests 恢复触发（D5）：配置重载 / 重新注册清除 sticky「认证不可用」标志后，下次调用重新取 token；不依赖定时退避自动清除。看到红
- [ ] 6.6 Implement 配置重载 / 重新注册时清除 sticky 标志（恢复触发），看到绿
- [ ] 6.7 Write failing tests 认证不可用期间的工具调用（D8）：对已标记「认证不可用」的 oauth2 服务发起工具调用 → 直接返回「认证不可用」结果，不取 token、不发请求、不抛异常；其他服务不受影响。该降级自包含、不依赖 MCP3 健康态。看到红
- [ ] 6.8 Implement 认证不可用期间工具调用直接返回认证错误结果（独立 auth 标志，正交于 MCP3 连接健康态，不依赖 MCP3），看到绿

## 7. 配置示例

- [ ] 7.1 Write failing test / 校验：以 `config/mcp.yaml.example` 的 oauth2 示例（token_url / client_id / client_secret_env / scope，内网 token 端点）构造 `McpServerConfig` 可被正确加载。看到红
- [ ] 7.2 Implement：补 `config/mcp.yaml.example` 的 oauth2 示例（注释强调 token 端点为客户内网自托管授权服务器、secret 经环境变量、无云依赖），看到绿

## 8. 收尾

- [ ] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 8.3 `uv run mypy src` 无新增错误
