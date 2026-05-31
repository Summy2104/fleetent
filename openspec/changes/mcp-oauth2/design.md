## Context

MCP1（mcp-http-streamable，已合入）的 `_base_headers`（mcp_client.py 行 166-175）按 `auth_type` 决定 `Authorization` 头：`"api_key"` 时从 `os.environ[api_key_env]` 取静态 key 附 `Bearer`；`"none"` 不附。`McpServerConfig.auth_type`（行 34）注释已列 `"oauth2"` 为合法取值但无实现。docs/capabilities/mcp.md 规划项：「OAuth2 认证——Token 过期时自动刷新；认证失败时标记服务不可用并提示重新授权」。

CLAUDE.md 基础设施原则：所有外部服务组件必须可自托管，数据不出客户内网；云托管专有身份服务（如某些 SaaS IdP 云端）禁止。OAuth2 在本平台的定位是：平台作为 **OAuth2 客户端**，向**客户内网自托管的授权服务器 token 端点**（如自托管 Keycloak / 内部网关的 OAuth2 端点）取 token，用于认证对 MCP server 的请求。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM（aiosqlite 裸 SQL）；**禁止全局可变状态**（token 缓存按 server 隔离、可注入/重置；持久化路径可 monkeypatch）；外部 HTTP（token 端点、MCP server）用 respx mock、不发真实请求；token 存储隔离到 tmp_path 或内存；不吞异常；行长 100；mypy strict；TDD Hard Gate；新依赖须说明必要性与自托管方案。

## Goals / Non-Goals

**Goals:**
- `auth_type: "oauth2"` 服务向客户内网自托管 token 端点按 OAuth2（首选 client_credentials）取 access token，以 `Bearer` 附加到对该 MCP server 的请求。
- access token 过期前自动刷新（client_credentials 重新取，或有 refresh_token 时用之），对工具调用透明。
- token 存储按 server 隔离、可注入、可隔离测试（默认内存）。
- token 获取/刷新认证失败时标记服务认证不可用并提示重新授权，不反复无效重试。
- 全程无云托管身份依赖，token 端点可自托管。

**Non-Goals:**
- 不实现**浏览器交互式 authorization_code 授权流**（含人工同意页面、回调）——on-prem 无头服务首选 client_credentials；交互式授权（如需用户级授权）属后续 change（design 提及与未来 connector-oauth-store 的关系）。
- 不实现**会话管理**（MCP2）与**健康重连**（MCP3）——本 change 仅认证维度。
- 不改 `auth_type: "none"` / `"api_key"` 既有行为、stdio 传输、命名空间、降级。
- 不对接任何云托管专有身份服务。

## Decisions

### D1：首选 client_credentials，平台作纯 OAuth2 客户端
`auth_type: "oauth2"` 服务按 OAuth2 `client_credentials` 流程：向配置的 token 端点 POST（`grant_type=client_credentials` + client_id/client_secret + 可选 scope），解析响应 `access_token` / `expires_in` / 可选 `refresh_token`。token 端点是客户内网自托管授权服务器。
**为何**：on-prem 无头部署、服务到服务调用，client_credentials 无需人工交互最合适；平台只作 OAuth2 客户端，token 端点自托管满足数据主权（CLAUDE.md），不引入任何云身份服务。
**Alternatives**：①authorization_code（需浏览器同意 + 回调）——被否，无头服务无人交互；用户级授权场景留作后续 connector-oauth-store；②直接静态 token——已是 `api_key` 模式，OAuth2 的价值正在于短时 token + 自动刷新。

### D2：无新依赖，手写 client_credentials（复用 httpx）
client_credentials 流程足够简单（POST 表单 → 解析 JSON），用 MCP1 已引入的 `httpx` 手写实现，不引入 OAuth2 库。
**为何**：CLAUDE.md 新依赖须讨论；手写 client_credentials 仅几十行，避免为简单流程背负 `authlib` 等库的体积与攻击面。若未来需 authorization_code/PKCE 等复杂流，再在专门 change 评估引入纯客户端、可自托管对接的 OAuth2 库。
**Alternatives**：①引入 `authlib`——被否（本 change 不需要其复杂能力）；保留为未来交互式授权的备选，届时须确认其无云依赖、可对接自托管端点。

