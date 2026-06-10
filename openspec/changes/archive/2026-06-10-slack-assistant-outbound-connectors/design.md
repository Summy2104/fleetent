## Context

`slack.py` 两条入站路径构造 `NormalizedMessage`：`_handle`（channel/普通 DM）已传
`outbound_connectors={"slack": client}`；`_route_assistant_message`（Assistant 面板 DM）
漏传，导致该路径下 ToolContext / permission_gate 拿不到连接器。

## Goals / Non-Goals

**Goals:** assistant-pane 路径与 `_handle` 对齐，补传连接器。
**Non-Goals:** 任何其他路径/平台改动。

## Decisions

**D1 直接在 NormalizedMessage 构造处补字段**——`client` 已在函数签名中，零结构改动。

## Risks / Trade-offs

- 无（纯补漏，行为只可能从"报错"变"可用"）

## Migration Plan

纯增量，无迁移。
