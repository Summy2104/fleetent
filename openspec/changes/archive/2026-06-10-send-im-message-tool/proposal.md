## Why

agent 知道用户 id（c8297ebf 注入）却没有任何发消息工具——`outbound.py` 原语只接到审批门和调度器，未暴露给 agent。直接后果是 Jira 三个 bug 的共同根因：AAA-8037②（发私信受阻）、AAA-8034（被迫用 google mcp 代替发消息）、AAA-8052（无法向固定频道发通知）。审批分层批次 Change 3/3：把已验证的外发原语经 `@tool` 摆上 agent 菜单，并纳入 medium 审批门（Change 1 requester 路由 + Change 2 按钮使审批仅一次点击）。

## What Changes

- **新增内置工具 `send_im_message(target, text, target_type, platform)`**，注册 `risk_level="medium"`：底层复用 `outbound.is_reachable` + `outbound.send_to`；`platform` 留空默认当前会话平台
- **`ToolContext` 扩展 `outbound_connectors` 字段**：loop 已持有的连接器经既有 out-of-band 通道注入工具（与 `session_context` 同模式）；`run()`（IM 路径）填充，`run_stream()`（TUI/HTTP 路径）为空——工具在无连接器时返回明确错误说明
- **设计修正（偏离脑暴时方案 C，理由见 design D2）**：不做"当前会话目标直发"的按目标分流——回复当前会话本就是 reply 既有能力，工具的边际能力恰是"发给第三方"，全量 medium 门控概念正确，且避免触碰 loop「risk 永不取自 LLM 参数」的 anti-escape 红线

## Capabilities

### New Capabilities

- `builtin-outbound-tool`: agent 主动 IM 外发工具——send_im_message 的参数契约、medium 门控、连接器注入与可达性/失败语义

### Modified Capabilities

（无——ToolContext 字段扩展属实现细节，公开契约由新 capability 表述）

## Impact

- **代码**：`tools/registry.py`（ToolContext +1 字段）、`runtime/loop.py`（run() 路径 ToolContext 构造传入 outbound_connectors）、`tools/builtin_tools.py`（新工具）
- **模块边界**：owning package = `tools`；public API = `send_im_message`（经 registry 注册）+ `ToolContext.outbound_connectors`；owned tables = 无；config namespace = 无（复用 allowed_tools / approval_routing 既有配置）；依赖 `fleetent.outbound` public API；无 shim 需求
- **治理**：medium 注册 → 默认走审批（approval_routing 配 `requester` 即会话内一键批准）；`allowed_tools` 白名单不含它的 agent 看不到此工具
- **关单映射**：AAA-8037②、AAA-8034、AAA-8052
