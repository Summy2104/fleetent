# memory

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

跨 session 的用户事实提取与注入，让 agent 在多次对话中积累知识、越用越懂用户。

**调用关系**：
- 依赖：model_router（Haiku 提取）、config
- 被依赖：agent_loop（load + extract）

## 现状

- ✅ **事实提取**：对话结束后用 Haiku 异步提取用户相关事实，写入 JSONL
  - 提取不阻塞主响应，在 SSE done 之后异步执行
  - 存储路径：data/users/{user_id}/memories.jsonl

- ✅ **记忆注入**：每次 run() 开始前加载最近 20 条记忆注入 system prompt
  - 固定 top-20，无检索，无排序

## 规划中（v1.0）

- [ ] **向量相似度检索**：用 sqlite-vec 替代全量 top-20 注入
  - 根据当前对话内容召回最相关的记忆条目
  - 解决长期用户记忆质量下降问题

- [ ] **记忆重要性排序**：提取时为每条记忆打重要性分，注入时优先选高分条目

- [ ] **记忆去重与冲突检测**：新提取的事实与已有记忆冲突时自动合并或标记

## 验收标准

**场景 1：记忆跨 session 持久化**
- Given：用户在第一次对话中告知"我是后端工程师"
- When：用户开始第二次对话（新 session）
- Then：agent 在新 session 中能体现对用户身份的了解，无需用户重复说明

**场景 2：提取不阻塞响应**
- Given：一次正常对话
- When：agent_loop.run_stream() 发送 SSE done
- Then：记忆提取在后台执行，不延迟 done 事件

**场景 3：向量检索（v1.0）**
- Given：用户有 50 条历史记忆，当前话题是"Python 调试"
- When：开始新一轮对话
- Then：注入的记忆条目与"Python 调试"高度相关，而非固定最近 20 条

## 待决问题

- [ ] sqlite-vec 还是 DuckDB 做向量存储（负责人：待认领）
- [ ] 记忆条目的 embedding 模型选型：本地模型 vs API（影响 on-premises 部署）
