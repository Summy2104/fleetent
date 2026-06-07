## Context

session-restart-recovery 在 agent_app._start_infra 启动时调 scan_and_mark_recent 标记近期活跃 session。normalizer 处理 IM 消息时 load→run→save，但从不读 resume_pending，标记永久残留。

## Goals / Non-Goals

**Goals:**
- IM 消息处理时检测 resume_pending，记日志，清除标记（消费闭环）
- best-effort，不阻断消息处理

**Non-Goals:**
- 不实现「续接特殊行为」——已落盘 session 文件 + load 读回完整历史即是续接基础
- 不动 CLI 路径（一次性进程不涉重启恢复）

## Decisions

### D8：消费位置与清除时机

**位置**：normalizer.py，`session_mgr.load(session_id)`（L157）之后，构建 system / 跑 loop 之前。

**清除时机**：检测到立即清除（load 后即 clear），而非 save 后。理由：
- resume_pending 是「这次请求是中断恢复」的一次性提示；一旦本次请求开始处理，标记已完成使命
- 即使本次 run 失败，session 文件仍在，下次仍能正常 load；不需要靠 resume_pending 重试
- 立即清除避免「run 失败 → 标记残留 → 下次又报 resumed」的误报

**容错**：整段 try/except 包裹，`get_meta`/`clear_resume_pending` 失败仅记 warn，不阻断消息处理（标记消费是辅助，不能拖垮主流程）。

## Risks / Trade-offs

- **[风险] 清除后 run 失败，丢失「中断」信息** → 可接受：session 文件完整，下次正常处理；resume_pending 仅运营可见性，非数据正确性依赖
- **[风险] get_meta 增加一次 DB 读** → 每条 IM 消息多一次轻量 SELECT；session_meta 按主键查，开销可忽略

## Migration Plan

无 schema 变更。部署即生效。已标记的 session 在下次 IM 消息到来时被消费清除。
