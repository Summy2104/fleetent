## MODIFIED Requirements

### Requirement: 沙箱容器按 scope 决定存活粒度

沙箱生命周期层 SHALL 支持两种存活粒度（scope）：`session`（默认）与 `agent`。`session` scope 的容器以会话为归属边界，`agent` scope 的容器以 agent 定义为归属边界。每个容器 MUST 有唯一且编码了归属信息的名称，scope 与归属 key 不同的请求 MUST 取得相互隔离的容器。

容器名中编码归属的稳定标识 MUST 基于**完整未截断**的归属 key 计算——当容器名受长度上限约束需要截断时，名称中 MUST 包含一段由完整 key 派生的无碰撞标识（如可读前缀 + 完整 key 的哈希后缀），使任意两个不同归属 key MUST NOT 产生相同容器名，**即便它们共享超过长度上限的相同前缀、仅在被截断的尾部不同**。

#### Scenario: session scope 默认生效
- **WHEN** 配置未显式指定 scope，沙箱生命周期层为某会话取得容器
- **THEN** 该容器以 `session` scope 创建，名称编码了该会话的归属信息

#### Scenario: 不同归属取得隔离容器
- **WHEN** 两个不同 session（或两个不同 agent）分别取得沙箱容器
- **THEN** 两者得到名称不同、相互隔离的容器，一方在容器内产生的状态对另一方不可见

#### Scenario: 超截断边界的同前缀 key 不碰撞
- **WHEN** 两个归属 key 共享超过容器名长度上限的相同前缀、仅在会被截断的尾部不同（例如同一长前缀下的两个不同会话标识）
- **THEN** 两者仍取得名称不同、相互隔离的容器，任何一方在容器内产生的状态对另一方不可见
