# fleetent 核心模块深度审计报告

**审计日期**：2026-06-06
**审计范围**：8 个核心模块的代码流程、现有能力、缺口与优先级路线图

---

## 一、执行摘要

- **基础架构扎实，安全设计超越同类**：im_gateway 的双层访问控制、skills 的静态注入审计、tools 的带外参数注入、MCP 的三状态健康模型，均优于 LangChain / AutoGen / LangGraph 的同等设计。
- **核心运行治理完备**：AgentLoop 拥有可组合的 TerminationController、两维预算（turns + tokens）+ grace call、AR3 三相并行工具调度、AR4 + AR10 双信号循环检测，属于工业级实现。
- **关键阻塞性缺口集中在三处**：① AgentLoop 缺少结构化输出、崩溃检查点恢复和流式路径的审批门；② Context 压缩使用同步 LLM 调用阻塞事件循环，且 CJK token 估算严重偏低；③ MCP 未处理 `isError` 字段，导致工具错误被当成正常结果传入对话。
- **存在多处"功能存在但未连通"的问题**：platform 层的 channel allowlist 从未被 `normalizer.route()` 调用；`engine_audit` 占位符导致 Admin API 上传的 Skill 绕过注入审计；`engine_set_global_disabled` 为空操作。
- **SQL 规范与 Alembic 违规**：`session/index.py` 和 `runtime/context.py` 的 `init_anti_flap_db()` 均使用 `CREATE TABLE IF NOT EXISTS` + `?` 位置参数，违反项目 Forbidden Patterns，需在下一个 schema 迁移窗口中整改。

---

## 二、逐模块分析

### 2.1 IM 接入层（im_gateway）

#### 消息流程

| 步骤 | 说明 | 关键代码 |
|------|------|----------|
| 1 | 平台适配器接收事件（Slack: `@app.event('message')`；Telegram: `MessageHandler(filters.TEXT\|PHOTO)`） | `slack.py:67` / `telegram.py:57` |
| 2 | Slack 频道过滤（channels 白名单），Telegram 无此过滤 | `slack.py:73-74` |
| 3 | 身份解析（当前为 pass-through，直接使用平台原生 user_id） | `access.py:71-78` |
| 4 | Session ID 派生（DM→`user:<id>`；thread→`thread:<ts>`） | `slack.py:40-46` / `telegram.py:38-43` |
| 5 | 图片附件下载（Slack: httpx Bearer；Telegram: `PhotoSize` 最大版本） | `slack.py:12-37` |
| 6 | 构造 `NormalizedMessage` | `normalizer.py:21-38` |
| 7 | 审批命令拦截（`approve/reject <uuid>`） | `normalizer.py:103-121` |
| 8 | Agent 解析（channel→user→default，或 agent_name 快捷路径） | `normalizer.py:127-130` |
| 9 | 频道 & 用户访问门（`access.channel_allowed()` + `access.user_allowed()`） | `access.py:81-90` |
| 10 | Session 锁获取 + 命名空间（`owner_id:session_id`） | `normalizer.py:154-156` |
| 11 | 加载历史 + 构造系统提示 | `normalizer.py:157-186` |
| 12 | 用户内容构建（含图片 VLM 分析） | `normalizer.py:75-99` |
| 13 | `agent_loop.run()` 执行 | `normalizer.py:189-200` |
| 14 | 保存 Session + 发送最终回复 | `normalizer.py:202-206` |
| 15 | 连接器生命周期管理（SlackSupervisor / ConnectorManager） | `slack_supervisor.py:27-111` |

#### 现有能力

- NormalizedMessage 平台无关封装；Slack Socket Mode 每 agent 独立 Task 隔离
- 文件驱动 agent 路由（启动时冲突检测）；默认拒绝姿态（no agent = closed）
- 双层访问控制（静态 YAML + 动态 LocalApprovalStore）；审批命令拦截
- 图片下载 + VLM 分析降级；多租户 owner 命名空间；per-session asyncio.Lock
- inline secret 拒绝（`_reject_inline_secrets`）；config-change-driven Slack 重启

#### 缺失能力（分级）

