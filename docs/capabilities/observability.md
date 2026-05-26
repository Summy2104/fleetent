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

- [ ] **日志级别**：支持七级，按严重度从高到低：`silent` / `fatal` / `error` / `warn` / `info` / `debug` / `trace`，运行时可配置输出级别
  - 低于当前级别的日志不写入文件，也不输出到控制台
  - 各级含义：
    - `silent`：完全静默，不输出任何日志（测试 / 关闭日志场景）
    - `fatal`：致命错误，进程无法继续（服务启动失败、配置损坏、关键依赖缺失）
    - `error`：操作失败，进程可继续（单次 API 调用失败、tool 执行抛异常、session 崩溃）
    - `warn`：异常但已处理，功能可能降级（重试、rate limit 退避、字段截断、MCP server 不可达）
    - `info`：正常运行的关键事件（服务启动成功、session 创建/销毁、agent 触发）
    - `debug`：调试细节，生产默认不开（路由决策、工具调用入参/出参、记忆匹配过程）
    - `trace`：最细粒度，逐函数调用级（原始 Webhook payload、每次 LLM chunk、heartbeat）
  - `fatal` 和 `error` 级别日志附带报错文件名和行号，方便定位问题

- [ ] **日志字段规范**：每条日志包含以下结构化字段

  | 字段 | 说明 | 示例 |
  |------|------|------|
  | `timestamp` | 时间戳，精确到毫秒 | `2026-05-26T14:32:01.123+08:00` |
  | `level` | 日志级别 | `info` |
  | `logger` | 日志器名称，标识产生日志的模块 | `agent_loop` / `mcp_client` / `server` |
  | `session_id` | 会话 ID，跨日志追踪同一对话 | `sess-abc123` |
  | `user_id` | 触发本次操作的用户 | `user-uuid-xxx` |
  | `agent_name` | 处理本次请求的 agent | `support-bot` |
  | `model` | 实际使用的模型 | `claude-sonnet-4-5` |
  | `source` | 触发来源 | `slack` / `webhook` / `cli` / `cron` |
  | `tokens` | 本次消耗 token，含 `prompt` 和 `completion` | `{"prompt": 512, "completion": 128}` |
  | `duration_ms` | 本次操作耗时（毫秒） | `1340` |
  | `message` | 日志实际内容 | `tool calculate called` |

  - 非 agent 运行类日志（如启动、配置加载）中 session_id / user_id / agent_name / model / tokens / duration_ms 字段留空
  - `fatal` / `error` 级别额外附带 `file`（报错文件名）和 `line`（行号）

- [ ] **按日期滚动日志文件**：日志按天写入文件，同一天生成两份：
  - `data/logs/2026-05-25.log` — 完整日志，记录所有级别
  - `data/logs/2026-05-25.error.log` — 仅记录 `warn` / `error` / `fatal`，方便排错
  - 时间戳精确到时分秒（HH:MM:SS）

- [ ] **双通道输出**：日志同时写入文件和终端，两个通道独立配置
  - 终端：实时输出，human-readable 格式（带颜色、级别标识）
  - 文件：JSON 格式，便于日志系统采集和程序解析
  - 两个通道可分别设置日志级别（如终端 info、文件 debug）
  - 任一通道写入失败不影响另一通道

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

- [ ] **敏感信息脱敏**：日志和 trace 写入前自动脱敏，防止敏感字段明文落盘
  - 脱敏范围：API key（`sk-*`、`ma-*` 等格式）、Bearer token、密码字段（`password`、`secret`、`token` 等 key 名）、手机号、邮箱
  - 脱敏规则：保留前 4 位 + `****`（如 `sk-an****`），不可逆
  - 脱敏在写入 JSONL / 日志文件前统一处理，不影响运行时传递的原始值

