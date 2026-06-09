## Context

`runtime/loop.py` `_plan_run_slots`（~726 行）现以 `risk in ("medium","high") and reply_func and permission_gate_enabled` 决定是否走审批，否则直跑。approval-routing 刚合并入 main（permission_gate default-closed、approval_store 持久化、per-agent timeout）。run_code + 5 个文件工具（C3/C4）已在 sandbox 容器内自隔离。约束：纯 agent 运行时、不改 permission_gate 契约、不碰 run_stream（streaming-approval-gating 独立未合并）。

## Goals / Non-Goals

**Goals:**
- 把隐式风险分支抽成显式四级×四 mode 的 Action Gate，纯函数可单测。
- CRITICAL 结构性硬拒，不可配置、不可经 LLM 参数绕过。
- fail-closed：证明不了安全（未知风险 / 无法保证 sandbox 隔离）一律升级。
- 默认零行为变化（兼容刚合并的 approval-routing）；medium/high mode 可配置以支持审批最小化。

**Non-Goals:**
- 不改 run_stream 审批（另一 change 负责）。
- 不实现「把任意 medium 工具塞进 sandbox 执行」的通用沙箱包装——sandbox-backed 是工具自身属性（run_code/文件工具已自隔离），gate 只识别该属性，不代为容器化。
- 不做 critical 工具的具体定级（本 change 只提供 reject 档与机制；哪些工具是 critical 由后续/部署标注）。

## Decisions

**D1：Action Gate 是纯函数 + 枚举，放 `governance/action_gate.py`。**
`resolve_action_mode(risk, *, medium_mode, high_mode, sandbox_capable, force_ask) -> ActionMode`。纯函数无副作用、无 IO，便于穷举单测。放 governance（横切治理），与 permission_gate / agent_policy 同域。

**D2：风险→mode 映射规则（含 fail-closed 顺序）。**
```
if risk == "critical":            return REJECT          # 硬编码，最高优先级，配置不可覆盖
mode = {none/low: DIRECT, medium: medium_mode, high: high_mode}.get(risk, APPROVAL)  # 未知→APPROVAL(fail-closed)
if force_ask:                     mode = APPROVAL         # hook ask 升级（critical 已在上面返回，不受影响）
if mode == SANDBOX and not sandbox_capable: mode = APPROVAL  # 无法保证隔离→升级(fail-closed)
return mode
```
顺序关键：critical 最先（不可被 force_ask 或配置改变）；未知风险落 APPROVAL 而非 DIRECT（fail-closed）。

**D3：sandbox_capable 是工具属性，用已知集合判定。**
`SANDBOX_BACKED_TOOLS = {"run_code","read_file","write_file","edit_file","search_content","search_files"}`，`is_sandbox_backed(name)` 查表。这些工具（C3/C4）已在容器内操作 `/workspace`，故 mode=SANDBOX 对它们等价「已隔离、无需审批」。其他工具即便配 medium_mode=sandbox 也会被 D2 的 fail-closed 升级为 APPROVAL。备选：registry 加 `@tool(sandbox_backed=True)` 元数据——否决（增大装饰器面，且当前集合稳定、集中），留作后续。

**D4：loop 接入——替换分支，不改审批调用。**
`_plan_run_slots` 内 `risk = get_risk_level(name)` 之后：
```
mode = resolve_action_mode(risk, medium_mode=..., high_mode=..., sandbox_capable=is_sandbox_backed(name), force_ask=force_ask)
if mode is REJECT:  placeholder("tool execution rejected by action gate: {name} (critical risk)", counts_failure=False); state.approval_rejected=True; continue
if mode is APPROVAL and reply_func and permission_gate_enabled:  <既有 request_approval 块>
# DIRECT / SANDBOX / (APPROVAL 但 gate 未启用) → 落 pending slot 执行
```
审批块原封不动（含 `risk if risk in ("medium","high") else "medium"` 归一化），只是触发条件从「risk 命中」变为「mode==APPROVAL」。

**D5：配置默认值保持兼容。**
GovernanceConfig + AgentFile 新增 `action_gate_medium_mode`/`action_gate_high_mode`，默认 `"approval"`，与现状一致。合法值 `direct|sandbox|approval`（critical 不可配，reject 仅 critical 走）。AgentFile 用 `Literal` 校验。

**D6：反逃逸 = risk 只来自 registry。**
get_risk_level(name) 按工具名查服务端注册表，与 tool_args 无关；测试构造「args 里塞 risk/risk_level 字段」证明不影响定级。

**D7：no_reply→reject 复用现有 default-closed。**
permission_gate 已在联系不到审批人时立即 reject（非 timeout）。本 change 不改 permission_gate，只加回归测试把该语义锁定为 Action Gate 的「无人可审=拒绝」契约。

## Risks / Trade-offs

- **与刚合并 approval-routing 的契约张力**：原 6-change 设计默认 medium=sandbox；为不破坏刚落地的 medium→approval 契约与其测试，本 change 默认 medium=approval、sandbox 改为可配置 opt-in。审批最小化的收益由配置开启 + C5（allow-always 指纹）共同达成。已在 proposal 标注供最终审核。
- **SANDBOX_BACKED_TOOLS 硬编码集合**：新增 sandbox-backed 工具需同步该集合，否则其 medium=sandbox 会被 fail-closed 升级为 approval（偏保守，安全侧）。可接受：fail-closed 不会造成不安全放行。
- **critical 档暂无工具命中**：本 change 只建机制；价值在后续把删除/外发等标 critical。提供机制本身即结构性兜底。

## Migration Plan

增量：新增字段有兼容默认；loop 分支改写后默认行为与 main 完全一致（穷举单测 + loop 集成回归保证）。无数据迁移。Rollback：还原 `_plan_run_slots` 分支为 risk 直判。