**P0**
- **Slack 连接崩溃无自动重连**：`SlackSupervisor._run()` 崩溃后状态变为 `error` 并停留，需外部调用 `reload()`。生产环境瞬态网络抖动会导致 Bot 永久下线。
- **Bot 自消息循环防护缺失**：`@app.event('message')` 未过滤 `subtype='bot_message'`，Bot 回复会再次触发 `handle_message`，产生潜在无限循环。
- **无主动外发消息 API**：im_gateway 完全被动，scheduler / agent 无法向用户/频道主动推送消息，不能实现任何 proactive agent 行为。

**P1**
- **消息去重（event_id 幂等存储）**：Slack 重连 / Telegram offset 问题可导致重复投递，引发工具重复执行。
- **typing indicator / 处理确认**：5-30 秒无反馈，用户可能重发消息。
- **回复消息长度分割**：Slack 4000 字符、Telegram 4096 字符限制无处理，超限静默失败。
- **platform-level channel allowlist 未接入**：`channel_allowlist.is_allowed()` 完全实现但 `normalizer.route()` 从未调用，造成静默策略绕过。
- **LocalApprovalStore 并发 read-modify-write 无锁**：`add_pending()` 无 asyncio.Lock，Telegram `concurrent_updates=True` 下存在竞态。
- **Telegram 缺少 per-agent connector**：仅有 owner 级 ConnectorManager，无法实现多 agent 独立 Bot 身份。

**P2**
- 入站消息队列 + backpressure（无并发上限）
- IM 调用层无超时包装（`asyncio.wait_for`）
- 非图片附件（文档、音频、视频）透传支持

#### 局部实现但不完整

- **多租户命名空间**：session_id 前缀正确，但 SlackSupervisor 仅支持单一 `admin_owner_id`
- **平台 channel allowlist**：数据模型 + 执行逻辑完整，但未接入路由路径
- **身份解析**：`resolve_identity()` 是 pass-through，从不调用 `im_users` DB，platform 层封禁用户无效
- **Session ID 作用域**：DM/thread 正确，但非线程频道消息用 `user:<id>` 导致跨频道 session 共用

---

### 2.2 Skill 注册与审计

#### 消息流程

1. 服务器启动时 `scan()` → `_build_index()` → `_scan_dir()` 双源（builtin + user）
2. 每个 `SKILL.md`：解析 YAML frontmatter → 名称冲突检测（lexicographic 胜出）→ `_audit_skill()` 静态注入审计
3. `available_skills_prompt()` 构建 `<available_skills>` XML 注入系统提示（只含 name/description/location）
4. 模型调用 `read_skill` 工具 → `registry.load(name)` 从磁盘读取完整 SKILL.md
5. `reload()` 原子替换 `_index` 模块全局变量（build 失败时保留旧 index）

#### 现有能力

- 8 规则静态注入审计（SEVERE 阻断 / SUSPICIOUS 放行）；四级禁用谓词 `_disabled_reason`
- read-on-demand 目录（系统提示只注入摘要，懒加载正文）；per-agent `allowed_skills` 窄化
- 原子热重载（`reload()` 构建失败保留旧 index）；加载错误隔离（`_load_errors` 可查询）
- zip-slip 防护；引用保护软归档（409 当 agent 仍引用）；Admin API 完整 CRUD + 批量上传

#### 缺失能力（分级）

**P0**
- **`engine_set_global_disabled` 为空操作**：Admin 控制台 disable skill 后 `_index` 不更新，skill 继续匹配，直到下次 `reload()` 才生效。
- **`engine_audit` 占位符绕过审计**：Admin API 上传（POST/PUT/import）的 skill 返回 `{verdict: pass, rules: []}`，跳过 8 规则引擎，攻击者可通过 Admin API 上传注入攻击 skill。

**P1**
- Skill 输入/输出 schema 声明（当前为自由格式 Markdown，模型无类型契约）
- 基于 embedding 的语义 skill 匹配（替换 `match()` 关键词匹配）
- Skill 使用遥测（`engine_observability` 返回 stub，无命中次数、会话列表）
- Skill 版本管理（version 字段仅展示，无多版本并存 / 回滚机制）

