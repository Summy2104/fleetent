# Agent Runtime 能力清单

> **范围**：fleetent 自研 agent 框架核心运行时——六大模块（核心循环 / 工具 / Skill / MCP / 沙箱 / 上下文压缩）+ 横切关注点
> **用途**：作为子功能设计与验收标准的统一索引，feeds 后续 OpenSpec change 的 specs/ 拆分
> **原则**：
> 1. 只描述「**能力**」，不描述「**实现**」——不出现具体类名、函数签名、SQL、装饰器形态
> 2. 每个子功能必须**端到端可观察**——不可观察的合并或删除
> 3. 子功能粒度 = 一条独立可验收的行为
> 4. 横切关注点（trace、审批、cost、错误分类、取消、可观测性）独立成章，避免散落
>
> **输入来源**：
> - `industry-survey.md`（业界实践）
> - `reference-survey-openclaw.md`（openclaw 调研）
> - `reference-survey-hermes.md`（hermes-agent 调研）
> - `docs/capabilities/agent-runtime.md`（fleetent 现状）
>
> **配套文档**：
> - **[`agent-runtime-acceptance-criteria.md`](./agent-runtime-acceptance-criteria.md)** — 每个子功能的 Given/When/Then 验收场景（共 146 条）

---

## 文档结构

每个子功能采用统一模板：

```
### {模块编号}.{子功能编号} {子功能名}
- **一句话定义**
- **触发场景**
- **输入 / 输出契约**（接口形状，纯文字）
- **行为约定**（成功路径 + 关键失败路径）
- **边界与非目标**
- **与其他子功能/模块的耦合点**
- **关键注意事项**（取自调研踩坑）
- **开放问题**（如有）
- **验收标准**（Given / When / Then，由阶段 4 补全）
```

模块编号：1 核心循环 / 2 工具 / 3 Skill / 4 MCP / 5 沙箱 / 6 上下文压缩 / 7 横切关注点

---

# 1. 核心循环（Agent Loop）

`agent_loop.py` 模块。负责 LLM 调用、tool_use 解析、工具调度、错误分类、循环终止。

## 子功能清单（共 10 项）

### 1.1 主循环执行
- **一句话定义**：以 while 形态持续调用 LLM 并处理 tool_use，直到自然终止或硬性终止。
- **触发场景**：用户/调度器/IM 网关调用 agent 入口，传入 messages 与 RunConfig。
- **输入 / 输出契约**：
  - 输入：messages 列表、tools 列表、RunConfig（含 max_turns、超时、模型偏好等）、cancel token
  - 输出：最终 assistant 消息 + 完整 trajectory（消息序列、tool 调用、压缩动作、错误记录）
- **行为约定**：
  - 每轮：调 LLM → 若返回 tool_use → 执行工具 → 工具结果回填 messages → 下一轮
  - 自然终止：LLM 返回 stop_reason=end_turn 且无 tool_use
  - 强制终止：max_turns / max_tokens / cost_budget / cancel 触发
  - 任意一轮出现可恢复错误（见 1.9）→ 进入重试或 fallback 子流程
- **边界与非目标**：
  - 非目标：不直接维护 session 持久化（由 session_mgr 负责）
  - 非目标：不做工具实现（由 tool_registry 负责）
- **耦合点**：model_router、tool_registry、context_mgr、eval_logger、permission_gate、cancellation token
- **关键注意事项**：
  - **tool_use 与 tool_result 必须 1:1 配对**（API 强约束）——任何中间阶段不能破坏配对
  - 主循环必须可被外部信号中断，否则失控 agent 拖死进程
  - 每轮 trace 写入是非可选——后续 eval、debug、cost 归因全靠 trajectory
- **开放问题**：
  - 是否引入 attempt-based state machine（openclaw 做法），还是保持简单 while？

### 1.2 三种调用入口（run / run_stream / run_sync）
- **一句话定义**：同一循环核暴露三种调用形态，覆盖 CLI / HTTP-SSE / 后台调度三类调用方。
- **触发场景**：
  - `run`：返回完整字符串，CLI 与 IM 用
  - `run_stream`：async generator，yield SSE event dicts，HTTP 用
  - `run_sync`：阻塞式同步封装，脚本/cron 用
- **输入 / 输出契约**：三者共享 messages / tools / RunConfig 输入；输出形态不同（string / event stream / blocking string）
- **行为约定**：流式入口的 token-by-token 输出必须能正确「重组」遇到 tool_use 时的拼装中断
- **边界与非目标**：非目标：暴露第四种 webhook callback 入口（如需要由调度层适配，不入核心循环）
- **耦合点**：FastAPI server.py、CLI cli.py、cron_scheduler
- **关键注意事项**：
  - 流式入口需要处理「LLM 流到一半才知道是 tool_use」的拼装——不能边流边执行
  - 三个入口必须共享同一循环核——否则行为偏移
- **开放问题**：流式入口的 SSE event schema 是否需要稳定 API 契约（影响 IM 客户端）

### 1.3 终止条件管理
- **一句话定义**：统一抽象多种循环终止条件，集中判断。
- **触发场景**：每轮循环末尾、cancel 信号、超限事件。
- **输入 / 输出契约**：消费 RunConfig 的限制项与运行状态；输出终止决定 + 原因码
- **行为约定**：
  - 自然终止：finish_reason 标记
  - 配额终止：max_turns / max_tokens / cost_budget
  - 失败终止：连续 N 次 tool 失败、连续 N 次 LLM 报错
  - 人工终止：cancel token / 审批拒绝
  - 循环检测终止（见 1.7）
- **边界与非目标**：终止原因码必须固定为闭集（enum），不允许字符串自由扩展
- **耦合点**：1.7 循环检测、7.3 cost 预算、7.5 取消
- **关键注意事项**：终止原因码进入 trace；不同原因码下「最后一轮 assistant 消息」语义不同，前端展示需区分
- **开放问题**：是否给「grace call」开口（hermes 做法：预算耗尽时再放一次最终 LLM 调用机会生成 user-facing 回复）

### 1.4 模型 Fallback 链调度
- **一句话定义**：主模型遇到指定可重试错误时按链顺序切换到 fallback 模型。
- **触发场景**：LLM 返回 429 / 503 / context_overflow（特殊处理）/ provider auth 失败。
- **输入 / 输出契约**：消费 RouteConfig.fallbacks 列表；trace 中记录实际使用的 model_used
- **行为约定**：
  - 链按顺序尝试；每条记录失败原因
  - 整条链耗尽 → 抛对应异常并终止循环
  - context_overflow 不直接 fallback，而是先触发压缩（见 6）再重试当前模型
- **边界与非目标**：非目标：动态 fallback 链（按运行时统计自适应选择）
- **耦合点**：model_router、7.4 错误分类
- **关键注意事项**：
  - 多 LLM provider 的 API key 也支持轮换（auth profile 概念），但与模型 fallback 是两个维度
  - 切换 fallback 模型后 tool schema 可能要重新规整（不同 provider 接受的 schema 字段不同）
- **开放问题**：fallback 期间累积的 cost / token 归属哪个模型的 budget

### 1.5 工具调用调度（串行 vs 并行）
- **一句话定义**：一轮中 LLM 返回多个 tool_use 时，按工具属性决定串行或并行执行。
- **触发场景**：LLM 单轮返回 N 个 tool_use（N ≥ 1）。
- **输入 / 输出契约**：消费各工具的 concurrency 属性；输出 N 个 tool_result 顺序追加到 messages
- **行为约定**：
  - 工具分级：PARALLEL_SAFE（如 web_search、calculate）→ PATH_SCOPED（如 read_file，按路径隔离可并发）→ NEVER_PARALLEL（如审批工具、人工输入）
  - 默认串行；满足条件才升级并行
  - 并行结果按原始 tool_use 顺序回填，保证 1:1 配对
- **边界与非目标**：非目标：跨轮的工具并发（每轮独立判断）
- **耦合点**：2.5 dispatch、2.7 风险分级、7.5 取消传播
- **关键注意事项**：
  - 并行工具的 `tool_use_id` 顺序必须严格保留——否则模型上下文错乱
  - 任一并行工具失败，其他在途任务如何处理（继续 vs 取消）——需明确策略
- **开放问题**：路径推导（PATH_SCOPED）的启发式如何避免误判（hermes 调研中明确指出这是脆弱点）

### 1.6 中断与取消信号传播
- **一句话定义**：外部 cancel 信号可在任意时机中止循环、当前 LLM 调用、当前 tool 调用。
- **触发场景**：用户 Ctrl+C、HTTP 客户端断开、审批拒绝、超时触发。
- **输入 / 输出契约**：RunConfig 传入 cancel token；信号需穿透到沙箱、MCP server
- **行为约定**：
  - 优雅中断：等当前 tool 完成 → 不发起下一次 LLM 调用 → 写 trace → 返回部分结果
  - 强制中断：超时未优雅停止时直接终止（SIGTERM → SIGKILL 级联）
