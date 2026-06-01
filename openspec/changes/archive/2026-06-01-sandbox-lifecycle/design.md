## Context

`tools.py::run_code` 当前直接 `client = SandboxClient(); ws = await client.create_workspace("run-code"); ... finally: await client.destroy_workspace(ws)`：每次工具调用一个全新容器，固定名 `sandbox-run-code`，执行完即毁。`SandboxClient`（`sandbox_client.py`）封装 `docker run -d` / `docker exec` / `docker rm -f`，容器名为 `sandbox-{清洗后的 session_id}`，资源限制（`--network none --memory 256m --cpus 0.5 --read-only --tmpfs /tmp`）硬编码。没有任何地方记录「哪个容器属于哪个 session / agent、是否可复用、何时销毁」。

`docs/capabilities/sandbox.md` 的 lifecycle 子图把 scope 定为容器粒度的单一开关：`session`（会话内复用，结束销毁）与 `agent`（跨会话保留，`docker commit` 固化依赖，`idle_hours` 闲置销毁）。本 change（SB2）**不是地基，而是 SB3（配置/通道）+ SB4（资源档位）的消费方**：它消费 SB3 的 run_code 上下文通道与 `sandbox:` 配置段、消费 SB4 的 `SandboxResources` 数据类，在其上拥有「scope→资源档位」映射与容器生命周期语义。实施顺序为 **SB3 → SB4 → SB2**。本 change 的职责是把 scope 语义、容器命名契约、scope→档位映射定准。

**既有 spec 归属说明**：现有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本（需求名为 Per-session workspace lifecycle / Tool execution in sandbox / Cross-session isolation / Sandbox failure handling / Host connectivity），属既有技术债，不在本 change 范围。本 change 引入的全部能力（含 SandboxClient 的 Docker 后端扩展）均为新增，以新 capability `sandbox-lifecycle` 下的 ADDED 表达，不对 sandbox-client 主 spec 做 MODIFIED（否则 archive sync 找不到同名既有需求）。

**共享资源归属与依赖顺序**：
- **`sandbox-` 前缀命名常量定义在 `sandbox_client.py`**（最底层，避免循环依赖）：本 change 使用、SB8（孤儿清理）复用同一常量；两 change 的 design 一致指向此处。
- **run_code 上下文通道 owner = SB3**：`run_code(code)` 签名只有 `code`，`dispatch` 不透传 session_id / agent_name / features。「新增 agent/session 上下文经 agent_loop → tool_registry.dispatch → tools.run_code 的传递通道」由 SB3 拥有实现任务；本 change 的 `acquire(scope, session_id, agent_name)` 复用该通道获取 session_id / agent_name，**不各自重造**。故本 change 在实施顺序上依赖 SB3 先落地该通道（归档顺序：SB3 在 SB2 之前，或二者在 SB3 落地通道后并行）。
- **`config/settings.yaml` 的 `sandbox:` 段骨架 owner = SB3**：本 change 仅向该段追加 `scope` / `idle_hours` 两个生命周期字段，不建段。
- **`SandboxResources` 数据类 + `sandbox.resources` / `sandbox.agent_scope` 字段 owner = SB4**：SB4 定义资源档位数据类（含 `read_only` / `network` / `memory` / `cpus`）及对应配置字段。本 change **消费**之，并拥有「scope→档位」映射策略——`session` 用 `sandbox.resources`（加固档），`agent` 用 `sandbox.resources` 叠加 `sandbox.agent_scope` override（`read_only=False` + 可配置 `network`）。故本 change 在实施顺序上依赖 SB4 先落地 `SandboxResources`（实施顺序 **SB3 → SB4 → SB2**）。本 change 不自引 network/read_only 旋钮。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（路径/配置常量可 monkeypatch，容器登记表挂在 `SandboxManager` 实例上而非模块级全局）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock Docker CLI（`asyncio.create_subprocess_exec`），不发真实 docker 命令；不吞异常。

## Goals / Non-Goals

**Goals:**
- 定义 `Scope` 两态（`session` / `agent`）与「按 (scope, session_id, agent_name) 取容器」的统一入口。
- `session` scope：会话内多次 `run_code` 复用同一容器；会话结束（`release_session`）销毁。
- `agent` scope：同 agent 跨会话复用同一容器；销毁前 `docker commit` 固化依赖；闲置超 `idle_hours` 由 `sweep_idle()` 销毁。
- 容器命名编码归属（`sandbox-{scope}-{key}`），供复用查找与 SB8 孤儿识别共用前缀约定。
- 拥有「scope→资源档位」映射策略：消费 SB4 的 `SandboxResources`，session 用加固档、agent 叠加 `read_only=False` + 可配置 network 的 override。
- `SandboxClient` 扩展 `find_workspace` / `commit_workspace`，并把 create 签名收敛为 `create_workspace(name, resources, image)`（既有可观察创建行为兼容）。

