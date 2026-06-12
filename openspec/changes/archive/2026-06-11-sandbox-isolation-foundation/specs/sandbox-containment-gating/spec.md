## ADDED Requirements

### Requirement: sandbox_capable 反映运行时封闭性

喂给 action gate（`resolve_action_mode` 的 `sandbox_capable` 入参）的真值 MUST 反映该工具**本次调用是否真正在容器 namespace 内被封闭执行**，而非仅静态判断该工具是否属于 sandbox-backed 工具集。`sandbox_capable` 为真**当且仅当**：沙箱 `effective_mode != OFF` **且**该工具本次确经容器后端在容器内执行（容器执行 / workspace mount 能力可用）。后端降级为宿主围栏执行（`_HostBackend`）或 `effective_mode == OFF` 时，`sandbox_capable` MUST 为假。

#### Scenario: 真正容器内执行才算 capable
- **WHEN** docker 可用、`effective_mode != OFF`，某 sandbox-backed 工具本次经容器后端在容器内执行
- **THEN** 该工具的 `sandbox_capable` 为真

#### Scenario: 降级态不算 capable
- **WHEN** docker 不可用使 `effective_mode == OFF`（或所选后端不提供容器内执行 / 无 workspace mount，文件工具走宿主围栏降级）
- **THEN** 即便该工具静态属于 sandbox-backed 集合，其 `sandbox_capable` 仍为假

### Requirement: 封闭性不成立时 fail-closed 升审批

当 `sandbox_capable` 为假而某操作的处置 mode 解析为 `SANDBOX` 时，系统 MUST 复用 action gate 既有 fail-closed 行为升级为 `APPROVAL`，MUST NOT 在未封闭环境下以 sandbox 之名直跑放行该操作。等价于结构性保证"无 docker / 无容器封闭 = 不免审批"——免审批的正当性绑定运行时封闭性，而非工具的静态分类或部署配置。

#### Scenario: 配置 sandbox 但运行时未封闭则升审批
- **WHEN** 部署将某 medium 操作配置为 `sandbox` 处置 mode，但运行时 `effective_mode == OFF`（盒子不封闭）
- **THEN** 该操作经 action gate 升级为 `APPROVAL` 走审批，不以 sandbox 名义静默直跑

#### Scenario: 封闭时按配置直跑
- **WHEN** 部署将某 medium 操作配置为 `sandbox` 处置 mode，且运行时 `sandbox_capable` 为真（封闭成立）
- **THEN** 该操作按 `SANDBOX` 处置在容器内直跑，不触发审批