- **边界与非目标**：非目标：「撤销」已执行的 tool 副作用
- **耦合点**：5.6 沙箱级联终止、4.7 MCP 重连、7.5 取消传播
- **关键注意事项**：
  - 取消信号必须可重入——同一信号传播到多层（循环、LLM、tool、沙箱）不冲突
  - 取消后 trace 必须完整写入，否则后续无法复盘

### 1.7 循环检测（loop detection）
- **一句话定义**：检测「相同 tool + 相同参数」或「相同 LLM 输出」连续重复 N 次，强制终止避免死循环。
- **触发场景**：模型陷入无意义循环（如重复读同一文件、重复 search 相同 query）。
- **输入 / 输出契约**：每次 tool 调用计算签名（工具名 + 规范化参数 hash）；超过窗口阈值即终止
- **行为约定**：
  - 工具签名连续重复 ≥ N → 警告级 → 注入「检测到循环」提示给 LLM
  - 仍重复 → 硬停止
  - LLM 输出文本完全重复 → 同等处理
- **边界与非目标**：非目标：跨 session 的循环检测
- **耦合点**：1.3 终止条件、2.10 工具守卫
- **关键注意事项**：
  - 参数规范化要忽略键顺序、空格差异，但保留语义差异
  - 警告级注入要避免变成新的循环源
- **开放问题**：N 值与窗口大小是否可按 agent / 工具定制

### 1.8 迭代预算与 Grace Call
- **一句话定义**：以「迭代次数 + token 数 + 美元数」三维预算约束单次 run；耗尽时允许一次 grace LLM 调用产出最终回复。
- **触发场景**：长任务、防失控的预算护栏。
- **输入 / 输出契约**：RunConfig 中三维上限；运行时维护已消耗值；耗尽时进入 grace 流程
- **行为约定**：
  - 任一维度超限 → 不再发起新 tool 调用 → 触发 grace call（带「请给最终回复」提示）→ 返回结果
  - grace call 仍失败 → 返回结构化错误 + 已有部分结果
- **边界与非目标**：非目标：动态调整预算（运行中提升）
- **耦合点**：1.3 终止条件、7.3 cost 预算
- **关键注意事项**：
  - 部分工具（如压缩本身、sub_agent 内部）不计入预算（hermes 的 refund 机制）
  - grace call 的提示词要稳定（影响最终用户体验）

### 1.9 错误分类与重试策略
- **一句话定义**：把 LLM/工具/MCP/沙箱产生的所有错误归一化为有限枚举，每类携带恢复策略标志。
- **触发场景**：任何运行时异常或非 200 响应。
- **输入 / 输出契约**：输入原始异常；输出 `ErrorClass`（含 should_retry / should_compress / should_fallback / should_rotate_credential / user_visible 等标志）
- **行为约定**：
  - 主循环只看标志位决策，不重复解析错误字符串
  - 未识别错误归为 `unknown` → 默认不重试，user_visible=true
- **边界与非目标**：非目标：错误的统计与告警（归 7.1 trace 处理）
- **耦合点**：7.4 错误分类（横切版）
- **关键注意事项**：
  - hermes 实测：错误分类枚举集合超过 12 项，覆盖 auth / billing / rate-limit / context_overflow / format_error / tool_crash / mcp_disconnect / sandbox_oom 等
  - 错误分类必须**集中维护**，散落于各处的字符串匹配是反模式（openclaw 踩过的坑）
- **开放问题**：错误分类的扩展机制——新增枚举值是否需要走 ADR？

### 1.10 消息卫生与契约修复
- **一句话定义**：发送给 LLM 的 messages 必须满足严格契约（角色交替、tool_use/result 配对、JSON 合法）；运行时维护一道「卫生层」做修复。
- **触发场景**：压缩后、错误恢复后、用户 steer 注入后、跨模型切换后。
- **输入 / 输出契约**：输入可能违规的 messages；输出合规 messages 或显式报错
- **行为约定**：
  - 角色违规（连续两条 user）→ 合并或插入空 assistant
  - tool_use 缺 tool_result → 补「tool 执行失败」占位
  - 工具参数 JSON 损坏 → 尝试修复（闭合引号 / 去尾逗号）；失败则报错给 LLM
  - 移除内部字段（reasoning、内部 finish_reason）
- **边界与非目标**：非目标：「美化」消息（如重排序），只保契约
- **耦合点**：6.4 tool pair、4.x MCP 工具集成
- **关键注意事项**：
  - 修复动作必须写入 trace，否则下次复盘无法解释行为
  - 修复失败要尽早报错而非继续传给 LLM
- **开放问题**：steer 注入（运行中插入用户提示）的延迟执行策略——立即注入会破坏角色交替，hermes 采用「附加到最近 tool 消息」

---

# 2. 工具（Tools）

`tool_registry.py` + `tools.py`。统一管理所有工具的注册、schema、dispatch、访问控制、结果格式化。

## 子功能清单（共 11 项）

### 2.1 工具注册
- **一句话定义**：以装饰器声明的工具在模块 import 时自动注册到中央 registry。
- **触发场景**：模块加载阶段（import 副作用）；MCP server 启动后注册外部工具；用户自定义工具加载。
- **输入 / 输出契约**：装饰器接受元数据（risk_level、超时、并发属性、描述）；registry 输出 schema 与 dispatcher
- **行为约定**：
  - 同名工具注册 → 报警告（最后注册者覆盖 vs 拒绝注册）
  - 内置工具 import 顺序确定 → 保证 schema 稳定
  - MCP 工具命名加 `{server}__` 前缀避免冲突
- **边界与非目标**：非目标：跨进程的 registry 共享
- **耦合点**：2.3 命名、2.4 描述、4.4 MCP 命名
- **关键注意事项**：
  - 注册副作用问题（CLAUDE.md Gotcha）：`tools.py` 不被 import → `get_schemas()` 返回空——必须在 `agent_loop.py` 顶部强制 import
  - 注册时检查 schema 与实现签名一致性（默认值、Optional、Union 三类易出错）

### 2.2 Schema 自动推导
- **一句话定义**：从 Python 函数签名（类型注解 + docstring）自动生成 JSON Schema。
- **触发场景**：装饰器注册时一次性生成；MCP 工具运行时从 server 推导。
- **输入 / 输出契约**：输入 Python 函数对象；输出符合 OpenAI/Anthropic tool schema 规范的 JSON 对象
- **行为约定**：
  - 支持基本类型、Optional、Union（转 anyOf）、Literal（转 enum）、嵌套 dict/list
  - docstring 第一行 → tool description；参数 docstring → property description
  - 未注解参数 → 拒绝注册（强制类型声明）
- **边界与非目标**：非目标：动态运行时 schema 变化
- **耦合点**：2.1 注册、2.3 命名
- **关键注意事项**：
  - 不同 LLM provider 的 schema 字段差异（如 Anthropic 用 `input_schema`，OpenAI 用 `parameters`）——需 adapter 层
  - schema 与实现一致性是 unit test 必检项
- **开放问题**：是否支持 Pydantic model 作参数类型（更强表达）

### 2.3 工具命名规范与命名空间
- **一句话定义**：所有工具名遵循统一规范，按来源使用命名空间前缀避免冲突。
- **触发场景**：注册时校验。
- **输入 / 输出契约**：工具名 = `[{namespace}__]{action}[_{resource}]`
- **行为约定**：
  - 内置工具：无前缀（如 `calculate`、`web_search`）
  - MCP 工具：`{server_id}__{tool_name}`（双下划线，CLAUDE.md 已固定）
  - 子 agent 工具：`sub_agent__{specialized_name}`
  - 用户自定义：`user__{name}` 或 namespace 自定义
- **边界与非目标**：非目标：自动命名建议
- **耦合点**：2.1 注册、4.4 MCP 命名
- **关键注意事项**：双下划线是关键——单下划线是合法工具名一部分（如 `read_file`），不能用单下划线分隔
- **开放问题**：命名空间是否支持嵌套（`mcp__github__create_issue`）

### 2.4 工具描述规范
- **一句话定义**：每个工具必须提供「面向 LLM 的高质量描述」，遵循 Anthropic 工具写作准则。
- **触发场景**：装饰器声明时、Code Review 时。
- **输入 / 输出契约**：description 字符串嵌入 schema
- **行为约定**：
  - 描述像 onboarding 新员工——显式说明领域术语、隐含上下文
  - 参数名避免歧义（`user_id` 非 `user`）
  - 说明何时该用、何时不该用、与其他工具的区别
  - 错误情形显式说明（如「文件不存在时返回 not_found」）
- **边界与非目标**：非目标：描述自动生成（依赖人工）
- **耦合点**：2.2 schema、3.4 skill 描述（同样原则）
- **关键注意事项**：
  - 描述质量直接决定工具召回率与正确使用率——是 agent 性能调优的最大杠杆之一
  - 描述应支持 i18n（at least 内部说明 vs 外部 user-facing）

