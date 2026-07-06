# Design — cron-hardening

## Context

评审发现的健壮性弱点集（详见 proposal），参照两套成熟实现收敛策略：vixie-cron 对时间跳变的五档分类（wild 任务不逐槽补跑、定点任务有界补跑、超 3h 放弃追赶）与 hermes-agent 的 inactivity 看门狗（600s）、grace 公式（半周期 clamp [120s, 2h]）、绝不静默禁用 recurring（#16265）。

**依赖**：F6.2 禁用告警复用 change-1（fix-cron-store-and-once）落地的 `_deliver` 冻结文案投递路径——本 change 须在 change-1 合并后 apply。实现时发现禁用告警不应直接调用 change-1 的 `_maybe_alert_failure`（那个助手内建了「fire 失败 streak」抑制语义——同一任务连续失败只告警一次）：boot 禁用是**一次性终结事件**（该任务从此不会再被注册，没有「下一次失败」的概念），套用 streak 抑制反而可能因任务历史的 `last_status` 巧合等于 `"error"` 而被误吞。改为直接复用 `_deliver` 本身（同样的目标解析 + 连接器发送 + best-effort 语义），跳过 streak 判定。

### 模块边界影响声明

- **Owning package**：`fleetent.cron_scheduler`、`fleetent.config`（SchedulingSettings）、`fleetent.tools.builtin_tools`、`fleetent.schedule_store`（`_decode` 容错）
- **Public API surface**：`schedule` 工具新增可选 `session` 参数（向后兼容）；`SchedulingSettings` 新增 `fire_timeout_seconds` 字段
- **Owned tables**：无 schema 变更（`missed` 状态已在 run-history 词汇表；`anchor` 列保留不迁移）
- **Config namespace**：`scheduling.fire_timeout_seconds`（默认 900，0=关闭）
- **Cross-module dependencies**：无新增；不触碰 platform
- **Migration / shim plan**：无

## Goals / Non-Goals

**Goals:**
- 宕机多日不补发陈旧定点任务；坏数据、卡死运行、静默禁用三类故障模式收敛；session 绑定用户可达；触发抖动亚秒化

**Non-Goals:**
- 不做重试/退避机制（同 change-1 立场）；不做跨进程锁（单进程模型不变）；不改 once 恢复窗口语义（既有 spec 已有界）；`anchor` 列不做删除迁移

## Decisions

**D1 — 宽限公式固定 `min(半周期, 2h)`，不加配置**：hermes 同公式（clamp [120s, 2h]）且 vixie 的 3h 界同量级；可配置性收益低于配置面膨胀成本。半周期由 CronTrigger 相邻两次 fire 差近似（hermes `_compute_grace_seconds` 同法）。判定点在 `_tick` 的 due 选择处：`now - next_run_at > grace` → `claim` 到未来值后**不 dispatch**，改记 `missed` history 行。只对 `cron` 型启用；`interval` 无日历身份、补跑即时内容，维持现状（与 vixie「wild 任务不逐槽补」一致——fleetent 本就不逐槽补，此处只是不加上界）。

**D2 — per-row 容错的切面**：`_tick` 对每行的处理包 try/except（含 `_decode` 抛出的 JSON 错误——`list_tasks` 改为逐行 decode、坏行跳过并记 warning，而非整批抛出）。备选「只在 `_decode` 吞错返回原始字符串」被否：下游会把字符串当 dict 用，错误后移更难定位。

**D3 — 看门狗用 `asyncio.wait_for` 包 `_dispatch` 的 `_run()` 内层**（信号量获取之后、`view.func()` 周围），超时 `CancelledError` 语义天然传播到 agent run 内部的 await 点；`finally` 已保证 `_inflight.discard`，信号量经 async with 自动释放。默认 900s 参考 hermes 600s inactivity + fleetent fired run 含 LLM 多轮的余量；0=关闭兜底罕见超长任务。备选「activity 追踪式 inactivity 超时」（hermes 式）更精细但需 agent loop 暴露活动心跳，超出本 change 范围，留待需要时演进。

**D4 — tick 对齐睡眠**：`_run_tick_loop` 睡眠时长 = `min(tick_interval, 最早 next_run_at - now)`，下界 0.5s。最早到期时刻从 `_jobs` 视图取（内存内，无额外查询）；空任务集回落 tick_interval。不改 `tick_interval_seconds` 默认值与语义（仍是扫描上界）。

**D5 — `session` 参数直通**：工具参数 `session: str = ""` → `session_id=session or None` 传入既有 facade 链，语义零新增。参数名用 `session`（面向模型的简洁名）而非内部列名 `session_id`。

**D6 — 死代码**：删除 `cron_scheduler._parse_cron` 与引用它的孤儿断言；`anchor` 列保留（删除列需迁移且无收益），在 `schedule_store.create` 的 docstring 标注 vestigial。

## Risks / Trade-offs

- [看门狗误杀合法超长任务] → 默认 900s 高于典型 fired run 一个数量级；可配置、可关闭；超时记录含运行时长便于诊断后调参
- [missed 判定改变宕机恢复行为，用户可能期待补跑] → 宽限 2h 覆盖常见重启窗口；超 2h 的「补跑」本质是发陈旧内容（AAA-8279 类投诉的另一形态）；release note 写明
- [对齐睡眠使 tick 频率在密集任务下升高] → 下界 0.5s + 到期即触发本就是目标行为；空闲时仍按 tick_interval 慢扫
- [list_tasks 逐行 decode 改变其对坏行的可见性（跳过而非抛错）] → 工具 `list` 看不到坏行——由 F6.2 的禁用告警与 warning 日志补偿可见性

## Migration Plan

依赖 change-1 合并后常规部署；回滚 = revert（新配置项缺省即默认行为，无配置迁移）。

## Open Questions

（无阻塞项）