**P2**
- Frontmatter schema 验证（未知字段静默忽略，typo 导致配置失效）
- `available_skills_prompt()` 无分页/上限（50+ skill 破坏前缀缓存优势）
- Skill 参数注入上下文（无模板变量替换机制）
- Skill 组合/链式执行（无 DAG / pipeline 原语）

#### 局部实现但不完整

- **静态注入审计**：disk scan 路径正确，Admin 写路径 `engine_audit` 为 placeholder
- **`engine_reload()` 调用 `scan()`**：使用原地变更路径而非 `reload()` 原子路径，丧失原子性保证
- **Skill 溯源 & drift**：drift flag 记录但未传播到模型上下文；`askit_override` 为硬编码 fake
- **反思提案收件箱**：提案 approve 后不触发 `scan()/reload()`，运行引擎不更新

---

### 2.3 工具层（Tools）

#### 消息流程

1. `import fleetent.tools` 触发 `builtin_tools.py` 注册（副作用）
2. `@tool` 装饰器调用 `_register()`，填充 `_registry` / `_risk_levels` / `_timeouts` / `_self_truncating`
3. `get_schemas()` 应用可见性过滤 → `allowed_tools` fnmatch 白名单 → 代码执行门控
4. LLM 返回 `tool_calls` → `_plan_run_slots()`（guardrail + 审批门 + resource_key 分组）
5. `_execute_pending()`：按 `resource_key` 分组，`asyncio.gather` 并行执行，`_safe_dispatch()` 包装超时
6. `_backfill_slots()`：结果截断（T4）→ 追加 `role=tool` 消息 → 循环检测记录

#### 现有能力

- `@tool` 双形式注册；`_build_schema()` Python 类型 → JSON Schema（int/float/bool/str）
- 带外参数注入（cancel_token / tool_context / client 不进入 LLM schema）
- Risk level 标签 + 人工审批门；per-tool 超时覆盖（DEFAULT 30s）
- 结果截断 T4（40KB，UTF-8 字节安全）；self_truncates 豁免
- 插件加载器（`{plugin_name}__{tool_name}` 命名空间）；connector OAuth 凭证注入
- 沙箱代码执行（Docker 隔离，SB2-SB9 全覆盖）；取消令牌树

#### 缺失能力（分级）

**P0**
- **`_build_schema()` 类型映射不完整**：list/dict/Optional/Union/Literal/Enum 全部降级为 `string`，模型对复杂参数格式盲飞。
- **无 per-parameter docstring 描述**：仅提取 docstring 第一行作为 tool description，参数级描述缺失。

**P1**
- 工具调用结果结构化输出（当前强制 string）
- per-tool 重试策略（`ErrorClassification.should_retry` 已定义但 `_safe_dispatch()` 从不读取）
- 工具输出格式控制（无 markdown/JSON/binary 声明）
- 工具执行遥测（per-tool 延迟 / 参数 hash / 结果大小未从 `dispatch()` 发出）

**P2**
- 工具间依赖图声明（同一 LLM 轮次内 DAG 调度）
- 工具 schema 版本 + deprecated 标记（重命名工具会破坏 in-flight session）
- per-tool 或 per-server 并发限制

#### 局部实现但不完整

- **`_build_schema()`**：标量类型正确，复杂类型无支持
- **插件加载器 `_namespace_new_keys()`**：只迁移 `_registry` 和 `_risk_levels`，`_timeouts` / `_self_truncating` / `_connectors` 不迁移，导致 `@tool(timeout=60)` 的插件工具静默回退到默认超时
- **Connector 凭证注入**：token 过期后无 silent refresh，持续返回 `NeedsConsent`
- **`allowed_tools` 白名单**：`_safe_dispatch()` 调用 `dispatch()` 时未传递 `mcp_server_ids`，MCP scope 隔离存在防御缺口

---

### 2.4 MCP 客户端

#### 消息流程

