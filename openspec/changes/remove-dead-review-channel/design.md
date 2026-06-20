## Context

审批门统一(R1)后,`reflection_gate.resolve_review_channel`(返回硬编码 "im")成死代码:生产零调用,真实审批渠道由 `resolve_approvers` + `_notify_approvers` 承担(`self-evolution-split` spec 已如此描述)。

## Goals / Non-Goals

**Goals:** 删 `resolve_review_channel` + `ReviewRoute` + 4 个对应测试;在 spec 固化"无独立 review-channel helper"。

**Non-Goals:** 不碰统一审批三侧;不碰 live 的 `_shared_memory_reviewer` 簇与 `_load_proposal_type`。

## Decisions

### D1:只删 resolve_review_channel + ReviewRoute,reviewer 解析器留着

已核实 `_shared_memory_reviewer`/`set_shared_memory_reviewer`/`_default_shared_memory_reviewer` 在 `reflection_gate.py:~496` live apply 路径决定 actor;`_load_proposal_type` 被 live resolve(行 ~120)与待删的 resolve_review_channel(行 ~61)共用——删后 `_load_proposal_type` 仍有 live 调用方,保留。仅 `resolve_review_channel` + 其专用返回类型 `ReviewRoute` 是死的。

### D2:spec 加守门 scenario

`self-evolution-split`「审批渠道按 proposal 类型路由」MODIFY,加一条 scenario 断言"代码中不存在独立 review-channel helper",把清理后状态写进 spec,防止以后又长出并行渠道路由。

## Risks / Trade-offs

- **[误删 live 代码]** reviewer 解析器与 `_load_proposal_type` 易被连带误删。→ tasks 2.2 显式核查它们仍在。零行为变更,被删函数无生产调用方。
