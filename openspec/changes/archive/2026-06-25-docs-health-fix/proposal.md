## Why

文档审计发现多处内容与当前代码现状不一致：命名漂移（`shared_memory` → `agent_memory`）、架构说明缺口（managed 下 node-edge、outbound delivery queue）、路线图进度未随 Pilot 执行期刷新、archive 目录缺少"历史记录"标注导致旧文档被误作事实参考。这些偏差会降低文档可信度，影响新成员对架构的理解。

## What Changes

- `docs/capabilities/memory.md`：全量替换 "Shared Memory" → "Agent Memory"，同步 vector namespace 表述和 migration 文件名
- `docs/capabilities/im-gateway.md`：补充 managed 模式下 normalizer 宿主从 agent 改为 node 的说明；补充出站 queue / delivery 机制现状
- `docs/capabilities/platform.md`：更新 v1.0 规划状态，明确 Admin Web UI 的范围与当前实现差距
- `docs/architecture/directed-reach.md`：补充 `outbound_queue_store` 已落地的说明，与 delivery queue 集成状态对齐
- `docs/capabilities/scheduling.md`：更新 Webhook 现状说明（已从 `server.py` 移除，agent runtime API 形式尚未回归）
- `docs/operations/pilot-runbook.md`：补充 node supervisor / desired-state 验收流程
- `docs/operations/pilot-install-checklist.md`：补充 node 注册与 agent placement 检查项
- `docs/roadmaps/` 下 5 个路线图文件：刷新当前（2026-06-25）执行状态，将预测值改为执行事实
- `docs/archive/` 下过期文件：添加"历史记录"标注头，防止误当现状参考

## Capabilities

### New Capabilities
<!-- 无新 spec 需求 -->

### Modified Capabilities
<!-- 纯文档修复，不涉及 spec 级别行为变更，无需 delta spec -->

## Impact

- 仅影响 `docs/` 目录下的 Markdown 文档和 `docs/archive/` 下的历史文件
- 不涉及 `src/`、`tests/`、`openspec/specs/` 任何代码或规格变更
- 不破坏任何现有接口或行为
