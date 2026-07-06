# Design — fix-cron-store-and-once

## Context

三个缺陷均经可执行脚本复现实证（复现链条见 proposal）。关键现状：

- `schedule_store.update_run_state`（schedule_store.py:170-189）单条 UPDATE 无条件写全部四列；引擎侧 `_record_run` 只传 3 个参数 → 每次 fire 后 `next_run_at` 被写 NULL；下个 tick 撞进 `_tick` 中为 legacy 行准备的 backfill 分支重算重锚——注释写着 "freshly created, legacy row" 的兜底分支成了稳态路径。
- once 不经 CAS 推进（设计如此），`_complete_once` 仅在 `last_status=="ok"` 时终结 → 失败后 `next_run_at` 停在过去，每 ~2 tick 重跑。
- `_parse_run_at` / `compute_next_run` once 分支不接收 timezone；naive 值经 `_iso()`→`astimezone(UTC)` 按宿主系统时区解释，与工具 schema 承诺（「run_at 按 timezone 的本地时间解释」）矛盾。
- 测试盲区：poll-engine 测试 stub `_fire`；fire 测试 patch `update_run_state` 为 no-op（test_cron_scheduler.py:360,393）——接缝零覆盖。

### 模块边界影响声明

- **Owning package**：`fleetent.schedule_store`、`fleetent.cron_scheduler`（顶层 agent 侧模块）
- **Public API surface**：`update_run_state` 签名不变（新增 sentinel 默认值，向后兼容）；`_parse_run_at` 为模块内私有函数，新增 `tz` 参数；`compute_next_run` 公开签名已有 `tz` 参数（once 分支开始使用它）
- **Owned tables**：`scheduled_tasks`、`scheduled_task_runs`（无 schema 变更）
- **Config namespace**：无新增
- **Cross-module dependencies**：无新增；不触碰 `fleetent.platform.*`
- **Migration / shim plan**：无 schema 迁移。存量 naive `run_at` 行在下次 boot 注册时改按任务时区解释（即自动纠正为用户本意；此前按宿主时区解释本就是错的）

## Goals / Non-Goals

**Goals:**
- interval 恢复固定网格节奏，消除累积漂移（AAA-8288）
- once 失败一次即终结，杜绝无退避热重试的 LLM 花费
- fire 失败对用户可见（告警），对操作者可查（store 状态列存活）
- naive `run_at` 按任务时区解释，兑现工具契约
- 补上「fire → 写回 → 下个 tick」贯通测试

**Non-Goals:**
- 不做自动重试/退避机制（业界成熟答案是终结+告警，crontab/hermes 同此哲学；`run_now` 覆盖人工重试）
- 不改投递目标的创建期校验（change-2 范围）
- 不做 misfire 宽限、看门狗、tick 消抖（change-3 范围）
- 不加任何审批门（2026-07-06 决策）

## Decisions

**D1 — update_run_state 用模块级 sentinel 实现动态 SET**，而非拆成多个专用函数或 kwargs 白名单字典。`_UNSET = object()` 作默认值，SET 子句只包含 `is not _UNSET` 的列。备选「拆函数」（`record_fire_state` / `set_next_run`）语义更显但要改全部调用点且与嵌入式迁移风格不符；备选「保留 PUT + 调用方补全四列」把正确性责任摊给每个调用点，正是本 bug 的成因。

**D2 — once 失败 = 终结（enabled=0 + last_status="error"）**，采用 hermes 语义（once 无论成败只跑一次）而非「有界重试 + 退避」。理由：①失败告警（D3）使用户即时知情并可 `run_now` 重试，比静默自动重试更可控；②重试机制是 scheduling.md 的规划项，单独设计（execution_id 幂等、死信）不应夹带在 bugfix 中；③vixie cron 四十年不做重试，「简单核心 + 人工补救」是被验证的策略。落点：`_task_fire` 的 once 收尾从「仅 ok 终结」改为「ok → completed；error → error 终结」，实现于 `_complete_once` 扩展或并列的 `_close_once_failed`。

**D3 — 失败告警复用 `_deliver` 冻结文案路径，不跑 agent**：告警 = `_deliver(task, "⚠️ ...", connectors)`，与 notify 型同路径，零新依赖。**streak 抑制**：仅当前次 `last_status != "error"` 时发送（依赖 F1 修复后 last_status 可靠存活）——recurring 持续故障只在首次告警，恢复后再失败重新告警。once 必告警（随即终结，无 streak）。告警在 `_record_run` 写回**之前**读旧 `last_status` 判定、之后发送，避免自锁。

**D4 — `_parse_run_at(spec, tz)` 接收 IANA 时区名**：naive `fromisoformat` 结果 `replace(tzinfo=ZoneInfo(tz))`；相对时长与带 offset 输入不受影响。传参链：facade `create_task` 归一化时传任务 timezone（空则部署默认，经 `SchedulingSettings.default_timezone`——与 cron 的解析优先级一致）；`compute_next_run` once 分支同样传 `tz`。存量 naive 行为兼容：见迁移声明——按任务时区重解释即为纠错。

**D5 — 贯通测试的 mock 边界钉在 `_agent_run`**：真实 store（tmp SQLite + 嵌入式迁移）+ 真实 `_fire`/`_deliver`（connector 用假对象），只 stub `_agent_run` 返回固定文本。这是唯一能覆盖「fire → 写回 → 下个 tick」接缝且不引入 LLM 依赖的切面；沿用既有 `isolated_schedule_db` fixture。

## Risks / Trade-offs

- [once 失败不再自动重试，瞬时故障会丢一次提醒] → 失败告警让用户即时知情，`run_now` 一步重试；比修复前「静默重试到成功但可能晚数小时投递陈旧提醒」更符合预期
- [告警依赖连接器在线，连接器故障时告警也失败] → 接受：告警 best-effort，store/history 仍有完整记录；连接器恢复后下次失败会再告警（streak 以 last_status 判定）
- [update_run_state 行为变化影响未知调用方] → 全仓 grep 确认调用方仅 cron_scheduler 三处 + 测试；三处均为部分更新意图
- [存量 naive run_at 行重解释后触发时刻改变] → 这是纠错而非回归；变更行为写入 release note 即可

## Migration Plan

常规部署，无迁移步骤；回滚 = revert commit。`docs/capabilities/scheduling.md` 的 once 失败策略、run_at 时区语义、失败告警三节随本 change 更新。

## Open Questions

（无阻塞项）
