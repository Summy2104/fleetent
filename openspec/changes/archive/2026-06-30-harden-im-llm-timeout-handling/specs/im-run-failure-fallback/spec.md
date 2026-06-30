## ADDED Requirements

### Requirement: IM 运行失败时投递兜底回复

IM 入站处理链（`im_gateway` 的消息路由）在调用 agent 运行（`agent_loop.run`）期间，若运行抛出任何异常（含 LLM 请求超时），SHALL 捕获该异常并经本轮消息的 `reply_func` 向用户投递一条可见的失败提示（如「⚠️ 处理时出错或超时了，请重试」），而非让异常静默冒泡。该兜底 MUST 同时适用于 standalone（agent 自托管 IM 连接）与 managed（node 托管 IM、经 agent `/im/route` 转发）两种宿主，因二者共用同一路由函数。

#### Scenario: agent 运行抛异常时回兜底提示
- **WHEN** IM 路由在 `agent_loop.run` 期间捕获到一个异常（如 LLM 超时）
- **THEN** 经 `reply_func` 投递一条非空的失败提示给用户

#### Scenario: 正常成功运行不触发兜底
- **WHEN** `agent_loop.run` 正常返回回复
- **THEN** 不投递兜底提示，仅投递正常回复（兜底路径不被触发）

> 注：失败兜底经 `reply_func` 投递，因而**同时清除 IM loading/"思考中…" 状态**——该状态清除的规范归 `im-progress-feedback`（其"agent run 失败时也清除状态" scenario），本能力不重复定义。

### Requirement: 运行失败被记录且不向上冒泡

IM 路由捕获 agent 运行异常后，SHALL 记录一条 error 级日志（含异常类型与会话标识），并保存本轮会话状态；随后 MUST NOT 将该异常继续向上抛出到 IM 适配器（避免触发适配器层的"listener 失败"且无任何用户反馈）。日志记录满足「catch 后必须 log，不吞异常」。

#### Scenario: 失败被记录而非静默吞没
- **WHEN** IM 路由捕获到 agent 运行异常
- **THEN** 产生一条包含异常类型的 error 日志

#### Scenario: 失败不冒泡到 IM 适配器
- **WHEN** IM 路由已捕获并兜底回复了异常
- **THEN** 该异常不再向上抛出（IM 适配器不记录未处理的 listener 失败）

#### Scenario: 失败轮的会话仍被保存
- **WHEN** IM 路由捕获 agent 运行异常并兜底
- **THEN** 本轮会话状态被保存（用户本轮输入不因异常而丢失）
