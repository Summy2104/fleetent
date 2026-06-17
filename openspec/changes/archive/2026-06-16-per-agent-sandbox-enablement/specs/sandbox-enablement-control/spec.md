## REMOVED Requirements

### Requirement: 全局三态 mode 控制代码执行能力

**Reason**: 三态 `mode`（`off`/`selective`/`all`）是"一份配置管多 agent"的机群策略，且其值从机器共享 `platform.yaml` 读取——是 `integrations/sandbox` 对 `platform.yaml` 的最后一个耦合读取点，与 agent⊥platform、每 agent 独享冲突。per-agent `features.code_execution` 已足以表达单个 agent 的启用意图。

**Migration**: 从 `platform.yaml` 删除 `sandbox.mode`。原语义经 per-agent `features.code_execution` 表达：`mode=off`（全机禁用）→ 对所有 agent 设 `features.code_execution=false`；`mode=selective`（默认拒、逐个授权）→ 仅给需要的 agent 设 `code_execution=true`，其余不声明或设 false；`mode=all`（默认放）→ 保持不声明（=开）。运行时无 Docker 仍自动禁用（见「选定后端不可用时自动降级为 off」）。

## ADDED Requirements

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

## MODIFIED Requirements

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
