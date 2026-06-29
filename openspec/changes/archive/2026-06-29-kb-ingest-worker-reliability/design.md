## Context

`kb_ingest_jobs`(迁移 099)有 `status` / `attempts` / `claimed_at` 列。worker(`knowledge_base/worker.py`)长驻 claim/drain;admin 端点(`kb_admin_api`)入队后 `_wait_for_kb_ingest_job` 阻塞轮询,`_KB_INGEST_WAIT_TIMEOUT_SECONDS=30`,超时返回 `{"status":"pending"}`。当无 worker 运行时该 pending 与"正常排队"无法区分 → 静默失败。

## Goals / Non-Goals

**Goals:**
- worker 存活可观测;admin 非终态状态能区分"无活跃 worker(降级)"与"处理中"。

**Non-Goals:**
- 不引入 in-process drain / 任何绕过队列的 ingest 路径(现有 spec 排除,worker 是唯一消费者)。
- 不改失败重试语义、入队 seam、轮询超时的同步体验。
- worker 进程编排(supervisor / compose service)属部署,本 change 只要求"受管常驻 + 可观测",具体 compose 接线与 dockerize-deploy-stack 协同。

## Decisions

### 决策:存活判定优先复用 `claimed_at`,避免新表
- **方案 A(默认):claim-age 启发** —— 控制面查 `kb_ingest_jobs`:若存在 pending job 且最近 N 秒内无任何 job 的 `claimed_at` 推进,判为无活跃 worker。零新 schema。
- **方案 B:独立 heartbeat 行** —— worker 周期写一张 `kb_worker_heartbeats`(或单行 ops 表)last_seen。更直接(能区分"worker 活着但空闲"),但需 Alembic 管理库迁移。
- **取舍**:默认 A(无迁移、够用——降级判定关心的是"有没有人在 claim",空闲且无 pending 时无需判活)。若实现中发现"worker 活着但长期空闲、又恰有新 job"误判,升级到 B。**实现阶段定**,spec 只要求"可观测 + 区分降级",不锁机制。

### 决策:degraded 是端点响应的显式状态,不改轮询/超时契约
- `_wait_for_kb_ingest_job` 超时返回前,查存活判定:活跃 → `in_progress`;非活跃 → `degraded`。轮询窗口、超时值、入队 seam 不变。

### 决策:worker 作为受管常驻服务
- 容器/compose 形态新增/确认 `kb-worker` 服务;判定逻辑不依赖"谁启动了 worker",只依赖存活信号,故单机手工起 worker 也能正确判活。

## Risks / Trade-offs

- **[claim-age 误判]** worker 活着但空闲且无 pending 时,A 方案无信号 —— 但此时也无 job 等待,不触发 degraded,无害;仅当"有 pending + 长期无 claim"才判降级,语义正确。**Mitigation**:阈值取 worker 轮询周期的数倍;必要时升级方案 B。
- **[阈值过敏]** 阈值过短 → 慢 job 被误判降级。**Mitigation**:阈值 >> 单 job 典型 claim 间隔;只看"claim 是否推进"而非"job 是否完成"。

## Migration Plan

- 默认方案 A 无 schema 变更。部署即生效。回滚还原代码。
- 若选方案 B,新增 Alembic 管理库迁移(单行/小表 heartbeat),forward-only。

## Open Questions

- 方案 A vs B 在实现阶段按实测误判率定;不阻塞 propose。
