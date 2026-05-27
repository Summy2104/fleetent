# 业界实践调研：agent runtime 六模块

> 调研时间：2026-05-25
> 用途：为 fleetent agent-runtime 自研框架子功能设计提供输入
> 范围：核心循环 / 工具 / Skill / MCP / 沙箱 / 上下文压缩
> 方法：6 个模块各做一次 WebSearch + 1-2 个权威来源 WebFetch 深读
> **本文档只罗列他人怎么做、为什么这么做、踩了什么坑——不做实现选型**

---

## 1. 核心循环（Agent Loop）

### 1.1 业界共识架构

Claude Code、Claude Agent SDK、LangGraph、smolagents、Sketch、Cursor 等主流实现**都收敛于同一形态**：while 循环，调 LLM → 检查是否有 tool_calls → 有则执行并把结果回填、继续；无则停止。这是 ReAct 模式（reasoning interleaved with acting）的工业化版本。

> **要点**：「最简形态 9 行代码」可以跑通，但生产可用版本需要额外的「外围机制」，简单与生产之间的 gap 全部在循环外。

### 1.2 生产化必备能力

调研明确提到的生产硬化要素：

- **上下文压缩**（compaction）：循环内集成压缩触发点（见 §6）
- **循环检测**（loop detection）：相同 tool_call + 相同参数连续 N 次需告警/中断
- **成本预算**（cost budget）：token / 美元 / 调用次数上限
- **优雅终止**（graceful termination）：处理 SIGINT/cancel，允许中途取消但完成当前 tool 调用
- **检查点**（checkpointing）：支持中途暂停、人工审批、time-travel debug、失败恢复
- **完整轨迹评估**：不仅看最终输出，看整个 trajectory——工具顺序、参数是否合理

### 1.3 终止条件（多源）

- 自然终止：`finish_reason=stop` 且无 tool_calls
- 强制终止：`max_turns` / `max_tokens` / `budget` 超限
- 失败终止：模型连续 N 次报错或 tool 连续失败
- 人工终止：审批拒绝 / cancel 信号
- 循环检测：同一 tool+params 连续重复 → 抑制

### 1.4 流式 vs 同步

- **同步**：等完整 `output + tool_calls`，逻辑简单，但 UX 差
- **流式**：token-by-token 输出，需处理「流到一半发现要 tool_call」的拼装
- 工业实践：双 API（一个返回 string、一个 yield event），共享同一循环核

### 1.5 错误处理与重试

简化版没有错误处理，**所有踩坑都在生产化版本里**：

- LLM 调用 429/503 → fallback model 或退避重试
- tool 执行抛异常 → 把异常转成 tool_result 回传给 LLM（让它自己决定怎么办）
- 模型出现「奇怪行为」（如 Sketch blog 报告："this test doesn't pass... let's just skip it"）→ 这类语义错误无法在循环层修复，需在提示词/审计层处理

### 1.6 关键注意事项

- **每次循环必须 trace**：trajectory（工具序列、参数、耗时）是后续 eval 与 debug 的唯一抓手
- **tool_use_id 完整性**：tool_use 与 tool_result 必须 1:1 配对——压缩、截断、错误处理时不能破坏这对关系，否则 API 直接报错
- **并发工具调用**：模型可一次返回多个 tool_calls；可串行/并行执行，但要小心副作用顺序
- **可中断性**：长循环必须可被外部信号中断，否则一个失控 agent 拖死整个进程

### 1.7 来源