1. `register_all()` 迭代配置，`_register_server()` 按 transport 分支（HTTP / stdio）
2. HTTP：`_open_session()` 发起 initialize 握手 → 捕获 `Mcp-Session-Id` → `tools/list` 枚举工具
3. 工具注册进 `tool_registry._registry`（`{server_id}__{tool_name}`）
4. `call_tool()` → `_call_http_tool()` / `_call_stdio_tool()`：健康检查 → Bearer 解析 → JSON-RPC POST
5. Session 过期（404）→ 重新 initialize → 单次重试
6. 断线 → `_handle_disconnect()` → `_reconnect_with_backoff()`（指数退避，最多 5 次）
7. 后台健康监控（每 30s 探测，单 asyncio.Task）
8. `install_schema_filter()` 将健康状态动态注入 `tool_registry.get_schemas()`

#### 现有能力

- 双 transport（Streamable HTTP + stdio）；三态健康（healthy/degraded/unavailable）
- Session 过期自动恢复；OAuth2 client_credentials 双检锁；sticky auth-unavailable 标志
- 指数退避重连（1s→60s，去重锁）；三种降级模式（strict/degrade/silent）
- Schema 可见性过滤（动态谓词，无需重注册）；`probe_server()` 不污染共享注册表
- 优雅关闭（HTTP session DELETE + AsyncExitStack stdio 清理）

#### 缺失能力（分级）

**P0**
- **`isError` 字段未处理**：`_call_http_tool` / `_call_stdio_tool` 均取 `content[0].text` 而不检查 `isError`，工具错误被当成正常结果传入对话。

**P1**
- Server-to-client push notifications（`notifications/tools/list_changed`）
- MCP resource 原语（`resources/list` / `resources/read` / `resources/subscribe`）
- per-server 可配置调用超时（当前硬编码 30s）
- 多内容工具结果处理（`ImageContent` / `EmbeddedResource` 静默丢失）
- tools/list 游标分页（多工具 server 静默丢失后续页）
- 客户端 capabilities 声明（当前 `{}`，无法接收服务器通知）
- MCP 调用遥测接入 eval_logger（当前仅 stdlib logging）
- OAuth2 authorization_code + PKCE（用户委托访问）

**P2**
- MCP prompt 原语（`prompts/list` / `prompts/get`）
- Elicitation（server 发起用户输入请求）
- HTTP 连接池（当前每次调用新建 AsyncClient）

#### 局部实现但不完整

- **OAuth2 refresh_token**：存储但从不使用，token 过期后重新走 client_credentials
- **Agent-scope 注册**：`(scope, server_id)` 键结构完整，但 `mcp_runtime.py` 明确标注 "out of scope"，实际不可达
- **MCP server store 字段缺失**：`degrade_mode` / `token_url` / `client_id` / `client_secret_env` 不在 `_COLS`，Admin API 无法配置 OAuth2 或 strict 模式

---

### 2.5 Session 管理

#### 消息流程

1. 调用方通过 `session_lock(session_id)` 获取 per-session asyncio.Lock
2. `load(session_id)` → `_read()` 读 JSON 文件（支持 bare list 旧格式）
3. 调用方执行 agent loop（session 模块不参与）
4. `save()` → 保留 meta → `mkdir(parents=True)` → `.json.tmp → rename` 原子写 → `session_index.record_activity()` → `maybe_run_maintenance()`
5. 维护：`cleanup_expired()`（TTL）+ `enforce_capacity()`（LRU 双维度）+ `_release_sandboxes()`

#### 现有能力

- 原子写（tmp→rename）；envelope 格式（meta + messages）；旧格式向后兼容
- 双触发维护（save 时间门控 + 后台 asyncio.Task）；两维容量限制（bytes + count）
- per-session asyncio.Lock；nested session ID（`/` → 子目录）；sandbox 容器回收
- 管理操作：`clear()` / `reset()` / `inject_message()`（均持锁）

#### 缺失能力（分级）

**P1**
- **缺少核心 `delete(session_id)` API**：`clear()` 清空内容，无原子删除文件 + index 行的接口，调用方只能在模块边界外自行实现。
- **跨进程分布式锁**：asyncio.Lock 仅进程内有效，多副本部署下同一 session_id 无互斥。
- **写前日志 / 事件日志**：进程崩溃于 LLM 调用后、`save()` 前，本次 turn 内容全部丢失，无恢复路径；企业合规场景缺少 per-turn 不可变审计轨迹。
- **Session 状态机（active→idle→ended→archived）**：`session_admin_store` 有 status 字段，但无状态转换守卫，可向 `ended` session 写入。

