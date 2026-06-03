## Context

`run_code`（`tools.py` 行 169-213）经 `_exec_or_cancel`（行 148-166）在 Docker 容器内执行代码。`_exec_or_cancel` 把 `client.exec(ws_id, command)`（内部 `docker exec`）包成 task，用 `_CANCEL_POLL_INTERVAL` 轮询：每轮先查 `cancel_token.is_cancelled()`，若取消则 `exec_task.cancel()` + `destroy_workspace(ws_id)`（`docker rm -f`）并返回 None；否则 `asyncio.wait` 等一个轮询间隔，task 完成则返回 `ExecResult`。

当前两个缺口：

1. **沙箱不消费自己的 `exec_timeout`**。`SandboxResources.exec_timeout`（SB4，`sandbox_config.py` 行 68，默认 30、已 clamp `[1, 600]`）已随资源档位传入容器创建路径，但 `_exec_or_cancel` 只看**外部** `cancel_token`——若上层没注入带 `deadline` 的 token，死循环代码会无限占用容器与轮询协程，沙箱自身无兜底时限。
2. **终止手段不是 `docker kill` 序列**。取消路径直接 `docker rm -f`，没有 `docs/capabilities/sandbox.md`（行 98-100）要求的「先 SIGTERM、5s 后 SIGKILL」优雅窗口。

依赖现状：
- **AR19**（`cancellation.py`）：`CancelToken(deadline: float | None)`，`is_cancelled()` 合并「显式 `cancel()`」与「`time.monotonic() >= deadline`」。docstring 明文「a timeout is just `CancelToken(deadline=now + timeout)`」「This module defines the contract wave-3 timeout features (T2 / SB7) reuse」——SB7 正是其消费者之一。
- **②(sub-agent-lifecycle, AR20) 对 `cancellation.py` 的增量补全**：`CancelToken` 新增可选 `parent: CancelToken | None = None` 字段，`is_cancelled()` 在自身判定外 OR 上 `parent.is_cancelled()`（纯加法、向后兼容）。该 `parent` 链接原语用于把「子任务 / 子执行自身 deadline」与「父 / 外部取消」合并为单一 token；增量归 ② 拥有，本 change 与 ⑤(tool-timeout)/⑫ 同为消费方。SB7 用它合并沙箱 `exec_timeout` deadline 与外部 cancel token（见 D1）。
- **AR5**（`error_classifier.py`）：`ErrorCategory.sandbox_timeout`（行 49）与 `CLASSIFICATION_TABLE` 条目（行 93，三标志均 False）已预留，但「预留分类码不被主动返回」直到对应错误源接入；本 change 是该接入。
- **SB4**（`sandbox_config.py`）：`exec_timeout` 已承载并校验，本 change 仅消费。
- **`SandboxClient`**（`sandbox_client.py`）：已封装 `exec` / `destroy_workspace` 等 Docker CLI，统一用 `asyncio.create_subprocess_exec`。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM（本 change 不涉数据库）；禁止全局可变状态（宽限期等以模块级常量承载，可 monkeypatch 注入）；新模块/扩展遵循 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock Docker CLI（`asyncio.create_subprocess_exec`）不跑真容器；超时用注入极短 `exec_timeout` / 受控慢 stub，不依赖墙钟长等待；隔离 `tmp_path`/`monkeypatch`；不吞异常（超时归一为错误文本返回，而非静默）。

## Goals / Non-Goals

**Goals:**
- 让 `run_code` 的容器内执行受 `SandboxResources.exec_timeout`（SB4 承载）约束：超过该时限即判定为沙箱执行超时。
- 复用 AR19 token 契约表达沙箱侧超时（`exec_timeout` → deadline 语义），并经 ②(AR20) 补全的 `parent` 链接原语把它与外部注入的 cancel token 合并为**单一子 token**（`is_cancelled()` 自然 OR 两源），二者任一先触发即中止。
- 容器侧强制终止用 `docker kill` 序列：SIGTERM → 宽限期（默认 5s）→ SIGKILL，给容器内进程优雅退出窗口。
- 沙箱执行超时归一为 `ErrorCategory.sandbox_timeout`（接入 AR5 预留码），返回明确的「沙箱执行超时」文本，对话可继续。

**Non-Goals:**
- 不重新加载/校验 `exec_timeout`（SB4 已 clamp `[1, 600]` 并随资源传入，本 change 只消费）。
- 不实现 T2 的工具层通用超时（`_safe_dispatch` await 竞速、`tool_timeout` 归类）——那是兄弟 change `tool-timeout` 的职责（见「与 T2 边界」）。
- 不改 AR19 token 接口（仅新增「以 `exec_timeout` 构造 deadline」用法）。
- 不改 AR5 分类表结构（仅令 `sandbox_timeout` 预留码经沙箱执行源首次可达）。
- 不改 SB2 的 scope→容器保留/销毁策略（终止后容器的去留沿用既有约定）。
- 不引入新依赖。

