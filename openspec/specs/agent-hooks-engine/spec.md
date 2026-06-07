### Requirement: hook 注册与按序派发

系统 SHALL 提供 `@hook(event)` 装饰器把进程内 Python 回调注册到指定事件，并提供 `dispatch(event, ctx)` 按**注册顺序**执行该事件的所有 hook。回调接收只读 `HookContext`（event + session_id/agent_name/user_id + 事件专属 payload），返回 `HookResult`（或 `None` 表示放行/不改）。对**决策类**事件 MUST first-deny-wins（任一 `deny` 短路返回）；对**变换类**事件 MUST 链式（后一 hook 见前一 hook 的输出）。`dispatch` MUST 提供 `has_hooks(event)` 供调用方在无注册时零开销跳过。

#### Scenario: 多 hook 按序执行
- **WHEN** 同一事件注册了多个 hook 并 `dispatch`
- **THEN** 它们按注册顺序执行，结果按事件类型（决策短路 / 变换链式）合并

#### Scenario: 决策点 first-deny-wins
- **WHEN** 某决策事件的前一个 hook 返回 `deny`
- **THEN** 立即短路返回该 deny，后续 hook 不再执行

### Requirement: 错误隔离与超时

单个 hook 抛异常时 `dispatch` MUST 记 warn 日志并跳过该 hook，**绝不**向 agent loop 传播（不破坏 run）。每个 hook MUST 受超时约束，不得挂起 loop。对**决策类**事件，hook 失败的处置 MUST 可配：默认 `open`（失败放行 + 审计），`strict` 时失败按 `deny` 处理。

#### Scenario: hook 异常被隔离
- **WHEN** 某 hook 执行抛出异常
- **THEN** 记日志并跳过，run 继续，不抛出

#### Scenario: 决策失败策略 open/strict
- **WHEN** 决策类 hook 失败且配置为 `strict`
- **THEN** 该次按 `deny` 处理；配置为 `open` 时按放行处理并审计

### Requirement: 默认关闭与可注入

hook 体系 MUST 默认关闭（`hooks_enabled=False`）：未启用时不派发、零行为变化。引擎的注册表 MUST 为可在测试中 `reset()`/monkeypatch 注入的 module-level 状态，MUST NOT 依赖 platform。hook 代码经 agent-local 插件包随 `plugin_loader` import 注册。

#### Scenario: 默认关闭零行为变化
- **WHEN** agent 未启用 hooks（默认）
- **THEN** loop 不调用 dispatch，行为与未引入 hook 体系时一致

#### Scenario: agent-local 插件内的 hook 被注册
- **WHEN** agent 本地插件包内定义了 `@hook(...)` 并被加载 import
- **THEN** 该回调出现在引擎注册表中、可被 dispatch