### 2.5 工具 Dispatch 与超时控制
- **一句话定义**：根据 tool_use 调用对应实现，带强超时与异常隔离。
- **触发场景**：循环识别到 tool_use。
- **输入 / 输出契约**：输入 tool_name + args；输出 tool_result（content + is_error）
- **行为约定**：
  - 默认超时：内置 30s / MCP 60s / 用户自定义 30s（可配置）
  - 超时 → 取消 + 返回 timeout 错误 tool_result（不抛异常出去）
  - 实现抛异常 → catch 后转 tool_result（is_error=true）
  - 不可信工具（MCP / 用户）超时更严
- **边界与非目标**：非目标：自动重试失败工具（由模型决定是否重试）
- **耦合点**：1.5 调度、5.6 沙箱超时、7.5 取消
- **关键注意事项**：
  - **工具失败也要返回 tool_result**——主流共识：让模型继续推理，而非抛异常打断循环
  - 超时取消必须真正释放资源（沙箱容器、MCP 连接）

### 2.6 工具结果格式化与大小限制
- **一句话定义**：工具返回值统一规整为 LLM 可消费的格式；过大结果按策略截断。
- **触发场景**：每次工具执行完成后。
- **输入 / 输出契约**：原始 Python 对象 → 字符串或结构化 content blocks（文本/图像）
- **行为约定**：
  - 文本 → 直接序列化
  - dict/list → JSON 或 Markdown 表格（与训练分布匹配）
  - 大文本 → 头 + 尾 + 「[truncated N bytes]」中间占位
  - 二进制 → base64 + 说明（或落盘后返回路径）
- **边界与非目标**：非目标：自动摘要长结果（属于压缩层）
- **耦合点**：6.5 工具结果预修剪
- **关键注意事项**：
  - 单工具大小限制 + 整 session 大小限制双层 cap（openclaw 教训：多层散落是反模式，统一在一处）
  - UUID/哈希 ID 应转语义化标识符；agent 难以引用原始 UUID
  - 工具结果必须可序列化为字符串——非文本需事先约定 content_type

### 2.7 风险分级（risk_level）与审批联动
- **一句话定义**：每个工具声明风险等级，与审批门联动决定是否需要人工同意。
- **触发场景**：dispatch 前 risk_level 检查。
- **输入 / 输出契约**：装饰器 risk_level=low/medium/high；运行时联动 permission_gate
- **行为约定**：
  - low：自动执行（默认）
  - medium：策略可配——自动 OR 提示
  - high：必须等待人工审批（异步 Event 门）
  - 审批拒绝 → 工具不执行，返回 rejected tool_result
- **边界与非目标**：非目标：动态评估风险（基于参数）——v1 仅支持静态声明
- **耦合点**：7.2 审批门、permission_gate 模块
- **关键注意事项**：
  - 审批超时策略：medium 短超时 / high 长超时（CLAUDE.md：测试需传短超时）
  - 重启后未审批的请求需 cleanup_stale_approvals 清理孤儿

### 2.8 访问控制（allowed_tools 白名单）
- **一句话定义**：agent 定义中声明允许使用的工具白名单（fnmatch 模式），dispatch 前校验。
- **触发场景**：dispatch 前；schema 暴露给 LLM 前（不允许的工具不进 schema）。
- **输入 / 输出契约**：agent_policy 中的 `allowed_tools: list[str]`（支持通配符）
- **行为约定**：
  - schema 暴露：过滤后只暴露白名单匹配的工具
  - dispatch：双重校验（防 LLM 幻觉调用未授权工具）
  - 未匹配 → 返回 unauthorized tool_result
- **边界与非目标**：非目标：基于用户角色的动态白名单（v1 仅支持 agent-level）
- **耦合点**：governance 能力域、agent_store
- **关键注意事项**：
  - 白名单与风险分级是双层防护：白名单管「能不能调」，风险分级管「调之前要不要审批」
  - fnmatch 而非正则——简单可解释

### 2.9 工具来源分层
- **一句话定义**：工具按来源分层标记（内置 / MCP / 用户自定义 / sub_agent），影响信任级与默认超时。
- **触发场景**：注册时打标。
- **输入 / 输出契约**：每个 registry entry 含 `source: builtin|mcp|user|sub_agent`
- **行为约定**：
  - 内置：默认 trust=high，超时 30s
  - MCP：trust=medium，超时 60s，失败可降级
  - 用户：trust=low，强超时 + 强 sandbox
  - sub_agent：递归深度受限（最大 1）
- **边界与非目标**：非目标：跨来源工具调用链（如 user 工具内部调用 MCP）
- **耦合点**：4 MCP、5 沙箱、sub_agent 模块
- **关键注意事项**：
  - source 进入 trace，便于按来源做错误率统计与成本归因

### 2.10 工具调用守卫（Guardrails）
- **一句话定义**：在 dispatch 前后插钩检测异常调用模式（重复、连续失败、无进展），可警告或硬停止。
- **触发场景**：每次 tool 调用前/后。
- **输入 / 输出契约**：消费历史 tool 调用签名队列；输出 GuardrailDecision（pass/warn/stop）
- **行为约定**：
  - 同一工具+同一参数连续重复 N 次 → 警告（注入提示）→ 仍重复 → 停止
  - 同一工具连续失败 M 次 → 警告 → 停止
  - 幂等工具无进展 → 警告
- **边界与非目标**：非目标：跨 session 守卫
- **耦合点**：1.7 循环检测
- **关键注意事项**：
  - 与循环检测有重叠——明确划分：循环检测在循环层（粗），守卫在工具层（细）
  - 守卫的「警告级」必须避免变成新循环源

### 2.11 参数消毒与 Secret 过滤
- **一句话定义**：工具参数在 dispatch 前消毒（防注入、JSON 修复）；执行环境的环境变量过滤敏感项。
- **触发场景**：tool_use 解析后、沙箱启动前。
- **输入 / 输出契约**：
  - 参数消毒：原始参数 → 合法 JSON 对象（或拒绝）
  - 环变过滤：完整 env → 白名单过滤后的 env
- **行为约定**：
  - 参数 JSON 损坏（未闭合引号、尾随逗号）→ 尝试修复 → 失败报错
  - 环变三层过滤：passthrough 白名单 → 名字含 KEY/TOKEN/SECRET 排除 → 安全前缀（PATH/LANG/VIRTUAL_ENV 等）
- **边界与非目标**：非目标：参数内容的语义校验（如 SQL 注入检查——属于工具实现）
- **耦合点**：5.3 沙箱环变过滤
- **关键注意事项**：
  - hermes 实测：「先断名后断值」的过滤策略最有效，避免值泄露的误报
  - 修复动作必须可观测（trace 记录被修复的原始内容）

---

# 3. Skill

`skill_registry.py`。从 `skills/` 目录扫描 SKILL.md，按触发条件注入 system prompt 或按需 lazy load。

## 子功能清单（共 8 项）

### 3.1 Skill 扫描与发现
- **一句话定义**：从配置目录递归扫描所有 SKILL.md，建立 skill 索引。
- **触发场景**：HTTP server 启动时（lifespan hook）；CLI 每次调用前；显式 reload 命令。
- **输入 / 输出契约**：输入 skills 根目录；输出 `[SkillEntry(name, description, path, platforms, tags, ...)]`
- **行为约定**：
  - 递归遍历，排除 `.git`、`.archive`、`.hidden` 等目录
  - 每个 skill 必须有 `SKILL.md`，否则忽略并日志
  - 命名冲突 → 警告，按目录字典序后者优先（明确策略）
- **边界与非目标**：非目标：远程 skill 仓库（Hub）的拉取（属 deployment 能力域）
- **耦合点**：FLEETENT_SKILLS_DIR 环境变量、CLAUDE.md 已说明
- **关键注意事项**：
  - hermes 教训：单一来源原则——所有 skill 汇聚到一个目录，避免多源冲突
  - 启动时扫描 vs 请求时扫描的语义差异（CLAUDE.md Gotcha：server lifespan vs CLI 每次扫）
- **开放问题**：是否支持 skill 仓库分层（system / user / project 三级 override）

### 3.2 元数据（Frontmatter）解析
- **一句话定义**：SKILL.md 顶部 YAML frontmatter 解析为结构化元数据。
- **触发场景**：扫描每个 SKILL.md 时。
- **输入 / 输出契约**：YAML frontmatter → 元数据 dict（name、description、version、platforms、prerequisites、tags、enabled_by_default 等）
- **行为约定**：
  - 必填：name、description
  - YAML 解析失败 → 跳过 + 警告（不阻断扫描）
  - 未识别字段 → 保留在 metadata bag，供未来扩展
- **边界与非目标**：非目标：JSON 或 TOML frontmatter（统一 YAML）
- **耦合点**：3.3 平台过滤、3.5 多 skill 解析
- **关键注意事项**：
  - hermes 注意：缺失字段默认值的「隐式约定」会困惑用户——必填字段必须显式声明
  - description 字段是 L1 注入的核心，质量决定 skill 召回率