**Non-Goals:**
- 不**定义** `SandboxResources` 数据类与资源旋钮字段（属 SB4，本 change 仅消费并做 scope→档位映射）；不实现 mode/agent 级启用控制（SB3）、不实现密钥/环境变量过滤（SB5）、不实现孤儿清理触发（SB8，仅与其约定命名前缀）、不实现执行 trace（SB9）。
- 不实现执行超时与强制终止（波次 3，依赖 cancel token）。
- 不改 agent_loop、permission_gate、工具访问控制；不引入新依赖。

## Decisions

### D1：生命周期层为实例对象 `SandboxManager`，容器登记表挂实例而非模块全局
新增 `src/fleetent/sandbox_manager.py`：
- `Scope`：`str` 枚举，`SESSION = "session"` / `AGENT = "agent"`。
- `SandboxManager`：持有一个 `SandboxClient`、「scope→`SandboxResources` 档位」映射（消费 SB4 的 `sandbox.resources` / `sandbox.agent_scope`）与一个内存登记表 `dict[str, _Entry]`（key 为容器名，`_Entry` 记 workspace_id / scope / last_used 时间戳）。
- `acquire(scope, session_id, agent_name) -> str`：按 scope 算出容器名与资源档位（session 用加固档、agent 叠加 `read_only=False` override），先 `find_workspace` 查已存在（复用并刷新 last_used），否则 `create_workspace(name=..., resources=..., image=...)` 新建并登记。
- `release_session(session_id)`：销毁该 session 的 `session` scope 容器。
- `sweep_idle()`：遍历登记表，对 `agent` scope 且 `now - last_used > idle_hours` 的容器先 `commit_workspace` 再 `destroy_workspace`。

**为何**：CLAUDE.md 禁止全局可变状态、要求可 `monkeypatch` 注入；把登记表与依赖（`SandboxClient`、`scope`、`idle_hours`）放在实例上，测试可直接构造隔离实例，无需 patch 模块全局。idle_hours/scope 作为构造参数（默认值来自配置），路径/默认值常量留在模块级且可注入。
**Alternatives**：①模块级全局字典记容器——被否，违反「禁止全局可变状态」、测试需反复清理；②把生命周期塞进 `SandboxClient`——被否，`SandboxClient` 是无状态的 Docker CLI 薄封装（现状每次新建即用即弃），混入跨调用状态会破坏其单一职责，也不利于 SB8 复用 client 做无状态销毁。

### D2：容器命名编码归属 `sandbox-{scope}-{key}`
- `session` scope：`sandbox-session-{清洗后的 session_id}`，key 为 session_id。
- `agent` scope：`sandbox-agent-{清洗后的 agent_name}`，key 为 agent_name。
- 清洗复用现有 `_SAFE_NAME` 正则与截断逻辑（保持与现状一致的安全字符集）。
- 前缀常量 `SANDBOX_NAME_PREFIX = "sandbox-"` **定义在 `sandbox_client.py`**（最底层，避免循环依赖）：本 change 的命名规则与 SB8 的孤儿枚举共用同一常量来源，两处 import 之，单一事实来源。

**为何**：单一命名规则同时满足三件事——复用查找（`find_workspace` 按名查）、归属判定（从名字解析 scope/key）、SB8 孤儿识别（统一 `sandbox-` 前缀）。把约定写进命名，避免再引入旁路状态表。前缀常量放最底层的 `sandbox_client.py`，SB2/SB8 一致引用，避免「SB2 放 manager、SB8 放 client」两处漂移。
**Alternatives**：用 Docker label 记归属——可行但需 `docker inspect` 解析，比按名匹配重；本轨已用 `sandbox-` 前缀约定（sandbox.md 明确），沿用即可。**Open**：是否额外打 label 以便 `docker ps --filter label` 精确筛选，留作 SB8 决定（见 Open Questions）。

### D3：agent 容器降档（可写 rootfs + 可配置 network）以使 `docker commit` 固化依赖成立
按 scope 选择资源档位（消费 SB4 的 `SandboxResources`）：
- `session` scope：用 `sandbox.resources` 加固档——保持 `read_only=True`（`--read-only`）+ `network=none`（`--network none`），与现状全加固一致。
- `agent` scope：用 `sandbox.resources` 叠加 `sandbox.agent_scope` override——`read_only=False`（**去掉 `--read-only`**，rootfs 可写以容纳 site-packages）+ `network` 可配置（默认仍可收紧，按需放开装依赖）。

`agent` scope 容器在 `sweep_idle()` 销毁前先 `commit_workspace(ws_id, image_tag)`，`image_tag` 形如 `fleetent-sandbox-agent-{key}:latest`；下次 `acquire(agent)` 新建时把该 tag 作为 `image` 传入（存在则用，不存在回退到默认 `python:3.12-slim`）。