- [ ] **日志 CLI 工具**：通过 `fleetent-admin` 查询日志，无需直接操作文件

  ```
  # 查看最新 N 行日志
  fleetent-admin log tail [--n 100]

  # 实时跟踪，持续输出新日志
  fleetent-admin log follow

  # 按条件过滤查询（可组合）
  fleetent-admin log query [--user <user_id>] [--agent <agent_name>] [--level warn] [--keyword <text>] [--n 200]

  # 动态调整运行中服务的日志级别（无需重启）
  fleetent-admin log set-level <level>
  fleetent-admin log set-level <level> --channel console
  fleetent-admin log set-level <level> --channel file
  ```

  过滤条件可任意组合，如：
  - `--user alice --level error` — alice 的报错
  - `--agent support-bot --keyword "timeout"` — support-bot 中含 timeout 的日志

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

**场景 3：双通道同时输出**
- **Given**：配置终端级别 info、文件级别 debug
- **When**：服务处理一次请求，产生 debug、info、warning 各一条日志
- **Then**：终端显示 info 和 warning 两条；日志文件写入全部三条

**场景 3a：两通道格式独立**
- **Given**：双通道均已启用
- **When**：写入同一条 warning 日志
- **Then**：终端输出带颜色的 human-readable 格式；文件中为 JSON 格式同一条记录

**场景 3b：文件通道故障不影响终端**
- **Given**：日志目录不可写（磁盘满）
- **When**：服务继续运行
- **Then**：终端日志正常输出，服务不崩溃，文件写入失败记录一条 error 到终端

**场景 3：日志级别过滤**
- **Given**：配置日志级别为 `warn`
- **When**：系统执行了一次正常对话（产生 `info` 级别日志）
- **Then**：`info`、`debug`、`trace` 日志均不出现在日志文件中；`warn` 及以上正常写入

**场景 3c：fatal / error 日志含文件行号**
- **Given**：配置日志级别为 `error`，某模块抛出未捕获异常
- **When**：异常被记录为 `error` 或 `fatal`
- **Then**：日志中包含报错的文件名和行号（如 `agent_loop.py:185`）

**场景 3d：trace 级别可开启**
- **Given**：配置日志级别为 `trace`
- **When**：收到一条 Webhook 请求
- **Then**：原始 payload 和每次 LLM chunk 均出现在日志文件中

**场景 3e：silent 完全静默**
- **Given**：配置日志级别为 `silent`
- **When**：服务正常运行并处理请求
- **Then**：终端无任何输出，日志文件无任何写入

**场景 3f：日志字段完整性**
- **Given**：用户 alice 通过 Slack 向 support-bot 发送一条消息，触发工具调用
- **When**：请求完成，写入日志
- **Then**：日志条目包含 `timestamp`（毫秒精度）、`level=info`、`logger=agent_loop`、`session_id`、`user_id=alice`、`agent_name=support-bot`、`model=claude-sonnet-4-5`、`source=slack`、`tokens.prompt`、`tokens.completion`、`duration_ms`、`message`

**场景 3g：非 agent 日志字段留空**
- **Given**：服务启动，写入一条 `info` 级别的启动成功日志（由 `server` 模块产生）
- **When**：查看日志
- **Then**：该条记录含 `timestamp`、`level`、`logger=server`、`message`，`session_id`、`user_id`、`tokens`、`duration_ms` 字段为空或不存在

**场景 4：日志文件按日期生成，每天两份**
- **Given**：服务在 2026-05-25 产生 info、warn、error 各若干条；在 2026-05-26 00:01 再处理一次请求
- **When**：查看 `data/logs/` 目录
- **Then**：
  - 存在 `2026-05-25.log`（含全部级别）和 `2026-05-25.error.log`（仅含 warn/error/fatal）
  - 跨天后生成 `2026-05-26.log` 和 `2026-05-26.error.log`
  - 所有文件时间戳格式为 HH:MM:SS

**场景 4a：error.log 内容正确**
- **Given**：2026-05-25 产生 10 条 info、3 条 warn、2 条 error
- **When**：查看 `2026-05-25.error.log`
- **Then**：仅有 5 条记录（3 warn + 2 error），info 不出现

