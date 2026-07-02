## Why

**AAA-8266（P0）**：managed（node 托管、agent 自托管 IM）部署下，点击 Slack/Telegram 审批按钮报 `⚠️ 无权审批`，审批永远无法通过 → 挂起 run 不恢复 → 无结果（bi-intern claw1 稳定复现）。根因是**身份空间不一致**：

- permission gate 记录的"授权决策人集合"是 run 的 `principal.user_id`——managed 下入站已经过 `resolve_identity` 解析为**内部 user_id (UUID)**。
- 但审批按钮 handler（`slack.handle_approval_action`、`telegram.handle_approval_callback`）把交互 payload 里的**原始平台 id**（`body.user.id` / `cq.from_user.id`）直接当决策人传给 `resolve_approval_request`，**未经过 `resolve_identity`**。
- 两个 id 空间永不相等 → `permission_gate.resolve()` 判 `approval_unauthorized_actor`。

证据：claw1 journal `approval_unauthorized_actor id=3d00eab1 actor=U09M5T71R25`；`im_users` 映射 Slack `U09M5T71R25` → 内部 `352a2162-…`。**standalone 不复现**（无注入 resolver，principal 与 clicker 都是原始平台 id，天然一致）——所以 standalone-only 的测试漏掉了此路径（疑为「agent 自托管 IM」重构 30ef5ff9 引入）。

**AAA-8267（P1）**：`materialize._apply_overrides` 深合并 `config_overrides` 后若 `AgentFile` 校验失败，`except Exception: return base` **静默丢弃整包 override 且无任何日志**，一处无关坏字段（如悬空 model route）就会连累 IM 绑定被清空、agent 失联却无可观测信号。

## What Changes

- **P0（agent 侧 IM edge）**：审批决策路径在判权前，把点击/命令发起者的平台 id 经**同一个 `resolve_identity` 缝**解析成内部 user_id，与 gate 记录的授权集同处一个身份空间。
  - `im_gateway/access.py` 新增 `resolve_decision_actor(platform, platform_user_id, agent_name) -> str | None`（薄封装 `resolve_identity`；非真实/不可解析 id 返回 None = fail-closed）。
  - `slack.handle_approval_action` / `telegram.handle_approval_callback`：用解析后的内部 id 作 `approver_user_id`；解析失败 → 走原"无权审批"提示；原始 id 仅保留用于展示（`by @clicker`）。
  - **standalone 自动兼容**：未注入 resolver 时 `resolve_identity` 原样返回平台 id，三处仍一致，行为零变化。
  - 补 **managed 场景回归测试**（注入 identity resolver，断言请求者点自己按钮/命令能通过授权），堵住 standalone-only 测试盲区。
- **P1（平台侧物化，可观测性）**：`materialize._apply_overrides` 校验失败时打 **ERROR 日志**（agent 名 + 具体校验错），不再静默 `return base`。（写入侧校验为 AAA-8267 后续 task，本 change 不含。）

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `permission-gate`: 审批决策人身份在判权前 SHALL 经 IM 身份缝解析到与授权集同一空间（修复 managed 下请求者无法审批自己请求）。
- `agent-config-single-source`: 物化时无效的 `config_overrides` 被回退丢弃 SHALL 记录可诊断的 ERROR 日志，不得静默。

## Impact

- **owning packages**：`im_gateway/access.py`（新 helper）、`im_gateway/slack.py` + `im_gateway/telegram.py`（决策人解析）、`platform/agent_lifecycle/materialize.py`（P1 日志）。
- **public API surface**：新增 `access.resolve_decision_actor`（agent 侧 edge helper）。审批 handler 签名不变。
- **owned tables**：无。
- **config namespace**：无。
- **cross-module dependencies**：仅用既有 agent 侧 `resolve_identity` 缝；无新增 agent→platform 反向依赖。P1 只加日志，无新依赖。
- **migration / shim plan**：无迁移。行为变化：managed 下决策人 id 从原始平台 id 改为解析后的内部 id（这才是与授权集一致的正确值）；standalone 不变。
