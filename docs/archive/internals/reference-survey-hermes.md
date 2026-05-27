# hermes-agent 调研笔记

> **项目类型**：Python + FastAPI + 多协议网关的自学习 AI Agent 平台
> 
> Nous Research 开发的生产级 agent 框架。支持 100+ LLM 提供商、7 种终端后端（Docker/SSH/模态网络/无服务器）、自我改进型技能系统、多平台网关（Telegram/Discord/Slack）。代码库 ~70K 行 Python，设计强调流式、容错、可观测性。

---

## 1. 核心循环（Agent Loop）

### 1.1 它做了什么

- **While 循环的消息驱动 tool-use**（run_agent.py:12541）：条件为迭代预算>0 且 API 调用未超过限制；每次循环拉取最新模型响应，分离 tool_calls，执行，收集结果，逐步构建 messages 列表。
- **非流式 vs 流式双路**：支持 stream_callback 参数用于 TTS 流式触发，同时主循环保持非流式消息积累以保证 tool-call 的可靠解析。
- **中断响应**（run_agent.py:12546-12551）：检查 `_interrupt_requested` 标志，允许用户在 API 调用期间打断（用于 /steer 命令、手动中断）。
- **三层重试与分类**（agent/error_classifier.py）：API 错误分为 12+ 类（auth/billing/timeout/context_overflow/format_error 等），每类关联不同恢复策略（重试/轮换凭证/fallback/压缩）。
- **Iterator 预算与 grace call**（run_agent.py:287-330）：线程安全的 IterationBudget 类追踪消耗与剩余，支持 refund 机制（execute_code 迭代不消耗预算），超预算后还给一个"grace call"机会。
- **Tool 并发执行**（run_agent.py:334-359）：根据工具属性划分并发安全集（IDEMPOTENT/PARALLEL_SAFE）与互斥集（NEVER_PARALLEL），使用 ThreadPoolExecutor 最多 8 个 worker；跨工具去重哈希避免重复执行。
- **故障检测与验证**（run_agent.py 内联）：每个工具响应经历 tool_result_classification 判定（文件变更是否真的落地、超时、崩溃），失败时合成错误消息注入回循环。
- **消息修复与清理**（run_agent.py:12658-12683）：修复工具调用参数的 JSON 损坏、消息角色交替违规、去除内部字段（reasoning/finish_reason）以适配严格 API。

### 1.2 关键设计点

- **IterationBudget 的 grace call 机制**：预算耗尽时允许最后一个API调用，让模型有机会生成最终回复而非被硬截断。设计精妙地避免了"偏离预期的切割点"问题。
- **工具并发的三层划分**：NEVER_PARALLEL（clarify）→ PARALLEL_SAFE（web_search）→ PATH_SCOPED（read_file）。不是全局黑名单，而是细粒度地允许独立路径的文件操作并发。
- **Error_classifier 的 enum 驱动设计**：12+ FailoverReason 类避免了分散的字符串匹配；每个错误类携带 should_compress/should_rotate_credential/should_fallback 等决策字段，主循环只需读标志而无需重复分类逻辑。
- **"steer 注入"的延迟执行**（run_agent.py:12602-12650）：/steer 用户指令不立即注入 user message（会破坏角色交替），而是附加到最近的 tool 消息或挂起到下一个工具批。设计妥协了立即性以保证消息有效性。

### 1.3 关键文件清单

| 文件 | 用途 |
|------|------|
| run_agent.py:12541-12900 | While 循环骨架、API 调用序列、工具执行调度 |
| run_agent.py:287-330 | IterationBudget 类，线程安全的迭代计数 |
| run_agent.py:334-359 | 工具并发安全分类（PARALLEL_SAFE/NEVER_PARALLEL）与哈希去重 |
| agent/error_classifier.py | 12+ FailoverReason enum，错误分类与恢复策略 |
| agent/anthropic_adapter.py:54-86 | 模型特定参数映射（adaptive thinking/output limits） |
| agent/retry_utils.py | jittered_backoff 重试延迟 |
| agent/tool_result_classification.py | 工具执行结果验证（文件变更、超时、崩溃） |