**场景 5：性能追踪字段完整**
- **Given**：一次包含 2 次工具调用的 `/chat` 请求
- **When**：请求完成
- **Then**：trace 中 `timing` 字段包含 `memory_load_ms`、`llm_ms`（数组，每轮一条）、`tool_ms`（数组，每次调用一条）、`memory_extract_ms`

**场景 6：结果来源标注**
- **Given**：回复内容一部分来自记忆注入，一部分来自模型推理
- **When**：SSE 流结束
- **Then**：done 事件的 `sources` 字段包含 `["记忆", "推理"]`，不包含 `"知识库"`

**场景 7：log tail 查看最新 N 行**
- **Given**：日志文件已积累数百条记录
- **When**：执行 `fleetent-admin log tail --n 50`
- **Then**：输出最新 50 行日志，不阻塞，立即返回

**场景 7a：log follow 实时跟踪**
- **Given**：服务正在处理请求
- **When**：执行 `fleetent-admin log follow`
- **Then**：终端持续输出新产生的日志，Ctrl+C 退出

**场景 7b：log query 按用户过滤**
- **Given**：用户 alice 产生了若干条日志，其中有 error
- **When**：执行 `fleetent-admin log query --user alice --level error`
- **Then**：仅返回 alice 的 error 及以上日志

**场景 7c：log query 按 agent 过滤**
- **Given**：agent `support-bot` 产生了 30 条日志
- **When**：执行 `fleetent-admin log query --agent support-bot --n 10`
- **Then**：返回 support-bot 最新 10 条日志

**场景 7d：log query 关键词搜索**
- **Given**：日志中有多条含 `timeout` 的记录
- **When**：执行 `fleetent-admin log query --keyword "timeout"`
- **Then**：返回所有含 `timeout` 的日志行，按时间升序

**场景 7e：log query 多条件组合**
- **Given**：agent `ops-bot` 有多条日志，其中部分含 `calculate`
- **When**：执行 `fleetent-admin log query --agent ops-bot --keyword "calculate" --level warn`
- **Then**：返回同时满足三个条件的日志

**场景 7f：log set-level 动态生效**
- **Given**：服务正在运行，当前终端级别为 `info`
- **When**：执行 `fleetent-admin log set-level debug --channel console`
- **Then**：无需重启，后续终端立即输出 `debug` 级别日志；文件通道级别不变

**场景 7f：启动诊断——API key 缺失**
- **Given**：未设置 `ANTHROPIC_API_KEY` 环境变量启动服务
- **When**：进程退出
- **Then**：stderr 输出包含组件名 `model_router`、原因 `ANTHROPIC_API_KEY not set`、建议 `export ANTHROPIC_API_KEY=...`

**场景 7g：启动诊断——MCP server 不可达**
- **Given**：`config/mcp.yaml` 配置了一个无法连接的 server URL
- **When**：服务启动完成（非致命错误，不退出）
- **Then**：启动日志中输出 `warn` 级别诊断，包含 server id 和连接失败原因

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

**场景 12：API key 脱敏**
- **Given**：工具调用的参数中包含字段 `api_key=sk-ant-abc123456`
- **When**：trace 写入 `traces.jsonl`
- **Then**：文件中该字段值为 `sk-a****`，原始值不出现在文件中

**场景 13：Bearer token 脱敏**
- **Given**：日志中记录了一条含 `Authorization: Bearer ma-deadbeef...` 的请求头
- **When**：写入日志文件
- **Then**：日志中显示 `ma-d****`，完整 token 不落盘

**场景 14：运行时值不受影响**
- **Given**：agent 调用工具时传入含敏感字段的参数
- **When**：工具实际执行
- **Then**：工具收到的是原始未脱敏值，脱敏仅发生在日志写入阶段

---

## 待决问题

- [ ] 结果来源标注的粒度：整条回复打一个标签，还是按段落/句子标注？（负责人：待认领）
- [ ] 启动诊断中 MCP 不可达是警告还是致命错误？（负责人：待认领）