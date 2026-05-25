# observability

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

让每次 agent 运行可查、可分析、可排障。面向运维人员和管理员，不面向最终用户。

**调用关系**：
- 依赖：eval_logger、config
- 被依赖：agent_loop（写 trace）、server.py（未来的统计 API）

---

## 现状

- ✅ **append-only trace 日志**：每次 run 写一条 JSONL 到 `data/traces.jsonl`
  - 字段：`user_id`、`agent_name`、`model_used`、`usage`（input/output tokens）、`reply`、`duration`、`timestamp`

- ✅ **流式 token 统计**：在流式响应模式下，系统能够正确记录每次对话完整的输入和输出 token 用量，确保 trace 中的 usage 不为空。

---

## 规划中

- [ ] **日志级别**：支持 debug / info / warning / error 四级，运行时可配置输出级别
  - 低于当前级别的日志不写入文件，也不输出到控制台
  - error 级别日志附带报错文件名和行号，方便定位问题

- [ ] **按日期滚动日志文件**：日志按天写入独立文件，如 `data/logs/2026-05-25.log`
  - 时间戳精确到时分秒（HH:MM:SS）

- [ ] **性能耗时分解**：在 trace 日志中新增 `timing` 字段，以结构化 JSON 的形式，详细输出单次运行在各个阶段（记忆加载、模型调用、工具执行、记忆提取）的毫秒级耗时明细
  - 模型调用含每轮耗时，工具执行含每次调用耗时

- [ ] **结果来源标注**：回复附带来源标签，标明内容出处
  - 标签范围：`[记忆]`（来自 memory_layer 注入）、`[知识库]`（来自 skill/RAG）、`[推理]`（模型直接生成）
  - SSE 流中新增 `source` 事件，done 事件携带 `sources` 字段

- [ ] **每步 token 消耗**：多轮工具调用中，每一轮 LLM 调用的 token 用量单独记录
  - trace 中 `steps` 字段为数组，每个元素包含该轮的 `prompt_tokens`、`completion_tokens` 和触发的工具名（若有）

- [ ] **per-user token 统计**：按用户汇总历史 token 用量
  - CLI：`uv run fleetent-admin token-stats --user <user_id> [--period 2026-05]`
  - 输出：总 prompt_tokens、总 completion_tokens、总 turns、时间范围

- [ ] **per-agent token 统计**：按 agent 名称汇总 token 用量
  - CLI：`uv run fleetent-admin token-stats --agent <agent_name> [--period 2026-05]`
  - 输出格式同上

- [ ] **启动诊断**：服务启动失败时输出结构化诊断信息，说明具体原因
  - 覆盖场景：API key 缺失或无效、数据库不可写、MCP server 连接失败、配置文件解析错误
  - 每条诊断包含：组件名、失败原因、建议修复步骤

---

## 验收标准

**场景 1：trace 记录完整**
- **Given**：一次正常的 `/chat` 请求
- **When**：请求完成
- **Then**：`traces.jsonl` 新增一条记录，包含 `user_id`、`model_used`、`usage`、`duration`

**场景 2：流式响应下 usage 不为空**
- **Given**：客户端发起一次配置为流式 (streaming) 的 `/chat` 请求
- **When**：SSE 流结束
- **Then**：trace 中 `usage.input_tokens` 和 `usage.output_tokens` 均有值

**场景 3：日志级别过滤**
- **Given**：配置日志级别为 `warning`
- **When**：系统执行了一次正常对话（按预期会产生 `info` 级别的常规流转日志）
- **Then**：该条 `info` 日志不出现在日志文件中；`debug` 日志同样不出现

**场景 3b：error 日志含文件行号**
- **Given**：配置日志级别为 `error`，某模块抛出未捕获异常
- **When**：异常被记录
- **Then**：日志中包含报错的文件名和行号（如 `agent_loop.py:185`）

**场景 3c：debug 级别可开启**
- **Given**：配置日志级别为 `debug`
- **When**：系统执行一次工具调用
- **Then**：工具调用的入参、出参均出现在日志文件中

**场景 4：日志文件按日期生成**
- **Given**：服务在 2026-05-25 23:59 和 2026-05-26 00:01 各处理一次请求
- **When**：查看 `data/logs/` 目录
- **Then**：存在 `2026-05-25.log` 和 `2026-05-26.log` 两个文件，时间戳格式为 HH:MM:SS

**场景 5：性能追踪字段完整**
- **Given**：一次包含 2 次工具调用的 `/chat` 请求
- **When**：请求完成
- **Then**：trace 中 `timing` 字段包含 `memory_load_ms`、`llm_ms`（数组，每轮一条）、`tool_ms`（数组，每次调用一条）、`memory_extract_ms`

**场景 6：结果来源标注**
- **Given**：回复内容一部分来自记忆注入，一部分来自模型推理
- **When**：SSE 流结束
- **Then**：done 事件的 `sources` 字段包含 `["记忆", "推理"]`，不包含 `"知识库"`

**场景 7：启动诊断——API key 缺失**
- **Given**：未设置 `ANTHROPIC_API_KEY` 环境变量启动服务
- **When**：进程退出
- **Then**：stderr 输出包含组件名 `model_router`、原因 `ANTHROPIC_API_KEY not set`、建议 `export ANTHROPIC_API_KEY=...`

**场景 8：启动诊断——MCP server 不可达**
- **Given**：`config/mcp.yaml` 配置了一个无法连接的 server URL
- **When**：服务启动完成（非致命错误，不退出）
- **Then**：启动日志中输出 `warning` 级别诊断，包含 server id 和连接失败原因

**场景 9：每步 token 分解**
- **Given**：一次包含 2 轮工具调用的 `/chat` 请求（共 3 次 LLM 调用）
- **When**：请求完成
- **Then**：trace 中 `steps` 数组长度为 3，每个元素含 `prompt_tokens`、`completion_tokens`，工具调用轮次含对应工具名

**场景 10：per-user token 统计**
- **Given**：用户 alice 本月有 5 次对话，累计消耗 10000 prompt tokens、3000 completion tokens
- **When**：执行 `uv run fleetent-admin token-stats --user alice --period 2026-05`
- **Then**：输出显示 `prompt_tokens=10000`、`completion_tokens=3000`、`turns=5`

**场景 11：per-agent token 统计**
- **Given**：agent `support-bot` 本月被调用 20 次，累计 50000 prompt tokens
- **When**：执行 `uv run fleetent-admin token-stats --agent support-bot --period 2026-05`
- **Then**：输出显示 `agent_name=support-bot`、`prompt_tokens=50000`、`turns=20`

---

## 待决问题

- [ ] 结果来源标注的粒度：整条回复打一个标签，还是按段落/句子标注？（负责人：待认领）
- [ ] 启动诊断中 MCP 不可达是警告还是致命错误？（负责人：待认领）