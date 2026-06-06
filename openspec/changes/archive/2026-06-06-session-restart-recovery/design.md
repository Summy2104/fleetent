## Context

session 维护任务（`start_session_maintenance`）在 `agent_app._start_infra` 启动，不在 platform server lifespan——platform server 已不维护 session（见 server.py 注释 platform-control-plane）。因此重启恢复扫描也应挂在 agent_app。

## Goals / Non-Goals

**Goals:**
- agent 进程重启时，自动标记近期活跃 session 为 resume_pending
- 提供标记的读写接口（mark/clear/list）
- 启动扫描 best-effort，不阻断 boot

**Non-Goals:**
- 不实现「消费」resume_pending 的续接逻辑（normalizer/loop 层后续 wiring）
- 不持久化进行中的 loop 状态（仅标记，下次请求续接靠已落盘的 session 文件）
- 不在 platform server lifespan 扫描（session 不归 platform server）

## Decisions

### D6：扫描挂在 agent_app._start_infra，非 server.py lifespan

**决策**：resume 扫描在 `agent_app._start_infra` 的 `start_session_maintenance()` 之后调用。

**理由**：
- platform server 注释明确「no longer maintains sessions at boot」
- session 维护任务本身就在 _start_infra 启动，恢复扫描与之同址，职责一致
- agent run 进程才是 session 的实际宿主

### D7：120 秒窗口 + 标记式恢复

**决策**：扫描 `updated_at > now - 120s` 的 session 标记 resume_pending。窗口 120 秒（对标 hermes-agent）。

**理由**：重启通常在秒级完成；120 秒窗口覆盖「重启前最后活跃」的 session，又不会把早已结束的旧 session 误标。标记式（而非保存 loop 状态）：下次请求时已落盘的 session 文件 + resume_pending 标记足以让上层决定续接。

## Risks / Trade-offs

- **[风险] 标记后无消费逻辑** → 本 change 只建机制；标记可被 list_resume_pending 查询，消费是后续 wiring。标记本身无副作用（仅一个 flag）
- **[风险] 窗口内但已正常结束的 session 被误标** → resume_pending 是提示非强制；消费层可结合 status=ended 排除。本 change 不做该判断

## Migration Plan

migration 056 加 resume_pending INTEGER default 0，向后兼容。已有行为 0。启动扫描 best-effort，扫描失败仅记 warn，boot 继续。
