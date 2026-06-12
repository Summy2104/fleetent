## ADDED Requirements

### Requirement: 模块级活异步资源单例护栏

长生命周期异步资源（网络连接、SDK 会话、子进程流）SHALL 由唯一 owner task 拥有其生命周期
（谁打开谁关闭；跨 task 只传句柄，不传生命周期操作）。`src/fleetent` 内 MUST NOT 在模块作用域
以全局单例形式持有此类活资源——特别地，模块级 `AsyncExitStack` 持有连接/会话上下文属违例
（该形态曾导致 2026-06-11 优雅关停崩溃：跨 task 退出 anyio cancel scope）。护栏单测 SHALL
扫描 `src/fleetent` 并对违例 fail，使违规死在 PR 门禁而非生产 teardown。该契约同时记入
AGENTS.md 架构契约区，作为既有「不可注入的全局可变状态」风格铁律的异步资源细化；in-repo
范式实现为 IM 连接 supervisor（每连接一个 owner task）与 MCP 会话宿主。

#### Scenario: 模块级 AsyncExitStack 持有被护栏拦截

- **WHEN** 任一 `src/fleetent` 模块在模块作用域声明 `AsyncExitStack` 单例并用于持有连接/会话
- **THEN** 护栏单测 fail 并指出违例模块

#### Scenario: MCP 纳编后零违例

- **WHEN** 护栏在 MCP 会话宿主重构落地后的代码库上运行
- **THEN** 扫描结果为零违例（原 `integrations/mcp/client.py` 的 `_exit_stack` 已移除）
