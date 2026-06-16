## MODIFIED Requirements

### Requirement: 沙箱资源限制经配置声明

沙箱资源限制（内存 `memory`、CPU `cpus`、网络策略 `network`、单次执行超时 `exec_timeout`、文件系统只读 `read_only`）SHALL 经配置声明，不再硬编码。配置 SHALL 来自 **per-agent 的 `agent.yaml` `sandbox.resources`**（每个 agent 独享一份资源画像），不再来自机器共享的 `platform.yaml`。配置 MUST 支持嵌套 `sandbox.resources` 结构，各字段均为可选。`read_only` 纳入资源档位、可配置。每个 agent 的 `workspace_scope`（数据隔离粒度）SHALL 沿用该 agent 的同一份 `sandbox.resources`，不再存在 session/agent 两档资源差异。

#### Scenario: 配置值生效到容器创建
- **WHEN** 某 agent 的 `agent.yaml` 声明 `sandbox.resources.memory=512`、`sandbox.resources.cpus=1.0`
- **THEN** 该 agent 创建沙箱容器时的资源限制相应为 512 MB 内存、1.0 CPU

#### Scenario: 网络策略 none 可配置
- **WHEN** 配置 `network=none`
- **THEN** 容器以无网络方式创建（`docker run` 含 `--network none`，与默认推荐一致）

#### Scenario: 网络策略 allow_all 放行全部出站
- **WHEN** 配置 `network=allow_all`
- **THEN** 容器创建命令不包含 `--network none`（使用 Docker 默认 bridge，放行全部出站）

#### Scenario: 网络策略 public_only 使用预置受限网络
- **WHEN** 配置 `network=public_only`
- **THEN** 容器以指向「仅放行公网出站、隔离内网」的预置 Docker 网络创建；该网络的创建与命名为运维侧部署前提，未预置时按 design 约定回退到安全默认（`none`）或明确报错

#### Scenario: read_only=True 时创建命令含 --read-only
- **WHEN** 资源配置 `read_only=True`（默认）
- **THEN** 容器创建命令包含 `--read-only`（文件系统只读），`--tmpfs /tmp` 仍保留

#### Scenario: read_only=False 时创建命令不含 --read-only
- **WHEN** 资源配置 `read_only=False`（agent 显式承担风险）
- **THEN** 容器创建命令不包含 `--read-only`（文件系统可写），`--tmpfs /tmp` 仍保留

### Requirement: 内存硬上限（swap 控制）

沙箱容器创建 SHALL 总是携带 `--memory-swap` flag。`memory_swap_mb` 未配置（None）时其值 SHALL 等于 `--memory`（禁 swap，内存限制成为硬 RAM 上限）；配置为正整数时表示 memory+swap 总额（MB）。flag 求值时 SHALL 钳制 `effective = max(memory_swap_mb, memory)`（Docker 要求 swap 总额 ≥ memory），钳制实际生效时 SHALL 记录 warning；任何配置组合 MUST NOT 因 swap/memory 关系导致容器创建失败。`memory_swap_mb` 与其余资源字段一样经 per-agent `agent.yaml` `sandbox.resources` 声明（不再有 `sandbox.agent_scope` 覆盖）。

#### Scenario: 默认禁 swap

- **WHEN** `memory=256` 且 `memory_swap_mb` 未配置
- **THEN** 容器创建命令包含 `--memory 256m --memory-swap 256m`，容器内超过 256 MB 的常驻分配被 OOM 终止

#### Scenario: 显式放宽 swap 总额

- **WHEN** 配置 `memory=256`、`memory_swap_mb=512`
- **THEN** 容器创建命令包含 `--memory 256m --memory-swap 512m`

#### Scenario: swap 小于 memory 时钳制兜底

- **WHEN** 配置 `memory=512`、`memory_swap_mb=256`
- **THEN** `--memory-swap` 取 512m（钳制到 memory），记录 warning，容器创建不失败

#### Scenario: 非法 memory_swap_mb 不被静默接受

- **WHEN** 配置 `memory_swap_mb=0`、负数或非整数
- **THEN** 系统记录该问题并回退默认（None，即禁 swap），不以非法值创建容器

## ADDED Requirements

### Requirement: 沙箱资源配置 per-agent 且不依赖 platform.yaml

沙箱资源/硬化/生命周期配置 SHALL 完全来自 per-agent `agent.yaml`，每个 agent 独享。`integrations/sandbox` 在解析资源限制、硬化参数、`workspace_scope`/`idle_hours`、`skill_mount` 时 MUST NOT 读取 `platform.yaml`（不再 `paths.platform_yaml_path()`）。未在 `agent.yaml` 声明的字段 SHALL 回退到代码内置安全默认（`SandboxResources()` / 既有默认），而非回落 `platform.yaml`。standalone agent（无 platform 服务、无 `platform.yaml`）SHALL 能完整解析其沙箱资源配置并创建容器。

#### Scenario: 两个 agent 独享互不影响的资源配置
- **WHEN** agent A 的 `agent.yaml` 配 `sandbox.resources.network=public_only`，agent B 不配（默认 `none`）
- **THEN** A 的容器以受限公网出站创建，B 的容器以 `--network none` 创建，互不影响

#### Scenario: 无 platform.yaml 时按 agent.yaml + 默认解析
- **WHEN** standalone agent 启动且 `platform.yaml` 不存在，`agent.yaml` 仅声明 `sandbox.resources.memory=512`
- **THEN** 沙箱以 memory=512、其余字段取代码默认创建容器，全过程不读取 `platform.yaml`

#### Scenario: 沙箱资源解析不触达 platform.yaml
- **WHEN** 解析某 agent 的沙箱资源/硬化/lifecycle/skill_mount 配置
- **THEN** 解析路径不调用 `paths.platform_yaml_path()`、不读取 `platform.yaml` 的 `sandbox.resources`/`agent_scope`/`workspace_scope`/`idle_hours`/`skill_mount`
