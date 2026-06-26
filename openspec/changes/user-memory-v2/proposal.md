## Why

现有用户记忆系统用自由文本片段存储记忆，无结构导致去重失效、事实冲突无法追踪、近似重复持续累积。以三元组（subject, relation, object）+ 状态机替换自由文本模型，从根本上解决这三个问题。

## What Changes

- **BREAKING** 废弃 `memory_items` 表及其 identity/preferences/context 三分类模型
- **BREAKING** 废弃 `extract_and_update()` 现有接口，替换为基于三元组流水线的新实现
- **BREAKING** 废弃 `search()` 现有接口，替换为返回 `Fact` 结构的新接口
- 新增 `facts` 表存储三元组事实，`fact_edges` 表记录 supersedes 链，`relation_clusters` 表维护可扩展词表
- 新增写入流水线：LLM 提取三元组 → relation 归并 → 并发裁决 → 状态机提交
- 新增生命周期机制：短期记忆靠 `last_accessed_at` 自然消亡，高频命中自动升级为长期，用户可主动 pin/retract
- 新增后台 job：定期 archive 超过 30 天未命中的短期记忆、`valid_until` 到期的记忆

## Capabilities

### New Capabilities

- `user-memory-facts`: 三元组事实存储模型——facts 表、fact_edges 表、relation_clusters 词表的 schema 定义与嵌入式迁移
- `user-memory-pipeline`: 写入流水线——LLM 提取三元组、relation 归并、并发 classify_relation 裁决、状态机事务提交
- `user-memory-lifecycle`: 生命周期机制——短期记忆消亡（last_accessed_at 30天窗口）、自动升级（access_count + 首次命中跨度）、用户 pin/retract、valid_until 时间边界
- `user-memory-search`: 检索接口——向量检索、存活过滤、max score 门控、access 计数异步更新

### Modified Capabilities

- `memory-layer`: 现有 memory-layer spec 的所有 requirement 被上述新 capability 完全替换，原 spec 标记为 deprecated

## Impact

- `src/fleetent/memory/` 全模块重写：store.py、extraction.py、operations.py、search.py、maintenance.py、models.py
- `src/fleetent/runtime/agent_app.py`：boot 时注入新的 facts DB schema
- `src/fleetent/memory/agent_memory_migrations.py`（或新建 facts_migrations.py）：嵌入式迁移脚本
- `tests/unit/` 和 `tests/integration/`：memory 相关测试全部重写
- 现有 `memory_items` 数据无迁移路径，旧记忆在升级后不可用（新系统从零开始积累）
