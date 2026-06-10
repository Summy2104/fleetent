# sandbox-memory-hard-limit — Design

## Context

- `SandboxClient._resource_flags`（client.py）由 `SandboxResources`（config.py）驱动生成 `docker run` flags，现有 `--memory {memory}m` 但无 `--memory-swap`。
- Docker 语义：`--memory-swap` 是 **memory+swap 总额**；未设时默认 `2×--memory`；设为与 `--memory` 相等即禁 swap；设为小于 `--memory` 的值 `docker run` 直接报错。
- 2026-06-10 本地实测（Docker Desktop 28.5.1）：`--memory 256m` 下 400 MB 常驻分配存活、600 MB 被 OOM（137）；`--memory-swap 256m` 后 400 MB 立即被 OOM。
- `build_resources_by_scope` 中 agent tier 经 `replace(base, memory=override...)` 派生，`sandbox.agent_scope` 可单独 override `memory`。
- `hardening.config_hash` 哈希 `sorted(vars(resources).items())`——`SandboxResources` 任何字段增删都会改变所有容器的 config_hash。

## Goals / Non-Goals

**Goals:**

- 默认配置下内存限制成为**硬 RAM 上限**（禁 swap），实测可验证（超 memory 即 OOM）。
- 运维可显式放宽（`memory_swap_mb` 配置 memory+swap 总额）。
- 任何配置组合都不导致 `docker run` 失败（钳制兜底）。

**Non-Goals:**

- 不改 `memory` 默认值（仍 256 MB）；不动 CPU/network/pids 等其它资源维度。
- 不为 config_hash 引入字段级豁免（一次性容器重建可接受，机制保持简单）。
- 不处理 `--memory-swappiness` / `--oom-kill-disable` 等更细的内存调优旋钮（YAGNI）。

## Decisions

### D1：`memory_swap_mb: int | None = None`，None = 禁 swap（而非 None = Docker 默认）

- **选定**：`None` 表示「未显式配置 → 取最安全语义：`--memory-swap == --memory`」。
- **备选**：`None` = 不传 flag（保留 Docker 2× 默认），要求运维显式配 0 才禁 swap。否决：与「dataclass 默认即安全默认」的既有约定（spec：未配置回退安全默认）相悖——隐式 2× 余量正是本变更要修的问题，默认必须收紧。
- **字段语义**：正整数 = memory+swap 总额（MB），与 Docker flag 语义一致，不引入「swap 增量」的二次换算。

### D2：钳制在 `_resource_flags` 求值时做，而非 config 载入时

- **选定**：`effective_swap = max(memory_swap_mb or memory, memory)`，在 flag 生成处求值；钳制实际生效（`memory_swap_mb < memory`）时 log warn。
- **理由**：`agent_scope` 可单独 override `memory`（`build_resources_by_scope` 的 `replace`），载入时校验无法防住「base 配了 `memory_swap_mb=512`、agent_scope 把 memory 提到 1024」的组合穿透；flag 求值是所有组合的最终汇聚点，在此钳制保证运行时永不因此失败。
- **配合**：config 载入仍做正整数形态校验（非法值回退 None 并 log，复用 `_load_positive_int` 模式）；载入校验管「值合法性」，求值钳制管「跨字段关系」。

### D3：`agent_scope` 段同样支持 `memory_swap_mb` override

- agent tier 经 `replace(base, ...)` 派生时一并读取 `agent_scope.memory_swap_mb`（缺省继承 base）。`None` 的「等于 memory」语义在求值时才解析，因此 agent_scope 只 override `memory` 而不配 swap 时，swap 自动跟随提高后的 memory——无意外缩水。

### D4：config_hash 不做兼容处理

- 加字段后 `vars(resources)` 变化 → 全部存活容器 hash 失配 → 下次 acquire 重建一次。资源语义确实变了（旧容器没有 swap 限制），重建是**正确**行为而非副作用妥协；proposal 已声明该一次性影响。

## Risks / Trade-offs

- [默认收紧后，依赖隐式 swap 余量的现有负载更早 OOM] → 这是变更目的（可预期的硬上限）；受影响负载经 `memory_swap_mb` 或调大 `memory` 显式放宽，proposal 标注行为变化。
- [宿主/VM 无 swap 或 cgroup 不支持 swap 限制时，Docker 对 `--memory-swap` 的处理存在平台差异] → flag 恒等于或大于 memory，最坏情形与现状等价（限制不更松）；integration 测试带 docker-availability skip guard，在不支持的环境跳过而非误报。
- [一次性容器重建造成的短暂冷启动] → session 容器本就短生命周期；agent 容器重建后由 committed image 恢复依赖，符合既有生命周期设计。

## Migration Plan

1. 合入即生效：新建容器带 `--memory-swap`；存活旧容器在下次 acquire 因 config_hash 失配重建。
2. 运维如需旧行为（2× 余量），显式配 `sandbox.resources.memory_swap_mb: <2×memory>`。
3. 回滚：revert commit；旧代码不识别 `memory_swap_mb` 配置键（多余键本就被忽略），容器再经一次 hash 失配重建回无 swap-flag 形态。

## Open Questions

（无）