## 与 T2（`tool-timeout`，工具层通用超时）边界

T2 与 SB7 都源自 AR19 的同一 token 契约，但**层级与中止手段不同**，本 change 明确划界（与 `tool-timeout` design 的同名表镜像一致）：

| 维度 | T2（`tool-timeout`） | SB7（本 change，`sandbox-exec-timeout`） |
| --- | --- | --- |
| 层级 | **工具层通用**：任意工具（IO/外部进程/MCP/run_code）单次调用 | **沙箱内特化**：仅 `run_code` 在 Docker 容器内执行 |
| 时限来源 | 全局默认 + `@tool(timeout=...)` per-tool 覆盖 | `SandboxResources.exec_timeout`（SB4 承载，默认 30、最长 600） |
| 中止手段 | asyncio await 层竞速 + `cancel()` token（协作式停止等待，**不调 `docker kill`**） | 对容器 `docker kill`（SIGTERM → 宽限 → SIGKILL）**强制终止**容器内进程 |
| 归类 | `tool_timeout` | `sandbox_timeout` |

一次 `run_code` 超时在概念上可被两层覆盖：**T2 保证 await 层不阻塞主循环并归类 `tool_timeout`；SB7 负责容器侧把进程真正杀掉并归类 `sandbox_timeout`**。本 change 只做 SB7 的容器侧硬终止，不触碰 `_safe_dispatch` 的 await 竞速，也不改 T2 的全局/ per-tool 时限来源。两者的时限互不替代：T2 兜底「工具卡死」，SB7 兜底「容器内代码真正被杀」。

## Decisions

### D1：以 `parent` 链接合并沙箱 deadline 与外部 token，按 deadline 是否先到区分

`_exec_or_cancel`（或其重构后等价物）的取消判定从「只看外部 `cancel_token`」改为「经 `parent` 链接的**单一** token 判定」——复用 ②(sub-agent-lifecycle, AR20) 对 `cancellation.py` 增量补全的 `parent` 链接原语（`CancelToken` 可选 `parent` 字段，`is_cancelled()` 在自身判定外 OR 上 `parent.is_cancelled()`），不手写 OR：

- 进入执行前以 `start = time.monotonic()` 算沙箱 deadline `sandbox_deadline = start + exec_timeout`，构造 `child = CancelToken(deadline=sandbox_deadline, parent=external_token)`，其中 `external_token` 即现状的 `cancel_token or CancelToken()`（外部注入或默认永不取消的 token）。
- 轮询循环的取消判定**收为单个 `child.is_cancelled()`**——它自然 OR 了「自身 deadline（沙箱 `exec_timeout`）到点」与「父 / 外部 token 取消（显式 `cancel()` 或上层 deadline）」两个源，无需在轮询里手写 `external_token.is_cancelled() or now >= sandbox_deadline`。
- 触发后区分归类：查 `time.monotonic() >= child.deadline`？是 → 沙箱 deadline 先到 → 沙箱执行超时（归 `sandbox_timeout`，见 D3）；否（父 / 外部触发）→ 已取消。**这套「按子 token 自身 deadline 是否已过区分超时 vs 取消」与 ② 的 `timed_out` vs `cancelled` 判定逐字镜像。**
- **不改 poll + docker kill 结构**：`docker exec` 不可被 asyncio 干净取消，仍是 poll 到取消后再 kill（D2）——`parent` 链接只把轮询条件从「手写双判定」统一成「单 token `is_cancelled()`」，终止手段与轮询骨架不变。

**为何**：沙箱 `exec_timeout` deadline 与外部 cancel token 是与 ②(sub-agent-lifecycle)/⑤(tool-timeout) 同一的**双取消源合并**场景；既然 ② 已为此向 `cancellation.py` 增量补全 `parent` 链接原语并对外发布，本 change 应作为消费方**复用同一原语**，而非在沙箱轮询里手写一套并行的 OR 合并——后者会让同一概念在代码库里存在两套机制。`parent` 链接保证「用户 / 上层 cancel」与「沙箱自身时限」任一先到都能经单一 token 中止，符合 SB7「沙箱自己兜底」与 AR19「显式 cancel」并存。
**Alternatives**：①把 `exec_timeout` 塞进外部 token 的 `CancelToken.deadline`（在 `run_code` 处构造 `CancelToken(deadline=now+exec_timeout)` **覆盖**外部 token）——被否，会丢失外部 token 的显式 `cancel()` 与上层 deadline；改用 `parent` 链接而非覆盖：子 token 自身 deadline 承载沙箱 `exec_timeout`、`parent` 保住外部 token 的显式 cancel 与上层 deadline，二者并存而非替换。②在轮询里手写 `external_token.is_cancelled() or now >= sandbox_deadline`——被否，这是与 ②/⑤ 已有 `parent` 链接**同一概念的第二套合并机制**，徒增维护面；统一用 `parent` 链接的单 token 判定。③用 `asyncio.wait_for(exec_task, timeout=exec_timeout)` 直接超时——可行但中止仅 `cancel()` 协程、不触发容器侧 `docker kill`，且不便与外部 token 经 `parent` 合并，故仍以轮询 + 单 token 判定为准，超时分支接 D2 的 `docker kill`。

