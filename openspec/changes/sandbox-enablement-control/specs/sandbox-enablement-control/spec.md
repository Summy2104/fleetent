## ADDED Requirements

### Requirement: 全局三态 mode 控制代码执行能力

平台 SHALL 提供全局沙箱 `mode`，取值 `off` / `selective` / `all`，默认 `all`。`mode=off` 时 `run_code` 工具 MUST NOT 注册（AI 不可见该能力）；`mode=selective` 时仅授权 agent 可用；`mode=all` 时默认所有 agent 可用。

#### Scenario: off 模式下工具不注册
- **WHEN** 生效 mode 为 `off`
- **THEN** 工具 schema 中不包含 `run_code`，AI 无从感知代码执行能力存在

#### Scenario: all 模式默认全员可用
- **WHEN** 生效 mode 为 `all` 且某 agent 未显式声明 `code_execution`
- **THEN** 该 agent 可调用 `run_code`

### Requirement: agent 级 code_execution 开关

agent 定义 SHALL 支持 `features.code_execution` 开关，取值真 / 假 / 未声明。`selective` 模式下仅 `code_execution` 为真的 agent 可用代码执行；`all` 模式下未声明视为可用、显式为假则关闭。判定 MUST 由单一纯函数依据 mode 与该开关给出，调用入口仅消费判定结果。

#### Scenario: selective 模式仅授权 agent 可用
- **WHEN** 生效 mode 为 `selective`，某 agent 未声明或声明 `code_execution=false`
- **THEN** 该 agent 调用 `run_code` 被拒绝并被告知能力不可用，不进入沙箱执行

#### Scenario: all 模式下 agent 显式关闭
- **WHEN** 生效 mode 为 `all`，某 agent 显式声明 `code_execution=false`
- **THEN** 该 agent 调用 `run_code` 被拒绝；其它未关闭的 agent 不受影响

### Requirement: Docker 不可用时自动降级为 off

平台启动时 SHALL 探测 Docker CLI 是否可用。Docker 不可用时，生效 mode MUST 降级为 `off`、记录警告，且平台 MUST 正常启动不被阻断。

#### Scenario: Docker 缺失降级且不阻断启动
- **WHEN** 平台启动时 Docker CLI 不可用
- **THEN** 生效 mode 为 `off`、`run_code` 不注册、记录一条警告，平台正常完成启动

#### Scenario: 探测失败不抛异常
- **WHEN** Docker 可用性探测命令报错或 Docker 未安装
- **THEN** 探测返回不可用且不抛异常，由降级逻辑接管

### Requirement: agent 定义承载 features 配置并兼容旧库

agent 存储 SHALL 在 agent 定义上提供一个 `features` 配置容器（JSON），承载 `code_execution` 等能力开关。创建与读取 agent 时 MUST 往返保留 `features`；对引入 `features` 列之前已存在的旧库 MUST 通过迁移补列，旧行读取时回退为空配置，不得因缺列报错。

#### Scenario: features 往返保留
- **WHEN** 以 `features={"code_execution": true}` 创建 agent 后读取该 agent
- **THEN** 读回的 agent 的 `features` 等于 `{"code_execution": true}`

#### Scenario: 旧库迁移补列且旧行兼容
- **WHEN** 对一个在 `features` 列引入之前建立、已有 agent 行的旧库执行初始化
- **THEN** `features` 列被补齐（迁移），既有旧行读取时 `features` 回退为空配置，读取不抛异常

### Requirement: run_code 调用可获取 agent 与 session 上下文

工具调用链 SHALL 提供一条把当前 agent 标识 / agent features / session 标识从 agent 主循环经工具分发传递到 `run_code` 的上下文通道。`run_code` 的启用判定 MUST 依据该通道提供的 agent features，而非仅全局默认。

#### Scenario: agent 上下文抵达 run_code
- **WHEN** 某 agent 触发 `run_code` 工具调用
- **THEN** `run_code` 能取得该 agent 的 features（含 `code_execution`），据此进行启用判定

#### Scenario: 缺省上下文安全降级
- **WHEN** 调用链未提供 agent 上下文（如无 agent 绑定的直接调用）
- **THEN** 启用判定退回全局 mode 默认，不因缺上下文抛异常

### Requirement: 沙箱客户端提供 Docker 可用性探测

沙箱客户端 SHALL 提供 Docker CLI 可用性探测能力，返回布尔结果供启用控制层判定降级。探测在 Docker 未安装或命令失败时 MUST 返回不可用且不抛异常。既有创建、执行、销毁能力的可观察行为保持不变。

> 归属说明：本需求是 Docker 后端新增能力，落在本 change 的新 capability `sandbox-enablement-control` 下以 ADDED 表达。既有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。

#### Scenario: 探测可用
- **WHEN** Docker CLI 可正常响应探测命令
- **THEN** 返回可用

#### Scenario: 探测不可用安全返回
- **WHEN** Docker CLI 不存在或探测命令返回非零
- **THEN** 返回不可用，不抛异常