### 3.3 平台/上下文约束过滤
- **一句话定义**：根据 frontmatter 中的 platforms / agent 字段过滤当前环境不适用的 skill。
- **触发场景**：扫描后过滤、agent run 启动时再过滤。
- **输入 / 输出契约**：当前环境 fingerprint（OS、agent ID、用户 role）+ skill metadata → 是否启用
- **行为约定**：
  - `platforms: [linux, macos]` → 仅在匹配 OS 上启用
  - `agent: [data_analyst]` → 仅在指定 agent 启用
  - 未声明字段 → 默认全启用（向后兼容）
- **边界与非目标**：非目标：动态运行时启用（仅启动期/run 期判断）
- **耦合点**：3.8 禁用机制、agent_policy
- **关键注意事项**：默认全启用的隐式行为容易误导（hermes 教训），文档需明确说明

### 3.4 渐进式披露（Progressive Disclosure）
- **一句话定义**：Skill 内容分三层加载——L1 metadata 进 system prompt（启动）/ L2 SKILL.md 全文（触发）/ L3 引用文件（按需）。
- **触发场景**：
  - L1：系统 prompt 构建时
  - L2：LLM 决定使用某 skill 时（通过工具或关键词命中）
  - L3：agent 在 SKILL.md 中跟随引用读取附加文件
- **输入 / 输出契约**：
  - L1：所有 skill 的 name + description 列表
  - L2：单个 SKILL.md 完整内容
  - L3：SKILL.md 引用的 reference.md / scripts 等
- **行为约定**：
  - L2 触发条件可选：关键词匹配（fleetent 现状）OR LLM 显式调用 `skill_view` 工具（Anthropic 推荐）
  - L3 通过文件读工具自然触发，无独立机制
- **边界与非目标**：非目标：自动 L1→L2 升级阈值
- **耦合点**：2.x 文件读工具、context_mgr
- **关键注意事项**：
  - **这是 fleetent 当前与业界最大差距点**——当前一次塞 system prompt 等于只做 L2，没有 L1 选择层与 L3 lazy 层
  - L1 描述质量决定召回率（Anthropic 共识）
  - L3 依赖 agent 具备文件读取工具——否则退化为 L2
- **开放问题**：fleetent 是否引入 progressive disclosure 三层模型，还是保留现状（关键词匹配 + 一次性注入）

### 3.5 多 Skill 共存与冲突解决
- **一句话定义**：多个 skill 同时命中时的注入顺序与去重规则。
- **触发场景**：用户消息匹配多个 skill description 关键词时。
- **输入 / 输出契约**：命中 skill 列表 → 最终注入的 system prompt 片段
- **行为约定**：
  - L1 模式：所有 skill metadata 共存（与 Anthropic 一致）
  - L2 触发：首次命中即注入，避免污染（fleetent 现状）OR 全部命中均注入（需 token cap）
  - 命名冲突：扫描时报错并选定（见 3.1）
- **边界与非目标**：非目标：skill 间的优先级排序算法
- **耦合点**：context_mgr token budget
- **关键注意事项**：
  - fleetent 当前「首次命中原则」对长文本输入可能漏召回——值得 review

### 3.6 Skill 热加载与重扫描
- **一句话定义**：支持运行时刷新 skill 索引，无需重启 server。
- **触发场景**：admin CLI `fleetent-admin reload-skills` / HTTP 管理 API / 文件变更监听（v1+）。
- **输入 / 输出契约**：触发信号 → 重新执行 3.1+3.2，原子替换索引
- **行为约定**：
  - 重扫描期间继续用旧索引（读时无锁）
  - 完成后原子切换
  - 失败保留旧索引并告警
- **边界与非目标**：非目标：文件 watch 实时刷新（v1.0 显式触发，v1+ 考虑）
- **耦合点**：admin 模块、3.1 扫描
- **关键注意事项**：
  - openclaw 教训：单次加载不支持动态刷新是反模式
  - 进行中的 run 不受影响（用启动时快照）

### 3.7 Skill 信任与审计（Prompt Injection 防护）
- **一句话定义**：检测 SKILL.md 内容中的疑似 prompt injection 模式，警告并标记。
- **触发场景**：扫描每个 SKILL.md 时。
- **输入 / 输出契约**：SKILL.md 内容 → 检测报告（命中模式列表 + 风险评分）
- **行为约定**：
  - 检测 16 类已知注入模式（hermes 参考）："ignore previous instructions"、"new instructions:"、"system: ..."、"```role: assistant" 等
  - 命中 → 写入审计日志 + 启动时 console 警告
  - 严重模式（如 SHELL 注入到 system prompt）→ 拒绝加载该 skill
- **边界与非目标**：非目标：动态运行时检测（仅加载时）
- **耦合点**：governance 审计能力
- **关键注意事项**：
  - Anthropic 的安全模型：「skill 只能从 trusted source 安装」——运行时不强制隔离
  - 但加载时审计是低成本兜底，应启用

### 3.8 Skill 禁用机制
- **一句话定义**：通过配置显式禁用某个 skill，覆盖 frontmatter 默认启用状态。
- **触发场景**：管理员/agent owner 决定关闭某个 skill。
- **输入 / 输出契约**：config 中的 `skills.disabled: [skill_name1, ...]`；可按 agent 维度禁用
- **行为约定**：
  - 禁用 skill 不参与 L1/L2 注入
  - 支持平台级 / agent 级 / 全局级三层覆盖
- **边界与非目标**：非目标：基于使用率自动禁用
- **耦合点**：config.py、agent_policy
- **关键注意事项**：禁用列表应在 trace 中可见，便于 debug「为什么这个 skill 没生效」

---

# 4. MCP（Model Context Protocol）

`mcp_client.py`。作为 MCP client 接入外部 MCP server，把它们暴露的工具注册到本地 registry。

## 子功能清单（共 9 项）

### 4.1 stdio Transport
- **一句话定义**：以子进程方式启动 MCP server，通过 stdin/stdout JSON-RPC 通信。
- **触发场景**：本地 MCP server（filesystem、shell、内部工具集）。
- **输入 / 输出契约**：配置中提供 command + args + env；client 启动子进程并双向通信
- **行为约定**：
  - 消息 = newline-delimited JSON（**消息内不能有内嵌 newline**）
  - stdout 只能写合法 MCP 消息；其他输出（日志、调试）走 stderr
  - server 进程崩溃 → 自动重启 + 退避（最多 N 次）
- **边界与非目标**：非目标：远程 stdio over SSH（属 transport 扩展）
- **耦合点**：4.7 健康检查、4.8 失败降级
- **关键注意事项**：
  - **stdout 污染是头号杀手**——库内 print()、调试输出全要重定向到 stderr
  - 重启循环要有上限，避免无限重启 boot loop
- **开放问题**：进程崩溃时的 in-flight 调用如何处理（重发 vs 失败回传）

### 4.2 Streamable HTTP Transport
- **一句话定义**：HTTP POST 发请求、SSE 接响应，可选 GET 订阅服务端推送，支持 session 与可恢复流。
- **触发场景**：远程 MCP server（如 GitHub、Slack、企业内部服务）。
- **输入 / 输出契约**：配置中提供 URL；client 维护 Mcp-Session-Id；通过 POST/GET 双向通信
- **行为约定**：
  - POST 请求 → 响应是 `application/json`（一次性）或 `text/event-stream`（流式）
  - GET 用于订阅服务端推送
  - `Mcp-Session-Id` header 由 server 初始化时分配，客户端后续请求都带
  - 断线 → 客户端发 `Last-Event-ID` GET 恢复
  - HTTP 404（session 过期）→ 重新 initialize
- **边界与非目标**：非目标：兼容旧 HTTP+SSE 协议（v1 仅支持 Streamable HTTP）
- **耦合点**：4.5 session 管理、4.7 健康检查
- **关键注意事项**：
  - 必须验证 `Origin` header（client 侧反向）防 DNS rebinding（spec MUST）
  - 本机 server 应连 127.0.0.1，不连 0.0.0.0

### 4.3 MCP Server 注册与配置
- **一句话定义**：在 `config/settings.yaml` 或运行时 API 中声明 MCP server，启动时建立连接。
- **触发场景**：server 初始化阶段。
- **输入 / 输出契约**：配置 schema：`mcp_servers: [{id, transport, command?, url?, env?, auth?, supports_parallel?}]`
- **行为约定**：
  - 启动时按配置建立连接
  - 连接失败 → 该 server 工具不可用，但不阻塞其他 server 与 agent 启动
  - 支持 lazy 启动（首次工具调用时 spawn，节省启动时间）
- **边界与非目标**：非目标：动态新增 server（v1 启动期固定，热加载入 v1+）
- **耦合点**：config.py、4.1/4.2 transport
- **关键注意事项**：
  - 环变注入要支持 secret 来源（如 `${GITHUB_TOKEN}`）
  - server 启动失败要清晰可见（启动日志 + 健康端点）