- [Sketch: The Unreasonable Effectiveness of an LLM Agent Loop](https://sketch.dev/blog/agent-loop)
- [Steve Kinney: The Anatomy of an Agent Loop](https://stevekinney.com/writing/agent-loops)
- [Databricks: Agent system design patterns](https://docs.databricks.com/aws/en/generative-ai/guide/agent-system-design-patterns)
- [LangChain: The Agent Improvement Loop Starts with a Trace](https://www.langchain.com/blog/traces-start-agent-improvement-loop)
- [Oracle: What Is the AI Agent Loop?](https://blogs.oracle.com/developers/what-is-the-ai-agent-loop-the-core-architecture-behind-autonomous-ai-systems)

---

## 2. 工具（Tools）

### 2.1 注册与 schema

- **注册形态**：Registry 模式，作为「单一事实源」——同时供给 LLM（schema）和执行环境（实现）
- **schema 形式**：JSON Schema 描述参数；OpenAPI / Pydantic / dataclass 三种主流来源
- **来源多样性**：内置 / 用户自定义 / MCP 工具 / 子 agent——都进同一 registry，注意命名冲突

### 2.2 命名与描述（Anthropic「Writing Tools for Agents」核心建议）

- **namespacing**：用前缀分组（`asana_search`、`asana_projects_search`）划定边界
- **描述像 onboarding 新员工**：把领域术语、隐含上下文显式写出
- **参数命名**：用 `user_id` 而非 `user`，**避免歧义降低幻觉**
- **`response_format` 枚举**：让 agent 自己选 verbose / concise，concise 可降 ~65% token

### 2.3 错误返回（pedagogical 优于 opaque）

- 不要返回 stack trace 或晦涩错误码
- 返回「具体可操作的改进建议」，让 agent 自动纠正
- 错误结构（XML / JSON / Markdown）影响后续 token 预测——选与训练分布更接近的

### 2.4 结果格式化

- 不要返回原始大数据：`list_contacts` 全列表 → 浪费上下文；用 `search_contacts`
- UUID / 哈希 ID 让 agent 难以引用；用语义化标识符
- 工具应「内部合并多步操作」——`schedule_event` 内部既查可用性又预定，减少 agent 决策点

### 2.5 访问控制

- **白名单（allowed_tools）**：fnmatch 或前缀匹配，按 agent 角色控制
- **风险分级**：low（自动执行）/ medium（提示）/ high（人工审批），与审批门联动
- **数据 redaction**：敏感参数（密码、token）打码后才能进 trace

### 2.6 反模式

- 工具过多（tool proliferation）反而降低准确率——少而精
- 工具返回完整数据集——浪费 token
- 暴露技术 ID（UUID）——agent 难关联
- 工具边界过死——agent 无法组合使用

### 2.7 关键注意事项

- **schema 必须与实现一致**：装饰器自动推导 schema 时，参数默认值、Optional、Union 三类容易出错
- **超时是必备**：工具调用必须有强超时；不可信工具（MCP、用户自定义）超时更严
- **工具结果必须可序列化为 string**：LLM API 只接受文本回传——非文本（图片、二进制）需另作约定
- **工具失败也要返回**：抛异常 vs 返回错误结构——主流选后者，让模型继续推理

### 2.8 来源

- [Anthropic: Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Premai: LLM Function Calling Complete Implementation Guide 2026](https://blog.premai.io/llm-function-calling-complete-implementation-guide-2026/)
- [Future Insights: Function Calling and Tool Use Patterns](https://www.futureinsights.com/function-calling-tool-use-patterns-llm/)
- [arXiv 2508.02979: Unified Tool Integration for LLMs](https://arxiv.org/pdf/2508.02979)

---

## 3. Skill

### 3.1 Anthropic Agent Skills 范式（核心参考）

Skill 不是「关键词匹配后塞 system prompt」那么简单，Anthropic 引入了**渐进式披露（progressive disclosure）** 三层模型：

| 层级 | 时机 | 内容 |
|------|------|------|
| L1 | 启动时 | 所有 skill 的 `name` + `description` 进 system prompt |
| L2 | LLM 决定使用某 skill 时 | 通过 Bash/file 工具读 SKILL.md 完整内容到上下文 |
| L3+ | 任务执行中 | SKILL.md 里引用的额外文件按需读取 |

**底层原理**：把 skill 库当成「可文件系统遍历的知识库」，agent 用代码执行能力自主导航，**绕开 token 预算限制**。

### 3.2 Skill 结构

- 目录形态：`{skill_name}/SKILL.md` + 引用文件（reference.md / forms.md / 脚本）
- 元数据：SKILL.md 顶部 YAML frontmatter，必填 `name` + `description`
- SKILL.md 主体：详细指令，L2 时被加载

### 3.3 多 skill 组合

- 没有显式组合协议——所有 skill 的 metadata 共存于同一 system prompt
- agent 基于任务相关性自主选择
- 进度披露设计确保 skill 之间「互不污染上下文」

### 3.4 安全模型

- 只信任已审计来源——**runtime 不强制隔离**
- 审计关注点：文件内容、bundled 脚本、外部网络指令
- 风险：恶意 skill 可指示 agent 调用工具，超出 skill 声明用途

### 3.5 关键注意事项

- **L1 描述质量决定 skill 召回率**：description 写不好 → agent 永远不会触发它
- **lazy loading 要求 agent 有文件读工具**：否则退化成传统 system-prompt 注入
- **热加载**：文档未提，工业实践通常启动时扫描；CLI 模式可每次重扫
- **skill 嵌套**：SKILL.md 可引用其他 skill，需防循环引用
- **比 fleetent 现状的差距**：fleetent 当前是关键词匹配后一次性塞 system prompt，未做 progressive disclosure——值得讨论是否引入

### 3.6 来源

- [Anthropic: Equipping Agents for the Real World with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Anthropic Platform Docs: Agent Skills Overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Lee Hanchung: Claude Agent Skills First Principles Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)

---

## 4. MCP（Model Context Protocol）

### 4.1 协议状态

截至 2026-03，MCP 月下载 9700 万次、GitHub star 8.1 万，Anthropic / OpenAI / Google / Microsoft / AWS 全部支持——**事实标准**。

### 4.2 两种官方 transport

#### 4.2.1 stdio
- 客户端 spawn 子进程；通过 stdin/stdout 收发 JSON-RPC
- **消息以换行符分隔，消息内不能有嵌入换行**
- stderr 留给日志（客户端可捕获/转发/忽略）
- stdout 必须只包含合法 MCP 消息
- 优势：进程隔离、易实现；劣势：本机限定、不易复用

#### 4.2.2 Streamable HTTP（2024-11 替代旧 HTTP+SSE）
- 单一 endpoint，支持 POST 与 GET
- POST：客户端发请求；响应可以是 `application/json`（一次性）或 `text/event-stream`（SSE 流）
- GET：客户端订阅 server → client 推送
- **session 管理**：`Mcp-Session-Id` header，初始化时由 server 分配
- **可恢复**：SSE event 带 `id`，断线后客户端发 `Last-Event-ID` GET 恢复
- 终止：客户端 DELETE 该 session

### 4.3 安全要求（强制 MUST）

- Streamable HTTP server **必须**验证 `Origin` header 防 DNS rebinding
- 本机运行**应**绑 127.0.0.1 而非 0.0.0.0
- 所有连接**应**实施认证

### 4.4 认证

- OAuth 是主流（hermes 实测有 `mcp_oauth_manager.py`，调研也提到）
- 协议层不强制认证机制，留给 transport 实现

### 4.5 工具命名

- 没有协议强制，但客户端通常用 `{server_id}__{tool_name}` 双下划线（fleetent 当前做法）规避冲突

### 4.6 关键注意事项

- **stdio 不能往 stdout 写非协议数据**——库的 `print()`、调试输出全部要重定向到 stderr，否则解析挂掉
- **Streamable HTTP 替代 HTTP+SSE 但兼容老 client**：实现时要支持两条路径并存的迁移期
- **session 过期处理**：server 可任意时刻 404，client 必须能识别并重新 init
- **MCP server 健康检查**：协议没定义，需上层定期探活（initialize 请求或自定义 ping）
- **降级策略**：MCP 失败时，是停整个 agent 还是只屏蔽该 server 的工具？

### 4.7 来源

- [MCP Spec: Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Builder AWS: MCP Transport Mechanisms STDIO vs Streamable HTTP](https://builder.aws.com/content/35A0IphCeLvYzly9Sw40G1dVNzc/mcp-transport-mechanisms-stdio-vs-streamable-http)
- [dasroot: Model Context Protocol Technical Deep Dive](https://dasroot.net/posts/2026/04/model-context-protocol-mcp-technical-deep-dive/)
- [OpenTelemetry: MCP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/mcp/)

---

## 5. 沙箱（Sandbox）

### 5.1 业界共识：Docker 已不够

2026 共识：「**shared-kernel container isolation (Docker/runc) isn't cutting it anymore for executing untrusted AI agent code**」。AWS / Azure / GCP 已悄然把控制平面迁向硬件隔离。

### 5.2 隔离技术对比

| 技术 | 隔离模型 | 启动时间 | 内存开销 | 适用场景 |
|------|---------|---------|---------|---------|
| **Docker (runc)** | 共享 kernel + namespace | ms 级 | 10-50MB | **仅受信内部代码** |
| **gVisor** | 用户空间 syscall 拦截 | 100-200ms | 20-100MB | LLM 生成代码、中等信任 |
| **Firecracker** | 硬件虚拟化 microVM | ~125ms | ~5MB | 不可信代码、最高安全 |
| **Kata** | 完整 microVM + 专用 kernel | 500-1000ms | 50-200MB | 企业多租户 |

### 5.3 资源限制建议

- **CPU**：1-2 核上限，防 logic bomb / 意外 DoS
- **Memory**：512MB-2GB 硬限制 + OOM kill
- **Network**：默认禁用出网；按需开白名单
- **FS**：只读挂载必要路径，挂卷处理大数据
- **进程**：限制 fork 防 fork bomb

### 5.4 启动时间真相

冷启动数字（Firecracker 125ms）不是全部成本——CNI / TAP 网络配置在高并发时可加 263% 开销。生产做法：维护「**预启动池**」（warm pool）摊薄冷启动，但要在「闲置成本」与「冷启动延迟」间取舍。

### 5.5 输出处理

- **stdout/stderr 截断**：首尾各 10KB 防内存爆炸
- **可观测性穿越 VM 边界**：标准 observability 工具进不去隔离环境，需专门链路
- **编码安全**：不可信代码可能输出非 UTF-8 / 控制字符，需 sanitize

### 5.6 攻击向量与缓解

| 攻击 | 缓解 |
|------|------|
| Kernel exploit | Firecracker / Kata（独立 kernel） |
| Syscall 滥用 | gVisor 拦截过滤 |
| 资源耗尽 | cgroup CPU/mem 限制 + 进程限制 |
| 网络透传攻击 | 默认禁出网；MCP 层级权限门 |
| 数据外泄 | 出网限制；机密计算（AMD SEV-SNP / Intel TDX） |

### 5.7 关键注意事项

- **「假设代码是敌对的」**——这是沙箱设计的核心心态
- Docker 适合 fleetent 当前 trusted-tenant 场景，但**需要规划升级路径**（gVisor / Firecracker）
- 资源限制必须**配置可调**，不同 agent / 用户档位不同
- 长时间运行任务需考虑「沙箱续命」（保留状态）vs「每次重建」（牺牲性能换隔离）的取舍
- **多语言支持**：Python 之外是否要 Node/Bash？每种语言一个镜像 vs 通用镜像

### 5.8 来源

- [Manveerc: How to sandbox AI agents in 2026](https://manveerc.substack.com/p/ai-agent-sandboxing-guide)
- [Northflank: How to sandbox AI agents in 2026](https://northflank.com/blog/how-to-sandbox-ai-agents)
- [Firecrawl: AI Agent Sandbox Safe Run Autonomous Agents](https://www.firecrawl.dev/blog/ai-agent-sandbox)
- [Fast.io: 10 Best Code Execution Sandboxes for AI Agents](https://fast.io/resources/best-code-execution-sandboxes-ai-agents/)
- [Codeant: How to Sandbox LLMs & AI Shell Tools](https://www.codeant.ai/blogs/agentic-rag-shell-sandboxing)

---

## 6. 上下文压缩（Context Compaction）

### 6.1 主流策略：anchored iterative summarization（Factory.ai 案例）

> Factory.ai 的方案被多篇评测列为「2025-2026 收敛最优解」之一，方法论清晰。

**双阈值机制**：
- **Tmax**（fill line）：触发压缩的上限
- **Tretained**（drain line）：压缩后保留量目标
- 两者之间留出 bandwidth，控制压缩频率

**核心做法**：维护**持久化摘要**（persistent summary），每次只对「新被截断的那一段」做增量摘要，merge 进持久 summary——避免重摘已压缩内容。

### 6.2 头-尾保留策略

| 区段 | 处理 |
|------|------|
| **头**（system prompt + 首轮交互） | 强制保留 |
| **中** | 持续做摘要 |
| **尾**（最近消息） | 完整保留至 Tretained 容量 |

**保留要素**：
- Session intent（用户最初要做的事）
- High-level progression（请求序列与 agent 动作）
- Artifact trail（创建/修改/删除的文件与关键变更）
- Breadcrumbs（文件路径、函数名、关键标识符，方便 agent 回溯）

### 6.3 Tool calls 完整性（fleetent 既有强约束）

- **tool_use 和 tool_result 必须 1:1 配对**——压缩边界不能切到一对 tool 中间
- fleetent 现有 `_keep_tail` 用 identity check 防误判（CLAUDE.md Gotchas）——这是必须保持的细节
- 截断 tool result 时可保留首尾摘要（如「[truncated 12KB of output]」）

### 6.4 失败模式（Factory.ai 实测踩坑）

- **过度压缩反噬**：摘要掉的 artifact 后续要重新 fetch，**总成本反而升**
- **Tmax 调到顶**：模型在 max context 时性能退化（well-known）
- **Tmax-Tretained 间隔太小**：压缩频繁 → prompt cache 失效 → 延迟+成本暴涨
- **「永久边缘」问题**：一开始压缩就持续运行在 max 附近，质量持续退化

### 6.5 高级方向（暂不引入）

- **KV-level compaction**（MIT/Harvard 2026 Feb）：在 attention 空间压缩，不生成文本——目前 SOTA 但需深度 model 集成
- **Provider-native compaction**（Anthropic compact-2026-01-12 beta）：API 自带压缩
- **proactive memory management**：agent 自主选择压缩时机（任务完成点），而非被动触发

### 6.6 关键注意事项

- **缓存友好**：Anthropic prompt cache TTL 5 分钟，过度压缩会频繁 invalidate——压缩策略要与缓存策略协同
- **压缩用什么模型**：Haiku 类轻量模型够用（fleetent memory_layer 已采此路）
- **压缩的可观测性**：trace 里要记录「这条消息是压缩生成的」+ 原始范围，方便 debug
- **「不压」也是策略**：短会话不要触发；先做截断（drop old tool results）再做摘要——分层
- **fleetent 现状**：已有 in-session 压缩，token 超 80% 阈值触发，`keep_tail` 用 identity check——基础架构在；可补充：双阈值、persistent summary、artifact trail 提取

### 6.7 来源

- [Factory.ai: Compressing Context](https://factory.ai/news/compressing-context)
- [Medium AI Forum: Automatic Context Compression in LLM Agents](https://medium.com/the-ai-forum/automatic-context-compression-in-llm-agents-why-agents-need-to-forget-and-how-to-help-them-do-it-43bff14c341d)
- [Kenhuangus: Context Management at Scale Claude Code vs Hermes](https://kenhuangus.substack.com/p/chapter-6-context-management-at-scale)
- [Zylos: AI Agent Context Compression Strategies](https://zylos.ai/research/2026-02-28-ai-agent-context-compression-strategies)
- [Microsoft Learn: Compaction](https://learn.microsoft.com/en-us/agent-framework/agents/conversations/compaction)
- [arXiv 2511.08128: Sentence-Anchored Gist Compression](https://arxiv.org/pdf/2511.08128)

---

## 7. 横切关注点（cross-cutting concerns）

调研过程中反复出现，但不归属任何单一模块——必须在能力清单里独立成章：

### 7.1 Trajectory / Trace
- LangChain 2026 强调：「The Agent Improvement Loop Starts with a Trace」
- 每个工具调用、模型调用、压缩动作、审批事件都必须写 trace
- 用于：eval、debug、cost 归因、合规审计

### 7.2 审批门（permission gate）
- 与工具的 `risk_level` 联动
- 调研结论：human-in-the-loop 已是 2026 标配，非 optional
- 实现层面：异步 Event 优于轮询（fleetent 现做法）

### 7.3 成本预算（cost budget）
- per-session token cap / per-user 美元 cap / per-tool 调用次数
- 超限时优雅降级而非硬中断

### 7.4 错误分类（error classification）
- hermes 的 `error_classifier.py` 是一个范例
- 三类：transient（重试）/ permanent（降级）/ user-fault（不重试，反馈）

### 7.5 取消与超时（cancellation & timeout）
- 多层超时：单次 LLM 调用 / 单次工具调用 / 单轮循环 / 整个 session
- 取消信号传播：cancel 信号要能穿透到沙箱、MCP server

### 7.6 可观测性穿透沙箱
- 沙箱执行的 stdout/stderr/exit_code 要能进 trace
- MCP 调用要能 trace 到具体 server + tool + latency

---

## 8. 框架对比（LangChain / LlamaIndex / LangGraph，仅参考勿用）

CLAUDE.md 明确禁用——但了解它们解决了什么问题对设计有帮助。

| 框架 | 优势 | 我们不用的原因 |
|------|------|---------------|
| **LangChain** | 工具/链/记忆抽象齐全 | 频繁 breaking change；抽象过厚 debug 难 |
| **LangGraph** | 状态机式 agent 编排；checkpoint | 引入 graph DSL；对模块化单体过重 |
| **LlamaIndex** | RAG 工具链强；data connector 多 | 偏 RAG 不偏 agent；与本项目领域错位 |

**借鉴点**（不引入但参考）：
- LangGraph 的 **checkpoint** 思想：循环每轮可序列化暂停，值得在自研 trace 中体现
- LangChain 的 **tool result schema**：StructuredTool / ToolException 的区分模式
- LlamaIndex 的 **callback handler** 钩子点：trace 注入点的灵感

---

## 9. 调研结论摘要（给阶段 3 用）

**6 个模块各自必须包含的子能力（来自调研）**：

1. **核心循环**：循环执行 / fallback 路由 / 流式与同步双 API / 取消与超时 / 循环检测 / cost 预算 / checkpoint
2. **工具**：注册与 schema 推导 / 命名规范 / 描述质量 / 错误返回风格 / 结果格式化 / 风险分级 / 白名单 / 超时
3. **Skill**：渐进式披露 3 层 / 元数据扫描 / SKILL.md 加载 / 引用文件 lazy load / 多 skill 共存 / 信任与审计
4. **MCP**：stdio transport / Streamable HTTP transport / session 管理 / 可恢复流 / Origin 校验 / OAuth / 健康检查 / 命名空间
5. **沙箱**：隔离档位（Docker/gVisor/Firecracker）/ 资源限制可配置 / 输出截断 / warm pool / 多语言 / 可观测性穿透
6. **上下文压缩**：双阈值 Tmax/Tretained / head-middle-tail 分层 / persistent summary 增量更新 / artifact trail 提取 / tool pair 完整性 / 缓存友好

**横切关注点**：trace、审批门、cost 预算、错误分类、取消传播、沙箱可观测性

**关键设计决策点（需在阶段 3 design.md 中讨论）**：
- Skill 是否引入 progressive disclosure（架构改造）
- 沙箱是否规划 Docker → gVisor 升级路径
- 压缩是否升级到 Factory.ai 式双阈值 + persistent summary
- 工具是否支持 `response_format` enum 参数
- MCP 是否同时支持新旧两套 transport
