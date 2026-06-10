# sandbox-resource-limits — Delta（sandbox-memory-hard-limit）

## ADDED Requirements

### Requirement: 内存硬上限（swap 控制）

沙箱容器创建 SHALL 总是携带 `--memory-swap` flag。`memory_swap_mb` 未配置（None）时其值 SHALL 等于 `--memory`（禁 swap，内存限制成为硬 RAM 上限）；配置为正整数时表示 memory+swap 总额（MB）。flag 求值时 SHALL 钳制 `effective = max(memory_swap_mb, memory)`（Docker 要求 swap 总额 ≥ memory），钳制实际生效时 SHALL 记录 warning；任何配置组合 MUST NOT 因 swap/memory 关系导致容器创建失败。`sandbox.agent_scope` 段 SHALL 支持 override `memory_swap_mb`；agent_scope 仅 override `memory` 而未配 swap 时，swap 上限 SHALL 跟随 override 后的 memory（None 语义在求值时解析）。

#### Scenario: 默认禁 swap

- **WHEN** `memory=256` 且 `memory_swap_mb` 未配置
- **THEN** 容器创建命令包含 `--memory 256m --memory-swap 256m`，容器内超过 256 MB 的常驻分配被 OOM 终止

#### Scenario: 显式放宽 swap 总额

- **WHEN** 配置 `memory=256`、`memory_swap_mb=512`
- **THEN** 容器创建命令包含 `--memory 256m --memory-swap 512m`

#### Scenario: swap 小于 memory 时钳制兜底

- **WHEN** 配置 `memory=512`、`memory_swap_mb=256`（或 agent_scope 把 memory override 到大于 base 的 `memory_swap_mb`）
- **THEN** `--memory-swap` 取 512m（钳制到 memory），记录 warning，容器创建不失败

#### Scenario: agent_scope 只提 memory 时 swap 跟随

- **WHEN** base 未配置 `memory_swap_mb`，`sandbox.agent_scope` 配置 `memory=1024`
- **THEN** agent tier 容器创建命令包含 `--memory 1024m --memory-swap 1024m`

#### Scenario: 非法 memory_swap_mb 不被静默接受

- **WHEN** 配置 `memory_swap_mb=0`、负数或非整数
- **THEN** 系统记录该问题并回退默认（None，即禁 swap），不以非法值创建容器

## MODIFIED Requirements

### Requirement: 未配置时回退安全默认值

任一资源字段未配置时 SHALL 回退到安全默认值：`memory=256`（MB）、`cpus=0.5`、`network=none`、`exec_timeout=30`（秒）、`read_only=True`、`memory_swap_mb=None`（等效 `--memory-swap == --memory`，禁 swap）。配置文件不存在时 MUST 全部使用默认值。`network=none` 为默认且推荐值；`read_only=True` 为默认（保 session 只读现状）；禁 swap 为默认（内存限制为硬 RAM 上限）。

#### Scenario: 缺字段逐项回退

- **WHEN** 配置仅声明 `memory=512`，未声明其余字段
- **THEN** `memory` 为 512，`cpus`/`network`/`exec_timeout` 取默认值（0.5 / none / 30），`--memory-swap` 等于 `--memory`（512m，禁 swap）

#### Scenario: 无配置文件全默认

- **WHEN** 配置文件不存在
- **THEN** 资源限制全部使用安全默认值，容器仍能以默认隔离参数创建（含 `--memory-swap 256m`）
