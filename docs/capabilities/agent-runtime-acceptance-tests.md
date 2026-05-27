# Agent Runtime 模块验收测试用例

> **定位**：模块级主流程验收场景，关注可观察的端到端行为。细粒度子功能场景见 [`agent-runtime-acceptance-criteria.md`](./agent-runtime-acceptance-criteria.md)。
>
> **格式**：每个场景采用 Given / When / Then 结构，聚焦主路径与关键失败路径。
>
> **运行方式**：每条场景应能映射为一条集成测试或手动验收步骤；LLM 调用在自动化测试中 mock。

---

## 模块一：核心循环

**场景 1.1：基本工具调用循环**
- Given：用户发送「计算 2+3*4 并告知结果」，LLM 需调用 calculate 工具
- When：调用 `agent_loop.run()`
- Then：LLM 调用工具 → 工具返回结果 → LLM 生成最终回复；用户收到含计算结果的文本；trace 中含 `llm_call` 和 `tool_call` 事件

**场景 1.2：自然结束**
- Given：用户发送「今天星期几」，LLM 无需工具即可回答
- When：调用 `run()`
- Then：循环在第一轮结束；trace 中 `finish_reason = natural_end`；用户收到直接回复

**场景 1.3：模型 fallback**
- Given：主模型配置为返回 429 限流，fallback 模型正常
- When：调用 `run()`
- Then：自动切换到 fallback 模型继续执行；用户收到正常回复；trace 中 `model_used` 记录实际使用的 fallback 模型

**场景 1.4：步数预算触发 Grace Call**
- Given：`max_turns=3`，任务实际需要 6 轮；LLM mock 为始终返回工具调用
- When：调用 `run()`
- Then：第 3 轮后触发 Grace Call（给 LLM 最后一次总结机会）；用户收到包含当前进展的回复，而非空响应；trace 中 `finish_reason = budget_exceeded`

**场景 1.5：流式调用事件序列**
- Given：用户消息触发一次工具调用
- When：`async for event in run_stream()`
- Then：事件序列依次包含 `text_delta`、`tool_start`、`tool_end`、`text_delta`、`done`；无事件乱序

---

## 模块二：工具

**场景 2.1：内置工具正常调用**
- Given：工具注册表中有 `calculate` 内置工具；LLM 请求调用该工具
- When：`tool_registry.dispatch("calculate", {"expression": "100 / 4"})`
- Then：返回 `25.0`；tool_result 写入 context；trace 中记录工具名、参数、结果、耗时

**场景 2.2：插件工具访问控制**
- Given：`crm_tools` 插件已加载；agent A 的 `plugins: []`，agent B 的 `plugins: [crm_tools]`
- When：两个 agent 分别尝试调用 `crm_tools__search_customer`
- Then：agent A 调用被拦截，返回「工具不存在」；agent B 正常执行

**场景 2.3：高风险工具需审批**
- Given：`write_file` 工具 `risk_level=high`；用户发送触发该工具的消息
- When：LLM 请求调用 `write_file`
- Then：执行暂停，用户收到审批请求；用户批准后工具执行并返回结果；用户拒绝后 LLM 收到「操作已拒绝」结果

**场景 2.4：工具调用超时**
- Given：某工具执行时间超过配置超时上限（mock 为永不返回）
- When：dispatch 该工具
- Then：超时后返回包含超时说明的 tool_result；主循环继续；不抛出未捕获异常

**场景 2.5：大结果写入时面包屑压缩**
- Given：`read_file` 返回 5000 token 的文件内容；context 进入下一轮
- When：下一轮开始，组装消息
- Then：上一轮的 tool_result 已降级为面包屑格式（含文件路径和关键字段摘要）；完整内容不出现在新一轮 context 中

---

## 模块三：Skill

**场景 3.1：关键词命中注入**
- Given：已加载 `crm_skill`，其 keywords 含「客户」；用户发送「帮我查一下这个客户的合同」
- When：`run()` 开始前执行 Skill 匹配
- Then：`crm_skill` 的 L2 全文被注入 system prompt；LLM 在该 Skill 指导下回复

**场景 3.2：无匹配不注入**
- Given：已加载若干 Skill；用户发送「今天天气怎么样」（与所有 Skill 无关）
- When：执行 Skill 匹配
- Then：没有 Skill 注入 system prompt；LLM 以基础能力回复

**场景 3.3：多 Skill 命中共存**
- Given：`crm_skill` 和 `hr_tools` 同时命中；两者无指令冲突
- When：执行匹配
- Then：两个 Skill 的 L1 摘要均注入 system prompt；置信度最高的 Skill 加载 L2 全文；LLM 可感知两个 Skill 的存在

**场景 3.4：Skill 热加载**
- Given：平台运行中，管理员通过 admin CLI 新增一个 Skill 并触发重扫描
- When：下一条用户消息到达
- Then：新 Skill 对本次及后续请求生效；存量进行中的任务不受影响

---

## 模块四：MCP

