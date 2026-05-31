## Context

`SandboxClient` 用 `--name f"sandbox-{safe}"` 命名容器（sandbox_client.py 行 29），销毁经 `destroy_workspace`（`docker rm -f`，行 60-68）。但 `destroy_workspace` 只在 `tools.py::run_code` 的 `finally` 分支被调用——平台崩溃、容器进程被 kill、或未来 SB2 的 session/agent 容器未走正常释放路径时，`sandbox-*` 容器会遗留为孤儿。`server.py` 已有 `lifespan`（asynccontextmanager，行 66-67）作为启动钩子（现用于 skill 扫描等），是启动期清理的天然挂载点。

`docs/capabilities/sandbox.md` 的启动子图：`平台启动 → Docker 可用? → 扫描遗留容器（sandbox-* 前缀）→ 销毁孤儿容器 → 平台就绪`。「孤儿容器清理」明确为启动期行为。roadmap 决定调度器触发暂缓，故本 change 不引入 APScheduler、不做定期清理，只做启动时一次 + 按需手动。

**既有 spec 归属说明**：现有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。本 change 引入的全部能力（含 SandboxClient 的按前缀枚举）均为新增，以新 capability `sandbox-orphan-cleanup` 下的 ADDED 表达，不对 sandbox-client 主 spec 做 MODIFIED（否则 archive sync 找不到同名既有需求）。

**共享资源引用**：`sandbox-` 前缀命名常量 `SANDBOX_NAME_PREFIX = "sandbox-"` **定义在 `sandbox_client.py`**（最底层，避免循环依赖），SB2 与本 change 一致 import 之，单一事实来源。SB2 design 已同向指向此处。

约束（CLAUDE.md）：禁止全局可变状态；新模块 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 mock Docker CLI、不发真实 docker；不吞异常（清理失败要 log）；不引入未经讨论的新依赖（明确不引入调度器）。

## Goals / Non-Goals

**Goals:**
- `cleanup_orphans()`：枚举 `sandbox-` 前缀容器并 `docker rm -f` 销毁，返回清理计数。
- 平台启动（lifespan）时触发一次；失败记录警告不阻断启动。
- 提供同一函数作为按需手动触发入口（admin/运维可调）。
- 严格限定 `sandbox-` 前缀，不误删非沙箱容器。

**Non-Goals:**
- 不引入调度器、不做定期/周期清理（roadmap 暂缓）。
- 不区分「活跃容器 vs 孤儿容器」做精细判断——启动期所有 `sandbox-*` 容器都是前次遗留（本进程尚未创建任何容器），全部回收即可。
- 不实现 scope（SB2）、mode（SB3）、资源（SB4）、密钥（SB5）、trace（SB9）。

## Decisions

### D1：清理函数独立模块，复用 SandboxClient 的枚举与销毁
新增 `src/fleetent/sandbox_cleanup.py`：
- 引用单一前缀常量 `SANDBOX_NAME_PREFIX = "sandbox-"`——**定义在 `sandbox_client.py`**（已与 SB2 收口统一，见 Context），本模块 `from fleetent.sandbox_client import SANDBOX_NAME_PREFIX`，不在本模块或 manager 重复定义。
- `cleanup_orphans(client: SandboxClient) -> int`：`names = await client.list_containers(SANDBOX_NAME_PREFIX)`；逐个 `await client.destroy_workspace(name)`；返回成功销毁数；Docker 不可用（`list_containers` 返回空）时返回 0。

**为何**：清理是「枚举 + 销毁」的组合，枚举/销毁都是 Docker CLI 操作，归 `SandboxClient`；编排逻辑独立成 `sandbox_cleanup` 便于被 lifespan 与 admin 复用。前缀常量单一来源避免与 SB2 命名漂移。
**Alternatives**：把清理塞进 `SandboxClient`——可行但清理是「跨容器编排」而非单容器操作，独立函数职责更清晰，也便于 mock 测试编排逻辑。

