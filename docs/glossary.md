# 术语表

fleetent 平台全局术语定义。所有模块文档应以本表为准，避免同义词混用。

---

## 平台核心

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **tenant** | 平台上的一个企业客户，拥有独立的用户体系、agent 配置和知识库 | 不用 "organization"、"company" |
| **agent** | 由 system_prompt、allowed_tools 和 skill 组成的 LLM 实例配置，代表一个业务角色（如 HR 助手、代码审查机器人） | 不用 "bot"（bot 特指 IM 平台上的账号）|
| **agent_loop** | agent 的核心执行引擎：接收输入 → LLM 调用 → 工具执行 → 迭代，直到终止条件 | 不用 "run loop"、"execution cycle" |
| **scope** | 数据隔离的粒度标识，可以是 `tenant_id` 或 `agent_id`，用于区分不同租户或不同 agent 的数据 | 不用 "namespace"（namespace 专指 vector_store 内部的分区）|
| **principal** | 认证完成后贯穿 agent 运行时的身份抽象，携带 `user_id`、`tenant_id`、`agent_name` 等字段。由认证边界（bearer token 解析 / IM 渠道担保）构造，核心模块只消费 Principal，不直接处理认证逻辑 | 不用 "user"（user 是存储层实体，principal 是运行时身份令牌）|
| **node** | `fleetent node start` 进程，负责在某台宿主机上运行和管理一批 agent。轮询平台 `GET /nodes/{id}/desired-state` 获取期望列表，通过 spawn/stop 启停 `fleetent agent run` 子进程，并经 `POST /nodes/{id}/status` 上报实际运行态；注册信息存 `nodes` 表，以 `ma-<hex>` service key 鉴权。单机部署时，platform + node + agent 也可以同机，node 仍是唯一 launcher | 不用 "worker"、"host" |
| **materialize** | 平台将管理库中的 agent 定义、绑定和配置**单向刷写**为 agent 侧 `agent.yaml` 文件的操作，触发于 create / update / apply / clone 等变更后。agent 运行时只读自己的 `agent.yaml`，不查 platform DB（零 platform 依赖契约的执行点） | 不用 "sync"（暗示双向）、"deploy"（指发布上线，materialize 是配置刷写）|

---

## 会话与消息

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **session** | 一次完整的对话上下文，包含完整的消息历史，持久化为 `sessions/{session_id}.json`。session 是逻辑概念，跨越多条消息 | 不用 "conversation"（过于宽泛）|
| **thread** | IM 平台（如 Slack）的原生消息线程，是 session 的物理载体之一。一个 thread 对应一个 session | 不用 "channel thread"，容易与 channel 混淆 |
| **channel** | IM 平台上的频道或聊天窗口（Slack channel、Telegram chat），是消息的发送场所，一个 channel 可以有多个 thread | 保持原词 |
| **session_id** | session 的唯一标识，带平台前缀，由各 IM 适配器的 `_derive_session_id()` 构造。例如：`slack:dm:{user_id}:{thread_root}`（私信）、`slack:thread:{channel_id}:{thread_root}`（频道线程）；CLI 会话使用简单 UUID。 | 不用 "conversation_id"、"chat_id" |
| **platform** | 接入层的 IM 平台，如 `slack`、`telegram`、`whatsapp`。与 `fleetent 平台`（指本产品）区分，后者用 "系统" 或全称 | 消息上下文中保持原词 |

---

## Agent 与技能

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **skill** | 可复用的行为模式描述，存储为 `skills/` 目录下的包（含 `SKILL.md` + 可选脚本/资源）。平时以 **catalog**（名称 + 描述）形式出现在 system prompt，agent 按需调 `read_skill(name)` 加载全文；告诉 agent"怎么做某类任务" | 不用 "prompt template"、"behavior"（过于宽泛）|
| **skill_path** | skill 在 `skills/` 目录下的相对路径，如 `summarizer` 或 `tools/code_runner`，用于物理定位（文件系统相对路径），不是唯一标识符。skill 的唯一标识是 `name`（`skills` 表的 PK）。 | 不用 "skill_path 作为唯一标识符"（`name` 才是 PK）|
| **skill 注入（read-on-demand）** | 模型按需加载 skill 全文的机制：启动时 system prompt 只含 **catalog**（每个合格 skill 的 `name/description/location`）；模型决定使用某 skill 时调用 `read_skill(name)` 工具，运行时即时注入全文。旧的关键词自动匹配路径（`match()`）是 legacy，不再使用。 | 不用 "skill 激活"；"skill 加载"仅限描述 `read_skill` 工具调用本身 |
| **snapshot** | skill 变更提案中对整个 skill 目录的完整文件快照，格式为 `{"files": {"rel_path": "content", ...}}`。delete 提案的 snapshot 为 null | 不用 "diff"（snapshot 是全量，不是增量）|

