# mcp-result-handling Delta

## ADDED Requirements

### Requirement: 工具结果中的有效根内路径确定性改写为 /exchange 规范路径

MCP 客户端 SHALL 在返回工具结果文本给 agent 之前，把结果中位于该 server 有效文件根内的 host 绝对路径前缀替换为 `/exchange/<server_id>/` 规范路径（确定性字符串变换，映射来自 server 注册时绑定的有效文件根）。改写命中的文件 MUST 同步登记进 artifacts 台账并归因到触发调用 run 的 scope_key（审计列记具体 session_id/user_id）。有效根之外的路径 MUST NOT 被改写。

#### Scenario: localPath 被改写并登记

- **WHEN** 某 MCP 工具结果含 `"localPath": "<有效文件根>/outbound/report.xlsx"`
- **THEN** agent 收到的结果中该路径为 `/exchange/<server_id>/outbound/report.xlsx`，且台账新增一行，`scope_key` 为当前 run 的 scope_key

#### Scenario: 根外路径不改写

- **WHEN** 工具结果含一个不在该 server 有效文件根内的绝对路径
- **THEN** 该路径原样保留，不登记

### Requirement: 调用窗口 diff 兜底登记

对绑定了有效文件根的 stdio server，MCP 客户端 SHALL 在每次工具调用前后对产物区做快照对比（path/mtime/size），把调用窗口内新增且未经路径改写登记的文件登记进台账（归因到触发调用 run 的 scope_key）。同一 server 的"调用+diff"窗口 MUST 以 per-server 锁串行化，防止并发调用归因错乱。点文件与 `*.tmp` MUST 跳过。diff 失败 MUST 记录日志且 MUST NOT 影响工具结果返回。

#### Scenario: 结果未提及的新文件被兜底登记

- **WHEN** MCP 工具调用在产物区写了一个新文件但结果文本未包含其路径
- **THEN** 调用窗口 diff 将其登记进台账，`scope_key` 为触发调用 run 的 scope_key

#### Scenario: 并发调用归因不错乱

- **WHEN** scope_key K1、K2 的 run 并发调用同一 server 的工具且各产生文件
- **THEN** per-server 锁使两个调用窗口串行，K1 产生的文件归属 K1、K2 产生的文件归属 K2

#### Scenario: diff 失败不影响结果

- **WHEN** 快照对比过程抛出异常（如目录瞬时不可读）
- **THEN** 工具结果照常返回，仅记录一条警告日志
