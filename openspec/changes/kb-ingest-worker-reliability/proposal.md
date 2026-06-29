## Why

`kb-ingest-worker` spec 已定 `fleetent kb-worker` 为 `kb_ingest_jobs` 队列的唯一消费者,admin sync/导入端点"入队 + 轮询,超时返回 job id + 当前状态"。但当**没有任何 worker 在运行**时,job 永远停在 `pending`,而 admin 端点的"超时返回 pending"与"job 正在被处理"在外部完全无法区分——导入/同步看起来已受理、实则永不推进,是一个**静默失败**(看着成功,什么都没干)。

根因:worker 存活状态不可观测,系统无法把"无 worker(降级)"与"job 正常排队/处理中"区分开。

## What Changes

- **worker 存活可观测**:`fleetent kb-worker` SHALL 定期写入存活信号(heartbeat:last-seen 时间戳);控制面 SHALL 能据此判定当前是否有活跃 worker。
- **非终态状态区分降级**:admin ingest/sync 端点在返回非终态(未 done/failed)结果时,SHALL 区分:
  - `in_progress` / `queued`——有活跃 worker,job 正常排队或处理中;
  - `degraded`(或等价的明确标记)——**无活跃 worker**(heartbeat 过期),job 不会推进。
  端点 SHALL NOT 在无 worker 时返回与正常排队无差别的裸 `pending`。
- **(部署)** worker 作为受管常驻服务:在容器/compose 部署形态中 worker SHALL 是独立受监督服务(与 platform/node 并列),非"需手工拉起"。

不改变:worker 仍是队列唯一消费者(**不引入 in-process drain**,该路径被现有 spec 排除);入队 + 轮询的同步体验;失败重试语义;`kb_ingest_jobs` 表既有列。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `kb-ingest-worker`: 新增 worker heartbeat 存活信号要求;新增 admin ingest/sync 非终态状态必须区分"降级(无活跃 worker)"与"处理中"的要求;明确 worker 在容器部署中为受管常驻服务。

## Impact

- **owning package**:`fleetent.knowledge_base`(worker)+ `platform.knowledge_base_management`(admin 端点状态判定)。
- **public API surface**:admin ingest/sync 响应体新增/收紧状态字段(区分 degraded);worker 增加 heartbeat 写入。
- **owned tables**:worker heartbeat 的承载方式见 design(优先复用 `kb_ingest_jobs.claimed_at` 的 claim-age 启发,避免新表;若需独立 heartbeat 行则走 Alembic 管理库迁移)。
- **config namespace**:无新增(heartbeat 周期可复用 worker .env 既有部署级配置)。
- **cross-module 依赖**:无新增;worker 仍经 `db.py` 边界、✗→ `platform`;admin 端点在 platform 侧读判定。
- **部署**:容器/compose 形态新增/确认 kb-worker 服务(关联 dockerize-deploy-stack)。
- **测试**:integration(无 worker → 端点返回 degraded 而非裸 pending;有 heartbeat → 返回 in_progress)。
