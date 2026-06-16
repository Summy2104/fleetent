# sandbox-resource-limits Specification

## Purpose
TBD - created by archiving change sandbox-resource-limits. Update Purpose after archive.
## Requirements
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

### Requirement: 未配置时回退安全默认值

任一资源字段未配置时 SHALL 回退到安全默认值：`memory=256`（MB）、`cpus=0.5`、`network=none`、`exec_timeout=30`（秒）、`read_only=True`、`memory_swap_mb=None`（等效 `--memory-swap == --memory`，禁 swap）。配置文件不存在时 MUST 全部使用默认值。`network=none` 为默认且推荐值；`read_only=True` 为默认（保 session 只读现状）；禁 swap 为默认（内存限制为硬 RAM 上限）。

#### Scenario: 缺字段逐项回退

- **WHEN** 配置仅声明 `memory=512`，未声明其余字段
- **THEN** `memory` 为 512，`cpus`/`network`/`exec_timeout` 取默认值（0.5 / none / 30），`--memory-swap` 等于 `--memory`（512m，禁 swap）

#### Scenario: 无配置文件全默认

- **WHEN** 配置文件不存在
- **THEN** 资源限制全部使用安全默认值，容器仍能以默认隔离参数创建（含 `--memory-swap 256m`）

### Requirement: 非法资源配置不被静默接受

资源配置值非法时（如内存或 CPU 非正、网络策略不在允许枚举内）系统 MUST NOT 静默接受非法值；SHALL 记录后回退安全默认值或明确报错，不得吞异常。`exec_timeout` 超出允许范围时 SHALL 被 clamp 到 `[1, 600]`（< 1 → 1，> 600 → 600）。

#### Scenario: 非法值安全处理
- **WHEN** 配置 `memory=0` 或 `network` 为未知字符串
- **THEN** 系统记录该问题并回退默认值或抛出明确错误，不以非法值创建容器

#### Scenario: exec_timeout 超范围被 clamp
- **WHEN** 配置 `exec_timeout=0`（或 `exec_timeout=1000`）
- **THEN** 该值被 clamp 到范围边界（`1`，或 `600`），以合法值承载传递

### Requirement: exec_timeout 仅承载不在本能力强制终止

`exec_timeout` SHALL 被读入并随配置传递，供后续超时终止能力消费。本能力 MUST NOT 实现执行超时后的强制终止（`docker kill`）行为。

#### Scenario: 超时值被读取但不触发终止
- **WHEN** 配置声明 `exec_timeout=30` 并创建容器
- **THEN** 该值被读入资源配置，但容器创建命令不包含任何强制终止逻辑

### Requirement: 沙箱客户端按次传入资源配置构造创建命令

沙箱客户端创建容器时 SHALL 据**按次传入**的资源配置构造 `docker run` 命令，不在客户端构造期固定一套资源策略；未传入资源配置时 MUST 退回与现状等价的安全默认值（含 `read_only=True`）。`--tmpfs /tmp` 可写临时目录的行为保持不变。

> 归属说明：本需求是 Docker 后端新增能力，落在本 change 的新 capability `sandbox-resource-limits` 下以 ADDED 表达。既有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。

#### Scenario: 据配置构造命令
- **WHEN** 以指定资源配置创建容器
- **THEN** `docker run` 命令包含与配置一致的内存、CPU、网络标志

#### Scenario: 同一客户端按次传入不同资源配置
- **WHEN** 同一沙箱客户端先后以只读档位、可写档位两次创建容器
- **THEN** 两次创建命令分别据各自传入的资源配置构造，互不影响（客户端构造期不固定资源策略）

#### Scenario: 不传配置退回默认
- **WHEN** 不传入资源配置创建容器
- **THEN** 创建命令与现状等价（默认内存/CPU/无网络/只读文件系统）

### Requirement: 资源配置字段按后端归属消费

`SandboxResources` 的字段 SHALL 按后端归属消费：通用字段（`memory`、`cpus`、`network`、`exec_timeout`、`read_only`）为接口契约，每个后端 MUST 映射到等价的资源/隔离原语；Docker 专属硬化字段（`pids_limit`、`tmpfs_size_mb`、`cap_drop_all`、`cap_add`、`no_new_privileges`、`init`、`run_as_user`）MUST 仅由 Docker 后端渲染，其他后端 MUST 忽略且不报错。字段归属 MUST 在数据类文档中标注。既有 Docker 渲染需求（`docker run` 旗标构造）不变，约束 Docker 后端。

#### Scenario: 通用字段在 microsandbox 后端生效
- **WHEN** microsandbox 后端以 `memory=512`、`cpus=1.0` 创建工作区
- **THEN** microVM 以等价的内存与 CPU 限制启动

#### Scenario: Docker 专属字段在其他后端被忽略
- **WHEN** microsandbox 后端收到含 `pids_limit`、`cap_drop_all` 等字段的资源配置
- **THEN** 工作区正常创建，这些字段不产生任何效果也不报错

#### Scenario: Docker 后端行为不变
- **WHEN** Docker 后端以同一资源配置创建容器
- **THEN** 通用字段与硬化字段的 `docker run` 旗标渲染与引入抽象前一致

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