### D3：token 存储按 server 隔离、可注入，默认内存
access token + 过期时刻（由 `expires_in` 计算的绝对时间）+ 可选 refresh token 缓存按 server 实例隔离持有（沿用 MCP1/MCP2/MCP3「状态落 server 而非全局」原则），存储后端可注入：默认内存（按 server 隔离的字段/映射经实例持有），如需跨重启持久化则用 aiosqlite 裸 SQL、`DB_PATH` 可 monkeypatch（遵循 user_store 模式）。
**为何**：CLAUDE.md 禁止全局可变状态、要求测试隔离；默认内存即满足单进程运行期缓存与刷新；持久化为可选（OAuth2 client_credentials 重启重取代价低，未必需持久化）。可注入存储让测试用内存桩、不碰 `data/`。
**Alternatives**：①模块级 `dict[server_id, token]`——被否，全局可变状态违反 CLAUDE.md；②总是持久化到 SQLite——被否，client_credentials 重取廉价，强制持久化是过度设计；持久化设为可选。

### D4：过期前自动刷新，刷新对调用透明，不使用过期 token
取 token 时记录绝对过期时刻（`now + expires_in - 安全余量`）。resolve token 时若已过期/临近过期，先刷新再用新 token；刷新成功对工具调用透明（调用方无感知）。刷新失败时**不**用过期 token 发请求，转 D5 认证失败处理。过期判定所用的「当前时间」源 MUST 可注入（如可注入的时钟函数/参数），不直接硬编码 `time.time()`，以便确定性地测试「临近过期」「已过期」等边界。

**刷新主路径 = 重跑 client_credentials**：RFC 6749 §4.4（client_credentials）明确「响应**不应**包含 refresh_token」——服务到服务无人值守场景下，凭据本就在手，过期即用 client_id/client_secret 重新 POST 取新 token 即可，无需 refresh_token。因此本 change 的刷新**主路径就是重跑 client_credentials**。`refresh_token` 仅作**防御性附注**：万一目标授权服务器非标准地在 client_credentials 响应里返回了 refresh_token，可优先用 refresh_token grant；但实现 **MUST NOT** 假设 refresh_token 存在，缺失（正常情况）时直接重跑 client_credentials，不得因无 refresh_token 而判失败。
**为何**：docs 要求「Token 过期时自动刷新」；带安全余量避免「检查时未过期、到达服务端已过期」的竞态；不静默用过期 token 避免本可预期的 401。明确「client_credentials 重取为主、refresh_token 为防御性可选」纠正原文「否则重跑 client_credentials」把两者并列的措辞——按 RFC client_credentials 几乎不会有 refresh_token，主路径应是重取。
**Alternatives**：①等服务端 401 再刷新——被否，可预期的过期应主动刷新，避免一次失败往返；可作为兜底（401 触发刷新重试一次）但主路径按过期时刻预刷新。

### D5：认证失败标记服务认证不可用并提示重新授权，不反复无效重试
token 获取/刷新返回**真认证错误**（token 端点 401 / `invalid_client` / `invalid_grant` 等）时，置位该服务的 sticky「认证不可用」标志，提示「需重新授权 / 检查 OAuth2 凭据」，并停止对该 token 端点的反复无效重试（避免打爆端点 / 触发锁定）。

**瞬时错误不置 sticky**：token 端点的 **5xx / 网络错误 / 连接超时 / 读超时** 属瞬时错误（授权服务器临时故障或网络抖动，凭据本身未必有问题），实现 **MUST NOT** 据此置位 sticky「认证不可用」标志，而 MUST 按可重试处理（下次调用可正常再取 token）。仅 401 / `invalid_client` / `invalid_grant` 这类指向凭据/授权配置错误的响应才置 sticky。

**恢复触发**：sticky「认证不可用」标志的清除触发点为**配置重载 / 重新注册**（清除该 sticky 标志后下次调用重新取 token），可选附带显式 re-auth 命令；本 change **不**做定时退避重试来自动清除 sticky。
**为何**：docs 要求「认证失败时标记服务不可用并提示重新授权」；`invalid_client` 是配置/凭据问题，重试无益且可能触发授权服务器限流/锁定——与 AR5 `auth_failed`（全 False，不重试）的精神一致。区分瞬时错误（5xx/网络/超时）与真认证错误：把瞬时故障也置 sticky 会让一次授权服务器抖动导致服务长期「假性」认证不可用、需人工介入恢复，与「认证不可用 = 凭据需修复」的语义不符。恢复经配置重载/重新注册而非定时退避，避免在凭据未改时盲目重试打爆端点。
**Alternatives**：①认证失败也无限重试——被否，凭据错时无效且有害；②首次失败即永久放弃且不可恢复——被否，凭据可更新，应在配置/凭据更新后能恢复；③瞬时 5xx/超时也置 sticky——被否，会把临时故障误判为凭据错误、导致假性长期不可用；④定时退避自动重试清除 sticky——被否，凭据未改时定时重试仍无效且打爆端点，恢复应由配置重载/重新注册这一明确信号触发。