**P2**
- Session 分支 / fork（`reset()` 为破坏性截断，无 `fork(from_turn)` 接口）
- per-session 文件大小上限（单个 session 可无限增长）
- 分页可过滤的 session 列表 API

#### 局部实现但不完整

- **`index.py`**：三项规范违规：`CREATE TABLE IF NOT EXISTS`（违反 Alembic 规则）、`?` 位置参数（违反命名参数规则）、每次调用 `sqlite3.connect()`（无连接池）；index 行在 session 文件被维护删除后不清理（`count()` 高估）
- **session_admin_store**：与 core manager 完全解耦，两个元数据存储（index.py + session_admin_store）并存且不同步
- **Session TTL 维护**：仅清理文件，不清理 SQLite index 行和 `_locks` 字典（慢内存泄漏）

---

### 2.6 上下文压缩（Context）

#### 消息流程

1. 三个入口：`maybe_compress()`（Tmax 门控）/ `compress_for_context_overflow()`（无条件）/ `apply_anti_flap()`（anti-flap 门控）
2. `_resolve_config()` 从 AgentFile 提取 8 个压缩参数；校验 `tretained_ratio < tmax_ratio`
3. `estimate_tokens()` 估算 token 数（image_url 固定 1000，其余 `len(str) // 4`）
4. `_compress()` → 三层分割（head/middle/tail）→ `_pre_cleanup()`（图片替换 + 工具去重）
5. `_extract_prev_summary()` 提取增量摘要基础 → `_summarize()` LLM 摘要（同步调用！）
6. 摘要失败 → 静态降级 notice；成功 → 拼装 `[*head, summary_msg, *tail]`
7. Anti-flap 节省率追踪 → circuit breaker 更新 → 持久化到 `session_anti_flap` SQLite 表

#### 现有能力

- 三层 head/tail/middle 分割（identity-based 去重）；AR14 增量摘要合并
- AR15 纯规则预清理（图片块替换 + 重复工具调用去重）；工具对完整性保护
- AR17 anti-flap circuit breaker（per-session 持久化）；静态降级 fallback
- privacy-by-design trace（仅记录 SHA-256 指纹，不记录摘要正文）

#### 缺失能力（分级）

**P0**
- **`_summarize()` 使用同步 OpenAI 客户端**：在 async 事件循环内调用同步 HTTP，阻塞整个事件循环 1-5 秒，多 session 并发时延迟线性放大。
- **Anti-flap circuit breaker 无重置路径**：`auto_disabled=True` 后无任何 API / 自动重置机制，session 永久禁用自动压缩。
- **CJK token 估算严重偏低**：`len(str) // 4` 对中文字符（1-1.5 token/字）低估 3-6 倍，Tmax 触发时模型已在 context overflow 边缘。
- **`_summarize()` 过滤掉所有 `tool` role 消息**：tool result 内容对摘要不可见，重工具使用 agent 的 middle 几乎全为空 assistant stub，摘要质量极差。

**P1**
- `summary_max_tokens` 未纳入 AgentFile schema（操作员无法通过 `agent.yaml` 调整）
- `init_anti_flap_db()` 违反 Alembic + 命名参数规则（`context_compress_threshold` AgentFile 字段也是死字段）
- 压缩进度 SSE 事件（流式 UI 无 spinner 提示）
- 可配置的 head 保留策略（仅 `initial_intent_max` 头部用户消息，无 pin/重要性标记）

**P2**
- 结构化摘要格式（当前自由散文，LLM 难以区分"已完成"vs"进行中"）
- 跨 session 上下文（压缩时不感知 long-term memory，重复内容进摘要）

#### 局部实现但不完整

- **Token 估算**：图片固定成本正确，CJK 字符系统低估
- **Anti-flap 磁滞**：`min_interval_turns` 默认 1 几乎无效；circuit breaker 无半开重置
- **增量摘要**：架构正确，但 512 token 上限 + 自由散文格式导致多次压缩后信息退化

---

### 2.7 模型路由（Model）

#### 消息流程

