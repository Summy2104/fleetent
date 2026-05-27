# agent-runtime

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

核心 agent 执行引擎，负责 LLM 调用、工具执行、Skill 注入、上下文管理。是其他所有能力域的执行基础。

**调用关系**：
- 依赖：model_router、tool_registry、skill_registry、context_mgr、long_term_ctx、eval_logger、session_mgr
- 被依赖：server.py（HTTP 路径）、normalizer（IM 路径）、cron_scheduler（定时路径）

## 现状

- ✅ **tool-use 循环**：while 循环持续调用 LLM，处理 tool_calls 直到 finish_reason=stop
  - run()：完整循环，返回 string，供 CLI / IM 使用
  - run_stream()：async generator，yield SSE event dicts，供 HTTP 使用
  - run_sync()：asyncio.run(run()) 的同步封装

- ✅ **model fallback 链**：LLM 返回 429/503 时自动重试 fallback 模型
  - RouteConfig 支持 fallbacks: list[str]
  - 重试耗尽后抛出异常，trace 中记录实际使用的 model

- ✅ **内置工具**：time、calculate、read_file、write_file、run_code、sub_agent
  - @tool / @tool(risk_level="medium/high") 装饰器注册
  - import tools.py 即触发注册（副作用）

- ✅ **MCP 工具集成**：HTTP + stdio 两种传输方式
  - 工具命名：{server_id}__{tool_name}（双下划线）
  - server 启动时 register_all() 自动注册
  - 与内置工具共存于同一 tool_registry

- ✅ **Docker 沙箱代码执行**：run_code 工具通过 Docker 隔离执行
  - --network none --memory 256m --cpus 0.5 --read-only
  - 执行完毕自动清理容器
  - 降级方案（宿主机无 `/dev/kvm`）：Docker + gVisor runtime + seccomp profile，隔离级别较低，需在部署文档中注明

- ✅ **Skill 注入**：用户输入关键词匹配 SKILL.md description，命中后注入 system prompt
  - server 启动时 scan()，CLI 每次调用时 scan()
  - 首次命中原则，顺序相关

- ✅ **in-session 上下文压缩**：token 超 80% 阈值时自动压缩历史消息
  - keep_tail 保留最后 n 条，使用 identity check（m is tail[0]）防误判
  - 保留完整 tool pair，不在 tool call 中间截断

- ✅ **sub_agent 并行**：asyncio.gather 并发执行多个子 agent
  - 最大深度 1，sub_agent 内过滤 sub_agent 工具防递归
  - 每个子 agent 使用全新上下文
  - child trace 记录 `parent_session_id` 字段，可通过 traces.jsonl 追踪完整调用链

## 规划中（v1.0）

- [ ] **sub_agent 生命周期管理**：当前为 fire-and-forget，无法感知子任务阻塞或失败
  - 加 SQLite 状态表：pending → in_progress → done/failed
  - 支持超时检测与失败重试

- [ ] **多模态输入支持**：接收图片等非文本内容并透传给 LLM
  - 支持 base64 编码图片作为消息内容
  - 边界：音频/视频暂不支持

## 验收标准

**场景 1：基本对话**
- Given：用户通过 HTTP 发送消息，LLM 无需调用工具
- When：POST /chat
- Then：SSE 流式返回文本，最终发送 done 事件，traces.jsonl 写入一条记录

**场景 2：工具调用**
- Given：用户消息触发工具调用（如 calculate）
- When：LLM 返回 tool_calls
- Then：工具执行结果回传 LLM，LLM 继续生成最终回复

**场景 3：高风险工具审批**
- Given：工具 risk_level="high"
- When：agent_loop 准备调用该工具
- Then：暂停执行，通知用户审批 ID；用户 approve 后继续；用户 reject 后取消

**场景 4：model fallback**
- Given：RouteConfig 配置了 fallbacks，主模型返回 429
- When：agent_loop 发起 LLM 调用
- Then：自动切换到 fallback 模型重试，trace 记录实际使用的 model_used

**场景 5：上下文压缩**
- Given：session 历史超过 token 阈值（80%）
- When：新一轮 LLM 调用前
- Then：历史被压缩，保留最后 10 条完整 turn，LLM 调用正常继续

## 待决问题

- [ ] sub_agent 状态表设计：状态机字段、超时时间默认值（负责人：待认领）
