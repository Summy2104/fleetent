## ADDED Requirements

### Requirement: 封禁职责按层拆分
封禁能力 SHALL 按层拆分归属，行为不变：admin 级联编排（设置 status、吊销 API 密钥、禁用 IM 账号、写注册封禁、写审计）SHALL 由 platform 层拥有；注册封禁存储（记录与查询被禁止重新注册的 email）SHALL 由 governance 拥有且 agent 侧可读，不依赖 platform。

#### Scenario: 级联编排由 platform 提供
- **WHEN** admin 接口触发封禁/解封/批量封禁
- **THEN** 调用 platform 层的 block service，由它协调用户状态、密钥吊销、IM 禁用、注册封禁与审计

#### Scenario: 注册封禁查询 agent 可读
- **WHEN** agent 侧 user_store 在创建用户时校验 email 是否被禁止重新注册
- **THEN** 它调用 governance 的注册封禁查询，且该路径不 import platform
