# Design — cron-delivery-governance

## Context

AAA-8279「发错频道」的三条腿：half-set 参数静默回落（`builtin_tools.py` schedule create 仅当 `notify_platform and notify_target` 同时存在才组装 `deliver`）、generate 无目标照建、回执不显示目标。另有 fired run 可调 `schedule` 自我增殖的防御缺口。2026-07-06 决策：不加审批门——既有 spec 本就声明 `schedule` "SHALL NOT require human approval"，治理限于创建期校验与透明化。

### 模块边界影响声明

- **Owning package**：`fleetent.tools.builtin_tools`（schedule 工具）、`fleetent.schedule_store`、`fleetent.cron_scheduler`、`fleetent.runtime.loop`（工具排除通路）
- **Public API surface**：`schedule` 工具参数集不变（校验收紧）；`loop.run` 的工具抑制通路从「outbound 布尔」推广为可携带排除集合（内部参数，非公开 API）
- **Owned tables**：无变化
- **Config namespace**：无新增
- **Cross-module dependencies**：无新增；不触碰 platform
- **Migration / shim plan**：无

## Goals / Non-Goals

**Goals:**
- 投递目标错配在创建当下即可被发现（拒绝 + 回执明示）
- fired run 无法创建/修改定时任务

**Non-Goals:**
- 不加审批门（决策）；不做目标 ACL/频道成员资格校验（IM 侧成员查询成本与权限面均超出本 change；错发风险由创建期透明化缓解）
- 不改 fire 期投递语义（change-1 已覆盖 no_delivery_target）

## Decisions

**D1 — half-set 校验放工具层**：`notify_platform`/`notify_target` 是工具参数概念（store 只见组装后的 `deliver` dict），工具层在组装前校验并返回 `error: notify_platform 与 notify_target 须成对提供（缺 <名>）`。备选「store 层校验」无从下手——store 看不到 half-set。

**D2 — generate 目标可解析性校验放 store 层**，镜像既有 notify 校验（`create` 中 `notify` 已要求 `deliver or origin`）：`generate and deliver is None and origin is None → ValueError`。所有创建路径（工具、facade、直调）统一受检；`deliver={"mode":"none"}` 天然放行（deliver 非 None）。工具层照既有模式把 `ValueError` 转 `error:` 文本。实现前先 grep 仓内是否存在合法的「无目标 generate」创建点（如 reflection/内部任务），若有则该调用点显式传 `mode="none"`。

**D3 — fired run 排除 `schedule` 的机制**：沿 `_agent_run` → `loop.run` 既有的 `suppress_outbound_tools` 通路推广——`loop.run` 内部把「被抑制工具名集合」从固定的 outbound 集改为参数化：generate fire 传 outbound 集 ∪ {`schedule`}，action fire 传 {`schedule`}，交互路径不传（全量工具）。备选「工具内检测 fire 上下文自拒」被否：schema 中仍可见工具会持续诱导模型调用后失败，不如 schema 级不可见（hermes 同选择：cron 上下文直接禁 `cronjob` toolset）。
**取舍**：action 任务失去「自我管理」能力（如到期自删）——接受；once 自动完结覆盖主要场景，recurring 自删属罕见需求，由用户交互式操作。

**D4 — 回执格式**：显式目标 `投递目标: slack:C123(channel)`；origin 回落 `投递目标: 创建会话（origin）`；追加在既有 create 回执（含 next_fire_hint）之后，不改既有断言依赖的前缀文案。

## Risks / Trade-offs

- [收紧创建校验使既有「无目标 generate」调用方开始报错] → D2 的 grep 前置排查 + 显式 mode="none" 迁移；工具路径用户得到明确指引文本
- [排除集合参数化改动 loop.run 内部通路，可能影响交互路径] → 交互路径不传排除集，行为零变化；用既有 `test_cron_typed_dispatch.py` 模式断言两类 fired run 的 schema 差异
- [目标 id 打错仍会发错（无 ACL 校验）] → 回执明示 + change-1 失败告警共同缓解；ACL 属 Non-Goal 留待真实需求

## Migration Plan

常规部署；回滚 = revert。工具 schema 描述文案随代码同版发布，无独立迁移。

## Open Questions

（无阻塞项）