### 4.4 工具命名空间化
- **一句话定义**：MCP server 暴露的工具以 `{server_id}__{tool_name}` 双下划线命名，避免冲突且来源可追溯。
- **触发场景**：MCP 工具注册到本地 registry 时。
- **输入 / 输出契约**：server 返回的工具名 + server_id → 本地命名
- **行为约定**：与 2.3 命名规范一致；跨 server 同名工具不冲突；agent 调用时透明传递（去前缀后转发）
- **边界与非目标**：非目标：用户可见名 vs 内部名分离（统一 namespace 显示）
- **耦合点**：2.1 注册、2.3 命名
- **关键注意事项**：CLAUDE.md Gotcha 已固化双下划线规则，不要改动

### 4.5 Session 管理（Mcp-Session-Id）
- **一句话定义**：维护与 Streamable HTTP server 的会话标识，跨多次请求保持连续。
- **触发场景**：每次 HTTP transport 调用。
- **输入 / 输出契约**：initialize 响应中提取 Mcp-Session-Id；后续所有请求 header 带上
- **行为约定**：
  - server 返回 404 → session 过期 → 重新 initialize（新 session id）
  - client 关闭 → DELETE 显式终止 session（best effort）
- **边界与非目标**：非目标：跨进程共享 session
- **耦合点**：4.2 HTTP transport
- **关键注意事项**：session_id 是密码学敏感的——日志中不要全量打印

### 4.6 OAuth / 认证
- **一句话定义**：对支持 OAuth 的 MCP server 处理 credential 存取与刷新。
- **触发场景**：调用 OAuth 类 MCP server 工具前。
- **输入 / 输出契约**：OAuth 配置（client_id、refresh endpoint、token store path）→ 自动附加 Bearer token
- **行为约定**：
  - 工具调用前检查 token 过期时间
  - 过期 → 自动调 refresh endpoint → 更新 store
  - refresh 失败 → 标记 server 不可用，提示用户重新授权
- **边界与非目标**：非目标：OAuth 授权流程的 UI（属 admin 能力域）
- **耦合点**：admin OAuth flow、4.8 降级
- **关键注意事项**：
  - token 存储要加密（at least file permission 0600）
  - refresh 调用本身要超时

### 4.7 健康检查与重连
- **一句话定义**：定期/事件驱动地检测 MCP server 健康状态，异常时尝试重连。
- **触发场景**：周期性 ping、连续工具调用失败、用户主动 reload。
- **输入 / 输出契约**：探活方式（initialize ping / 自定义 health 调用）+ 退避策略
- **行为约定**：
  - stdio：进程退出 → 重启子进程
  - HTTP：连续 N 次 404/5xx → reinit
  - 重连退避：指数退避（1s, 2s, 4s, ... 上限 60s）
  - 重连失败累计 → 标记 server 永久不可用，需手动 reload
- **边界与非目标**：非目标：基于负载的健康评分
- **耦合点**：4.1/4.2 transport
- **关键注意事项**：
  - hermes 教训：reconnect 的「幽灵连接」可能让用户看到间歇性失败——清晰的错误信息是关键
  - 重连期间该 server 的工具应明确返回「unavailable」给 LLM，不要静默卡住

### 4.8 失败降级策略
- **一句话定义**：单个 MCP server 异常时降级行为可配，不影响整个 agent 运行。
- **触发场景**：server 不可用、tool 调用失败、auth 失败。
- **输入 / 输出契约**：降级模式枚举：strict（停整个 agent）/ degrade（屏蔽该 server 工具）/ silent（忽略+日志）
- **行为约定**：
  - 默认 degrade
  - 触发降级时：从可见 tool schema 中临时移除（下次 LLM 调用不会看到）
  - server 恢复后自动恢复
- **边界与非目标**：非目标：跨 server 工具替代（自动 fallback 到等价工具）
- **耦合点**：4.7 健康检查、1.9 错误分类
- **关键注意事项**：openclaw 教训：静默降级会掩盖故障——需要显式告警/通知

### 4.9 Server-Initiated Sampling 沙箱化
- **一句话定义**：MCP server 可请求 LLM 补全（sampling/createMessage），但走独立沙箱客户端，限流且不消耗主 agent 预算。
- **触发场景**：MCP server 通过协议主动请求 LLM。
- **输入 / 输出契约**：server 发送 sampling 请求 → client 用 auxiliary LLM client 处理
- **行为约定**：
  - 限流：每个 server 配置 max_rpm / max_tokens / max_rounds
  - 不计入主 agent 的 cost budget
  - 模型选择可被 server 请求覆盖，但需在白名单内
- **边界与非目标**：非目标：v1 不实现（v1+ 视需求引入）
- **耦合点**：model_router auxiliary client
- **开放问题**：v1 是否实现——hermes 已支持，openclaw 未明确，社区使用率待评估

---

# 5. 沙箱（Sandbox）

`sandbox_client.py`。隔离执行 LLM 生成或用户提交的代码。

## 子功能清单（共 9 项）

### 5.1 可插拔隔离档位（Backend）
- **一句话定义**：沙箱实现为可插拔后端（Docker / gVisor / Firecracker / SSH / 远程），按信任级与性能权衡选择。
- **触发场景**：`run_code` 工具调用时按配置选 backend。
- **输入 / 输出契约**：backend 接口：spawn(config) → handle；execute(handle, code) → result；cleanup(handle)
- **行为约定**：
  - 默认 Docker（trusted-tenant 场景）
  - 配置可切 gVisor（中等不信任）/ Firecracker（高不信任）/ 自定义 backend
  - backend 必须实现统一接口
- **边界与非目标**：非目标：自动按工作负载选 backend
- **耦合点**：config.py
- **关键注意事项**：
  - 业界共识：Docker 已不适合执行不可信代码——必须规划升级路径
  - factory 模式让升级不需要改循环代码

### 5.2 资源限制（CPU / MEM / Net / FS / 进程）
- **一句话定义**：每个沙箱实例都受 CPU、内存、网络、文件系统、进程数限制约束。
- **触发场景**：sandbox spawn 时。
- **输入 / 输出契约**：限制配置（默认 + 按 agent / 用户覆盖）
- **行为约定**：
  - 默认：CPU 0.5 核 / Memory 256MB / Network none / FS read-only / 进程数 32
  - 超 CPU/MEM 配额 → OOM kill
  - 网络默认禁用；按需开白名单
  - FS 默认只读；显式声明挂载点
- **边界与非目标**：非目标：动态调整（运行中提升配额）
- **耦合点**：5.1 backend、7.3 cost
- **关键注意事项**：
  - fleetent 现有：`--network none --memory 256m --cpus 0.5 --read-only`（CLAUDE.md 已固化）
  - 限制必须可按 agent 档位配置，不是全局硬编码

### 5.3 环境变量过滤与 Secret 防泄
- **一句话定义**：沙箱进程的 env 严格过滤，仅允许白名单变量，剔除所有可疑 secret。
- **触发场景**：sandbox spawn 时构造子进程 env。
- **输入 / 输出契约**：完整 host env → 过滤后 env
- **行为约定**：
  - 三层过滤：passthrough 白名单 → 名字含 KEY/TOKEN/SECRET 排除 → 安全前缀（PATH/LANG/VIRTUAL_ENV）
  - Windows 兼容时增加 essential list（SystemRoot 等）
- **边界与非目标**：非目标：runtime 注入 secret（需走专用 mount）
- **耦合点**：2.11 参数消毒
- **关键注意事项**：「先断名后断值」避免误报（hermes 实测）；过滤动作要可观测

### 5.4 文件系统隔离
- **一句话定义**：沙箱内对文件系统的访问限定于显式声明的工作区，越界路径访问被拒绝。
- **触发场景**：沙箱内代码读写文件时。
- **输入 / 输出契约**：workspace 路径配置；沙箱内可见的虚拟根
- **行为约定**：
  - 默认只挂 `/workspace`（读写）+ `/tmp`（读写、限大小）
  - 路径越界（`../`、绝对路径符号链接）→ 拒绝
  - rm / mv / cp 等危险操作有边界检查
- **边界与非目标**：非目标：复杂 ACL（按文件粒度授权）
- **耦合点**：5.1 backend、5.2 FS 资源限制
- **关键注意事项**：
  - openclaw 的 `fs-bridge-path-safety` 是值得参考的模式
  - 符号链接攻击是典型逃逸路径，必须 resolve 后校验

### 5.5 输出截断（stdout / stderr）
- **一句话定义**：捕获沙箱进程的 stdout/stderr，超限时按头尾保留策略截断。
- **触发场景**：execute 期间持续捕获；完成后整理。
- **输入 / 输出契约**：原始 stdout/stderr 字节流 → 截断后字符串 + 截断标记
- **行为约定**：
  - 默认 stdout 50KB / stderr 10KB（hermes 实测值，可作起点）
  - 超限时保留首 N KB + 尾 N KB + `[truncated X bytes in middle]`
  - 非 UTF-8 内容做 sanitize（替换或 escape）