---

## 工具与权限

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **tool** | 注册在 `tool_registry` 中的可调用函数，agent_loop 通过 LLM 的 function calling 触发 | 不用 "function"（function 是代码概念，tool 是业务概念）|
| **tool 调用** | agent_loop 执行一次 tool 的完整过程：LLM 输出 tool_call → dispatch → 执行 → 返回结果 | 统一用"调用"，不用 "dispatch"、"invoke"、"execute"（这三个是调用链内部的动词，对外统称"调用"）|
| **dispatch** | `tool_registry` 内部根据 tool_name 找到对应函数并执行的步骤，是 tool 调用链的内部环节 | 仅在 tool_registry 实现相关的上下文使用 |
| **allowed_tools** | agent 配置中的工具白名单，使用 fnmatch 语法，如 `read_*`、`web_search`。agent 只能调用白名单内的工具 | 不用 "tool_whitelist"、"permitted_tools" |
| **permission_gate** | 针对 medium/high 风险工具调用的人工审批门，当前实现位置为 `fleetent.governance.permission_gate`，通过 asyncio.Event 实现阻塞等待 | 不用 "approval gate"、"human-in-the-loop"（后者范围更广）|
| **风险等级** | 工具的操作风险分类：`low`（只读）、`medium`（可撤销写入）、`high`（不可逆操作）。medium/high 需要 `fleetent.governance.permission_gate` 审批 | 保持 low/medium/high 三级，不用 "safe/unsafe" |

---

## 记忆系统

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **语义记忆** | 跨 session 的用户事实，按 `identity`/`preferences`/`context` 三类结构化存储于 `memory_items` 表，由 `fleetent.memory` 负责 | 不用 "semantic memory"（英文只在代码注释中使用）|
| **情节记忆** | 对话与工具执行的完整历史轨迹，写入 `traces` 表，由 `observability` 负责 | 不用 "episodic memory"、"execution log"（traces 是正式名词）|
| **程序记忆** | agent 完成特定任务的技能与方法，存储为 `skills/` 目录，由 `skill_registry` 负责 | 不用 "procedural memory"、"knowledge"（knowledge 指企业文档知识库）|
| **工作记忆** | 当前 session 的对话上下文，存储在内存中，session 结束即释放，由 `runtime.context` 负责（`context_mgr` 是遗留 re-export shim，`monkeypatch` 等须指真实模块 `fleetent.runtime.context`）| 不用 "working memory"、"context window"（context window 是 LLM 的技术概念）|
| **identity** | 语义记忆子类型：用户的身份事实（姓名、职位、技能），永久有效，新值覆盖旧值 | 保持英文，与代码 type 字段对齐 |
| **preferences** | 语义记忆子类型：用户的工作偏好（风格、输出格式），长期有效；需区分明确陈述（更新记忆）和一次性请求（不更新）| 保持英文，与代码 type 字段对齐 |
| **context** | 语义记忆子类型：用户的临时状态（当前项目、进行中任务），TTL 30 天，过期自动失效 | 保持英文，与代码 type 字段对齐。注意与"上下文（context window）"区分 |
| **TTL** | Time To Live，记忆条目的有效期。`context` 类记忆默认 TTL 30 天，`identity`/`preferences` 无 TTL | 保持缩写，不用"有效期"（有混淆时可括号注明）|

---