### D6：只替换 Authorization 头**来源**，复用 MCP1 全部传输（但 token resolve 是 async，见 D6a）
OAuth2 仅改变请求头里 `Authorization` 的取值来源（静态 env key → 动态 access token）；`initialize` / `tools/list` / `tools/call`、SSE/JSON 双解析、`Mcp-Session-Id`、递增 id、`{server_id}__{tool_name}` 命名空间、`register_all` 降级一律不变。
**为何**：认证是横切关注点，正交于传输；最小改动、最低回归风险，复用 MCP1 已验证的传输。
**Alternatives**：①为 oauth2 单列一套请求路径——被否，重复传输逻辑、维护两条路径。

#### D6a：token 的取/刷新是 **async**，与同步 `_base_headers(server) -> dict` 签名冲突——必须显式处理
**事实核实**（mcp_client.py 行 165-174）：`_base_headers(server: McpServerConfig) -> dict[str, str]` 是**同步**函数，`api_key` 分支只是 `os.environ.get(...)`（无 IO、无 await）。而 OAuth2 取/刷新 token 需要 `await`（向 token 端点发 HTTP、可能触发刷新）。因此「仅替换 Authorization 头来源」并非零涟漪——同步函数里**不能** `await`。本 change **必须**二选一显式处理（实现首步定夺，记录于此避免误以为是纯局部替换）：
- **(a) 构造头前先 resolve token（首选）**：在每个请求构造处（`_post_jsonrpc` / `initialize` / notification 等所有调 `_base_headers` 的 async 上下文），先 `await _resolve_oauth_token(server)`（取/必要时刷新，返回有效 access token 或在认证不可用时短路），把 token 传入 `_base_headers(server, bearer=...)`，让 `_base_headers` 保持同步、仅负责拼装。
- **(b) 把 `_base_headers` 改 async**：`async def _base_headers(...)`，内部 `await` token resolve，并随之更新所有调用点为 `await _base_headers(...)`（涟漪：当前所有同步调用点都要改 async 上下文）。
首选 (a)：让 `_base_headers` 保持同步、纯拼装，把「IO/await」收口到请求构造层，涟漪最小、最易测；MCP1 现有 `api_key`/`none`/`session_id` 分支不受影响（oauth2 时 bearer 由外部 resolve 后传入）。
**为何**：评审指出 D6「仅替换 Authorization 头来源」掩盖了真实的签名/async 改动——同步 `_base_headers` 中无法 await token。明确 async token fetch 发生在「构造头之前」并保持 `_base_headers` 同步，消除「以为是纯局部替换、实现到一半发现要改签名」的隐患。
**Alternatives**：①在 `_base_headers` 里同步阻塞拿 token（`asyncio.run` / 阻塞调用）——被否，在 async 事件循环里同步阻塞 IO 是反模式、会卡事件循环；②预先在别处刷好 token 只读字段、`_base_headers` 同步读——本质即 (a) 的变体，统一归入 (a)「构造头前 resolve」。

### D7：与未来 connector-oauth-store 的关系（本 change 自包含）
本 change 处理**服务到服务的 client_credentials**（无用户维度），token 缓存按 server 隔离、自包含。未来若需**用户级 OAuth 授权**（per-user token、authorization_code、跨 connector 复用的 token 存储），可演进出独立的 connector-oauth-store 模块统一管理；届时本 change 的 server 级 token 存储可作为其一种存储后端或被其取代。本 change 不预先构建该抽象，避免过度设计。
**为何**：明确边界——本 change 只解决 MCP server 的服务级 OAuth2，不背负用户级授权的复杂度；为未来留出演进路径但不提前抽象。

