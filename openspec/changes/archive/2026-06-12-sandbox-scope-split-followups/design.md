## Context

sandbox-workspace-scope-split 移除 docker-commit、改声明式 build 后,留下两个理由已失效的收尾项(见 proposal)。本 change 在其上补齐,均为小而明确的改动。已核实现状:
- `manager.resolve_workspace_scope` + `SandboxManager.multi_user`(默认 False)已存在;唯一构造点 `builtin_tools.init_sandbox_manager` 未传 multi_user → 恒 False、护栏永不触发。
- `config.build_resources_by_scope`:agent 档 `read_only=False` / `cap_add=_AGENT_CAP_ADD` / `run_as_user=None`(config.py:239-241),注释仍称"writable rootfs for docker commit"(已过时)。
- `acquire` 对 mounted workspace 无条件 `ws_path.chmod(0o777)`,非 root 用户可写 `/workspace`(不依赖 scope)。

## Goals / Non-Goals

**Goals:**
- multi_user 由显式配置 `sandbox.multi_user`(默认 false)驱动,真正接入 `init_sandbox_manager` → 护栏生效。
- agent 加固档收紧为与 session 同档(read_only + 非 root + 不补 caps),清理过时注释。

**Non-Goals:**
- 不在 agent 运行时 import platform(multi_user 经 agent.yaml 配置传递,platform 生成配置时写入)。
- 不改声明式 build / workspace_scope 语义(本 change 只补信号接线 + 加固收紧)。
- 不改 session 档(本就最严)。

## Decisions

### D1:multi_user 经 agent.yaml `sandbox.multi_user` 显式配置
新增 `SandboxSettings.multi_user: bool = False`(extra=forbid);`init_sandbox_manager` 读 `resolved.sandbox.multi_user` 传入 `SandboxManager(multi_user=...)`。护栏(已存在)在 `__post_init__` 据此纠正。
- **备选**:agent 运行时自动探测多用户(如看 IM 入口形态)。否决——agent 运行时不应承载 platform 拓扑知识,且探测易错;显式配置最简单可靠、零反向依赖。
- platform 侧:生成多用户共享 agent 的 agent.yaml 时写 `sandbox.multi_user: true`(本 change 不含 platform 改动,属配置约定)。

### D2:agent 加固档收紧为与 session 同档
`build_resources_by_scope` 的 agent 档去掉 `read_only=False` / `cap_add=_AGENT_CAP_ADD` / `run_as_user=None` 三处放松——agent 档继承 base(session)的 read_only=True / 非 root / 无额外 cap。保留 agent 档可经 `sandbox.agent_scope` 覆盖的 memory/cpus/network 等非加固字段。清理"writable rootfs for docker commit"陈旧注释。`_AGENT_CAP_ADD` 常量若不再被引用则删除。
- 依赖来自 build 期不可变镜像(#4 已落地),运行期无需写 rootfs/装依赖;`/workspace` 仍可写(bind mount + 既有 chmod)。
- **风险**:既有 hardening 测试断言 agent 档补 caps/root → 需按新档更新(见 tasks)。

## Risks / Trade-offs

- **存量 agent-scope 容器配置漂移**:agent 档资源变更使 config_hash 改变 → 既有 agent 容器复用时失配重建。可接受(重建从只读镜像启动,数据在 workspace 不丢)。
- **声明式 build 仍需 build 期可写**:收紧的是**运行期**档位;build 期(`build_deps_image` 的 `docker build`)本就在独立构建上下文,不受运行期 read_only 影响。已确认无冲突。
- **multi_user 默认 false**:若 platform 未写 `true`,多用户部署仍可能漏配 → 但默认 workspace_scope=session 本就安全,且本 change 把"信号来源"明确为配置项,platform 接入是一行配置。

## Migration Plan

- 无 DB 迁移。新增配置字段默认 false,行为不变。
- agent 档收紧对存量 agent-scope 容器经 config_hash 触发重建,无需手动迁移。
- Rollback:回滚代码即可。

## Open Questions

- 无(均为已明确的小改动)。
