## Why

`SandboxClient` 创建的容器以 `sandbox-` 前缀命名（`sandbox_client.py` 行 29：`--name f"sandbox-{safe}"`）。若平台异常退出（崩溃、被 kill、容器未走正常销毁路径），这些 `sandbox-*` 容器会遗留在 Docker 中——占用内存/CPU 配额、累积成「孤儿容器」，且重启后名称冲突可能导致再次 `docker run` 失败。当前没有任何清理路径：`destroy_workspace` 只在正常 `finally` 分支调用，崩溃时不会执行。

`docs/capabilities/sandbox.md` 的「孤儿容器清理」与启动子图要求：平台启动时检测并销毁上次遗留的孤儿容器（`sandbox-*` 前缀）。roadmap 已决定**调度器触发暂缓**，因此本 change 把清理设计为**平台启动时触发 + 按需手动触发**，不依赖 cron/APScheduler。沙箱后端保留 Docker，清理通过 `docker ps` 枚举 + `docker rm -f` 实现。

## What Changes

- 引入**孤儿沙箱清理** `cleanup_orphans()`：枚举所有 `sandbox-` 前缀的容器（`docker ps -a --filter name=sandbox-`），逐个 `docker rm -f` 销毁，返回清理计数。
- **平台启动时触发**：server 启动（lifespan）时调用一次 `cleanup_orphans()`，回收上次崩溃遗留的孤儿容器；清理失败（如 Docker 不可用）记录警告但不阻断启动。
- **按需触发入口**：提供可被 admin CLI 或运维手动调用的清理入口（同一 `cleanup_orphans()` 函数），不绑定调度器。
- 清理范围限定 `sandbox-` 前缀，**不误删**非沙箱容器；与 SB2 的容器命名前缀常量复用单一事实来源（避免命名规则两处漂移）。

## Capabilities

### New Capabilities
- `sandbox-orphan-cleanup`: 孤儿沙箱容器清理——枚举 `sandbox-` 前缀容器并销毁，回收上次异常退出遗留的资源；平台启动时自动触发一次 + 提供按需手动触发入口；不依赖调度器；严格限定前缀范围，不误删非沙箱容器。

### Modified Capabilities
<!-- 不修改既有 spec。既有 sandbox-client 主 spec 为 microsandbox 历史版本，与本 change 引入的 Docker 后端能力无对应需求，故不以 MODIFIED 表达。「按前缀枚举容器」属 Docker 后端新增能力，落在本 change 新 capability `sandbox-orphan-cleanup` 下以 ADDED 表达。 -->

### 共享资源引用
- **`sandbox-` 前缀命名常量 owner = `sandbox_client.py`**：`SANDBOX_NAME_PREFIX = "sandbox-"` 定义在最底层的 `sandbox_client.py`（避免循环依赖），SB2（生命周期命名）使用、本 change（孤儿枚举）复用同一常量。两 change 一致指向此处，不各执一词（不在 manager / cleanup 各自定义）。

## Impact

- **代码**：
  - 新增 `src/fleetent/sandbox_cleanup.py`（`SANDBOX_NAME_PREFIX` 常量复用/引用 + `cleanup_orphans()`：枚举 → 销毁 → 返回计数）。
  - 修改 `src/fleetent/sandbox_client.py`：增加 `list_containers(name_prefix) -> list[str]`（`docker ps -a --filter name=`，返回容器名/ID 列表，Docker 不可用时返回空列表不抛）；销毁复用既有 `destroy_workspace`（`docker rm -f`）。
  - 修改 `src/fleetent/server.py`：lifespan 启动段调用 `cleanup_orphans()`，失败记录警告不阻断（与 SB3 Docker 降级路径协调）。
- **配置**：无新增配置（清理无参数，前缀为常量）。
- **测试**：新增 `tests/test_sandbox_cleanup.py`（枚举→销毁→计数、空列表、前缀限定不误删、Docker 不可用安全跳过）；扩充 `tests/test_sandbox_client.py` 覆盖 `list_containers`。Docker CLI 全部 mock（`patch asyncio.create_subprocess_exec`），不触碰真实容器。
- **不影响**：SB2 生命周期复用逻辑（清理只回收遗留容器，不影响活跃容器的复用——启动期活跃容器尚不存在）、SB3 mode、SB4 资源、agent_loop；不引入新依赖（**不引入 APScheduler 等调度器**）。