---

## 2. 工具（Tools）

### 2.1 它做了什么

- **统一注册机制**（model_tools.py）：`get_tool_definitions()` 扫描 tools/ 目录与 plugins/，每个工具输出 OpenAI schema（name/description/input_schema）。支持内置、MCP、插件三类工具。
- **MCP 客户端内嵌**（tools/mcp_tool.py）：支持 stdio/HTTP/StreamableHTTP/SSE 三种传输；启动 MCP server 进程，在后台 asyncio 循环中与之通信；tool schema 自动从 MCP 服务端注册消息推导。
- **工具调用守卫**（agent/tool_guardrails.py）：按签名哈希跟踪重复工具调用，检测"同工具连续失败"、"幂等工具无进展"、"完全重复调用"三类模式；支持警告级与硬停止级两档控制。
- **超时与资源限制**（tools/code_execution_tool.py 与个别工具）：execute_code 默认 300s 超时、最多 50 工具调用、stdout/stderr 限制 50KB/10KB。MCP 服务器支持按 server 配置超时。
- **访问控制与 secret 过滤**（tools/code_execution_tool.py:118-154）：execute_code 沙箱严格过滤环境变量，仅允许 PATH/LANG/VIRTUAL_ENV 等安全前缀，过滤所有含 KEY/TOKEN/SECRET 的变量名。
- **工具调用参数消毒**（run_agent.py:12658-12662）：修复 JSON 损坏（未关闭的字符串、尾随逗号）、验证 schema 匹配，避免发送给严格 API 时的 400 错误。
- **内置 vs 用户工具的加载顺序**：MCP > plugins/tools > 内置工具，允许用户通过同名覆盖内置工具。
- **结果格式化与 Streaming**：tool_result 的 content 支持字符串和多部分块（文本/图像/结构化数据），适配多种 content 类型；支持流式输出到 UI。

### 2.2 关键设计点

- **MCP 后台循环的线程安全设计**（tools/mcp_tool.py:78-130）：MCP 服务器运行在独立 asyncio 循环的守护线程，工具调用通过 `run_coroutine_threadsafe()` 调度到循环，消息通过 Queue 传递。避免了单线程阻塞。
- **工具守卫的 ToolCallSignature 哈希**（agent/tool_guardrails.py:134-142）：计算工具名 + 规范化参数的 SHA256，允许检测参数相同但顺序不同的重复调用；支持比较精细的"同一意图"重复检测。
- **Secret 过滤的"先断名后断值"策略**（tools/code_execution_tool.py:146-148）：三层过滤（1.passthrough 白名单；2.名字包含 SECRET/KEY；3.安全前缀匹配），避免了"值泄露"的误报。
- **MCP server 的 reconnect + backoff**：stdio 连接失败时，自动退避重试最多 5 次，期间临时不可用该 server 的工具（不硬崩溃）。

### 2.3 关键文件清单

| 文件 | 用途 |
|------|------|
| tools/mcp_tool.py | MCP 客户端实现，stdio/HTTP/SSE transport，后台循环管理 |
| tools/mcp_tool.py:119-168 | MCP stderr 重定向与日志管理 |
| agent/tool_guardrails.py | 工具循环检测（重复/失败/无进展），警告与硬停止 |
| agent/tool_result_classification.py | 结果验证（落地检查、超时、崩溃检测） |
| tools/code_execution_tool.py:118-154 | 沙箱环境变量过滤与 secret scrubbing |
| model_tools.py | 工具注册与 dispatch 的中央枢纽 |

---

## 3. Skill

### 3.1 它做了什么