1. `AgentFile` → `ModelPolicySnapshot.from_agent()`（frozen，凭证间接化）
2. `policy.resolve(route_key)` → 有序 fallback 链 `tuple[ResolvedModelConfig, ...]`
3. `policy.require_api_key()` → call-time 读 `os.environ`（空值 → ModelConfigError）
4. `_policy_candidates()` 过滤 ProviderHealthCache 熔断器
5. `_call_policy_chat()` / `_stream_policy_chat()` 迭代候选 → 成功 `record_success` / 失败 `record_failure`
6. `ProviderHealthCache.is_available()` 实现 half-open probe（cooldown 过期后自动开放）

#### 现有能力

- agent-scoped 策略隔离；凭证间接化（fail-loud）；三级错误分类（ConfigError / AuthError / Switchable）
- frozen 不可变 snapshot；parse-time 协议校验；ProviderHealthCache（half-open + injectable time）
- 全链路熔断安全回退（所有 entry 熔断时返回完整链而非空列表）
- 重复 target ID parse-time 检测；vision route 图片内容自动路由

#### 缺失能力（分级）

**P1**
- **Retry-After header 感知 backoff**：429 立即切换而非等待，健康 provider 被错误熔断
- **per-route 并发令牌桶 / rate limiter**：突发请求直接打到后端，self-hosted vLLM 无保护
- **per-agent circuit breaker 隔离**：当前进程级单例，Agent A 的失败熔断影响 Agent B
- **流式 mid-stream 失败检测**：`record_success` 在 stream 对象打开时调用，stream 中途断流不计入失败

**P2**
- 路由错误子类区分（route 不存在 vs route 为空，当前同为 `ModelConfigError`）
- 优雅降级模式（fallback 静态响应）
- fallback 链最大长度 + 整体 deadline

#### 局部实现但不完整

- **ProviderHealthCache**：`call_with_policy`（resolver.py）完全不调用健康缓存；vision/embedding/rerank/image-gen 均用 `[0]` 无 fallback；`_states` dict 无 TTL
- **有序 fallback 链**：chat 路径正确，其他 protocol 仅取第一个 target

---

### 2.8 AgentLoop

#### 消息流程

1. `run_sync()` / `run_stream()` / `run()` 三入口，各自组装 messages
2. 模型路由（vision / default）→ MCP strict 可用性前置检查
3. `TerminationController` 初始化（6 个有序 checker）+ BudgetConfig + LoopState
4. 每轮：`controller.should_stop()` → `_gated_compress()` → 注入 loop warning → `sanitize()` → LLM 调用 + token 累计
5. finish_reason == `tool_calls`：`_plan_run_slots()` → `_execute_pending()` → `_backfill_slots()`
6. budget_exceeded → grace call（5% token 保留，流式 + 非流式双路径）
7. 循环退出：anti-flap 持久化 → `log_run()` → TraceEvent → 记忆提取

#### 现有能力

- 可组合 TerminationController；两维预算 + grace call；AR3 三相并行工具调度
- AR4 + AR10 双信号循环检测；AR17 anti-flap 门控压缩；message hygiene sanitize
- 多模型 fallback chain + ProviderHealthCache；hierarchical CancelToken 树
- Layered 跨 run 预算（AR18）；Sub-agent depth=1 隔离（SQLite 生命周期状态机）
- 双流式/非流式入口；SSE event vocabulary；eval/observability JSONL 日志

#### 缺失能力（分级）

**P0**
- **结构化输出 / typed response 强制**：无 JSON schema 验证和违规重试，数据提取类 agent 无安全网。
- **per-turn 可检查点 + 崩溃恢复**：进程崩溃丢失整个 run，长多轮任务不可靠。
- **瞬态 LLM 错误退避重试**：`ErrorClassification.should_retry=True` 是死代码，429 直接切换模型而非等待。
- **流式路径缺少 sub_agent 支持和审批门**：HTTP/SSE 是主要客户端路径，但两项企业合规关键功能缺席。

