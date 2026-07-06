# workflow-engine Specification

## Purpose
持久化工作流执行引擎：run/step 状态机、就绪判定、幂等 claim、双路驱动（热路径步进 + 冷路径 sweep）、断点续跑、并发上限、超时/取消、冻结快照、终态投递、运行历史保留。

## Requirements

### Requirement: 运行状态持久化与表归属

系统 SHALL 以两张 agent 侧表持久化 workflow 运行状态：`workflow_runs`（run 实例：`id`、`workflow_name`、`definition_json` 冻结快照、`status`、`inputs_json`、`principal_json`、`origin_json`、`deliver_json`、`error`、`created_at`/`started_at`/`ended_at`）与 `workflow_step_runs`（step 实例：`run_id`+`step_id`+`attempt` 联合主键、`status`、`output_json`、`error`、`claimed_at`、`started_at`/`ended_at`）。两表 SHALL 由 per-agent `agent_state.db` 的 embedded forward-only 迁移（`MIGRATIONS` append + `PRAGMA user_version`）建立，NOT Alembic、NOT store 自建。store SHALL 经 `set_state_db(db)` 注入访问（boot 接线），SQL 全部 named parameters。

#### Scenario: 迁移建表且无 platform 依赖
- **WHEN** 全新 `agent_state.db` 经 embedded 迁移打开并注入 workflow store
- **THEN** 两表存在且 CRUD 可用，全程无 platform 模块参与、无管理库表存在

#### Scenario: run 记录完整落库
- **WHEN** `start_run(name, inputs, principal, origin)` 被调用
- **THEN** `workflow_runs` 出现一行：冻结的 `definition_json`、`principal_json`、`status=pending`，并为每个 step 预建 `workflow_step_runs` 行（`attempt=1, status=pending`）

### Requirement: run 与 step 状态机

run 状态 SHALL 限于 `pending / running / succeeded / failed / cancelled`；step 状态 SHALL 限于 `pending / running / succeeded / failed / skipped / cancelled`。迁移 MUST 单向：终态不可再迁移；非法迁移 SHALL 报错拒绝，MUST NOT 静默接受。run 终态判定：全部 step 到达终态后——存在 `failed` step 则 run `failed`；全部非 skip 路径成功则 `succeeded`；被取消则 `cancelled`。

#### Scenario: 全部成功
- **WHEN** DAG 中所有 step 依次执行成功
- **THEN** 每个 step `succeeded`，run 最终 `succeeded` 且记录 `ended_at`

#### Scenario: 终态不可迁移
- **WHEN** 试图把已 `succeeded` 的 step 再置为 `running`
- **THEN** 状态迁移被拒绝并抛出明确异常

### Requirement: 就绪判定（AllPredecessor）

step SHALL 在且仅在以下条件同时满足时就绪：其全部控制前驱（`depends_on` ∪ 数据引用隐含依赖）状态为 `succeeded`。任一前驱进入 `failed` / `skipped` / `cancelled`，该 step SHALL 被置为 `skipped`（级联传播，Eino cascade-skip 语义）。无前驱的 step 在 run 启动后立即就绪。互不依赖的就绪 step SHALL 可并发执行。

#### Scenario: 前驱全成才就绪
- **WHEN** step c 依赖 a、b，a 已成功而 b 仍在 running
- **THEN** c 保持 pending，直到 b 成功后才被领取执行

#### Scenario: 失败级联 skip
- **WHEN** step a 失败，b 依赖 a，c 依赖 b
- **THEN** b、c 均被置为 `skipped`（不执行），run 最终 `failed`

#### Scenario: 无依赖并行
- **WHEN** step x、y 互不依赖且均就绪
- **THEN** 二者可同时处于 running（并发受信号量上限约束）

### Requirement: 幂等 claim（at-most-once）

step 的领取 SHALL 经条件 UPDATE 实现幂等 claim（仅当行仍处 `pending` 且未被有效 claim 时成功，同时写入 `claimed_at`）；并发竞争者中 MUST 恰有一个成功，失败方放弃。`claimed_at` 超过 claim 窗口（step `timeout_seconds` + 余量）仍未到终态的 step，sweep SHALL 判为过期并以 `attempt+1` 新行重领，旧 attempt 标记失败留痕。

#### Scenario: 并发 claim 仅一个成功
- **WHEN** 热路径与 sweep 同时尝试 claim 同一 pending step
- **THEN** 恰有一方条件 UPDATE 生效并执行该 step，另一方放弃，step 不被执行两次

#### Scenario: 过期 claim 回收
- **WHEN** 某 step 被 claim 后进程崩溃，重启后 sweep 发现 `claimed_at` 已超窗
- **THEN** 旧 attempt 标记失败，新建 `attempt+1` 行重新领取执行

### Requirement: 双路驱动（热路径直推 + 冷路径 sweep）