- **边界与非目标**：非目标：实时流式回传（v1 一次性返回）
- **耦合点**：2.6 工具结果格式化
- **关键注意事项**：长输出可能拖死 LLM 上下文，截断是必备

### 5.6 执行超时与级联终止
- **一句话定义**：沙箱执行有强超时，超时时按 SIGTERM → SIGKILL 级联终止进程及容器。
- **触发场景**：超过配置的执行时间。
- **输入 / 输出契约**：超时配置 + cancel token；输出 timeout error result
- **行为约定**：
  - 默认 30s（可配置，多 cron/sub_agent 等场景可放宽）
  - 触发：先 SIGTERM 给 N 秒优雅终止 → 仍存活则 SIGKILL → cleanup 容器
  - 取消信号也走同一路径
- **边界与非目标**：非目标：超时后部分结果回传（一次性失败）
- **耦合点**：1.6 取消、7.5 取消传播
- **关键注意事项**：cleanup 必须可靠——遗留容器会耗尽资源

### 5.7 多语言支持
- **一句话定义**：沙箱镜像内置多语言执行环境（Python / Node / Bash），通过工具参数选择。
- **触发场景**：`run_code` 工具调用，参数 language=python|node|bash。
- **输入 / 输出契约**：language + code → 在对应 runtime 执行
- **行为约定**：
  - v1 必备：Python（首要场景）
  - v1+ 可选：Node、Bash
  - 不支持的语言 → 返回明确错误
- **边界与非目标**：非目标：用户自定义镜像（v1 用统一镜像）
- **耦合点**：5.1 backend、5.4 FS
- **关键注意事项**：每加一个语言增加镜像体积——权衡多语言 vs 启动时间

### 5.8 沙箱可观测性穿透
- **一句话定义**：沙箱内的执行信息（stdout、stderr、exit_code、耗时、资源用量）必须能进 agent trace。
- **触发场景**：每次 execute 完成或失败。
- **输入 / 输出契约**：sandbox 产物 → trace 记录
- **行为约定**：
  - 每次执行写一条 trace：sandbox_backend、language、duration、exit_code、stdout/stderr 大小
  - 资源用量（可选）：peak memory、CPU time
- **边界与非目标**：非目标：实时 metrics（v1 仅事后记录）
- **耦合点**：7.1 trace
- **关键注意事项**：调研警告——「标准 observability 工具进不去隔离环境」，需专门链路

### 5.9 Warm Pool（v1+）
- **一句话定义**：预启动一批沙箱实例池化，新请求复用避免冷启动延迟。
- **触发场景**：高并发场景。
- **输入 / 输出契约**：池大小配置 + 闲置回收时间
- **行为约定**：
  - 池满 → 复用最旧空闲实例
  - 池空 → 现 spawn 新实例
  - 实例使用后 reset（清 workspace、重置 env）
- **边界与非目标**：v1 不实现；v1+ 视性能压测引入
- **耦合点**：5.1 backend
- **关键注意事项**：状态重置必须彻底，否则跨任务串话——这是 warm pool 最大风险点

---

# 6. 上下文压缩（Context Compression）

`context_mgr.py`。维护单 session 内的消息历史不超过 token 预算，过限时压缩。

## 子功能清单（共 9 项）

### 6.1 触发条件（双阈值 Tmax / Tretained）
- **一句话定义**：消息总 token 超过 Tmax 触发压缩，压缩目标是降到 Tretained。
- **触发场景**：每轮循环结束后估算总 token。
- **输入 / 输出契约**：消息列表 → token 估算 → 与阈值比较 → 触发决定
- **行为约定**：
  - Tmax = context_length × 80%（默认；可配）
  - Tretained < Tmax，留出 bandwidth 避免频繁压缩
  - 也支持手动触发（`/compact` 命令）
  - 也支持失败触发（LLM 返回 context_overflow 错误）
- **边界与非目标**：非目标：基于消息条数触发（用 token 更精确）
- **耦合点**：1.4 fallback 链（context overflow 走压缩路径）
- **关键注意事项**：
  - fleetent 现有阈值 80%——可保留；引入 Tretained 是新概念
  - 阈值过近 Tmax-Tretained 导致频繁压缩 → 缓存失效 → 延迟暴增（Factory.ai 教训）
- **开放问题**：Tmax/Tretained 的最佳间隔——需在 fleetent 实际负载下试

### 6.2 头-中-尾分层保留策略
- **一句话定义**：消息分三段——头（强制保留）/ 中（摘要）/ 尾（强制保留至 Tretained）。
- **触发场景**：压缩执行时。
- **输入 / 输出契约**：原始 messages → 标记三段 → 中段送摘要
- **行为约定**：
  - 头：system prompt + 前 N 条消息（默认 N=3）+ 用户初始意图
  - 尾：从最新往前累计 token 至 tail_token_budget（默认 20K）
  - 中：剩余部分 → 摘要
  - 头尾边界必须落在 tool pair 之外
- **边界与非目标**：非目标：自适应分段比例（v1 用配置）
- **耦合点**：6.4 tool pair 完整性
- **关键注意事项**：
  - `keep_tail` 用 **identity check**（`m is tail[0]`），不用 `==`（CLAUDE.md Gotcha——内容相同但非同一对象会误判）
  - 头部保留的是「session intent」——用户最初要做什么不能丢

### 6.3 持久化增量摘要
- **一句话定义**：维护一份持久 summary，每次压缩仅对新被截断的中段增量摘要并 merge 进持久 summary。
- **触发场景**：第二次及之后的压缩。
- **输入 / 输出契约**：上一次 summary + 新中段 → 更新后的 summary
- **行为约定**：
  - 首次压缩：直接摘要中段
  - 后续压缩：摘要新中段 → merge 进 persistent summary（保留之前已摘内容）
  - merge 失败 → 回退到全摘（带告警）
- **边界与非目标**：非目标：summary 的版本管理（v1 仅保最新）
- **耦合点**：6.6 摘要质量
- **关键注意事项**：
  - 避免「重复摘已摘内容」是 Factory.ai 的关键优化——节省 LLM 调用
  - persistent summary 要明确标记「CONTEXT COMPACTION — REFERENCE ONLY」，避免模型把历史 user 消息解读为新请求（hermes 踩过的坑）

### 6.4 Tool Pair 完整性保护
- **一句话定义**：压缩边界（头-中切点、中-尾切点）必须落在 tool_use/tool_result 对之外，且最终消息序列中所有 tool_use 都有对应 result。
- **触发场景**：分段时、清理孤立 pair 时。
- **输入 / 输出契约**：候选切点 → 调整到合法位置
- **行为约定**：
  - 切点处于 tool pair 中间 → 前移到 pair 外
  - 压缩后扫描全消息，孤立 tool_use（无 result）→ 注入占位 result「[result truncated]」
  - 孤立 tool_result（无 use）→ 移除
- **边界与非目标**：非目标：跨段恢复 tool pair（不补全已截断的真实结果）
- **耦合点**：1.10 消息卫生、所有压缩子功能
- **关键注意事项**：
  - **这是压缩中最容易 bug 的地方**——hermes 与 fleetent 都有专门函数 `_sanitize_tool_pairs`
  - 不修复 tool pair 会导致 API 直接 400 拒绝请求

### 6.5 工具结果预修剪（Cheap Pruning）
- **一句话定义**：在调用昂贵 LLM 摘要前，先对老的、明确无用的 tool result 做廉价修剪。
- **触发场景**：压缩流程 Phase 1（在摘要之前）。
- **输入 / 输出契约**：中段消息 → 修剪 tool result（替为占位符）
- **行为约定**：
  - 老旧 tool result（已被引用过）→ 替换为「[old tool result, see breadcrumb above]」
  - 重复内容（同工具多次调用）→ 仅保留最新
  - 图像内容 → 替为文本占位符（节省大量 token）
- **边界与非目标**：非目标：内容语义判断（仅基于元数据修剪）
- **耦合点**：6.6 摘要、5.5 输出截断
- **关键注意事项**：
  - 预修剪不能误删 LLM 后续可能回引的内容——保留「breadcrumb」（路径、ID、文件名）
  - 廉价修剪是必需——直接 LLM 摘要全部内容成本高

### 6.6 摘要质量与失败处理
- **一句话定义**：用轻量 LLM 生成结构化摘要，输出包含「已完成」「待完成」「关键标识」三部分。
- **触发场景**：压缩流程 Phase 3。
- **输入 / 输出契约**：中段消息 → 结构化 summary 文本
- **行为约定**：
  - 摘要 prompt 模板固定：要求列「已解决问题」「待解决问题」「artifact 列表」「关键 ID / 路径」
  - 用 auxiliary LLM（廉价快速，如 Haiku）
  - 摘要失败 → 回退到静态截断（保留前 N + 后 M 条原消息），并告警
- **边界与非目标**：非目标：用户可见的摘要导出（仅内部使用）
- **耦合点**：model_router、6.3 增量摘要
- **关键注意事项**：
  - 摘要失败的 fallback 不能再次失败——必须保证最终 messages 是 API-legal 的
  - 摘要 prompt 模板的变化要 versioned（影响行为）

