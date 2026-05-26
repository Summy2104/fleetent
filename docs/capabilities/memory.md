# memory

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

per-user 语义记忆的提取、存储与检索，让 agent 在多次对话中积累用户知识、越用越懂用户。

**负责**：从对话中提取用户相关事实，按类型结构化存储，支持向量相似度检索。

**不负责**：企业文档知识（→ knowledge_base）、注入 system prompt 的协调与 token 预算（→ long_term_ctx）、记忆质量的定期优化（→ reflection）。

**调用关系**：
- 依赖：model_router（Haiku 提取与冲突判断）、vector_store（向量索引）、config
- 被依赖：long_term_ctx（检索注入内容）、reflection（读取现有记忆、写回优化结果）

## 现状

- ✅ **事实提取**：对话结束后用 Haiku 异步提取用户相关事实，写入 JSONL
  - 提取不阻塞主响应，在 SSE done 之后异步执行
  - 存储路径：data/users/{user_id}/memories.jsonl

- ✅ **记忆注入**：每次 run() 开始前加载最近 20 条记忆注入 system prompt
  - 固定 top-20，无检索，无排序
  - v1.0 后注入由 long_term_ctx 统一协调，memory_layer 只暴露 search() 接口

## 规划中（v1.0）

- [ ] **结构化记忆类型**：按类型区分存储，取代 free-text JSONL 平铺
  - `identity`：身份事实（姓名、职位、技能）— 永久有效
  - `preferences`：工作偏好（风格、输出格式偏好）— 长期有效
  - `context`：临时状态（当前项目、进行中任务）— TTL 30 天，过期自动失效

- [ ] **冲突检测与合并**：新提取的事实与已有同类记忆比较，冲突时合并或替换，不追加矛盾条目

- [ ] **向量相似度检索**：通过共享 vector_store 对记忆条目建立向量索引
  - 对外接口：`search(user_id: str, query: str) → List[MemoryItem]`
  - 由 long_term_ctx 在对话开始时调用

- [ ] **embedding 模型**：自托管本地模型（bge-m3 或 multilingual-e5）
  - 禁止使用 OpenAI Embeddings 等云托管专有服务

## 验收标准

**场景 1：记忆跨 session 持久化**
- Given：用户在第一次对话中告知"我是后端工程师"
- When：用户开始第二次对话（新 session）
- Then：agent 在新 session 中能体现对用户身份的了解，无需用户重复说明

**场景 2：提取不阻塞响应**
- Given：一次正常对话
- When：agent_loop.run_stream() 发送 SSE done
- Then：记忆提取在后台执行，不延迟 done 事件

**场景 3：冲突检测（v1.0）**
- Given：用户记忆中已有 identity 条目"用户是后端工程师"
- When：用户在新对话中说"我现在转做产品了"
- Then：旧条目被替换，不出现两条矛盾的身份记忆

**场景 4：向量检索（v1.0）**
- Given：用户有 50 条历史记忆，当前话题是"Python 调试"
- When：long_term_ctx 调用 memory_layer.search()
- Then：返回与"Python 调试"相关的记忆条目，而非固定最近 20 条

**场景 5：context 类记忆过期（v1.0）**
- Given：用户 35 天前提到"正在做支付系统项目"（context 类，TTL 30 天）
- When：该记忆被检索
- Then：不出现在返回结果中

## 待决问题

- [ ] 冲突判断粒度：同 type 下全量比较，还是只对语义相似度超过阈值的条目做冲突检测？（负责人：待认领）
- [ ] context TTL 起算点：首次提及时间，还是最后一次提及时间？（负责人：待认领）

## 相关能力域（待建文档）

以下能力域与 memory 共同构成长期上下文层：

| 能力域 | 职责 |
|--------|------|
| `knowledge-base` | 企业文档知识，per-tenant，与 memory 并列由 long_term_ctx 统一注入 |
| `reflection` | 定期优化 memory 内容；读取 traces，生成/改进 skills（per-agent） |