## 知识库

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **knowledge base（KB）** | 企业文档知识库，按 `tenant_id + kb_id` 隔离，由 `knowledge_base` 模块管理。与用户个人的语义记忆并列，由 `long_term_ctx` 统一调度注入 | 不用 "knowledge"（单独使用时过于宽泛）、"RAG 知识库"（RAG 是技术手段，不是业务概念）|
| **chunk** | 文档分块后的最小检索单元，保留来源文档信息（filename、position）| 保持英文，与代码字段对齐 |
| **entity** | 从文档中 LLM 提取的命名实体（人名、组织、概念、产品等），用于图增强检索 | 保持英文 |
| **relation** | 两个 entity 之间的关系描述，从文档中 LLM 提取，存储为有向边 | 保持英文 |
| **connector（KB 数据源）** | KB 数据源连接器，实现 `DataSource` 接口，负责从外部系统（Confluence、Google Drive、本地目录等）拉取文档并写入知识库。当前仍使用 connector 命名（`knowledge_base/connectors/`）。 | 不用 "adapter"、"integration" |
| **external service / external_services** | 工具级外部服务授权体系（OAuth2 / API-key），由 `platform/connector_management/` 管理。凭证存储在 `external_credentials`，授权关系存储在 `agent_service_grants`。旧称"工具 OAuth connector"，已重设计为 Vault 体系，不再使用 connector 一词。 | 不用 "connector"（工具 OAuth 语境下已废弃）|
| **[废弃] IM connector** | IM 渠道接入的旧称，v1 阶段 4 正式废弃，改称 im（ImAccess / ImBinding）。 | 不用 "connector"（IM 语境下已废弃）|
| **ingest** | 将文档导入知识库的过程：解析 → 分块 → embedding / 索引写入；图提取属于后续 graph search 阶段 | 不用 "import"、"upload"（upload 特指文件直传这一种 ingest 方式）|

---

## 检索技术

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **向量检索** | 基于 embedding 相似度的语义检索，擅长同义词、语义相近的查询 | 不用 "语义检索"（语义检索是目的，向量是技术手段；两者在本项目中等价，统一用"向量检索"）|
| **BM25 检索** | 基于词频的关键词检索，擅长精确词匹配（产品编号、人名、专有名词），当前实现使用 SQLite FTS5 | 不用 "全文检索"（全文检索包含多种算法，BM25 是具体算法）|
| **混合检索（Hybrid Search）** | BM25 和向量检索并行执行，通过 RRF 融合排序后返回结果 | 不用 "hybrid retrieval" |
| **RRF** | Reciprocal Rank Fusion，将多路检索结果按倒数排名融合的算法，无需人工调节权重 | 保持缩写 |
| **图增强检索** | 从匹配实体出发，按关系图谱展开，收集关联 chunk，适合关系型查询（"谁负责 X？"）| 不用 "graph RAG"、"knowledge graph search" |
| **namespace** | vector_store 内部的向量分区标识，格式为 `mem:{user_id}`（记忆向量）或 `kb:{tenant_id}:{kb_id}`（知识库向量）。不同 namespace 的向量物理隔离，检索不跨 namespace | 不用 "scope"（scope 是业务层概念，namespace 是 vector_store 内部概念）|

---

## 失败处理

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **fallback** | 主路径不可用时自动切换到备用路径的机制。特指 model_router 的 LLM provider fallback 链 | 仅用于 LLM provider 切换场景 |
| **降级** | 某能力不可用时以有限功能继续服务的策略，如 knowledge_base 无结果时 long_term_ctx 仍正常返回 memory 内容 | 不用 "degradation"（英文留在代码注释）、"fallback"（fallback 特指 provider 切换）|
| **重试** | 同一操作失败后按策略重新执行，通常含退避逻辑（backoff） | 不用 "retry"（英文留在代码注释）|

---

## 存储与数据

| 术语 | 定义 | 禁止混用 |
|------|------|---------|
| **trace** | 一次完整 agent 运行的记录，包含 user_id、agent_name、消息列表、工具调用、token 用量、耗时等，append-only 写入 `traces` 表 | 不用 "log"（log 是系统日志，trace 是业务执行记录）、"history" |
| **vector_store** | 统一的向量索引基础设施，提供 upsert/search/delete 接口；当前支持 in-memory 与普通 SQLite persistent backend，后续可扩展 sqlite-vec / Qdrant | 不用 "向量数据库"（向量数据库是后端实现，vector_store 是抽象层）|
| **embedding** | 将文本转换为向量的过程，或指转换后的向量本身。当前支持 deterministic 测试 provider 与 OpenAI-style HTTP provider；生产默认应指向自托管模型服务 | 保持英文，与行业通用用法一致 |

---

> 本表持续更新。新增术语 PR 时，如引入新概念请同步在此补充定义。