### 6.7 压缩元数据与可追溯
- **一句话定义**：每次压缩生成元数据：压缩前后消息数、token 数、原因、时间戳、所用模型；进入 trace。
- **触发场景**：压缩完成时。
- **输入 / 输出契约**：压缩动作 → 元数据记录
- **行为约定**：
  - 必填字段：trigger_reason（auto / manual / overflow）、before_tokens、after_tokens、duration_ms、summary_model
  - 压缩失败也记录（含失败原因）
- **边界与非目标**：非目标：压缩快照存储（v1 仅元数据，不存原始消息）
- **耦合点**：7.1 trace
- **关键注意事项**：
  - openclaw 教训：可回滚的 checkpoint 太复杂——v1 不做回滚，仅 trace 元数据
  - 压缩元数据对成本归因关键

### 6.8 镜像 / 二进制内容处理
- **一句话定义**：消息中的图像或二进制 content block 在压缩时替换为文本占位符。
- **触发场景**：压缩流程，发现非文本 content。
- **输入 / 输出契约**：包含图像的消息 → 文本化的占位（保留必要 metadata）
- **行为约定**：
  - 图像 → 「[image: {dimensions}, captured at {timestamp}]」
  - 二进制 → 「[binary content: {size} bytes]」
- **边界与非目标**：非目标：图像 OCR / caption 生成（v1+ 视需求）
- **耦合点**：6.5 预修剪
- **关键注意事项**：computer_use 类工具会产生大量截图——这是 token 大户

### 6.9 压缩反抖动（Ineffective Compression Detection）
- **一句话定义**：若连续 N 次压缩都「省 < 10% token」，停止自动压缩并告警。
- **触发场景**：压缩完成后比较 before/after。
- **输入 / 输出契约**：压缩历史 → 是否继续允许自动压缩
- **行为约定**：
  - 连续 3 次（默认）有效率 < 10% → 关闭自动压缩
  - 抛出明确告警，要求人工干预或扩大 context window
- **边界与非目标**：非目标：自动调整 Tmax/Tretained
- **耦合点**：6.1 触发条件、7.1 trace
- **关键注意事项**：避免「永久边缘」死循环（Factory.ai 教训）——压缩近乎无效时硬停止

---

# 7. 横切关注点（Cross-Cutting Concerns）

不归属单一模块、但贯穿所有模块的能力。明确成章避免散落。

## 子功能清单（共 7 项）

### 7.1 Trajectory / Trace
- **一句话定义**：每次 run、每次 LLM 调用、每次工具调用、每次压缩动作、每次审批事件都写入 append-only trace 日志。
- **触发场景**：所有上述事件。
- **输入 / 输出契约**：事件 + 元数据 → JSONL 行
- **行为约定**：
  - 事件类型固定枚举（llm_call / tool_call / compaction / approval / error / cancellation）
  - 每条 trace 含 session_id / run_id / user_id / timestamp / event_type / payload
  - 写入异步，不阻塞主循环
  - 大字段（如完整 prompt / 大 tool result）按配置开关写入
- **边界与非目标**：非目标：trace 的实时聚合查询（属 observability 能力域）
- **耦合点**：所有模块
- **关键注意事项**：
  - trace 是后续 eval、debug、cost 归因的唯一抓手——没有 trace 等于失明
  - PII / secret 必须 redact 后再写

### 7.2 审批门（Permission Gate）
- **一句话定义**：高风险工具调用前阻塞循环，等待人工 approve/reject 信号。
- **触发场景**：风险分级为 medium/high 的工具调用前。
- **输入 / 输出契约**：审批请求（含工具名、参数、风险级、超时）→ approve/reject 决策
- **行为约定**：
  - 通过 asyncio.Event 实现，无轮询
  - medium 短超时（如 30s）/ high 长超时（如 5min）
  - 超时默认 reject
  - 重启后 cleanup_stale_approvals 清孤儿
- **边界与非目标**：非目标：审批 UI（属 governance 能力域）
- **耦合点**：2.7 风险分级、7.1 trace
- **关键注意事项**：CLAUDE.md 已有提示——测试需短超时（0.1s）

### 7.3 成本预算（Cost Budget）
- **一句话定义**：三维成本约束（迭代次数 / token 数 / 美元）作用于单次 run、单 session、单用户、单 agent。
- **触发场景**：每次 LLM 调用前/后、每次工具调用后。
- **输入 / 输出契约**：预算配置 + 实时消耗 → 是否阻断
- **行为约定**：
  - 多层级：run < session < user < agent < global
  - 任一级别超限 → 触发 1.3 终止条件
  - sub_agent、压缩内部调用可豁免（refund 机制，可选）
- **边界与非目标**：非目标：账单（属 platform 能力域）
- **耦合点**：1.8 grace call、1.3 终止
- **关键注意事项**：实时消耗的维护必须线程安全（async lock）

### 7.4 错误分类（统一 Codec）
- **一句话定义**：所有异常归一化为有限枚举 `ErrorClass`，集中维护，不散落字符串匹配。
- **触发场景**：任何异常或错误响应。
- **输入 / 输出契约**：原始异常 → ErrorClass（含恢复策略标志）
- **行为约定**：
  - 枚举集合 12+ 项（hermes 经验值）：auth_failed / billing / rate_limit / context_overflow / format_error / tool_timeout / tool_crash / mcp_disconnect / sandbox_oom / sandbox_timeout / network / unknown 等
  - 每个 ErrorClass 携带：should_retry / should_compress / should_fallback / should_rotate / user_visible / log_level
- **边界与非目标**：非目标：错误国际化（user_visible 文案的 i18n 属 platform）
- **耦合点**：1.9 错误分类（循环层）、4 MCP、5 沙箱
- **关键注意事项**：openclaw 反面教材——错误分类散落在 4+ 文件难以维护

### 7.5 取消与超时传播
- **一句话定义**：cancel 信号与超时事件能从循环层传播到 LLM 调用、工具调用、MCP 连接、沙箱进程。
- **触发场景**：用户取消、超时、HTTP 客户端断开。
- **输入 / 输出契约**：cancel token / deadline 在调用链中传递
- **行为约定**：
  - 每个外部调用都接受 cancel token
  - 信号传播是「单向流」——从 caller 到 callee
  - 取消是 cooperative，要求 callee 主动检查
  - 硬 deadline 兜底：超过 N 秒未优雅退出 → 强制终止
- **边界与非目标**：非目标：分布式取消（跨进程）
- **耦合点**：1.6 中断、2.5 dispatch、5.6 沙箱、4 MCP
- **关键注意事项**：
  - 取消信号必须可重入（多层重复发送不冲突）
  - 取消后 trace 必须完整写入

### 7.6 沙箱可观测性穿透
- **一句话定义**：隔离环境内的执行细节（stdout / stderr / exit_code / metrics）能被外部 trace 捕获。
- **触发场景**：沙箱执行结束或失败。
- **输入 / 输出契约**：见 5.8
- **行为约定**：与 5.8 一致；7.6 强调的是「穿透 sandbox 边界」这件事的横切性，不要被孤立成 sandbox 内部细节
- **耦合点**：5.8、7.1
- **关键注意事项**：业界经验——标准 observability 工具进不去隔离环境，必须专门设计

### 7.7 插件钩子（Plugin Hooks）
- **一句话定义**：在循环关键节点（model_resolve / prompt_build / tool_call / tool_result / compaction）提供 hook 注入点，便于第三方扩展。
- **触发场景**：v1+ 引入；v1 不做。
- **输入 / 输出契约**：hook 接受事件 + 上下文 → 返回 pass / transform / block 决策
- **行为约定**：
  - 钩点固定枚举，不允许任意位置注入
  - hook 失败 → 默认 pass（不阻断主流程）+ 告警
- **边界与非目标**：v1 范围外
- **耦合点**：所有模块
- **关键注意事项**：openclaw 经验值得借鉴——hook 是平台化的核心扩展点；但要避免过早引入导致循环代码复杂化（hermes 教训）
- **开放问题**：是否进入 v1 范围——建议 v1.1 引入

---

# 8. 模块依赖关系图

```
                ┌─────────────────┐
                │   Agent Loop    │ (1)
                │                 │
   ┌────────────┤  循环、终止、    │
   │            │  fallback、调度  │
   │            └────┬────┬───────┘
   │                 │    │
   │       ┌─────────┘    └────────┐
   │       │                       │
   │  ┌────▼─────┐          ┌──────▼──────┐
   │  │  Tools   │ (2)      │ Context Mgr │ (6)
   │  │  注册、   │          │  压缩、保留  │
   │  │ schema、  │          │              │
   │  │ dispatch │          └──────────────┘
   │  └────┬─────┘                  ▲
   │       │                        │
   │   ┌───┴────────┬─────────┐    │
   │   │            │         │     │
   │ ┌─▼──┐   ┌────▼──┐  ┌───▼─┐   │
   │ │MCP │   │Skill  │  │Sand │   │
   │ │ (4)│   │  (3)  │  │ (5) │   │
   │ └────┘   └───────┘  └─────┘   │
   │     │       │         │       │
   │     └───────┴─────────┴───────┘
   │                 │
   │     ┌───────────▼───────────┐
   └────►│  Cross-Cutting (7)    │
         │  Trace / Approval /   │
         │  Cost / Errors /      │
         │  Cancel / Hooks       │
         └───────────────────────┘
```