### D2：容器侧强制终止用 `docker kill` 序列（SIGTERM → 宽限 → SIGKILL）

`SandboxClient` 新增封装该序列的方法（如 `kill_workspace(workspace_id)`）：

1. `docker kill --signal=SIGTERM <id>`：向容器 PID 1 发 SIGTERM，给容器内进程优雅退出窗口。
2. 等待**固定宽限期** `_KILL_GRACE_SECONDS`（模块级常量，默认 `5.0`，可 monkeypatch 注入）——宽限期内**不**做 `docker inspect` 轮询探测容器运行态，只等满该固定时长。
3. 宽限期满后**无条件**发 `docker kill --signal=SIGKILL <id>`：对已在 SIGTERM 后停止的容器再发一次 SIGKILL 是幂等、无害的（Docker 对已停容器的 kill 仅返回非零码而无副作用），省掉一次 `docker inspect` CLI 往返与运行态解析。
- 该方法用 `asyncio.create_subprocess_exec` 调 Docker CLI，与既有方法一致；返回码非预期（含对已停容器 SIGKILL 的非零码）时 log 警告但不让超时路径崩溃（终止是尽力而为，最终仍由 SB2 的容器去留约定兜底）。
- 超时路径调用 `kill_workspace` 替代当前的直接 `destroy_workspace`（`rm -f`）；终止后容器的保留/销毁沿用 SB2 既有约定（本 change 不改）。

**为何**：`docs/capabilities/sandbox.md`（行 99）明确「先 SIGTERM，5s 后 SIGKILL」——直接 `rm -f` 跳过了优雅窗口，可能让容器内进程没有清理机会；SIGTERM 宽限 → SIGKILL 是标准的优雅-强制两段式终止。「固定宽限后无条件 SIGKILL」比「宽限期内轮询 `docker inspect` 探测运行态、停了就早退」更简：少一次（或多次）CLI 往返与运行态解析，且对已停容器再 SIGKILL 幂等无害，仍精确满足「SIGTERM → 宽限 → SIGKILL」的可观察序列。宽限期作模块级常量，满足「禁止全局可变状态、可注入」且让测试用极短宽限（如 `0.01s`）不靠墙钟长等。
**Trade-off**：两段式比一次 `rm -f` 多一次 CLI 往返与一个宽限等待；但这是 capability 明确要求的优雅性，且宽限期可配。`docker kill` 只停进程不删容器，容器最终去留交 SB2，避免本 change 越界改销毁策略。
**Alternatives**：①保持 `rm -f` 一步到位——被否，违反 capability 的 SIGTERM 宽限要求；②宽限期内轮询 `docker inspect -f {{.State.Running}}` 探测，容器已停就提前结束、不发 SIGKILL——被否，多一次（或多次）`docker inspect` CLI 往返与运行态解析，收益仅是省一次对已停容器幂等无害的 SIGKILL，不划算；定为「等满固定宽限后无条件 SIGKILL」。③`docker stop`（其本质也是 SIGTERM→超时 SIGKILL）——可考虑，但 `docker stop` 的超时语义与默认信号不如 `docker kill --signal` 显式可控，且 capability 直书 `docker kill`，故用 `docker kill` 显式发两次信号以精确匹配「SIGTERM → 宽限 → SIGKILL」。

### D3：沙箱执行超时归一为 `sandbox_timeout`（接入 AR5 预留码）

沙箱 deadline 先到的中止路径：归类为 `ErrorCategory.sandbox_timeout`，复用 AR5 `CLASSIFICATION_TABLE[sandbox_timeout]` 既有条目与标志位（三标志均 False：超时不自动重试/压缩/切模型，交 LLM/用户决定下一步）。返回给用户的文本明确指出「沙箱执行超时」（区别于外部 cancel 路径的「已取消」/「code execution cancelled」）。

**接入点**（实现时二选一，spec 不绑定具体形态，只约束可观察行为）：
- (a) 沙箱执行超时路径直接读 `CLASSIFICATION_TABLE[ErrorCategory.sandbox_timeout]` 取标志位（与 `mcp_client._disconnect_classification()` 既有「直接读表、不调 `classify()`」做法一致）；
- (b) 若需经 `classify()`，扩展 `_categorize` 识别沙箱超时信号——但当前 `classify()` 仅识别 `APIStatusError`，沙箱超时非 API 异常，故优先 (a)。

