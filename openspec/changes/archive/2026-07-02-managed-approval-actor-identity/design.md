# Design — managed-approval-actor-identity

## 根因（代码级已确认）

审批授权校验两端处在不同身份空间：

| 端 | 用的身份 | 代码 |
|---|---|---|
| 记录"谁可审批" | 内部 user_id (UUID) | `permission_gate.py` `authorized.add(requester_user_id)`；`requester_user_id` = run `principal.user_id`，managed 入站已 `resolve_identity` 解析 |
| 判定"点击者是否有权" | **原始平台 id** | `slack.py:238 clicker=body.user.id`→`:258`；`telegram.py:103 clicker=cq.from_user.id`→`:120` |

`permission_gate.resolve()`（L317）`if approver_user_id not in authorized` → managed 下 `U09M5T71R25 ∉ {352a2162-…}` → `approval_unauthorized_actor` → 审批卡死不恢复。

**standalone**：`resolve_identity` 无注入 resolver → 原样返回平台 id → principal / 授权集 / clicker 三者都是原始平台 id → 天然匹配 → 正常。故 bug 仅 managed 复现，且 standalone-only 测试覆盖不到。

## 方案：决策人身份收敛到单一解析缝

**原则**：审批决策人身份，必须经过与入站消息**同一个** `resolve_identity` 缝解析，让整条审批链路统一活在"内部 user_id"空间。**不是移除映射**（那会砍掉跨渠道统一身份、让审批授权与全平台身份模型分叉），而是**把映射用一致**——按钮/命令路径补上入站消息早已在做的解析（`slack.py:543 / :673 user_id=identity`）。

### 新增 seam helper（`im_gateway/access.py`）

```python
def resolve_decision_actor(platform: str, platform_user_id: str, agent_name: str) -> str | None:
    """Resolve an IM approval decision actor into the run principal's identity space.

    The gate records authorized actors as the run's principal.user_id — under managed
    identity resolution that is the internal user id, not the raw platform id. Button/
    command handlers must resolve the acting user through the same seam so the
    authorization check compares like-for-like. Standalone (no injected resolver) returns
    the raw platform id unchanged. Returns None for a non-real/unresolvable id (fail closed).
    """
    try:
        return resolve_identity(platform, platform_user_id, agent_name or "default")
    except IMIdentityResolutionError:
        return None
```

- 复用既有 `resolve_identity`：managed（注入 resolver）→ 内部 UUID；standalone → 原样平台 id。零新依赖、零反向依赖。
- fail-closed：`resolve_identity` 对空/`unknown` 抛 `IMIdentityResolutionError` → 返回 None → 调用方按"无权/失败"处理，绝不放行 ghost。

### 两个按钮 handler 接入

- **Slack** `handle_approval_action`（`agent_name` 已在签名）：
  ```python
  clicker = (body.get("user") or {}).get("id", "")
  actor = resolve_decision_actor("slack", clicker, agent_name or "default")
  if actor is None:
      # fail closed → 原"无权审批"ephemeral
      ...
  found = await resolve_approval_request(..., approver_user_id=actor, ...)
  ```
  展示仍用原始 `clicker`（`by <@{clicker}>` mention）。
- **Telegram** `handle_approval_callback`（`agent_name` 已在签名）：同构，`resolve_decision_actor("telegram", str(cq.from_user.id), agent_name)`。

**文本 approve/reject 路径不改**：入站消息在 `slack._handle`(L673)/`_dispatch_assistant`(L543) 已把 `user_id=identity`（解析后内部 id）写入 `NormalizedMessage`，`normalizer` 用 `msg.user_id` 判权，本就一致。

## P1：物化不再静默降级（`materialize._apply_overrides`）

```python
try:
    merged = _deep_merge(base.model_dump(...), overrides)
    return AgentFile.model_validate(merged)
except Exception as exc:  # noqa: BLE001 — invalid override must not break deploy/preview
    _logger.error("agent_override_validation_failed", agent=base.name, error=str(exc))
    return base
```

只加 ERROR 日志（含 agent 名 + 具体校验错），行为（回退 base 保证 deploy/preview 不崩）不变——把"静默降级"变成"可诊断降级"。写入侧校验（坏配置不入库）为 AAA-8267 后续 task，本 change 不含。

## 边界与契约

- **agent⊥platform**：改动全在 agent 侧 edge（im_gateway）+ platform 侧自身（materialize）；无新增反向依赖，护栏保持绿。
- **owner-task**：无活资源改动。
- **兼容性**：standalone 审批行为逐字节不变（resolver=None → 原样 id）；managed 从"永远无权"修为"请求者/被通知审批人可决策"。

## 测试策略（分层）

- **unit**（`tests/unit/`）：
  - `resolve_decision_actor`：注入 resolver（managed）→ 内部 id；未注入（standalone）→ 原样；非真实 id → None。
  - `handle_approval_action` / `handle_approval_callback`：注入 resolver 映射 `U123→uuid-x`，mock `approval_store`/`session_mgr`/`resolve_approval_request`，断言传给 `resolve_approval_request` 的 `approver_user_id == uuid-x`（managed）；未注入时 == 原始 id（standalone）。
  - `_apply_overrides`：坏 override（悬空 model route）→ 返回 base **且**打出 `agent_override_validation_failed` ERROR（`caplog`）。
- 层：只 mock，无真实 DB → unit。
