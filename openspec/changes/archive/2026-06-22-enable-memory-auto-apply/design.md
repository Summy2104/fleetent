## Context

reflection 维护提案的现状（grounding 2026-06-23）：

- `run_reflection(scope)`：读 trace + memory 信号 → 生成 findings → `_save_report` →
  `for memory_proposal in generate_memory_maintenance_proposals(...): _persist_memory_maintenance_proposal(...)` →
  skill 提案同理。**只生成+持久化，不 apply。**
- `reflection/scheduler.py`：`start_reflection_scheduler(interval, scope)` → `_reflection_loop` 周期调 `run_reflection(scope)`。
  `agent_app` 在 boot 时若 `reflection.enabled` 则启动它（`interval=reflection_settings.interval_seconds`）。
- `apply_memory_maintenance_proposal(proposal_id, *, actor_user_id=None, auto_policy=None)`：
  `auto_allowed = _auto_apply_allowed(proposal, auto_policy)`；不 allowed 时要求 owner + approved 状态，
  allowed 时直接 `_apply_maintenance_action` 落地。
- `_auto_apply_allowed`（两份相同副本：`reflection.py:1923` + `reflection_gate.py:503`）：
  `policy is not None and policy.allow_low_risk and risk=="low" and action not in {delete,merge,rewrite,compact}`。
- `_apply_maintenance_action` 处理的 user-memory 动作：`mark_stale`、`rewrite/compact`、`merge`、`delete`、
  `suggest_shared_memory_or_kb`（target=shared_memory → `shared_memory.apply_shared_memory_proposal`；
  target=knowledge_base → raise；target=None → legacy no-op）。
- `AutoMaintenancePolicy(allow_low_risk: bool = False)`：从未实例化。
- `ReflectionSettings`（agent.yaml）：`enabled: bool=False`、`interval_seconds: float=86400`，`extra="forbid"`。

**两个问题**：(1) policy 永远 None → auto-apply 死；(2) `suggest_shared_memory_or_kb` 生成时 `risk="low"` 且不在黑名单
→ 若开启 auto-apply 会绕过 team 审批写共享记忆。

## Goals / Non-Goals

**Goals:**
- 让 auto-apply 真正可启用，**默认 OFF、仅显式 opt-in**。
- 自动应用范围严格限定为 **owner 自己的、非破坏的低风险 user-memory 维护**（实际只有 `mark_stale`）。
- 堵住 `suggest_shared_memory_or_kb` 被 auto-apply 的安全洞。
- auto-apply 失败舱壁化，绝不波及 reflection loop 或其它提案。

**Non-Goals:**
- 不接 skill auto-apply（skill 恒人批）。
- 不改 approver 找对人（A4）/ 平台 resolve（A3）。
- 不引入新的"auto-apply 扫描器"独立组件——复用既有 scheduler 触发点。

## Decisions

**D1 · 配置：`reflection.auto_apply.allow_low_risk`（默认 false）**。在 `agent_config.py` 新增
`class ReflectionAutoApplySettings(BaseModel)`（`extra="forbid"`，`allow_low_risk: bool=False`），
`ReflectionSettings` 增字段 `auto_apply: ReflectionAutoApplySettings = Field(default_factory=...)`。
未配置 = 默认 OFF。映射到 `AutoMaintenancePolicy(allow_low_risk=...)` 1:1。

**D2 · 触发点：scheduler 线程传 policy 进 run_reflection**。
- `agent_app`：boot 时构造 `policy = AutoMaintenancePolicy(allow_low_risk=settings.auto_apply.allow_low_risk)`，
  传 `start_reflection_scheduler(interval=..., scope=..., auto_policy=policy)`。
- `start_reflection_scheduler` / `_reflection_loop` 增 `auto_policy` 透传。
- `run_reflection(scope, *, auto_policy: AutoMaintenancePolicy | None = None)`：在 persist 各 memory 提案后，
  对该提案调用 `apply_memory_maintenance_proposal(proposal.id, auto_policy=auto_policy)`（仅当 auto_policy 非 None）。
  白名单不符的提案 `_auto_apply_allowed` 返回 False、apply 因无 actor_user_id 抛 PermissionError → 被 D4 的 best-effort 吞掉、
  提案保持 pending 等人批。**不传 auto_policy = 当前行为完全不变**（向后兼容测试/手动调用）。

  *为何放 run_reflection 内而非 scheduler 里再查库*：刚生成的提案在手，无需按 scope 重新查询（`list_memory_maintenance_proposals`
  按 `subject_user_id` 查，而 scope 与 user_id 的对应是既有语义，绕开它最稳）。

**D3 · 判定改正向白名单（安全修复）**。两处 `_auto_apply_allowed` 一致改为：
```
policy is not None and policy.allow_low_risk
and proposal.risk == "low"
and proposal.action in _AUTO_APPLY_ACTIONS   # {"mark_stale"}
```
正向白名单比黑名单安全：未来新增 action 默认**不可** auto-apply，必须显式加白名单。`suggest_shared_memory_or_kb`
（写共享记忆、需 team 审批）与所有破坏性动作自然被排除。

**D4 · 舱壁化**。run_reflection 内的 auto-apply 逐条独立 try/except，失败只 `_logger`/observability 记录，
continue 下一条；任何 auto-apply 异常**不得**中断提案持久化循环、不得使 `run_reflection` 抛出、不得波及 `_reflection_loop`。

## Risks / Trade-offs

- **白名单收窄到只剩 mark_stale**：当前低风险非破坏 user-memory 动作实际只有 mark_stale，符合"只省最烦人小事"的意图。
  若未来要把别的动作纳入 auto-apply，需显式扩 `_AUTO_APPLY_ACTIONS` 并评估审批归属——这是有意的保守默认。
- **两份 _auto_apply_allowed 副本**：A1 已决定不合并 gate fallback 副本（属 A3）。本切片必须**两处同步改**，
  否则两条路径判定漂移。靠测试在两处各断言一次白名单行为。
- **policy 经 boot 一次性读取**：改 agent.yaml 后需重启 agent 才生效（与 `enabled`/`interval_seconds` 一致，符合既有约定）。
- **auto-apply 静默**：失败被 best-effort 吞、提案留 pending——这是期望行为（降级为人工审批），但需确保有日志可观测，
  不致"以为自动处理了其实没有"。测试需覆盖"失败→留 pending+有日志"。