**为何**：AR5 已把 `sandbox_timeout` 及标志位定为单一事实来源，本 change 是其「错误源接入」，不应另立码或重定义标志位。三标志为 False 符合 AR5 既有语义（沙箱超时是用户代码侧问题，盲目重试同段代码无益）。
**与 AR5 spec 的关系**：AR5「预留分类码不被主动返回」限定「未接入对应错误源前」；本 change **正是**该接入，故本 change 后 `sandbox_timeout` 可达，不与 AR5 spec 冲突（AR5 的限定语正为本 change 留口）。本 change 不 MODIFY AR5 spec，避免归档顺序敏感。
**Alternatives**：①新建独立沙箱超时码——被否，与 AR5 预留码重复，违反单一事实来源；②超时即 `should_retry=True` 自动重试——被否，会改 AR5 既有标志位语义且可能放大卡顿。

### D4：超时与外部 cancel 的语义区分，终止后对话可继续

- 中止后须能区分「沙箱 `exec_timeout` 超时」与「外部 token 显式 cancel / 上层 deadline」：前者归类 `sandbox_timeout`、文本「沙箱执行超时」；后者沿用既有「已取消」语义（不归 `sandbox_timeout`）。
- 两种路径都对容器执行 D2 的 `docker kill` 序列（容器内进程都需被真正终止），但**归类与返回文本不同**。
- 超时作为错误返回给用户后，对话可继续（`run_code` 正常 `return` 文本，不抛异常杀循环）——与 capability 验收场景 2「对话可继续进行」一致。

**为何**：用户需要知道是「代码跑太久被沙箱杀了」还是「上层主动取消」，二者后续动作不同（前者可能要优化代码/调大 `exec_timeout`，后者是外部意图）。容器侧硬终止动作两者共用（都要杀进程），但可观察的归类/文本分流，诚实反映原因。

## Risks / Trade-offs

- [SIGTERM 后容器内进程在宽限期内不退出，SIGKILL 仍可能因 Docker/内核延迟未即时生效] → 宽限期后发 SIGKILL 已是最强手段；`kill_workspace` 返回码非预期时 log 警告，容器最终去留由 SB2 约定兜底；spec scenario 锁定「宽限期内未停 → 发 SIGKILL」，不承诺内核级即时性。
- [外部 cancel 与沙箱 `exec_timeout` 同时到点导致归类歧义] → D1/D4 明确：经 `parent` 链接的单一子 token 触发后，按 `child.deadline` 是否已过区分——「沙箱 deadline 先到 → `sandbox_timeout`，否则（父 / 外部触发）→ 已取消」（与 ② 的 `timed_out` vs `cancelled` 镜像）；spec scenario 各自独立覆盖两条路径。
- [被误以为 SB7 同时实现了 T2 的工具层通用超时] → proposal/design/spec 均明确「仅 `run_code` 容器侧、`docker kill`、归 `sandbox_timeout`」，与 T2（await 竞速、`tool_timeout`、不调 `docker kill`）边界表镜像；spec scenario 不涉及非 `run_code` 工具。
- [`exec_timeout` 被本 change 重复加载/校验导致与 SB4 双源] → 本 change 只消费随资源传入的 `exec_timeout`，不读 yaml、不再 clamp（SB4 已 clamp `[1, 600]`）；design Non-Goals 与 tasks 前置核实明确。
- [异步超时测试不稳定 / 真实长 sleep 拖慢测试] → 测试注入极短 `exec_timeout`（如 `0.01s`）与极短宽限期常量，配受控慢 exec stub（`asyncio.Event` / 受控 `sleep`），mock `asyncio.create_subprocess_exec` 断言信号序列，不依赖墙钟长等待。

## Open Questions

- 宽限期 `_KILL_GRACE_SECONDS` 是否也应可经 `sandbox.resources` 配置（如 `kill_grace`），还是固定模块级常量即可？capability 只点名 5s，本 change 先以可注入的模块级常量承载（v1.0 够用）；是否并入 SB4 资源段保留为后续，本 change 不动。
- ~~`kill_workspace` 宽限期内「容器是否已停止」的探测方式：`docker inspect` 轮询 vs 等固定宽限后无条件 SIGKILL？~~ **已定**（见 D2）：宽限期内**不**轮询 `docker inspect`，等满固定宽限期后**无条件**发 SIGKILL（对已停容器幂等无害、省一次 CLI 往返与运行态解析）。spec 仍只约束「SIGTERM → 宽限 → SIGKILL」可观察序列，无条件 SIGKILL 满足之。
- 终止后是否需把沙箱执行超时写入 trace（SB9 已记 `log_sandbox_exec`，但超时路径当前 `result is None` 跳过 trace）便于运维核对慢代码？本 change 暂不要求，留待观测类 change。