### D2：`list_containers` 用 `docker ps -a --filter name=` 且 Docker 不可用安全降级
`SandboxClient.list_containers(name_prefix: str) -> list[str]`：执行 `docker ps -a --filter name={prefix} --format {{.Names}}`，按行解析返回名称列表；命令失败 / Docker 不存在 / 返回非零时返回空列表并 log 警告（不抛）。
**为何**：`--filter name=` 让 Docker 侧做前缀过滤，减少传输；`-a` 含已停止容器（孤儿可能已 exited 但未删）；安全降级与 SB3 的 Docker 不可用路径一致——清理在无 Docker 环境下静默无操作，不阻断启动。
**Alternatives**：枚举全部容器后在 Python 侧过滤前缀——被否，`--filter` 由 Docker 高效完成且语义清晰。**Trade-off**：`--filter name=` 是子串匹配（Docker 行为），可能匹配到名字含但不以 `sandbox-` 开头的容器→在 Python 侧二次校验 `name.startswith(prefix)` 兜底，确保前缀语义（见 D3）。

### D3：严格前缀校验防误删
对 `list_containers` 返回的每个名称，销毁前在 Python 侧再校验 `name.startswith(SANDBOX_NAME_PREFIX)`，不满足的跳过。
**为何**：Docker `--filter name=` 是子串匹配，可能误纳入名字中段含 `sandbox-` 的无关容器；二次前缀校验确保只删真正的沙箱容器，符合「不误删非沙箱容器」的硬要求。
**Alternatives**：信任 `--filter`——被否，子串匹配语义有误删风险，数据/资源安全上不能信任。

### D4：lifespan 启动期触发，失败不阻断
`server.py` lifespan 启动段调用 `cleanup_orphans()`，包在 try/except 中：异常 log 警告后继续启动（与 sandbox.md「Docker 不可用 → 降级 → 平台就绪」一致）。
**为何**：清理是尽力而为的资源回收，不应成为启动的硬依赖；与 SB3 的启动期 Docker 降级在同一启动段协调（先探测 Docker → 降级 mode → 若可用则清理孤儿）。
**Open**：清理与 SB3 Docker 探测的先后/合并——建议「探测一次，结果同时用于 mode 降级与是否执行清理」，避免重复探测（见 Open Questions）。

## Risks / Trade-offs

- [误删运维自己的非 fleetent 容器] → 严格 `sandbox-` 前缀 + Python 侧 `startswith` 二次校验；spec 用 scenario 钉死「非前缀容器不被删」。
- [启动期清理删掉本进程稍后要用的容器] → 启动期本进程尚未创建任何 `sandbox-*` 容器，所有此前缀容器都是遗留孤儿，全删安全；SB2 的活跃容器在启动后才创建。
- [Docker 不可用时清理报错阻断启动] → `list_containers` 返回空、`cleanup_orphans` 返回 0、lifespan try/except 兜底；spec 覆盖「Docker 不可用安全跳过」。
- [前缀常量与 SB2 命名规则漂移] → 单一常量来源（SB2 导出 / 本模块定义二选一，落地时统一），两处引用同一常量。

## Open Questions

- ~~前缀常量归属~~ **已定**：定义在最底层的 `sandbox_client.py` 供 SB2/SB8 import，避免循环依赖（与 SB2 design 一致收口）。
- 与 SB3 启动期 Docker 探测合并：探测一次结果复用（可用才清理），还是各自独立探测？建议合并以省一次子进程调用。
- 按需触发是否需要 admin CLI 子命令（如 `fleetent-admin sandbox-cleanup`）？本 change 提供函数入口，CLI 暴露可作为 SB8 的可选收尾或独立小改动。
- 清理是否记录每个被删容器的名称到日志/trace 供审计？（建议至少 log 计数与名称列表；写 trace 与 SB9 协调）
