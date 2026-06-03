## Context

`eval_logger.py` 是项目唯一的 append-only JSONL trace 模块：`log_run`（行 20-67）记 agent 整轮运行（input/reply/messages/tokens/elapsed/model/stop_reason/error_category 等），`log`（行 70-99）记 IM 消息。两者各用一个常量指向同一文件——`log_run` 用 `_LOG_PATH = Path("data/traces.jsonl")`（行 12），`log` 用 `TRACE_PATH = Path("data/traces.jsonl")`（行 13），写前 `parent.mkdir(parents=True, exist_ok=True)`，`json.dumps(..., ensure_ascii=False)`。两份记录目前**都没有 `kind` 字段**，仅靠结构区分；且**没有任何程序消费 traces.jsonl**（只写不读）。`eval_logger` 有明确的克制原则：`_placeholder_images` 把 base64 图片替换为 `[图片：{mime}，{n}字节]` 占位符，从不写原始大对象。

`run_code`（tools.py 行 49-69）执行后只 `"\n".join(parts)` 返回文本，不写 trace。`docs/capabilities/sandbox.md` 现状条目确认「未写入运行日志」，规划项要求记录「执行时长、退出码、输出大小、使用的沙箱类型」。

约束（CLAUDE.md）：禁止全局可变状态（`_LOG_PATH` 可 monkeypatch）；mypy strict 全注解；行长 100；TDD Hard Gate；trace 隔离到 tmp_path；不吞异常（但 trace 写入失败属旁路，需 log 警告而非中断主流程——这是「catch 后 log」而非「静默吞」）。

## Goals / Non-Goals

**Goals:**
- `eval_logger.log_sandbox_exec(...)`：append 一条沙箱执行 trace，含执行时长、退出码、stdout/stderr 字节大小、沙箱 scope 类型、可选 agent/user 标识、`kind: "sandbox_exec"` 类型标记。
- 统一 trace taxonomy：趁当前无消费者，给既有 `log_run` 追加 `kind: "agent_run"`、给 `log` 追加 `kind: "im_message"`，三类 trace 共用一套 `kind` 判别。
- 合并 `_LOG_PATH`/`TRACE_PATH` 为单一常量，消除测试隔离漏洞。
- `run_code` 测量耗时、计算输出大小、写入 trace。
- trace 写入失败不影响 `run_code` 返回结果。
- 只记元数据，不记代码原文与完整输出。

**Non-Goals:**
- 不记录代码原文、完整 stdout/stderr 内容（避免膨胀与敏感落盘）。
- 不改 `log_run` / `log` 既有字段与写入语义——**仅向其记录追加 `kind` 字段**（纯增量、零风险，既有字段一个不动）；不调整既有任何字段的取值或结构。
- 不实现 scope（SB2，本 change 仅承接其 scope 值；未落地时记 None）、mode（SB3）、资源（SB4）、密钥（SB5）、清理（SB8）。
- 不引入新依赖、不新增配置。

## Decisions

### D1：新增专用出口 `log_sandbox_exec`，复用统一 trace 路径常量，用 `kind` 区分
在 `eval_logger.py` 新增：
```
def log_sandbox_exec(
    elapsed_s: float,
    exit_code: int,
    stdout_bytes: int,
    stderr_bytes: int,
    sandbox_scope: str | None = None,
    agent_name: str | None = None,
    user_id: str | None = None,
) -> None: ...
```
append 一条 `{"ts": ..., "kind": "sandbox_exec", "elapsed_s": round(...,3), "exit_code": ..., "stdout_bytes": ..., "stderr_bytes": ...}`，可选字段（scope/agent/user）非 None 才写入（与 `log_run` 的 `if x is not None: entry[...] = x` 模式一致）。复用统一 trace 路径常量（见 D6）的 `parent.mkdir` + append 写法。

**为何**：沙箱执行是比「agent 整轮」更细的事件，硬塞进 `log_run` 会污染其字段语义；新出口 + `kind` 标记让查询方按 `kind` 过滤沙箱事件。复用统一常量与既有写法保持单一 trace 文件、单一隔离点（测试只需 monkeypatch 一处）。
**Alternatives**：①扩展 `log_run` 加 sandbox 字段——被否，run_code 是工具调用、与「整轮运行」不是一回事，字段语义会混乱；②单独 JSONL 文件 `sandbox_traces.jsonl`——被否，多一个路径多一处隔离、查询方要读两个文件，`kind` 标记已足够区分。

### D5：统一 trace taxonomy——给 `log_run`/`log` 也补 `kind`
本 change 在新增 `kind: "sandbox_exec"` 的同时，给既有 `log_run` 记录追加 `kind: "agent_run"`、给 `log` 记录追加 `kind: "im_message"`。三类 trace 写入同一文件，统一靠 `kind` 字段判别，不再依赖记录结构猜类型。
**为何**：现状 `log_run`/`log` 记录**都没有 `kind` 字段**，仅靠字段结构区分；且目前**没有任何程序消费 traces.jsonl**（只写不读）。趁现在没有消费者，给三类记录建立一套统一的 `kind` 判别，未来的 traces 入库/eval 工具就能用单一维度过滤，不必为每类记录写脆弱的结构嗅探。该追加是**纯增量**：只新增 `kind` 一个字段，既有字段与写入语义全部不动，对（当前不存在的）读取方零风险。
**Alternatives**：①维持现状只给沙箱记录加 `kind`——被否，三类记录里两类无 `kind`、一类有，taxonomy 不统一，未来消费者仍要混合判别；②等真有消费者再补——被否，那时 traces.jsonl 已有历史记录，补 `kind` 会面临新旧记录混存、需兼容两套判别，反而比现在零成本追加更贵。

