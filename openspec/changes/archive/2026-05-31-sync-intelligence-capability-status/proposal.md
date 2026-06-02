## Why

常乐负责的 intelligence / observability / deployment 相关模块已经完成多批 foundation specs，
但部分 `docs/capabilities/*.md` 仍停留在旧状态，出现“尚未实现”、JSONL memory、top-20 注入等
过时描述。后续要讨论自动化效果验证、目录组织和服务化边界，必须先有一份与当前代码和 OpenSpec
归档状态一致的模块全貌。

## What Changes

- 同步常乐负责模块的 capability 文档状态：
  - `memory`
  - `long-term-ctx`
  - `knowledge-base`
  - `vector-store`
  - `reflection`
  - `observability`
  - `deployment`
- 为每个模块补充或修正：
  - 当前实现状态
  - 已完成 foundation
  - 仍不完整的能力缺口
  - 下一批候选 specs
  - 自动化效果验证缺口
  - 未来服务化 / 独立目录判断
- 不修改运行时代码。
- 不改变现有正式 specs 的行为要求。

## Capabilities

### Modified Capabilities

- `module-boundaries`：补充 intelligence 相关 capability 状态文档同步要求。

## Impact

- **代码**：无。
- **数据库**：无。
- **文档**：更新常乐负责模块的 capability 文档。
- **不包含**：
  - 不实现新功能。
  - 不创建自动化评估框架。
  - 不调整目录结构。
  - 不拆分服务。