引擎 SHALL 以两条路径推进 run：**热路径**——step 到达终态后同进程内立即计算新就绪 step 并尝试 claim 执行（多步链路推进 MUST NOT 依赖轮询周期）；**冷路径**——周期 sweep 扫描非终态 run，恢复孤儿（重启遗留、过期 claim）。两路径 SHALL 汇聚到同一幂等 claim，无双跑。

#### Scenario: 链式步进无轮询延迟
- **WHEN** 三步线性链 a→b→c 执行且进程存活
- **THEN** b 在 a 成功后立即（无需等待 sweep tick）被领取执行，c 同理

#### Scenario: sweep 兜底孤儿 run
- **WHEN** 存在一个 running 状态但无任何活动 step、也无有效 claim 的 run（重启遗留）
- **THEN** 下一次 sweep 将其中就绪 step 领取执行，run 继续推进

### Requirement: 断点续跑

进程被 kill 后重启，引擎 SHALL 从持久化状态接续所有非终态 run：已 `succeeded` 的 step MUST NOT 重跑（其 `output_json` 继续供下游映射），未完成 step 按就绪判定继续。恢复 MUST NOT 依赖任何内存驻留状态。

#### Scenario: kill 后从断点接续
- **WHEN** 五步链执行到第三步时进程被 kill，随后重启
- **THEN** 前两步不重跑，第三步（按过期 claim 回收或 pending 状态）起继续执行至 run 终态

### Requirement: 并发上限

引擎 SHALL 以信号量限制同时执行的 step 数，默认 4，可经 agent.yaml `workflow.max_parallel` 覆盖。超出上限的就绪 step SHALL 保持 pending 排队，不丢失。

#### Scenario: 超限排队
- **WHEN** 六个互不依赖的 step 同时就绪且上限为 4
- **THEN** 至多 4 个同时 running，其余在槽位释放后被领取

### Requirement: 超时与取消

每个 step SHALL 受 `timeout_seconds`（默认 300）约束，超时即该 attempt 失败（按 retry 策略决定重试或终败）。run 取消 SHALL 经 CancelToken 级联传播到在跑 step，未执行 step 置 `cancelled`，run 置 `cancelled`。

#### Scenario: step 超时失败
- **WHEN** 某 agent step 执行超过其 `timeout_seconds` 且 `max_attempts=0`
- **THEN** 该 step 失败（error 注明超时），下游级联 skip，run `failed`

#### Scenario: 取消级联
- **WHEN** 对 running 状态的 run 发起取消
- **THEN** 在跑 step 收到取消信号终止，剩余 step 置 `cancelled`，run `cancelled`

### Requirement: 定义与 principal 冻结

run 启动时 SHALL 将 workflow 定义序列化冻结进 `workflow_runs.definition_json`，发起者 principal 冻结进 `principal_json`；run 全程 SHALL 仅依据冻结副本执行。启动后修改磁盘上的 workflow.yaml MUST NOT 影响在跑 run。

#### Scenario: 定义编辑不影响在跑 run
- **WHEN** run 启动后 workflow.yaml 被修改（增删 step）
- **THEN** 该 run 按启动时冻结的定义执行到底，行为与文件修改前一致

### Requirement: 终态投递与运行历史保留

run 到达终态（succeeded/failed/cancelled）SHALL best-effort 按投递解析（显式 `deliver_json` 优先，否则回落 `origin_json`）通知发起人（含 run 名、终态、错误摘要）；投递失败只记日志，MUST NOT 改变 run 终态。无可解析投递目标（如 CLI 发起）只记日志。历史 run SHALL 按 retention 策略裁剪（每 workflow 保留最近 N 个终态 run，N 默认对齐 `scheduled_task_runs` 先例）。

#### Scenario: 失败 run 通知发起人
- **WHEN** 由 IM 对话发起的 run 因 step 失败到达 `failed`
- **THEN** 发起人收到一条包含 workflow 名、失败 step 与错误摘要的通知

#### Scenario: 投递失败不改终态
- **WHEN** 终态通知因连接器故障发送失败
- **THEN** run 终态保持不变，失败仅记录日志

### Requirement: 引擎生命周期与模块边界

引擎 SHALL 在 agent 进程 lifespan 内启停（启动于 boot、优雅关停于 shutdown），遵守 owner-task 契约（enter/exit 同 task、关停舱壁化、单组件收尾失败不改退出码）。`fleetent.workflow` 包 MUST NOT import `fleetent.platform.*`（纳入 module-dependency 护栏）；`workflow.enabled=false` 时引擎不启动、触发工具不可用，已有表保持休眠。

#### Scenario: 无 platform 环境全功能
- **WHEN** 在无 platform、管理库表不存在的环境运行 `fleetent agent run` 并触发 workflow
- **THEN** run 正常执行到终态，无 import 错误、无管理库访问

#### Scenario: 关停不拖垮进程
- **WHEN** agent 进程优雅关停时引擎内有在跑 step
- **THEN** 引擎在超时内收尾（step 留待重启后 sweep 回收），关停异常只记日志、退出码不变