### D6：合并 `_LOG_PATH`/`TRACE_PATH` 为单一常量
`eval_logger` 现有两个常量 `_LOG_PATH`（`log_run` 用）与 `TRACE_PATH`（`log` 用），**取值完全相同**（都是 `Path("data/traces.jsonl")`），合并为单一常量；`log_run`/`log`/`log_sandbox_exec` 三处写入统一引用它。
**为何**：两个常量指向同一文件却是两个名字，制造了「测试只 monkeypatch 一个、另一个漏隔离」的隐患——若某测试只 monkeypatch `_LOG_PATH`，`log` 仍会写到真实 `data/traces.jsonl`，违反 CLAUDE.md「trace 隔离到 tmp_path、绝不触碰 data/」。合并后单一隔离点，monkeypatch 一处即覆盖全部写入路径。常量仍为模块级可注入路径，符合「禁止全局可变状态、路径须可 monkeypatch」约束。
**Alternatives**：保留两个常量——被否，零收益却长期留隔离陷阱。

### D2：只记元数据（大小）不记内容
trace 记 `stdout_bytes` / `stderr_bytes`（`len(s.encode("utf-8"))`），不记 stdout/stderr 原文，也不记代码原文。
**为何**：sandbox.md 要的是「输出大小」非内容；代码与输出可能含敏感数据或巨量文本，落盘违背数据主权与日志膨胀控制；与 `eval_logger` 既有「不写 base64 原文」的克制原则一致。
**Alternatives**：记截断后的内容——被否，截断属 SB6（波次 3），本 change 不碰内容；只记大小最简且满足需求。

### D3：trace 写入失败不阻断执行返回
`run_code` 中 `log_sandbox_exec` 调用包在 try/except，捕获后 `logger.warning(...)` 不 re-raise；执行结果照常返回。
**为何**：trace 是旁路观测，不能让日志故障影响用户拿到代码执行结果。这是 CLAUDE.md「catch 后必须 log 或 re-raise」中的「log」分支——旁路观测失败选择 log 而非中断主流程，理由明确。
**Alternatives**：写入失败也抛出——被否，会让一次磁盘/权限问题连带搞挂正常的代码执行，可观测性不应成为可用性的单点。

### D4：耗时与大小在 run_code 测量
`run_code` 用 `start = time.monotonic()` 包住 `exec`，`elapsed = time.monotonic() - start`；`stdout_bytes = len(result.stdout.encode())`、`stderr_bytes = len(result.stderr.encode())`；`exit_code = result.exit_code`。`sandbox_scope` 在 SB2 落地后由生命周期层提供，未落地传 `None`。
**为何**：这些值在 run_code 现有执行路径里都已有或可廉价算出（`ExecResult` 已含 stdout/stderr/exit_code），无需改 `SandboxClient`。
**Open**：`monotonic` 测的是 `exec` 时长，是否要包含容器创建/获取时长？建议只测 `exec`（纯执行时长，语义清晰）；容器获取时长属 SB2 生命周期关注点（见 Open Questions）。

## Risks / Trade-offs

- [trace 写入失败被静默忽略导致观测缺口] → 失败必 `logger.warning`（非静默吞），运维可见；主流程不受影响是有意取舍。
- [`sandbox_scope` 在 SB2 未落地前恒为 None] → 字段可选，None 不写入；SB2 落地后接通即可，本 change 不强依赖 SB2。
- [新增 `kind: sandbox_exec` 记录混入同一 JSONL 影响既有 trace 消费者] → 当前**没有任何程序消费 traces.jsonl**，无消费者可被影响；本 change 同步给三类记录建立统一 `kind`（`agent_run`/`im_message`/`sandbox_exec`），未来消费者按 `kind` 过滤即可，新记录不改既有记录的任何既有字段。
- [给 `log_run`/`log` 追加 `kind` 破坏既有行为] → 仅**追加** `kind` 一个字段，既有字段与写入语义不变；测试断言既有 trace 调用向后兼容（既有字段照旧）。趁无消费者落地，零回归风险。
- [字节大小用 UTF-8 编码长度，与 SB6 的「KB 截断阈值」口径需一致] → 统一用 `len(s.encode("utf-8"))` 字节口径，SB6 落地时复用同一度量。

## Open Questions

- `elapsed_s` 的测量边界：仅 `docker exec` 执行时长，还是含容器获取/创建时长？建议仅 exec（容器获取时长归 SB2）。
- 是否需要记录一个稳定的执行 ID 关联到所属 agent 整轮 `log_run` 记录？（便于把工具调用串到整轮 trace；可作为后续增强）
- `sandbox_scope` 的取值来源：SB2 的 `Scope` 枚举值字符串（`session`/`agent`）——待 SB2 落地后对齐字段命名与取值。
- 是否需要把 SB8 清理事件也经一个 `kind` 记入同一 trace（审计孤儿清理）？与 SB8 协调，不在本 change 强约束。