**P1**
- context_overflow 后 compress-and-retry（`should_compress` flag 从不读取，loop raise 而非恢复）
- per-run & per-tool 成本核算（USD / credits 维度）
- 流式中断 + mid-run 参数注入（dynamic interrupt / resume）
- 工具结果流式 / 增量输出
- 多 agent 通信协议（当前仅 parent→child 平铺，无 peer 协作）

**P2**
- 工具间 DAG 依赖声明
- 可配置 pre/post 工具 hook 中间件

#### 局部实现但不完整

- **人工审批门**：非流式路径完整，流式路径完全缺席；审批等待无超时
- **Sub-agent**：状态机完整，但子 agent 无 `allowed_tools` / governance 继承，实质为无管控执行
- **错误分类恢复**：`should_retry` / `should_compress` 定义存在但从不被 loop 读取；部分 reserved category 永远不被 `classify()` 返回
- **MCP 可用性处理**：run 开始时快照检查正确，run 中途 server 断线降级为 `consecutive_failures` 而非 `mcp_disconnect` stop reason

---

## 三、跨模块横切缺口

### 3.1 可观测性（Observability）

| 层次 | 现状 | 缺口 |
|------|------|------|
| Run 级别 | JSONL eval log，字段完整 | 无 per-turn 事件，无分布式 trace_id/span_id |
| Tool 级别 | run_code SB9 日志 | dispatch() 无 per-tool 延迟/参数 hash/结果大小发射 |
| MCP 级别 | stdlib logging | 完全不接入 eval_logger，无 server_id 标签，无 isError 计数 |
| Skill 级别 | `engine_observability` 返回 stub | 无命中次数、会话列表、stale 实际计算 |

### 3.2 多租户（Multi-tenancy）

- Session 命名空间通过 `owner_id:` 前缀实现，正确
- SlackSupervisor 仅支持单一 `admin_owner_id`，多租户 Slack 不可达
- Platform identity DB（im_users）与 per-agent LocalApprovalStore 完全解耦，admin 封禁无效
- ProviderHealthCache 进程级单例，租户间 circuit breaker 状态污染

### 3.3 认证与凭证安全

- `_reject_inline_secrets` 保护 agent.yaml；api_key_env 间接化防止 snapshot 泄漏
- Admin API 上传 skill 跳过注入审计（`engine_audit` placeholder）—— 安全缺口
- MCP OAuth2 仅支持 client_credentials，无 per-user 授权码 + PKCE
- Connector 凭证过期无 silent refresh，持续返回 NeedsConsent

### 3.4 SQL 规范违规汇总

| 文件 | 违规类型 |
|------|----------|
| `session/index.py` | `CREATE TABLE IF NOT EXISTS`（应用 Alembic）；`?` 位置参数；每次调用 `sqlite3.connect()` |
| `runtime/context.py` `init_anti_flap_db()` | `CREATE TABLE IF NOT EXISTS`；`?` 位置参数 |

---

## 四、优先级路线图

### P0（阻塞性，必须最优先解决）

| # | 模块 | 问题 | 核心影响 |
|---|------|------|----------|
| 1 | AgentLoop | 结构化输出/typed response 无强制 | 数据提取类 agent 无安全网 |
| 2 | AgentLoop | per-turn 检查点 + 崩溃恢复缺失 | 长多轮任务进程崩溃全丢 |
| 3 | AgentLoop | 瞬态 LLM 错误无退避重试（`should_retry` 死代码） | 瞬态 429 直接切换模型，健康 provider 被错误熔断 |
| 4 | AgentLoop | 流式路径缺少 sub_agent + 审批门 | HTTP/SSE 主路径功能不完整，企业合规缺席 |
| 5 | Context | `_summarize()` 使用同步 LLM 调用 | 多 session 并发时阻塞整个事件循环 |
| 6 | Context | Anti-flap circuit breaker 无重置 | Session 永久禁用自动压缩 |
| 7 | Context | CJK token 估算偏低 3-6 倍 | Tmax 触发过晚，已在 context overflow 边缘 |
| 8 | Context | `_summarize()` 过滤 tool role 消息 | 重工具 agent 摘要质量极差 |
| 9 | MCP | `isError` 字段未处理 | 工具错误被当成正常结果，agent 在错误上推理 |
| 10 | Skills | `engine_set_global_disabled` 为空操作 | Admin disable skill 无效，直到手动 reload |
| 11 | Skills | `engine_audit` placeholder 绕过注入审计 | Admin API 上传 skill 可绕过 8 规则审计 |
| 12 | IM 接入 | Slack 无自动重连 | 瞬态断线后 Bot 永久下线 |
| 13 | IM 接入 | Bot 自消息循环无防护 | 潜在无限消息循环 |
| 14 | IM 接入 | 无主动外发消息 API | 无法实现 proactive agent 行为 |
| 15 | Tools | `_build_schema()` 复杂类型全降级为 string | 模型对复杂参数格式盲飞，调用出错率高 |
| 16 | Tools | 无 per-parameter docstring 描述 | 模型缺乏参数级指导 |