- **文件系统扫描与发现**（tools/skills_tool.py:86-104）：~/.hermes/skills/ 为单一真实来源，递归扫描所有 SKILL.md 文件；支持嵌套分类目录；排除 .git/.github/.archive 等目录。
- **Frontmatter 元数据解析**（agent/skill_utils.py:52-86）：YAML 前言包含 name/description/version/platforms/prerequisites；支持 agentskills.io 标准（metadata.hermes.tags）；失败回退到简单 key:value 解析。
- **平台约束过滤**（agent/skill_utils.py:92-115）：frontmatter 中的 platforms: [macos, linux] 字段控制在该平台可见；当前平台通过 sys.platform 或 HERMES_PLATFORM 环保变量确定。
- **渐进式披露架构**：skills_list 返回仅元数据（name/description/版本），避免加载全量指令文本；skill_view 按需加载完整 SKILL.md；references/ 内的链接文件可单独加载（token 效率）。
- **与 agent loop 的集成**：skill nudge 机制；经历 N 个 tool 迭代后弹窗"是否保存新 skill"；skill_manage 工具用于创建/编辑/删除。
- **Skill 禁用列表**（agent/skill_utils.py:121-151）：config.yaml 中的 skills.disabled_skills 或平台特定的 skills.<platform>.disabled_skills 可禁用指定 skill。
- **Prompt 注入防护**（tools/skills_tool.py:134-144）：检测 SKILL.md 内容中的 16 个注入模式（"ignore previous instructions"、"new instructions:" 等），提示用户审查。

### 3.2 关键设计点

