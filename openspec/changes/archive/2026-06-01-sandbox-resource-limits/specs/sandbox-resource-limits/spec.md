## ADDED Requirements

### Requirement: 沙箱资源限制经配置声明

沙箱资源限制（内存 `memory`、CPU `cpus`、网络策略 `network`、单次执行超时 `exec_timeout`、文件系统只读 `read_only`）SHALL 经配置声明，不再硬编码。配置 MUST 支持嵌套 `sandbox.resources` 结构，各字段均为可选。`read_only` 纳入资源档位、可配置。

#### Scenario: 配置值生效到容器创建
- **WHEN** 配置声明 `memory=512`、`cpus=1.0`
- **THEN** 创建沙箱容器时的资源限制相应为 512 MB 内存、1.0 CPU

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
- **WHEN** 资源配置 `read_only=True`（session 默认）
- **THEN** 容器创建命令包含 `--read-only`（文件系统只读），`--tmpfs /tmp` 仍保留

#### Scenario: read_only=False 时创建命令不含 --read-only
- **WHEN** 资源配置 `read_only=False`（agent scope 可写，由 SB2 传入）
- **THEN** 容器创建命令不包含 `--read-only`（文件系统可写），`--tmpfs /tmp` 仍保留

### Requirement: 未配置时回退安全默认值

任一资源字段未配置时 SHALL 回退到安全默认值：`memory=256`（MB）、`cpus=0.5`、`network=none`、`exec_timeout=30`（秒）、`read_only=True`。配置文件不存在时 MUST 全部使用默认值。`network=none` 为默认且推荐值；`read_only=True` 为默认（保 session 只读现状）。

#### Scenario: 缺字段逐项回退
- **WHEN** 配置仅声明 `memory=512`，未声明其余字段
- **THEN** `memory` 为 512，`cpus`/`network`/`exec_timeout` 取默认值（0.5 / none / 30）

#### Scenario: 无配置文件全默认
- **WHEN** 配置文件不存在
- **THEN** 资源限制全部使用安全默认值，容器仍能以默认隔离参数创建

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