**场景 4.1：服务正常启动与工具注册**
- Given：配置文件声明一个 MCP 服务（stdio 或 HTTP）；服务正常运行
- When：平台启动
- Then：服务连接成功；该服务的所有工具以 `server__tool` 格式注册到工具注册表；LLM 可调用这些工具

**场景 4.2：单个服务启动失败不阻断平台**
- Given：配置了两个 MCP 服务；其中一个启动时连接失败
- When：平台启动
- Then：失败服务的工具不可用；平台正常启动；另一个服务的工具正常注册；告警日志记录失败原因

**场景 4.3：运行时工具调用**
- Given：MCP 服务已连接；LLM 请求调用 `github__create_issue`
- When：dispatch 该工具
- Then：请求转发到 MCP 服务；结果返回给 LLM；tool_result 写入 context

**场景 4.4：服务断开自动重连**
- Given：已连接的 MCP 服务中途断开
- When：LLM 尝试调用该服务的工具
- Then：工具返回「服务暂时不可用」；后台触发重连（指数退避）；重连成功后工具恢复可用

---

## 模块五：沙箱

**场景 5.1：代码在隔离环境执行**
- Given：`sandbox.mode=all`；LLM 调用 `run_code("import os; print(os.getcwd())")`
- When：sandbox 执行
- Then：代码在 Docker 容器内执行；网络不可用（`--network none`）；stdout 结果返回给 LLM；主机文件系统未被修改

**场景 5.2：执行超时强制终止**
- Given：提交一段死循环代码；超时配置为 5 秒
- When：sandbox exec
- Then：5 秒后先发 SIGTERM；未响应则 SIGKILL；容器被清理；LLM 收到超时错误结果；主循环继续

**场景 5.3：全局关闭沙箱**
- Given：`settings.yaml` 中 `sandbox.mode=off`
- When：平台启动
- Then：`run_code` 工具不出现在工具注册表中；LLM 的工具列表中无 `run_code`

**场景 5.4：Agent 级别禁用**
- Given：`sandbox.mode=all`；agent 定义 `features.code_execution: false`
- When：该 agent 运行时 LLM 尝试调用 `run_code`
- Then：调用被拦截；LLM 收到「工具不可用」结果；其他 agent 不受影响

**场景 5.5：平台重启清理孤儿容器**
- Given：上次运行异常退出，留有名为 `sandbox-*` 的遗留容器
- When：平台重新启动
- Then：启动过程中自动检测并销毁所有 `sandbox-*` 遗留容器；不影响正常启动流程

---

## 模块六：上下文压缩

**场景 6.1：超阈值自动触发压缩**
- Given：`context_max_tokens=8000`，`compress_threshold=0.8`；对话历史积累至 6500 token
- When：下一轮 LLM 调用前
- Then：压缩自动触发；中段历史替换为摘要；头部系统提示和尾部最近消息完整保留；压缩后 token 量低于 Tretained

**场景 6.2：压缩不破坏工具调用配对**
- Given：对话中含多对 tool_use / tool_result；触发压缩
- When：压缩执行
- Then：压缩后消息序列中不存在孤立的 tool_use（无对应 result）或孤立的 tool_result（无对应 use）；LLM 接口不报错

**场景 6.3：工具结果面包屑降级**
- Given：上一轮 `read_file` 返回 4000 token 的内容；本轮开始新一次 LLM 调用
- When：组装消息
- Then：上一轮的 tool_result 已替换为面包屑（如 `read_file("path") → N 行，含 {key_fields}`）；LLM 仍能感知文件被读取及关键信息

**场景 6.4：摘要失败安全降级**
- Given：aux LLM（摘要模型）调用失败
- When：压缩触发，摘要步骤抛出异常
- Then：降级为静态截断（保留头尾，丢弃中段）；对话继续；不抛出未捕获异常；trace 中记录压缩失败原因

---

## 模块七：横切关注点

**场景 7.1：Trace 完整记录**
- Given：一次包含工具调用的完整 agent 运行
- When：`run()` 完成
- Then：`traces.jsonl` 中追加一条完整运行记录；包含 `llm_call`、`tool_call`、`finish` 事件；每个事件含时间戳、耗时、token 用量（LLM 事件）

**场景 7.2：审批门阻塞与放行**
- Given：`write_file` 风险等级 `medium`；用户触发该工具
- When：agent_loop 准备调用工具
- Then：执行暂停，等待审批；用户调用 approve API → 工具执行，结果返回 LLM；用户调用 reject API → LLM 收到「已拒绝」，主循环继续

**场景 7.3：成本预算超限停止任务**
- Given：`run_budget_usd=0.01`；当前运行已累计消耗 $0.01
- When：下一次 LLM 调用前检查预算
- Then：任务停止；触发 Grace Call 给用户一个总结回复；trace 中 `finish_reason = budget_exceeded`

**场景 7.4：取消信号穿透工具执行**
- Given：一次耗时的工具调用正在进行中（如 sandbox 执行长任务）
- When：外部发送取消信号
- Then：工具调用被中断（容器或连接被终止）；主循环收到取消信号后退出；trace 记录取消时间点；不留悬空进程