- **单一真实来源 ~/.hermes/skills/**：hub 安装、用户自建、捆绑 skill 全部汇聚于此，避免多源冲突；git repo 中的 skills/ 仅为模板，安装时复制到 home。
- **渐进式披露的 token 节省**：skills_list 返回 ~100 bytes/skill，全量 skill_view 可能 ~5KB；对于 100 个 skill 的用户，列表查询仅消耗 10 token，精确加载时才支付成本。
- **平台字段的 backward compatibility**：omitted platforms 默认为"全平台可见"，老 skill 无需修改。

### 3.3 关键文件清单

| 文件 | 用途 |
|------|------|
| tools/skills_tool.py | 主要实现：SKILL.md 扫描、frontmatter 解析、渐进披露工具 |
| agent/skill_utils.py | 轻量型工具（frontmatter/平台检查），避免循环依赖 |
| agent/skill_commands.py | skill 命令注入与 prompt 生成 |
| agent/skill_preprocessing.py | 老格式兼容与规范化 |

---

## 4. MCP

### 4.1 它做了什么

- **Transport 多态**（tools/mcp_tool.py:182-201）：stdio（command+args）、HTTP/StreamableHTTP（url）、SSE（transport: sse）三种 transport 通过统一接口抽象；自动协议版本检测。
- **Server 注册与发现**（~/.hermes/config.yaml mcp_servers 节）：支持 command/args 或 url 配置；支持环变注入（GITHUB_PERSONAL_ACCESS_TOKEN）；按需延迟启动（首次工具调用时）。
- **工具命名规范**（tools/mcp_tool.py）：server_name + "_" + tool_name（e.g., "filesystem_read_file"）避免跨 server 工具名冲突；工具 schema 自动从 MCP 注册消息推导。
- **OAuth 与认证**（tools/mcp_oauth*.py）：对 OAuth 类 MCP server 支持 credential 存储与刷新；自动在 tool 调用前检查过期时间。
- **健康检查与降级**（tools/mcp_tool.py）：server 启动失败时，该 server 的所有工具暂时不可用；reconnect 重试 5 次，期间不影响其他 tool 和 server。
- **Parallel tool call opt-in**（config 中 supports_parallel_tool_calls: true）：逐 server 配置，允许同一 server 的多个工具调用并发执行。
- **Server-initiated sampling**（tools/mcp_tool.py:40-47）：MCP server 可请求 LLM 补全（via sampling/createMessage）；Hermes 支持与限流（max_rpm/max_tokens_cap/max_tool_rounds）。

### 4.2 关键设计点

- **后台循环中的 MCP 生命周期**：server Task 在背景 asyncio 循环中，连接保活；shutdown 时显式 exit async context，确保 anyio cancel scope 清理在同一 Task 执行（避免资源泄漏）。
- **Streamable HTTP 的设计**：允许 server 增量返回工具 schema 与结果，减少首次连接延迟（relative to 一次性加载所有 schema）。
- **Sampling 的沙箱化**：MCP server 请求的 LLM 调用在隔离的 auxiliary_client 上执行，不消耗主 agent 的 token 预算，支持模型覆盖。

### 4.3 关键文件清单

| 文件 | 用途 |
|------|------|
| tools/mcp_tool.py | MCP 客户端核心，transport 多态与后台循环 |
| tools/mcp_oauth*.py | OAuth credential 管理与自动刷新 |
| mcp_serve.py | Hermes 本身作为 MCP server（expose 会话 API） |
| hermes_cli/mcp_config.py | config.yaml mcp_servers 节的解析与验证 |

---

## 5. 沙箱（Sandbox）

### 5.1 它做了什么

- **双传输架构**（tools/code_execution_tool.py:8-28）：本地 backend 用 Unix Domain Socket（UDS）RPC；远程 backend（Docker/SSH/Modal/Daytona）用文件轮询（request/response 文件）。两者都支持工具调用的同步等待。
- **资源限制**（tools/code_execution_tool.py:70-75）：execute_code 默认 300s 超时、最多 50 工具调用、stdout 50KB/stderr 10KB 上限；可在 config.yaml 中按 code_execution.* 覆盖。
- **环境隔离与 secret 过滤**（tools/code_execution_tool.py:118-154）：子进程仅获得白名单环变（PATH/LANG/VIRTUAL_ENV 等）；所有名字包含 KEY/TOKEN/SECRET 的变量自动过滤；passthrough list 可显式允许特定变量。
- **多语言与多后端**（tools/code_execution_tool.py 与 tools/terminal_tool.py）：Python 脚本为主；支持远程 bash（terminal 工具调用）；Docker/SSH/Singularity/Modal/Daytona/Vercel Sandbox 七种后端。
- **执行超时与自杀**（signal handling）：使用 SIGTERM/SIGKILL 级联终止超期脚本；子进程可捕获 SIGTERM 做清理。
- **Stdout/stderr 流控**：脚本输出仅返回末尾 50KB stdout，避免 OOM；stderr 分开限制 10KB。
- **工具存根生成**（tools/code_execution_tool.py:182-500）：execute_code 动态生成 hermes_tools.py stub 模块，包含 web_search/read_file/write_file/patch/terminal 等 7 个工具的 RPC wrappers；脚本导入该模块即可同步调用。

### 5.2 关键设计点

- **UDS 与 TCP 的双选择**：Unix 系统优先 UDS（本地限制、权限安全），Windows 和 CI 退回 loopback TCP（0.0.0.0:random_port 再关闭）。设计兼容各平台。
- **文件轮询的异步状态机**：远程 backend 的脚本写 request JSON，parent 后台线程定期扫描，解析、执行工具、写 response；脚本 poll response 文件，避免阻塞。
- **Stub 的动态生成**：hermes_tools.py 按当前 session enable_tools 与 SANDBOX_ALLOWED_TOOLS 的交集生成，避免脚本调用不可用的工具。

### 5.3 关键文件清单

| 文件 | 用途 |
|------|------|
| tools/code_execution_tool.py:1-200 | 沙箱双传输架构与资源限制定义 |
| tools/code_execution_tool.py:118-154 | 环变过滤与 secret scrubbing |
| tools/code_execution_tool.py:182-500 | hermes_tools.py stub 生成器 |
| tools/code_execution_tool.py:560-630 | 远程 backend（Docker/SSH）的文件 RPC |
| tools/terminal_tool.py | 终端后端配置与 session 管理 |

---

## 6. 上下文压缩（Context Compression）

### 6.1 它做了什么

- **触发条件**（agent/context_engine.py:64-66 与 context_compressor.py:SUMMARY_* 常量）：threshold_percent（默认 75%）× context_length；当 prompt_tokens 超过阈值时触发。例如 200K 上下文的模型，150K token 时触发。
- **分阶段压缩**（context_compressor.py:1374-1583）：Phase 1 预修剪老工具结果（cheap）→ Phase 2 确定 head/tail 边界 → Phase 3 生成 LLM 摘要 → Phase 4 重组消息。
- **保留策略**（context_compressor.py:1401-1426）：protect_first_n（默认 3 条非系统消息）+ system_prompt 保留为 head；protect_last_n（默认 6 消息）+ tail_token_budget（~20K token）保留为 tail；中间部分摘要。
- **摘要算法**（context_compressor.py:1472-1503）：使用 auxiliary_client（廉价/快速的 LLM）生成结构化摘要，包含"已解决问题"、"待解决工作"、"活跃任务"三部分；迭代式摘要（再压缩时更新）。
- **Tool pair 完整性**（context_compressor.py:1560）：`_sanitize_tool_pairs()` 在压缩后清理孤立的 tool_call/tool_result（e.g., tool_call 被摘要移除但 result 保留）。
- **压缩元数据与引用**（agent/context_references.py）：保留引用链（哪次压缩生成的摘要）；可选的 focus_topic 参数引导摘要（e.g., `/compact focus_on:database`）。
- **镜像处理**（context_compressor.py:153-175）：strip_image_parts() 在 tool_call 中移除旧图像内容（computer_use 截图），替换为文本占位符；避免图像重复计入 token。
- **反抖动**（context_compressor.py:1565-1571）：tracking _ineffective_compression_count；若连续压缩节省 <10%，停止压缩（避免频繁无效操作）。

### 6.2 关键设计点

- **Token 预算尾部保护而非固定消息数**（context_compressor.py:1425-1426）：`_find_tail_cut_by_tokens()` 确保保留的 tail 消息至少包含 tail_token_budget（~20K）token，灵活适应长文本与多图像消息。
- **迭代式摘要的状态管理**（context_compressor.py:1440-1448）：跟踪 _previous_summary；再压缩时检查是否已有历史摘要，仅对 summary 之后的新消息进行更新，避免信息丢失。
- **SUMMARY_PREFIX 的"引用 vs 指令"区分**（context_compressor.py:37-51）：摘要开头明确标记"CONTEXT COMPACTION — REFERENCE ONLY"，避免模型将历史问题读作新的用户请求（踩过的坑 #11475）。
- **孤立 tool pair 的清理**（context_compressor.py:1560）：压缩后遍历消息，验证每个 tool_call 是否有对应的 tool_result，孤立的 call 被移除，保持 API 合法性。

### 6.3 关键文件清单

| 文件 | 用途 |
|------|------|
| agent/context_compressor.py | 主实现：分阶段压缩、摘要生成、tool pair 清理 |
| agent/context_engine.py | 抽象基类与接口定义（可插拔的 context 引擎） |
| agent/context_references.py | 摘要引用链与 focus_topic 处理 |
| agent/model_metadata.py | Token 估算（estimate_messages_tokens_rough） |

---

## 总结：值得借鉴的与值得规避的

### 借鉴的最佳实践

1. **错误分类驱动重试**：enum-based FailoverReason 避免分散的字符串匹配；每个错误类携带恢复策略标志（should_compress/should_rotate），主循环简化为"读标志 → 执行"。

2. **工具并发的三层划分**：不是全局黑名单，而是 PARALLEL_SAFE（幂等）→ PATH_SCOPED（路径隔离）→ NEVER_PARALLEL（交互式）的分级模型，允许尽可能多的并发而保证安全。

3. **MCP 后台循环的线程模型**：server Task 在独立 asyncio 循环的守护线程，工具调用通过 `run_coroutine_threadsafe()` 调度，消息 Queue 传递。避免了主线程阻塞，也避免了全局锁。

4. **Token 预算尾部保护而非固定消息数**：context_compressor 使用 token 预算而非固定 N 条消息来确定保留范围，自适应长文本/多媒体内容的变长 token 成本。

5. **Skill 的渐进式披露**：skills_list 返回仅元数据（~100 bytes/skill），skill_view 按需加载全文（~5KB），大幅降低 token 成本；符合 progressive disclosure 设计原则。

6. **Grace call 机制**：迭代预算耗尽时允许一次 API 调用，避免"硬截断导致无回复"的糟糕 UX；小的设计改进，大的用户体验提升。

7. **Secret 过滤的多层防御**：passthrough 白名单 → 名字包含检查 → 安全前缀匹配 → Windows essential list，避免"值泄露"的误报同时抓住大部分真实 secret。

8. **Steer 注入的延迟执行**：/steer 用户指令不直接改 user message（破坏角色交替），而是附加到最近 tool 消息或挂起，保证消息序列有效性。

### 值得规避的陷阱

1. **内联重试逻辑**：hermes 中的错误分类集中在 error_classifier.py，易于维护扩展；反面是早期项目可能散落重试逻辑于各处，难以一致地升级。

2. **tool_call 参数消毒的复杂性**：hermes 需要同时处理内置工具、MCP 工具、第三方 API 的参数格式差异，导致 _sanitize_tool_call_arguments/run_agent.py:12658 的逻辑复杂。fleetent 应早期统一参数规范。

3. **Context 压缩的摘要失败处理**：if summary generation fails, 插入静态 fallback（context_compressor.py:1491-1503）。但 auxiliary_client 本身也可能超时/错误，需要 defensive fallback，成本高；考虑预生成模板或缓存。

4. **MCP server reconnect 的幽灵连接**：stdio server 启动失败时，该 server 的工具会暂时不可用，但重试会一直进行；用户可能看到间歇性的"工具失败"而难以诊断。需清晰的用户警告。

5. **Parallel tool execution 的路径隔离启发式**：_extract_parallel_scope_path() 尝试从工具参数推导路径，但工具定义五花八门（有的没有 path 字段），启发式易失效。兼容性测试应全面。

6. **Skill frontmatter 的 backward compatibility**：omitted platforms = 全平台可见，老 skill 无需改但新 skill 应显式声明；这种隐式默认容易造成混淆（某些环境突然看不到 skill）。

7. **execute_code 的 stub 动态生成**：hermes_tools.py 按 enable_tools 生成，但脚本可能在运行中尝试调用被过滤的工具（e.g., 用户改配置），导致 import error 或 RPC fail；应在生成时更明确地枚举可用工具。

---

## 附录：关键模块的交互流

```
Agent Loop (run_agent.py:12541)
  ├─> API call (anthropic_adapter / bedrock_adapter)
  │   └─> Error Classification (error_classifier.py)
  │       └─> Failover/Retry/Fallback/Compress
  │
  ├─> Tool Execution
  │   ├─> Parallel decision (_should_parallelize_tool_batch)
  │   ├─> Dispatch (model_tools.py handle_function_call)
  │   │   ├─> MCP tool (tools/mcp_tool.py)
  │   │   ├─> execute_code (Sandbox, tools/code_execution_tool.py)
  │   │   └─> Built-in tools (terminal, write_file, etc.)
  │   │
  │   └─> Guardrails (tool_guardrails.py)
  │       └─> Duplicate/Loop detection
  │
  ├─> Context Management
  │   ├─> Token tracking (context_engine.py)
  │   └─> Compression trigger (context_compressor.py)
  │       └─> Summarization (auxiliary_client)
  │
  └─> Skill nudge (agent/skill_commands.py)
      └─> skill_manage tool
```