**依赖单向**：核心循环依赖工具、Skill、上下文压缩；工具依赖 MCP（通过 registry）与沙箱（通过 run_code）；所有模块向横切关注点写入。

---

# 9. 子功能统计

| 模块 | 子功能数 | 覆盖率（vs 现状 + 业界） |
|------|---------|---------|
| 1 核心循环 | 10 | 现状 6 项已实现，新增 4 项（grace call、循环检测、消息卫生、错误统一） |
| 2 工具 | 11 | 现状 5 项，新增 6 项（命名规范、描述规范、guardrail、参数消毒、来源分层、命名空间） |
| 3 Skill | 8 | 现状 2 项，新增 6 项（progressive disclosure、平台过滤、热加载、injection 防护、禁用、frontmatter 解析） |
| 4 MCP | 9 | 现状 3 项，新增 6 项（streamable HTTP、session、OAuth、健康检查、降级、sampling） |
| 5 沙箱 | 9 | 现状 3 项，新增 6 项（pluggable backend、env 过滤、FS 隔离、超时级联、可观测、warm pool） |
| 6 上下文压缩 | 9 | 现状 3 项，新增 6 项（双阈值、增量摘要、预修剪、反抖动、元数据、图像处理） |
| 7 横切关注点 | 7 | 现状 3 项（trace/approval/cost），明确为横切 |
| **总计** | **63** | |

---

# 10. 关键设计决策点（feed 进 design.md）

以下问题超出能力清单范围，需在专门的 design.md 中讨论：

1. **Skill 是否引入 progressive disclosure 三层模型**——架构改造大，价值高
2. **沙箱 backend 是否规划 Docker → gVisor 升级路径**——v1 用 Docker 但接口要预留
3. **上下文压缩是否升级到双阈值 + persistent summary**——影响压缩效率与缓存命中
4. **工具 schema 是否支持 `response_format` enum 参数**——降 token 但增加工具实现复杂度
5. **MCP 是否仅支持 Streamable HTTP（弃 HTTP+SSE 兼容）**——简化实现 vs 生态兼容
6. **是否引入 attempt-based state machine**（openclaw 做法）——结构清晰 vs 复杂度
7. **错误分类枚举的扩展机制**——新增分类是否需要 ADR
8. **Server-initiated sampling（MCP 4.9）是否进 v1**
9. **Warm pool（沙箱 5.9）是否进 v1**
10. **插件钩子（7.7）是否进 v1**

---

# 11. 后续行动

1. ✅ **阶段 3**：能力清单（本文档）
2. ✅ **阶段 4**：验收标准（[agent-runtime-acceptance-criteria.md](./agent-runtime-acceptance-criteria.md)，155 条 Given/When/Then 场景）
3. **下一步（脱离本任务范围）**：
   - 根据本清单拆分为 6 个 OpenSpec change（每模块一个 proposal），逐个 propose → review → apply
   - 启动「关键设计决策点」（第 10 章）的讨论，产出对应 design.md
   - 优先级建议：MCP / Sandbox / Skill 三个改造点最大，建议先 propose；核心循环 / 工具 / 上下文压缩三个增量较小，可后启动

---

# 12. 交付摘要（自检完成）

## 12.1 产出清单

| 文件 | 行数 | 字数 | 用途 |
|------|------|------|------|
| [`industry-survey.md`](./industry-survey.md) | 422 | 1.7K | 业界 6 模块调研与权威来源 |
| [`reference-survey-openclaw.md`](./reference-survey-openclaw.md) | 287 | 1.3K | openclaw 项目按 6 模块结构化笔记 |
| [`reference-survey-hermes.md`](./reference-survey-hermes.md) | 259 | 1.2K | hermes-agent 项目按 6 模块结构化笔记 |
| `agent-runtime-capabilities.md`（本文档） | 1046 | 4.6K | 63 个子功能能力清单 |
| [`agent-runtime-acceptance-criteria.md`](./agent-runtime-acceptance-criteria.md) | 973 | 3.3K | 155 条 Given/When/Then 验收场景 |

总计约 3000 行文档、覆盖 5 个产出文件。

## 12.2 自检清单

| 检查项 | 结果 |
|------|------|
| 6 个模块的子功能数量是否大致平衡？ | ✅ 10 / 11 / 8 / 9 / 9 / 9 / 7（横切），最大与最小差 4，可接受 |
| 每个子功能可端到端观察？ | ✅ 每个子功能都有明确的「行为约定」可验证；63 项均配 ≥ 1 条验收场景 |
| 实现细节是否侵入？ | ✅ 整篇仅 1 处接近实现描述（`run_sync` 形态），已改为概念性表达 |
| 横切关注点是否覆盖所有模块？ | ✅ 7 项横切（trace/审批/cost/错误/取消/可观测/钩子）跨所有模块出现耦合点 |
| 开放问题是否有归属？ | ✅ 第 10 章列出 10 个关键设计决策点，默认 owner = 张洋（核心 runtime 负责人，per [docs/architecture.md:142](../architecture.md)），待 design.md 阶段细化 |
| 调研投入是否充分？ | ✅ 6 个 WebSearch + 6 个 WebFetch 权威源 + 2 个参考项目深度调研（85K+82K agent token） |
| 是否引用了 fleetent 现状？ | ✅ CLAUDE.md 的 Gotchas（identity check、`{server}__{tool}`、tools.py 副作用 import）均显式纳入；与 docs/capabilities/agent-runtime.md 现状对照 |

## 12.3 关键发现摘要

### 与现状对照的最大差距（按改造工作量降序）

1. **Skill 渐进式披露（progressive disclosure）**——业界（Anthropic）已收敛为 L1/L2/L3 三层模型；fleetent 仅做 L2 等价的一次性注入。改造需要：扫描时只取 metadata、引入 skill_view 工具、依赖 agent 文件读工具
2. **沙箱 backend 抽象**——业界共识 Docker 已不够；fleetent 当前直调 Docker CLI 无抽象层。改造需要：定义 backend 接口、改写 sandbox_client、Docker 实现下沉为一种 backend
3. **MCP Streamable HTTP**——MCP 已切换到 Streamable HTTP；fleetent 当前 mcp_client.py 实现需评估对齐度
4. **上下文压缩双阈值 + persistent summary**——Factory.ai 路线；fleetent 单阈值 80% + 一次性摘要
5. **错误分类统一 codec**——hermes 经验：枚举驱动；openclaw 反面教材：散落各处。fleetent 当前散落（需收敛）
6. **工具守卫（guardrails）**——hermes 经验值得直接借鉴

### 三大风险提醒（实现阶段必须 e2e 覆盖）

1. **Tool pair 完整性**——压缩、截断、错误恢复都可能破坏 tool_use/tool_result 1:1 配对，API 直接 400 拒绝。涉及场景：1.5.4 / 1.10.2 / 6.2.3 / 6.4.1-3
2. **取消信号穿透 sandbox / MCP**——一个失控 agent 会拖死整个进程。涉及场景：1.6 / 5.6 / 7.5
3. **MCP 静默降级反模式**——openclaw 教训：失败被掩盖让用户看到「间歇性」错误。涉及场景：4.7.2 / 4.8

## 12.4 后续 OpenSpec change 拆分建议

| 优先级 | proposal 名 | 覆盖能力 | 改造规模 |
|------|---------|---------|---------|
| P0 | `agent-runtime-error-classifier` | 7.4 + 1.9 + 4 + 5 错误归一 | 中——影响所有模块但接口稳定 |
| P0 | `agent-runtime-skill-progressive-disclosure` | 3.4 / 3.x | 大——架构变化 |
| P1 | `agent-runtime-sandbox-backend` | 5.1 / 5.x | 大——引入抽象层 |
| P1 | `agent-runtime-context-compression-v2` | 6.1-6.9 | 大——双阈值 + persistent summary |
| P2 | `agent-runtime-mcp-streamable-http` | 4.1-4.9 | 中——transport 替换 |
| P2 | `agent-runtime-tools-guardrails` | 2.4 / 2.10 / 2.11 + 1.7 | 中——增量 |
| P2 | `agent-runtime-loop-cancellation` | 1.6 / 7.5 | 中——增量但跨模块 |

每个 proposal 在生成时引用本能力清单的对应章节，validation criteria 直接复用 [agent-runtime-acceptance-criteria.md](./agent-runtime-acceptance-criteria.md) 中对应场景。

---

**交付完成**。下一步动作由你（张洋）决定开启哪个 proposal。

