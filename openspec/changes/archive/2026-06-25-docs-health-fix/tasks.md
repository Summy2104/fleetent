## 1. 命名漂移修复

- [x] 1.1 `docs/capabilities/memory.md`：全量替换 "Shared Memory" → "Agent Memory"，同步 vector namespace 和 migration 文件名引用

## 2. 架构说明缺口补充

- [x] 2.1 `docs/capabilities/im-gateway.md`：补充 managed 模式下 normalizer 宿主从 agent 改为 node 的说明，补充出站 queue / delivery 机制现状
- [x] 2.2 `docs/architecture/directed-reach.md`：补充 `outbound_queue_store` 已落地的说明，与 delivery queue 集成状态对齐
- [x] 2.3 `docs/capabilities/scheduling.md`：更新 Webhook 现状说明（已从 server.py 移除，agent runtime API 形式尚未回归）
- [x] 2.4 `docs/capabilities/platform.md`：更新 v1.0 规划状态，明确 Admin Web UI 范围与当前实现差距

## 3. 运维文档补充

- [x] 3.1 `docs/operations/pilot-runbook.md`：补充 node supervisor / desired-state 验收流程
- [x] 3.2 `docs/operations/pilot-install-checklist.md`：补充 node 注册与 agent placement 检查项

## 4. 路线图进度刷新

- [x] 4.1 `docs/roadmaps/intelligence-roadmap.md`：更新 Agent Memory（原 Shared Memory）状态
- [x] 4.2 `docs/roadmaps/platform-channel-roadmap.md`：刷新 Pilot 执行期进度
- [x] 4.3 `docs/roadmaps/runtime-tooling-roadmap.md`：刷新 Pilot 执行期进度
- [x] 4.4 `docs/roadmaps/observability-deployment-roadmap.md`：刷新 Pilot 执行期进度
- [x] 4.5 `docs/roadmaps/pilot-readiness-roadmap.md`：更新为执行事实

## 5. Archive 历史标注

- [x] 5.1 `docs/archive/internals/memory_layer.md`：添加历史记录标注头
- [x] 5.2 `docs/archive/2026-05-23-lean-agent-platform-mvp-design.md`：添加历史记录标注头
- [x] 5.3 `docs/archive/architecture-2026-06.md`：添加历史记录标注头
- [x] 5.4 `docs/archive/` 下所有 `AUTONOMOUS_EXECUTION_LOG` 和 `file-exchange-*` 文件：添加历史记录标注头
