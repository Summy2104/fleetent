# observability

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

让每次 agent 运行可查、可分析、可排障。面向运维人员和管理员，不面向最终用户。

**调用关系**：
- 依赖：eval_logger、config
- 被依赖：agent_loop（写 trace）、server.py（未来的统计 API）

## 现状

- ✅ **append-only trace 日志**：每次 run 写一条 JSONL 到 data/traces.jsonl
  - 字段：user_id、agent_name、model_used、usage（input/output tokens）、reply、duration、timestamp

- ✅ **streaming usage 捕获**：run_stream() 从最后一个 chunk 提取 token 用量
  - 避免流式模式下 usage 为 null

## 规划中（v1.0）

- [ ] **USD 成本估算**：基于 model pricing 计算每次 run 的费用
  - 写入 trace 的 cost_usd 字段

- [ ] **per-user 累计统计**：汇总每个用户的 token 用量和费用
  - 支持按时间范围查询

- [ ] **用量查询 API**：GET /stats/usage，返回 per-user 汇总数据
  - 供管理后台或外部监控系统调用

- [ ] **结构化日志**：引入 structlog，替代 print/logging
  - 字段：timestamp、level、module、event、context
  - 支持 JSON 输出，方便日志系统采集

## 验收标准

**场景 1：trace 记录完整**
- Given：一次正常的 /chat 请求
- When：请求完成
- Then：traces.jsonl 新增一条记录，包含 user_id、model_used、usage、duration

**场景 2：streaming 下 usage 不为 null**
- Given：使用 run_stream() 的 HTTP 路径
- When：SSE 流结束
- Then：trace 中 usage.input_tokens 和 usage.output_tokens 均有值

**场景 3：成本估算（v1.0）**
- Given：使用 claude-sonnet 模型，产生 1000 input tokens + 500 output tokens
- When：run 完成
- Then：trace 中 cost_usd 按该模型的定价正确计算

**场景 4：per-user 用量查询（v1.0）**
- Given：用户 Alice 本月已有 10 次对话记录
- When：GET /stats/usage?user_id=alice&period=2026-05
- Then：返回本月累计 token 数和 USD 费用

## 待决问题

- [ ] model pricing 数据来源：写死配置 vs 从 API 获取（负责人：待认领）
- [ ] 统计数据存 traces.jsonl 实时聚合 vs 单独维护统计表（负责人：待认领）
