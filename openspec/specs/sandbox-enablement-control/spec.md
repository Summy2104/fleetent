# sandbox-enablement-control Specification

## Purpose
TBD - created by archiving change sandbox-enablement-control. Update Purpose after archive.
## Requirements
### Requirement: agent 级 code_execution 开关

agent 定义 SHALL 支持 `features.code_execution` 开关，取值真 / 假 / 未声明，作为代码执行启用的 **per-agent 唯一策略输入**（不再与全局三态 mode 联合）。当运行时具备沙箱能力（`Mode.ON`）时：未声明视为可用、显式为假则关闭、为真则可用；当无沙箱能力（`Mode.OFF`，如无 Docker）时一律关闭。该开关 MUST 与运行时能力门一同在 schema 过滤点生效——被关闭意味着 `run_code` 不出现在该 agent 的工具 schema 中，而非在调用入口返回拒绝文本。判定 MUST 由 `is_code_execution_enabled` 这一与能力门共用的同一纯函数给出。

#### Scenario: 未声明在有能力时默认可用
- **WHEN** 生效能力为 `Mode.ON`，某 agent 未声明 `code_execution`
- **THEN** 该 agent 的工具 schema 含 `run_code`

#### Scenario: 显式关闭不进其 schema
- **WHEN** 生效能力为 `Mode.ON`，某 agent 声明 `code_execution=false`
- **THEN** 该 agent 的 schema 不含 `run_code`；其它未关闭 agent 的 schema 仍含

#### Scenario: 无能力时显式为真也不可用
- **WHEN** 生效能力为 `Mode.OFF`（如 Docker 不可用），某 agent 声明 `code_execution=true`
- **THEN** 该 agent 的 schema 仍不含 `run_code`（运行时能力门优先 fail-closed）

### Requirement: agent 定义承载 features 配置并兼容旧库

agent 存储 SHALL 在 agent 定义上提供一个 `features` 配置容器（JSON），承载 `code_execution` 等能力开关。创建与读取 agent 时 MUST 往返保留 `features`；对引入 `features` 列之前已存在的旧库 MUST 通过迁移补列，旧行读取时回退为空配置，不得因缺列报错。

#### Scenario: features 往返保留
- **WHEN** 以 `features={"code_execution": true}` 创建 agent 后读取该 agent
- **THEN** 读回的 agent 的 `features` 等于 `{"code_execution": true}`

#### Scenario: 旧库迁移补列且旧行兼容
- **WHEN** 对一个在 `features` 列引入之前建立、已有 agent 行的旧库执行初始化
- **THEN** `features` 列被补齐（迁移），既有旧行读取时 `features` 回退为空配置，读取不抛异常

### Requirement: run_code 调用可获取 agent 与 session 上下文

工具调用链 SHALL 提供一条把当前 agent 标识 / agent features / session 标识从 agent 主循环经工具分发传递到 `run_code` 的上下文通道。该通道服务于沙箱**执行期**的上下文需求——SB2 的 scope `acquire` 需要 session_id / agent_name 才能定位/复用工作区，SB5 在执行时需要 agent features 才能注入 `sandbox_env`。该通道 MUST NOT 被用作启用 gate 的依据：启用判定已在 schema 过滤点完成（那里已知 agent features），抵达 `run_code` 的调用一律视为已通过 gate。

#### Scenario: agent 上下文抵达 run_code
- **WHEN** 某 agent 触发 `run_code` 工具调用
- **THEN** `run_code` 能取得该 agent 的标识 / features / session_id，供执行期（SB2 scope、SB5 env 注入）消费

#### Scenario: 缺省上下文安全降级
- **WHEN** 调用链未提供 agent 上下文（如无 agent 绑定的直接调用）
- **THEN** `run_code` 以缺省上下文执行、不因缺上下文抛异常

### Requirement: 选定后端不可用时自动降级为 off

平台启动时 SHALL 经选定后端的 `available()` 探测其可用性。后端不可用（Docker CLI 缺失/失败，或 msb server 不可达/认证失败）时，生效 mode MUST 降级为 `off`、记录警告，且平台 MUST 正常启动不被阻断。

#### Scenario: Docker 后端不可用降级且不阻断启动
- **WHEN** 选定 Docker 后端且启动时 Docker CLI 不可用
- **THEN** 生效 mode 为 `off`、`run_code` 不注册、记录一条警告，平台正常完成启动

#### Scenario: microsandbox 后端不可用同样降级
- **WHEN** 选定 microsandbox 后端且启动时 msb server 不可达
- **THEN** 生效 mode 为 `off`、记录一条警告，平台正常完成启动

#### Scenario: 探测失败不抛异常
- **WHEN** 任一后端的可用性探测命令报错或依赖缺失
- **THEN** 探测返回不可用且不抛异常，由降级逻辑接管

### Requirement: 沙箱后端提供可用性探测

每个沙箱后端 SHALL 实现可用性探测 `available()`，返回布尔结果供启用控制层判定降级。探测在后端依赖未安装、服务不可达或探测命令失败时 MUST 返回不可用且不抛异常。既有创建、执行、销毁能力的可观察行为保持不变。

#### Scenario: 探测可用
- **WHEN** 选定后端的底层服务可正常响应探测
- **THEN** `available()` 返回可用

#### Scenario: 探测不可用安全返回
- **WHEN** 选定后端的底层服务不存在或探测失败
- **THEN** `available()` 返回不可用，不抛异常

