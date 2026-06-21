## MODIFIED Requirements

### Requirement: 终端 TUI 客户端

系统 SHALL 提供一个纯 Python 终端客户端(入口 `fleetent chat` 子命令),连接 `/ws`,消费 `event` 通知做增量渲染:流式文本、工具调用展示、状态/spinner。客户端 SHALL 提供多行输入与斜杠命令(`/new`、`/session`、`/abort`、`/approve`、`/quit`、`/help`),并使输入行与流式输出在同一终端共存而不互相破坏。流式输出 SHALL **持久显示**:输出在运行中的输入行**上方**提交,不得被 prompt 的下一次重绘擦除("一闪而过");为此客户端 SHALL 仅以**完整行**(以换行结尾)输出流式文本——半行(无换行)文本在 prompt 上方不会被提交到终端 scrollback、会被重绘擦掉。结构化事件之间 SHALL NOT 产生多余空行。客户端 SHALL 支持通过 `--url`/`--token` 指定服务端地址与认证。不得引入 Node 或前端构建链。

#### Scenario: 流式文本持久显示
- **WHEN** 客户端收到一串 `text_delta` 事件
- **THEN** 对应文本在输入行上方显示,且在后续 prompt 重绘后**仍然可见**(不被擦除)
- **AND** 输入行保持可编辑、不被打断破坏

#### Scenario: 事件之间不堆多余空行
- **WHEN** 客户端连续收到结构化事件(如 `tool_call` 紧跟 `tool_result`),或在文本之后收到结构化事件
- **THEN** 各事件各占其行,相邻事件之间不出现由渲染产生的空行(agent 自身内容里的空行除外)

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
- **THEN** 经 `fleetent chat`(而非已改名的旧 `tui` 子命令或已移除的独立 `fleetent-tui` console-script)
