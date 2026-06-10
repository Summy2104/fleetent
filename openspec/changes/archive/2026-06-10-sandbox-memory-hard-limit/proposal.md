# sandbox-memory-hard-limit

## Why

沙箱容器的内存限制只设了 `--memory`，未设 `--memory-swap`。Docker 默认 `--memory-swap = 2×--memory`，因此配置 256 MB 实际允许约 512 MB（RAM+swap）——2026-06-10 本地实测确认：256m 限制下分配 400 MB 成功（exit 0），600 MB 才被 OOM 杀（exit 137），显式 `--memory-swap 256m` 后 400 MB 立即被杀。内存上限的实际语义是「RAM+swap 总额的 2 倍宽松上限」而非运维直觉的「硬 RAM 上限」，削弱了资源隔离的可预期性。

## What Changes

- `SandboxResources` 新增可选字段 `memory_swap_mb: int | None = None`：`None`（默认）表示 `--memory-swap == --memory`（禁 swap，硬 RAM 上限）；正整数表示显式的 memory+swap 总额。
- `SandboxClient._resource_flags` 追加 `--memory-swap <effective>m`，求值时钳制 `effective = max(memory_swap_mb or memory, memory)`（Docker 要求 swap 总额 ≥ memory，钳制兜底避免 `docker run` 失败，钳制时 log warn）。
- `config.py` 的 `sandbox.resources` 与 `sandbox.agent_scope` 两段均支持读取/校验 `memory_swap_mb`（正整数校验，非法回退默认并 log，复用现有 `_load_positive_int` 模式）。
- **行为变化（默认收紧）**：升级后默认禁 swap，原依赖隐式 swap 余量的负载会更早 OOM——这是本变更的目的；需要放宽的运维显式配置 `memory_swap_mb`。
- **一次性副作用**：`SandboxResources` 加字段改变 `config_hash`（其哈希 `vars(resources)` 全字段），升级后所有存活的复用容器在下次 acquire 时 hash 失配、触发一次重建。行为正确（资源语义确实变了），属预期。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `sandbox-resource-limits`: 新增「内存硬上限（swap 控制）」requirement——默认 `--memory-swap == --memory` 禁 swap；`memory_swap_mb` 可配置放宽；求值时钳制 ≥ memory。同时 MODIFIED「未配置时回退安全默认值」requirement，把 `memory_swap_mb=None（禁 swap）` 纳入默认值清单。

## Impact

- **代码**：`src/fleetent/integrations/sandbox/config.py`（`SandboxResources` 字段 + 两处 section 载入校验）、`src/fleetent/integrations/sandbox/client.py`（`_resource_flags`）。
- **配置**：`sandbox.resources.memory_swap_mb` / `sandbox.agent_scope.memory_swap_mb`（均可选，缺省禁 swap）。
- **owned tables**：无。**config namespace**：复用 `sandbox`。
- **跨模块依赖**：无新增；不触碰共享契约（`config_hash` 在 `integrations/sandbox` 包内）。
- **测试**：unit 层覆盖 `_resource_flags` 输出与 config 载入/校验/钳制；integration（真实 Docker，沿用 docker-availability skip guard）覆盖默认禁 swap 下超 memory 分配被 OOM 杀。