**为何**：原 D3 假设 commit 可在全加固容器上固化依赖，但 `--read-only` 下 site-packages 无法写入 rootfs，`docker commit` 捕获不到依赖层——固化形同空操作。**可写 rootfs 是 agent scope 依赖固化能成立的前提**：去掉 `--read-only` 后安装的依赖落在 rootfs，commit 才能把它捕获为镜像层，下次基于该镜像快速恢复（sandbox.md 的要求）。session scope 不需要跨会话固化依赖，故保持全加固。
**Trade-off**：agent 容器放宽 rootfs 写与 network 是有意的安全权衡——agent scope 本就是「长期、可信、需装依赖」的环境，加固让位于可用性；session scope（一次性、不可信代码）维持最严。commit 会累积镜像层、占磁盘；本 change 只在销毁前 commit 一次（非每次执行后），层数受控；镜像清理策略（如保留最近一份）留作 Open Question，不在本 change 强约束。

### D4：run_code 改为「申请—执行—不主动销毁」，session_id/agent_name 经 SB3 上下文通道获取
`run_code` 通过传入的 `SandboxManager`（或默认单实例）`acquire(scope, session_id, agent_name)` 取 workspace，执行后**不** `destroy_workspace`；销毁交由 `release_session`（会话结束）与 `sweep_idle`（agent 闲置）。
`acquire` 需要的 `session_id` / `agent_name` 来自 **SB3 拥有的 run_code 上下文通道**（agent_loop → tool_registry.dispatch → tools.run_code）。本 change **不自造**该通道，仅在通道落地后从中读取上下文值；故实施依赖 SB3 先行（见 Context 的依赖顺序）。
**为何**：复用是 scope 的核心价值；即建即毁与复用语义冲突。会话结束的 `release_session` 触发点由 session_mgr / server 侧后续接线（本 change 提供入口与单测，接线点在 Open Questions 标注，不强行改 session 生命周期）。
**Alternatives**：在 run_code 内按 scope 决定是否销毁——被否，销毁时机（会话结束 / 闲置）超出单次工具调用的可见范围，应由生命周期层掌握。各自重造上下文通道——被否，dispatch 签名改造是单点，由 SB3 统一拥有，SB2/SB5 复用。

## Risks / Trade-offs

- [容器复用导致状态泄漏（前一次 run_code 在 /tmp 写的文件被后一次看到）] → 这是 scope 复用的预期语义（session 内本就该共享）；spec 明确「同一 session/agent 内状态可见、跨 session/agent 隔离」，由命名 key 保证隔离边界。
- [`release_session` 的接线点未定，session 结束不触发销毁会导致 session 容器堆积] → 本 change 提供 `release_session` 与 `sweep_idle` 入口并单测；接线由 session_mgr/server 后续 change 完成，SB8 的启动清理作为兜底回收前次遗留容器。
- [SB8 启动清理用 `docker rm -f` 回收 agent 容器，绕过本 change 的「销毁前 commit 固化依赖」→ 丢失 agent scope 已固化依赖] → **结论：接受丢失**。SB8 的孤儿清理只在平台启动期运行，此时回收的是上次异常退出遗留的容器；agent scope 的依赖固化应是「可重建」的（下次 `acquire(agent)` 找不到镜像则回退默认 `python:3.12-slim` 并重装），而非「不可恢复的状态」。正常路径（`sweep_idle`）仍 commit-then-destroy 保留依赖；仅崩溃遗留容器被 SB8 直接回收时丢失上次未及固化的增量，属可接受退化。spec 的「销毁前固化依赖」scenario 限定于 `sweep_idle` 闲置回收路径，不约束 SB8 的崩溃兜底回收。
- [`docker commit` 镜像层无限累积] → 仅销毁前 commit 一次；镜像保留/清理策略列为 Open Question，不在本 change 实现（避免范围蔓延）。
- [复用查找与 SB8 孤儿识别共用 `sandbox-` 前缀，命名规则若改动需两处同步] → 把前缀/命名格式定义为本模块可导出的常量，SB8 引用同一常量，单一事实来源。

## Open Questions

- `release_session` 的触发点：挂在 `session_mgr` 会话关闭、还是 server 请求结束、还是显式 admin 命令？（影响 session 容器何时回收；本 change 仅提供入口）
- `sweep_idle()` 的触发方式：sandbox.md/roadmap 已决定 cron 触发暂缓——本 change 提供按需调用入口，启动时触发与 SB8 孤儿清理合流，定期触发留待调度器接入后。
- `agent` scope 是否额外打 Docker label 以便 SB8 用 `--filter` 精确筛选，还是仅靠 `sandbox-` 名称前缀？（与 SB8 协商）
- `docker commit` 固化镜像的清理/版本保留策略（保留最近一份 vs 累积）——待认领。