### Requirement: 部署 mode 推荐选型指引

部署文档 SHALL 为代码执行启用提供按部署形态的推荐指引，使部署者依据信任边界与免审批意图配置 per-agent `features.code_execution`，并与"封闭即免审批"配套。该指引为**文档 / 指引性质**，MUST NOT 改变启用判定语义、默认值，亦 MUST NOT 改变后端不可用时降级为 `Mode.OFF` 的行为。指引 SHALL 至少覆盖：封闭可信内网且希望兑现 medium 免审批的部署，将相关 agent 设 `code_execution=true`（不声明即默认可用）并将 `action_gate_medium_mode` 配为 `sandbox`；希望最小暴露代码执行面的部署，仅给特定 agent 设 `code_execution=true`、其余设 `false` 或不部署该能力；需完全禁用某 agent 代码执行的，设其 `code_execution=false`。指引 MUST 明确：medium 免审批仅在运行时封闭成立时生效（`sandbox_capable` 为真——后端可用且该 agent 启用代码执行），无 Docker / 降级 `Mode.OFF` 时由 fail-closed 升审批；某 agent `code_execution=false` 即该 agent 不存在容器封闭、其 medium 操作不会因 `sandbox` 配置免审批而仍走审批。

#### Scenario: 封闭可信部署的推荐
- **WHEN** 部署形态为封闭可信内网、希望容器内 medium 操作免审批自动化
- **THEN** 指引推荐相关 agent `code_execution=true`（或不声明）配合 `action_gate_medium_mode: sandbox`，并说明免审批仅在 `sandbox_capable` 为真时生效

#### Scenario: 最小暴露部署的推荐
- **WHEN** 部署形态希望最小暴露代码执行面、仅特定授权 agent 可用 `run_code`
- **THEN** 指引推荐仅给授权 agent 设 `code_execution=true`、其余 `false`

#### Scenario: 禁用某 agent 代码执行的推荐
- **WHEN** 部署形态需完全禁用某 agent 的代码执行
- **THEN** 指引推荐其 `code_execution=false`，并说明此形态下该 agent 不存在容器封闭、medium 操作不会因 `sandbox` 配置免审批而仍走审批

### Requirement: 沙箱启用由运行时能力门与 per-agent code_execution 门决定

代码执行的启用 SHALL 由两个门联合决定，不再有全局三态 `mode`，也不再读取 `platform.yaml`：① **运行时能力门**——`get_effective_mode(backend)` 经后端 `available()` 探测，能力可用时 `Mode.ON`、不可用时 `Mode.OFF`（`Mode` 取值集合收敛为 `{OFF, ON}`）；② **per-agent 门**——agent 的 `features.code_execution`。判定 MUST 由单一纯函数 `is_code_execution_enabled(mode, code_execution)` 给出：`mode=OFF → False`（无沙箱能力，对所有 agent 隐藏 `run_code`）；`mode=ON → code_execution is not False`（未声明=开、显式 `false`=关）。两个门 MUST 统一在 agent 主循环现有工具 schema 过滤点生效（`get_schemas()` + `check_tool_access` 同一处，与 `allowed_tools` 共用一条路径）：被关闭的能力 MUST NOT 出现在该 agent 的工具 schema 中。

#### Scenario: 无沙箱能力时不进任何 agent 的 schema
- **WHEN** 后端不可用导致生效能力为 `Mode.OFF`
- **THEN** 任何 agent 的工具 schema 中都不包含 `run_code`，AI 无从感知代码执行能力

#### Scenario: 有能力且未声明 code_execution 默认可用
- **WHEN** 生效能力为 `Mode.ON` 且某 agent 未显式声明 `features.code_execution`
- **THEN** 该 agent 的工具 schema 中包含 `run_code`（保留旧 `all` 默认放语义）

#### Scenario: 有能力但 agent 显式关闭
- **WHEN** 生效能力为 `Mode.ON`，某 agent 声明 `features.code_execution=false`
- **THEN** 该 agent 的 schema 不含 `run_code`；其它未关闭 agent 不受影响

### Requirement: 沙箱启用判定不读 platform.yaml

沙箱启用判定 MUST NOT 读取 `platform.yaml`：`integrations/sandbox/enablement.py` 不再 `paths.platform_yaml_path()`，删除 `sandbox.mode` 的读取与 `SETTINGS_PATH`。叠加 `per-agent-sandbox-resources`（resources/lifecycle/skill_mount 已停读）后，`integrations/sandbox` 中除 **backend 选型**（`load_sandbox_backend_config` 的 `sandbox.backend` 可选默认——既有、agent.yaml 优先、无 platform.yaml 时回落 docker，不在本次范围）外，MUST NOT 为沙箱启用/资源/lifecycle/skill_mount 读取 `platform.yaml`。standalone agent（无 `platform.yaml`）SHALL 能正常判定代码执行启用并按需创建沙箱。

#### Scenario: 启用判定零读 platform.yaml
- **WHEN** 解析某 agent 的代码执行启用
- **THEN** 判定路径不调用 `paths.platform_yaml_path()`、不读取 `platform.yaml` 的 `sandbox.mode`

#### Scenario: enablement 模块不再绑定 platform.yaml
- **WHEN** 检视 `integrations/sandbox/enablement.py` 源码
- **THEN** 该模块不引用 `paths.platform_yaml_path()` / `SETTINGS_PATH`，无 `sandbox.mode` 读取与 tri-state mode 加载器

