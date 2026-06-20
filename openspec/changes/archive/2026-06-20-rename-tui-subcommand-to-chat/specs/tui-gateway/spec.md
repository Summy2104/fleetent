## MODIFIED Requirements

### Requirement: 终端 TUI 客户端

系统 SHALL 提供一个纯 Python 终端客户端(入口 `fleetent chat` 子命令),连接 `/ws`,消费 `event` 通知做增量渲染:流式文本、工具调用展示、状态/spinner。客户端 SHALL 提供多行输入与斜杠命令(`/new`、`/session`、`/abort`、`/approve`、`/quit`、`/help`),并使输入行与流式输出在同一终端共存而不互相破坏。客户端 SHALL 支持通过 `--url`/`--token` 指定服务端地址与认证。不得引入 Node 或前端构建链。

#### Scenario: 流式增量渲染
- **WHEN** 客户端收到一串 `text_delta` 事件
- **THEN** 终端增量显示对应文本,且输入行保持可编辑、不被打断破坏

#### Scenario: 斜杠命令中断
- **WHEN** 用户在运行中输入 `/abort`(或按 Ctrl-C)
- **THEN** 客户端向服务端发送 `abort` 请求中断当前 run

#### Scenario: 审批决定
- **WHEN** 用户用 `/approve <approval_id> <approved|rejected>` 作出决定
- **THEN** 客户端发送 `approve` 请求并将决定回传服务端
- **NOTE** v1 不会收到 `approval_required` 推送(流式路径不门控,见上文范围说明);客户端的 `approval_required` 渲染待 `streaming-approval-gating` 落地后启用

#### Scenario: 工具调用展示
- **WHEN** 客户端收到 `tool_call`/`tool_result` 事件
- **THEN** 终端以可辨识的方式展示工具名与(截断的)结果

#### Scenario: 入口经 fleetent chat 子命令
- **WHEN** 用户启动终端客户端
- **THEN** 经 `fleetent chat`(而非已改名的 `fleetent tui` 或已移除的独立 `fleetent-tui` console-script)
