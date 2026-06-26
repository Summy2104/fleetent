## Why

用户问"我的所有记忆 / 你记得我什么"时，agent 列不全。根因：记忆只通过 `build_context()` 的**语义 top-N 检索**（`search_facts`，limit=10）自动注入到 prompt，agent 没有主动、全量读取记忆的能力。当 query 是"列出全部"这类元查询时，它与具体事实（如 `张洋|works_at=Northstar`）语义不相关、向量召回排不上，再叠加 limit 截断，导致 agent 嘴里的"所有记忆"只是被注入的那 top-N，实测漏掉整个第三方实体。

"查看自己有哪些记忆"是用户对记忆系统的基本诉求（可见性、可纠错）。这需要一条**全量列举**路径，而非语义检索。

## What Changes

- 新增 facts 全量查询接口 `list_active_facts(user_id, subject=None)`：直接查库返回该 user_id 名下全部 active facts（按 user_id 物理隔离的整个记忆空间），可选按 subject 过滤；不走向量检索、无 top-N 截断。
- 新增 agent 工具 `recall_memory(subject=None)`：agent 在用户要求查看记忆（全部 / 某个人）时主动调用，返回结构化的全量记忆列表。工具按当前会话的 user_id 取记忆，subject 为空时返回该用户名下所有 subject（user 本人 + agent + 第三方）的事实。
- `memory` 公开接口暴露 `list_active_facts`。

非目标：不改 `build_context` 的语义 top-N 自动注入（日常相关记忆仍走它，本 change 只补"主动全量列举"）；不改 facts 写入/检索语义；不引入分页（全量返回，单用户记忆量级小）。

## Capabilities

### New Capabilities

- `memory-recall-tool`: agent 主动全量读取用户记忆的能力——facts 全量列举接口 + agent 工具，使"列出我的所有记忆 / 某个人的记忆"可被完整、准确回答。

### Modified Capabilities
<!-- 无 -->

## Impact

- **owning package**: `tools`（新工具）+ `memory`（新接口）
- **public API surface**: `memory.list_active_facts(user_id, subject=None) -> list[Fact]`；新工具 `recall_memory` 注册进工具表
- **owned tables**: 无（只读现有 facts 表）
- **config namespace**: 无
- **cross-module dependencies**: `tools` 依赖 `memory.list_active_facts` public API；`memory` 不新增反向依赖
- **migration / shim plan**: 无（纯新增，不动现有路径）
- **affected code**: `memory/facts_store.py`（新增查询）、`memory/__init__.py`（暴露）、`tools/`（新工具注册）、对应 unit/integration 测试
