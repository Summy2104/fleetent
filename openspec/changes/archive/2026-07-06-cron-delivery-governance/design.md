# Design — cron-delivery-governance

## Context

AAA-8279「发错频道」的三条腿：half-set 参数静默回落（`builtin_tools.py` schedule create 仅当 `notify_platform and notify_target` 同时存在才组装 `deliver`）、generate 无目标照建、回执不显示目标。另有 fired run 可调 `schedule` 自我增殖的防御缺口。2026-07-06 决策：不加审批门——既有 spec 本就声明 `schedule` "SHALL NOT require human approval"，治理限于创建期校验与透明化。

### 模块边界影响声明

- **Owning package**：`fleetent.tools.builtin_tools`（schedule 工具）、`fleetent.schedule_store`、`fleetent.cron_scheduler`、`fleetent.runtime.loop`（工具排除通路）
- **Public API surface**：`schedule` 工具参数集不变（校验收紧）；`loop.run`/`_run_inner` 新增 `exclude_tools: frozenset[str] = frozenset()` 参数（内部参数，非公开 API；默认空集，不影响任何既有调用方）
- **Owned tables**：无变化
- **Config namespace**：无新增
- **Cross-module dependencies**：无新增；不触碰 platform
- **Migration / shim plan**：无

## Goals / Non-Goals

**Goals:**
- 投递目标错配在创建当下即可被发现（half-set 拒绝 + 回执明示/警示）
- fired run 无法创建/修改定时任务

**Non-Goals:**
- 不加审批门（决策）；不做目标 ACL/频道成员资格校验（IM 侧成员查询成本与权限面均超出本 change；错发风险由创建期透明化缓解）
- 不改 fire 期投递语义（change-1 已覆盖 no_delivery_target）

## Decisions

**D1 — half-set 校验放工具层**：`notify_platform`/`notify_target` 是工具参数概念（store 只见组装后的 `deliver` dict），工具层在组装前校验并返回 `error: notify_platform 与 notify_target 须成对提供（缺 <名>）`。备选「store 层校验」无从下手——store 看不到 half-set。

**D2 — 无目标 generate 放弃「创建时硬拒绝」，改为回执警示（实现期二次修正）**：第一次修正曾计划把校验从 store 层挪到工具层（避免 store 层测试基础设施的大范围破坏，见下方 Risks 的历史记录）。落地工具层校验时发现 blast radius 依然不小：仅 `tests/integration/test_tools_schedule.py` 一个文件内就有 7 个只测 create 其它维度（返回 id、注册 live job、pause/resume/remove 生命周期、owner stamping、degrade 文案）的既有测试，因为从不传 `origin`/`notify_target` 而会被新增的硬拒绝一并打断——为了改这些测试而改这些测试，不是在修 AAA-8279。同时注意到：无目标 generate 的**唯一真实风险**（produce 了内容却无处可去）已经被 change-1 的 fire-time `no_delivery_target`（记 error）+ 失败告警**完整覆盖**——用户在第一次触发时就会收到 ⚠️ 告警，创建时硬拒绝只是把这个信号提前几分钟到几小时，边际价值有限。于是改为**创建回执警示**：目标不可解析时在回执里追加一行警示文本（不阻断创建，`create` 仍成功）。这个方案零测试破坏面（现有测试只断言特定字段/子串，不断言「回执不含警示行」），且警示 + change-1 的 fire 期兜底两道防线组合，实际防护力不弱于硬拒绝。`deliver={"mode":"none"}`（显式不投递）不触发警示——那是有意配置，不是遗漏。

**D3 — fired run 排除 `schedule` 的机制（实现比原计划更简单）**：原计划把既有的 `suppress_outbound_tools` 布尔通路参数化为排除集合。实现时发现更简单的路径：`_filter_outbound_tools` 新增一个**正交**的 `exclude: frozenset[str] = frozenset()` 参数，与 `suppress` 独立生效（`names_to_drop = exclude | (outbound集 if suppress else 空)`），不改动 `suppress_outbound_tools` 参数本身的既有语义与其它调用方。`loop.run`/`_run_inner` 透传新增的 `exclude_tools` 参数（默认空集，交互路径不传，行为零变化）；`cron_scheduler._agent_run` 固定传 `exclude_tools=frozenset({"schedule"})`——generate/action 两类 fired run 统一排除，不需要按 task_type 分支。备选「工具内检测 fire 上下文自拒」被否：schema 中仍可见工具会持续诱导模型调用后失败，不如 schema 级不可见（hermes 同选择：cron 上下文直接禁 `cronjob` toolset）。
**取舍**：action 任务失去「自我管理」能力（如到期自删）——接受；once 自动完结覆盖主要场景，recurring 自删属罕见需求，由用户交互式操作。

**D4 — 回执格式**：显式目标 `投递目标: slack:C123(channel)`；origin 回落 `投递目标: 创建会话（origin）`；**目标不可解析**（无显式目标、无 origin、非 `mode=none`）→ `⚠️ 未配置投递目标且无法从当前上下文捕获——本任务触发产出的内容将无法送达（可用 notify_target 指定，或该任务本就无需广播）`；均追加在既有 create 回执（含 next_fire_hint）之后，不改既有断言依赖的前缀文案。

## Risks / Trade-offs

- [警示而非硬拒绝，用户可能忽略回执里的警示文本、仍然创建了无效任务] → 接受：change-1 的 fire-time `no_delivery_target` + 失败告警是真正的安全网，创建期警示只是「越早发现越好」的锦上添花，不是唯一防线
- [排除集合参数化改动 loop.run 内部通路，可能影响交互路径] → 交互路径不传排除集，行为零变化；用既有 `test_cron_typed_dispatch.py` 模式断言两类 fired run 的 schema 差异
- [目标 id 打错仍会发错（无 ACL 校验）] → 回执明示 + change-1 失败告警共同缓解；ACL 属 Non-Goal 留待真实需求

## Migration Plan

常规部署；回滚 = revert。工具 schema 描述文案随代码同版发布，无独立迁移。

## Open Questions

（无阻塞项）
