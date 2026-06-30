## ADDED Requirements

### Requirement: Webhook 端点两态对称，模式由运行时判别

webhook 端点 SHALL 按部署形态两态对称提供，且 MUST NOT 新增模式开关——运行时 SHALL 沿用 `outbound_connectors.is_node_managed_runtime()`（三个 `FLEETENT_NODE_*` env 是否齐备）自动判别。standalone（agent 直接运行、无 node env）下端点 SHALL 由 agent 自身的 HTTP 应用（`runtime/agent_app.py`）挂载，source 取自 `agent.yaml`，直接在本进程后台 `normalizer.route()`。managed（node 托管、注入 node env）下端点 SHALL 由 platform 公开挂载，source 取自管理库，platform 校验后 SHALL 经既有 platform→node→agent 转发通道把消息投递到目标 agent 执行；agent 运行时 MUST NOT import platform。

#### Scenario: standalone 自托管端点
- **WHEN** agent 以 `fleetent agent run`（无 node env）运行并配了 webhook source
- **THEN** `POST /webhook/{source_id}` 由 agent 自身 HTTP 应用受理，本进程后台触发该 agent 的 run

#### Scenario: managed 经 platform 转发
- **WHEN** node 托管的 agent（注入了 `FLEETENT_NODE_*`）配了 webhook source，外部 `POST /webhook/{source_id}` 打到 platform
- **THEN** platform 校验后经 platform→node→agent 通道把消息投给目标 agent 执行；agent 侧不直连 platform

#### Scenario: 不引入模式开关
- **WHEN** 判别当前是 standalone 还是 managed
- **THEN** 复用 `is_node_managed_runtime()`，不读取任何新增的 `mode` 配置项

## MODIFIED Requirements

### Requirement: Webhook source configuration

Webhook source MUST 由运行时 source 管理提供（见 `webhook-source-management` capability）：managed 取自管理库表 `webhook_sources`，standalone 取自 `agent.yaml` 的 `webhooks.sources`。Webhook sources SHALL NOT 从 YAML 文件加载（遗留 YAML source 文件不再被加载）。`POST /webhook/{source_id}` 在 source 未注册时 SHALL 返回 404。

#### Scenario: 遗留 webhook YAML 不被加载
- **WHEN** 存在遗留 webhook YAML source 文件
- **THEN** 系统不从该 YAML 加载 source（source 仅来自管理库 / agent.yaml）

#### Scenario: 未知 source 返回 404
- **WHEN** 某 `source_id` 未在运行时 source 中注册
- **THEN** `POST /webhook/{source_id}` 返回 404

### Requirement: Webhook 回投默认 no-op，可选投递到 IM 目标

传给 `normalizer.route()` 的 `reply_func`，当 source **未配置** `reply_target` 时 SHALL 为 no-op：run 结果只记入 eval trace，MUST NOT 发出任何出站消息。当 source **配置了** `reply_target`（内部 user_id）时，系统 SHALL 经 directed-reach `outbound_connectors.notify_user(reply_target, result)` 把 run 最终结果投递为私信。该接线两态一致：node-managed agent 进程内 `notify_user` 入 im_outbound_queue → node drain → DM；非 managed（standalone dev）运行时 `notify_user` 自身即 no-op。投递为尽力而为，失败 SHALL 只记日志、MUST NOT 影响 run 本身。

#### Scenario: 未配 reply_target 时 no-op
- **WHEN** 某 webhook source 未配 `reply_target`，其触发的 run 完成
- **THEN** 不发出任何出站消息，结果仅出现在 eval trace

#### Scenario: 配了 reply_target 时回投 DM
- **WHEN** 某 webhook source 配了 `reply_target`（内部 user_id），其触发的 run 完成
- **THEN** run 结果经 directed-reach `notify_user` 以私信投递给该用户（managed 实投，standalone dev 降级 no-op）

#### Scenario: 回投失败不影响 run
- **WHEN** 回投目标投递失败
- **THEN** 只记日志，run 本身已完成、结果仍入 eval trace