### D8：「认证不可用」与 MCP3 连接级健康状态正交，MCP3 非依赖
MCP3（mcp-health-reconnect）引入了**连接级**健康状态机（`healthy` / `degraded` / `unavailable`），表达「连接断了 / 正在重连 / 永久不可用」，由探活与断连映射驱动。本 change 引入的是**认证级**「认证不可用」标志，表达「凭据/授权有问题（`invalid_client` 等），重试无益」，由 token 获取/刷新的认证错误驱动。二者**正交、独立两态**：
- 一个服务可以「连接健康（MCP3 `healthy`）但认证不可用（凭据错）」——此时连接探活成功，但工具调用因认证不可用直接返回认证错误结果；也可以「连接降级但认证有效」。
- **不复用** MCP3 的 `unavailable`：连接级 `unavailable`（重连失败达阈值）与认证级「认证不可用」成因、恢复方式都不同（前者靠重连/手动重连恢复，后者靠凭据/配置更新恢复），混为一态会让「该重连还是该改凭据」语义糊掉。本 change 用**独立的 auth 标志**承载。
- **MCP3 非本 change 依赖**：本 change 的认证不可用降级（对该服务工具调用直接返回认证错误结果、不发请求）自包含实现，**不**要求 MCP3 已合入或其健康状态机存在即可生效。若 MCP3 也在场，则两套状态各自独立判定、各自返回各自的不可用信号（连接不可用 vs 认证不可用），实现上对同一服务工具调用按「先判认证不可用、再判连接健康」或等价的两态独立短路均可，互不耦合。
**为何**：评审指出 spec 新增「认证不可用」态却未说明对该服务工具调用的可观察行为（MCP3 有对应「返回服务暂时不可用」scenario），也未澄清与 MCP3 健康态的关系。明确为正交 auth 标志 + MCP3 非依赖，避免两态混淆与不必要的跨 change 耦合；同时本 change 单独可用（MCP3 可后到）。
**Alternatives**：①复用 MCP3 的 `unavailable` 态承载认证不可用——被否，成因/恢复路径不同，混淆「重连 vs 改凭据」；②让本 change 依赖 MCP3 才能降级——被否，认证降级是认证维度自包含行为，不应被连接维护能力绑定，强行依赖会让 MCP5 无法独立合入。

### D9：per-server 刷新锁串行化，防 token 过期时的 thundering herd
同一 server 的 token resolve/刷新用一把 per-server `asyncio.Lock` 串行化：进入 resolve 临界区后先在锁内复检当前 token 是否仍有效（double-check），仅在确实需要时才发 client_credentials 请求取/刷新 token，其余等锁的并发请求拿锁后直接复用已刷新的有效 token。锁**按 server 实例隔离持有**（随 token 缓存落在 server 维度，遵循 D3「状态落 server 而非全局」），**不**进模块级全局。
**为何**：token 临近/已过期的瞬间往往有多个工具调用并发触发 resolve（D4），若不串行化，它们会同时判定「需刷新」并各自向 token 端点打出一个 client_credentials 请求（thundering herd），既浪费、又可能触发授权服务器限流/锁定（与 D5「不打爆端点」一致）。per-server 锁 + 锁内 double-check 把「同一 server 的并发过期刷新」收敛为一次取 token；按 server 隔离避免不同 server 互相阻塞，也避免引入模块级全局可变状态（CLAUDE.md）。
**Alternatives**：①不加锁、每个并发请求各自刷新——被否，thundering herd 浪费且可能触发限流；②模块级单锁串行化所有 server——被否，不同 server 互不相关却互相阻塞，且属模块级全局状态，违反 D3/CLAUDE.md；③进程级全局锁映射 `dict[server_id, Lock]`——本质仍是模块级可变全局，归入②否决，锁应随 server 实例持有。

## Risks / Trade-offs

- [误接入云托管身份服务违反数据主权] → spec/Impact 明确 token 端点为客户内网自托管授权服务器；`config/mcp.yaml.example` 注释强调内网地址；禁止云专有身份服务。
- [token 缓存成全局可变状态或测试污染] → D3：缓存按 server 实例隔离、存储后端可注入、默认内存；持久化时 `DB_PATH` 可 monkeypatch、隔离到 tmp_path。
- [手写 client_credentials 漏处理边界（无 expires_in、时钟偏移）] → 无 `expires_in` 时按保守短 TTL 处理或每次校验；过期判断带安全余量；用例覆盖无 expires_in、临近过期、已过期。
- [认证失败反复重试打爆 token 端点] → D5：认证失败标记不可用、停止无效重试，凭据更新后恢复。
- [client_secret 明文泄漏] → 经环境变量引用（`client_secret_env`），不明文写入 `config/mcp.yaml`、不入库（与既有 `api_key_env` 模式一致）。
- [未来需引入 OAuth2 库] → 本 change 默认无新依赖；若引入须在 PR 说明必要性、确认纯客户端、可对接自托管端点、无云依赖。

## Open Questions

- token 端点错误响应的精确判据：`invalid_client` / `invalid_grant` 的 HTTP 状态与错误体形态——实现首步对照目标自托管授权服务器（如 Keycloak）核实 D5 判据。
- `expires_in` 缺失时的默认 TTL 与安全余量取值——实现时定保守默认（可注入），用例覆盖。
- 是否需要在 MCP server 返回 401 时触发一次 token 刷新重试（D4 兜底）——按目标 server 行为确认；本次主路径按过期时刻预刷新，401 兜底为可选增强。
- 用户级 OAuth 授权（authorization_code / per-user token）何时单列 connector-oauth-store——超出本 change 范围，待用户级授权需求出现再议。
