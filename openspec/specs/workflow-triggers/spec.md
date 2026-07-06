# workflow-triggers Specification

## Purpose
工作流触发面：run_workflow/workflow_status 内置工具与 fleetent workflow CLI，触发即冻结发起上下文。

## Requirements

### Requirement: run_workflow 内置工具

系统 SHALL 注册内置工具 `run_workflow(name, inputs)`：按名加载 workflow 定义、以调用时 `ToolContext` 的 principal 与会话来源（origin）启动 run，立即返回 `run_id` 与初始状态（非阻塞，不等待 run 完成）。workflow 不存在 SHALL 返回明确错误；`inputs` 缺少定义声明的必填参数 SHALL 拒绝启动。`workflow.enabled=false` 时该工具 SHALL 不可用（不出现在工具 schema 中）。

#### Scenario: 对话内发起
- **WHEN** IM 对话中 LLM 调用 `run_workflow("weekly-report", {"channel": "#reports"})`
- **THEN** run 以该用户 principal 与对话 origin 创建，工具立即返回 `run_id`，run 在后台推进

#### Scenario: 未知 workflow 报错
- **WHEN** 调用 `run_workflow("ghost", {})`
- **THEN** 工具返回 not-found 错误及可用 workflow 列表，不创建 run

#### Scenario: 缺必填 inputs 拒绝
- **WHEN** 定义声明必填参数 `channel`（无 default）而调用未提供
- **THEN** 启动被拒绝并指出缺失参数，不落任何 run 记录

### Requirement: workflow_status 内置工具

系统 SHALL 注册内置工具 `workflow_status(run_id)`：返回 run 的当前状态与逐 step 状态摘要（step id、status、错误摘要、时间戳）。run 不存在 SHALL 返回明确错误。输出 SHALL 适合 LLM 转述（结构化 JSON 文本）。

#### Scenario: 查询在跑 run
- **WHEN** 调用 `workflow_status(run_id)` 且 run 正在执行
- **THEN** 返回 run `running` 及各 step 的实时状态（含已成功 step 与 pending step）

#### Scenario: run 不存在
- **WHEN** 以不存在的 run_id 查询
- **THEN** 返回明确的 not-found 错误

### Requirement: CLI 触发面

系统 SHALL 提供 CLI 子命令：`fleetent workflow list`（列出定义目录中的可用 workflow 及校验状态）与 `fleetent workflow run <name> [--input k=v ...]`（以本地 principal 启动 run，输出 run_id，并可等待/轮询至终态输出逐 step 结果，供 dev/验证）。CLI 路径 SHALL 与工具路径共用同一 `start_run` 公开入口，MUST NOT 出现第二套启动逻辑。

#### Scenario: CLI 启动并观察
- **WHEN** 执行 `fleetent workflow run demo --input url=https://example.com`
- **THEN** 输出 run_id，run 推进到终态后可见逐 step 状态与最终结果

#### Scenario: list 展示校验状态
- **WHEN** 定义目录含一个合法与一个非法（成环）workflow
- **THEN** `fleetent workflow list` 列出两者，非法者标注校验错误摘要而非直接崩溃

### Requirement: 触发即冻结发起上下文

任一触发面启动 run 时 SHALL 在启动时刻冻结：定义快照（`definition_json`）、发起者 principal（`principal_json`）、发起来源（`origin_json`，工具路径=会话来源，CLI 路径=cli 标记）。后续执行与终态投递 SHALL 仅依据冻结值，MUST NOT 回查触发时刻之后的可变状态。

#### Scenario: 工具路径冻结会话来源
- **WHEN** 经 `run_workflow` 从某 IM 会话发起 run
- **THEN** `origin_json` 记录该会话地址，终态通知投递到该地址（即使用户随后切换会话）
