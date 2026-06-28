## ADDED Requirements

### Requirement: 两层注册表 — provider 是凭证边界,model 是可调用目标

平台管理库 SHALL 用两张表表达模型配置:`providers`(provider 注册)与 `models`(model 注册)。`providers` 行 SHALL 承载供应商身份与凭证(`vendor`、`api_key`、`api_key_env`,以及仅用于 UI 预填的可选 `base_url`),且 SHALL NOT 承载具体可调用目标的连接信息或定价。`models` 行 SHALL 承载一个具体可调用目标(`protocol`、`model_name`、`base_url`/`endpoint`、`max_tokens`、`input_price_per_1k`、`output_price_per_1k`、`params`),并 SHALL 经必填外键 `provider_id` 归属到一个 provider。同一 provider 下 MAY 挂多个 model,且这些 model MUST 共用该 provider 的凭证。

#### Scenario: 一家多能力供应商共用凭证
- **WHEN** 一个 `providers` 行(vendor=openai,配置了 `api_key`/`api_key_env`)下挂多个 `models`(如 chat、embedding 各一)
- **THEN** 每个 model 各自持有自己的 `protocol`/`model_name`/定价
- **AND** 这些 model 解析凭证时 MUST 取所属 provider 的 `api_key_env`,即共用同一把 key

#### Scenario: model 必须归属一个 provider
- **WHEN** 创建一个 `models` 行而未提供合法的 `provider_id`
- **THEN** 创建 MUST 失败(外键约束)

#### Scenario: 连接目标落在 model 而非 provider
- **WHEN** 解析某 model 的可调用配置
- **THEN** 其 `base_url`/`endpoint` MUST 取自 `models` 行,而非 provider 行;provider 的 `base_url` MUST NOT 参与运行时寻址(仅作新建 model 的 UI 预填默认)

### Requirement: 凭证仅归 provider 级且永不明文外泄

模型 API key SHALL 仅存于 `providers` 行的 `api_key`(用于连通测试与共享回填),并 SHALL 在所有 API/UI 输出中掩码、永不以明文返回。`models` 行 SHALL NOT 持有任何 key 字段。

#### Scenario: model 不含 key 字段
- **WHEN** 查询或序列化一个 `models` 行
- **THEN** 输出 MUST NOT 含任何 api_key 字段;凭证只经其所属 provider 的 `api_key_env` 间接表达

#### Scenario: provider key 输出掩码
- **WHEN** 任一接口返回一个配置了 `api_key` 的 provider
- **THEN** `api_key` MUST 以掩码占位呈现,明文 MUST NOT 出现在响应体、审计 detail 或日志中

### Requirement: agent 经 model_id 引用,堵死内联

`agents.model_overrides` 的规范 authoring 形态 SHALL 为每个 route 的有序 entry 引用一个 `model_id`,并 MAY 携带调用级 `max_tokens` 与 `params` 覆盖。规范写入路径 SHALL NOT 接受内联的 `base_url`/`model`/`api_key_env`(这些只能定义在 `models` 行上)。

#### Scenario: route entry 引用 model_id
- **WHEN** 控制台为某 route 选定一个 model 并保存
- **THEN** `agents.model_overrides` 中该 route 的 entry MUST 形如 `{model_id, max_tokens?, params?}`,不含内联连接字段

#### Scenario: 回退链为有序多 entry
- **WHEN** 某 route 配置了主 model 与一个回退 model
- **THEN** 该 route 的 entry 数组 MUST 按回退优先级有序保存

### Requirement: materialize 经 model_id join flatten 且 key 回填恒命中

平台 materialize(`_models_from_overrides`/`_target_from_model_override`)SHALL 把每个 route entry 的 `model_id` 解析为 `models` 行,join 其所属 `providers` 行,flatten 成 agent.yaml 的一个 `ModelTarget`:`api_key_env` MUST 取自 provider 行(与该 provider 的凭证同源),连接目标取自 model 行,`max_tokens`/`params` 为 model 默认与 entry 覆盖的合并。当引用的 `model_id` 在注册表中不存在时,materialize MUST 回落到既有的旧内联形态解析(向后兼容)并记 warn,而非报错中断。

#### Scenario: 命中注册表时 key 回填恒命中
- **WHEN** 某 route entry 引用一个存在的 `model_id`
- **THEN** 生成的 `ModelTarget.api_key_env` MUST 等于该 model 所属 provider 的 `api_key_env`
- **AND** `.env` 回填该 env 名时取得的值 MUST 与该 provider 的凭证同源(不会因 env 名与注册表脱钩而落空)

#### Scenario: 旧内联形态向后兼容
- **WHEN** 某历史 `model_overrides` entry 携带旧式 `provider_id`/内联 `base_url`/`model`/`api_key_env` 且无法在新注册表命中
- **THEN** materialize MUST 用旧内联逻辑解析出 `ModelTarget` 并记 warn,不报错

#### Scenario: 调用级覆盖深合并
- **WHEN** model 默认 `params` 为 `{"temperature": 0.7}`,route entry 覆盖 `{"temperature": 0}`
- **THEN** flatten 出的 `ModelTarget.params` MUST 为 `{"temperature": 0}`,`max_tokens` 取 entry 覆盖值(无则取 model 默认)

### Requirement: per-agent key 覆盖以 (agent, provider) 粒度解析

平台 SHALL 支持 agent 为某 provider 配置仅属于自己的 API key 覆盖,其粒度为 `(agent, provider)`,经现有 inject-slot 机制以 `(agent_id, provider.api_key_env)` 持久化于 `secret_store`,SHALL NOT 为此新建专表。materialize 为该 agent 写 `.env` 时,某 `api_key_env` 的取值优先级 MUST 为:① 该 agent 的 inject slot 值 → ② 所属 provider 的共享 `api_key` → ③ 共享 secret。

#### Scenario: agent 私钥覆盖 provider 共享默认
- **WHEN** agent A 为 provider P 配置了自己的 key,agent B 未配置
- **THEN** A 的 `.env` 中 `P.api_key_env` MUST 取 A 的 inject slot 值,B 的 MUST 回落 P 的共享 `api_key`

#### Scenario: 同 provider 多 model 共用覆盖 key
- **WHEN** agent A 为 provider P 配置了覆盖 key,且 A 的多个 route 用到 P 下不同 model
- **THEN** 这些 model 在 A 的 `.env` 中 MUST 共用同一把覆盖 key(粒度为 provider,而非 model)

### Requirement: 删除受引用约束保护

删除 `models`/`providers` 行 SHALL 受引用约束保护。删除一个被任一 agent route 引用的 model MUST 被拒绝(冲突)。删除其下仍挂有 model 的 provider MUST 被拒绝。引用判定 MUST 经扫描 `agents.model_overrides`(含对旧形态引用的识别)得出。

#### Scenario: 删除被引用的 model 被拒
- **WHEN** 某 model 被某 agent 的某 route 引用,管理员尝试删除它
- **THEN** 删除 MUST 被拒绝并提示引用方

#### Scenario: 删除仍挂 model 的 provider 被拒
- **WHEN** 某 provider 名下仍存在至少一个 model,管理员尝试删除该 provider
- **THEN** 删除 MUST 被拒绝,要求先删除/迁移其 model

#### Scenario: 无引用可删
- **WHEN** 某 model 无任何 agent route 引用,或某 provider 名下已无 model
- **THEN** 删除 MUST 允许
