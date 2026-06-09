## Why

Action Gate（C2）让 high（及可配 medium）操作走人工审批门，但**同一操作每次都要重新审批**——审批人对「这个 agent 反复跑同一条已确认安全的命令」要一遍遍点批，审批疲劳会导致「全批」或关闭审批门，反而削弱治理。需要在不牺牲「危险操作受控」的前提下**最小化重复审批**。

借鉴 openclaw 的 allow-always 指纹：审批人批准时可选「永久允许」，对该 (用户, 工具, 参数) 指纹持久记账；之后**相同指纹的调用自动放行**，无需再次打扰审批人。不同操作（不同指纹）仍照常审批。

## What Changes

- **新增 allow-always 指纹存储**（`governance/approval_allowlist_store.py`，纯 agent-side ensure_schema 表，**不经 alembic**，与 `approval_store` 同模式）：`approval_allowlist(fingerprint PK, scope_key, tool_name, created_at, created_by)` + `is_allowed/add_grant/list_grants`。
- **指纹纯函数** `fingerprint(scope_key, tool_name, tool_args)`：scope_key = 请求者 user_id；对 `tool_args` 取规范化 JSON（键排序）后与 scope/tool 一起 sha256。同一 (用户, 工具, 参数) → 同一指纹；任一不同 → 不同指纹。
- **`permission_gate.request_approval` 前置查指纹**：命中 allow-list → 写一条 `auto_approved` 审计行、**直接返回 approved**，不联系审批人（审批最小化）。未命中 → 照常审批，并记下本次 pending 指纹供 resolve 使用。
- **`permission_gate.resolve` 增加 `always: bool=False`**：当 `always and decision==approved` 时把该指纹写入 allow-list（持久）。默认 False，现有 resolve 调用方（server / tui）行为不变。
- **IM 审批指令支持 `approve always <id>`**（`im_gateway/normalizer.py` 扩展正则）：审批人回 `approve always <id>` → `resolve(always=True)`，授予永久允许；`approve <id>` 仍只批这一次。

无 BREAKING：不开 allow-always 时行为与 C2 完全一致；指纹存储为新表（IF NOT EXISTS）。

## Capabilities

### New Capabilities
- `approval-minimization`: allow-always 指纹契约——审批人可对 (请求者, 工具, 参数) 指纹授予持久「永久允许」，后续相同指纹调用在审批门自动放行；指纹由服务端规范化参数计算（不同参数不复用）；授予经审批人显式 `approve always` 动作、持久化、可审计；默认关闭时审批行为不变。

### Modified Capabilities
<!-- 无：permission-gate 的请求/解析契约被扩展（前置指纹查 + resolve always 参数），默认值保持既有行为；action-gate 路由不变。 -->

## Impact

- **代码**：新增 `governance/approval_allowlist_store.py`；`governance/permission_gate.py`（request_approval 前置查指纹 + pending 指纹记账；resolve 增 always 持久化）；`im_gateway/normalizer.py`（`approve always` 解析）。
- **约束**：纯 agent 运行时（governance/ + im_gateway/），不依赖 platform；ensure_schema-only 表（不经 alembic，drift guard 不覆盖该表）。
- **测试**：unit（指纹稳定性/敏感性；命中 allow-list 自动放行不联系审批人；resolve always 持久化指纹；`approve always` 解析）；integration（allow-list store 真实 SQLite CRUD + 持久化）。
- **依赖**：基于已合并 main 的 action-gate + approval-routing（permission_gate）。