### P1（重要，下一迭代解决）

| 模块 | 问题 |
|------|------|
| AgentLoop | context_overflow compress-and-retry；成本核算；流式 interrupt/resume；工具结果流式输出；多 agent peer 通信 |
| IM 接入 | 消息去重；typing indicator；回复长度分割；channel allowlist 接入路由；LocalApprovalStore 并发锁；Telegram per-agent connector |
| MCP | server push notifications；resource 原语；per-server 超时配置；多内容结果；tools/list 分页；capabilities 声明；MCP 调用遥测；OAuth2 PKCE |
| Session | `delete()` API；分布式锁；WAL/事件日志；状态机守卫 |
| Skills | Skill schema 声明；语义 skill 匹配；Skill 遥测；Skill 版本管理 |
| Model | Retry-After backoff；per-route 并发限制；per-agent circuit breaker；mid-stream 失败检测 |
| Context | `summary_max_tokens` 入 AgentFile；Alembic 迁移 anti_flap；压缩进度 SSE；head 保留策略 |
| Tools | 工具调用结构化输出；per-tool 重试策略；工具执行遥测 |

### P2（提升，按资源安排）

| 模块 | 问题 |
|------|------|
| IM 接入 | 消息队列 backpressure；IM 调用层超时；非图片附件透传 |
| Skills | Frontmatter schema 验证；catalog 分页上限；参数注入模板；Skill 链式组合 |
| MCP | MCP prompt 原语；elicitation；HTTP 连接池 |
| Session | Session fork/branch；per-session 文件大小上限；分页 session 列表 |
| Context | 结构化摘要格式；跨 session 上下文感知 |
| Model | 路由错误子类区分；优雅降级模式；fallback 链 deadline |
| AgentLoop | 工具间 DAG 依赖；pre/post 工具 hook |
| Tools | 工具间依赖图；schema 版本/deprecated 标记；per-server 并发限制 |

---

## 五、结论

fleetent 的核心架构设计具有超越同类开源框架的多项优势：NormalizedMessage 平台无关封装、@tool 带外注入机制、MCP 三态健康模型、TerminationController 可组合终止框架、anti-flap 压缩门控，这些都是经过深思熟虑的工程决策。

然而，平台距离生产级企业部署就绪还有三条主要障碍：

**第一，正确性缺口**：`engine_audit` placeholder 让 Admin API 成为注入攻击入口；MCP `isError` 未处理导致工具错误变成"有效结果"进入 LLM；Context 压缩中工具结果被过滤导致重工具 agent 摘要形同虚设。这三项必须最优先修复。

**第二，可靠性缺口**：Context 压缩的同步 LLM 调用在多并发场景下是显著瓶颈；CJK token 估算偏差导致压缩触发过晚；AgentLoop 缺少检查点恢复意味着长多轮任务在进程崩溃时全部丢失。

**第三，功能完备性缺口**：流式路径（HTTP/SSE 主要客户端）缺少 sub_agent 支持和审批门；无主动外发消息 API 使 proactive agent 行为完全不可实现；`_build_schema()` 类型映射不完整使模型对复杂参数盲飞。

建议按照上述 P0→P1→P2 路线图分三个迭代推进，优先在当前迭代内完成全部 16 项 P0 修复，同时在 PR 门禁中加入 `check_test_layers.py` 对新增 SQL 代码的 Alembic + 命名参数合规检查，防止技术债务进一步累积。
