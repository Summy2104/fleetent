## Context

`run_code`（`tools.py` 行 227-234）把沙箱执行结果拼装回 AI：

```python
parts = []
if result.stdout:
    parts.append(result.stdout.rstrip())
if result.stderr:
    parts.append(f"[stderr] {result.stderr.rstrip()}")
if result.exit_code != 0:
    parts.append(f"[exit {result.exit_code}]")
return "\n".join(parts) if parts else "(no output)"
```

`result` 来自 `SandboxClient.exec`（`sandbox_client.py` 行 235-252），其 `ExecResult.stdout` / `stderr` 是容器 `docker exec` 的 `stdout.decode()` / `stderr.decode()`，无大小约束。同一函数在写 trace 时已用 `len(result.stdout.encode("utf-8"))` / `len(result.stderr.encode("utf-8"))`（行 220-221）作字节口径——本 change 的截断字节口径必须与之**完全一致**。

`docs/capabilities/sandbox.md`「输出截断」给出：stdout 上限 50KB、stderr 上限 10KB、超限保留开头 + 结尾、中间插截断说明、非 UTF-8 字符安全转义。

兄弟 change `tool-result-truncation`（T4）对所有工具结果在写回 `messages` 前做通用截断，字节口径同为 `len(s.encode("utf-8"))`。T4 侧已新增 `self_truncates` opt-out：声明该属性的工具被 T4 跳过。`run_code` 声明 `self_truncates`，由 SB6 独占其 stdout/stderr 截断（沙箱侧、按两条流各自阈值），输出**不经 T4、不存在二次截断**；T4 只管其余工具。SB6 与 T4 各管各的工具、不叠加、无阈值耦合。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（阈值常量可 `monkeypatch`）；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock Docker CLI、路径隔离 tmp_path；不吞异常。

## Goals / Non-Goals

**Goals:**
- 在 `run_code` 拼装结果返回给 AI 之前，对 stdout / stderr **各自**按字节阈值（stdout 50KB、stderr 10KB）做「头尾保留 + 中间省略 + 标明原始大小」截断。
- 字节口径 `len(s.encode("utf-8"))`，与 T4 及 `sandbox_client.py` / `tools.py` 既有计量完全一致。
- 截断是纯规则、零 LLM 调用、毫秒级。
- 多字节字符 / 非 UTF-8 切点安全处理，截断结果恒为合法 UTF-8。
- 阈值可注入（模块级常量，可 `monkeypatch`），未配置回退安全默认（50KB / 10KB）。
- trace 记录的 stdout/stderr 原始字节大小（`tools.py` 行 220-221）不被本 change 削减。

**Non-Goals:**
- 不实现 T4 的工具层通用截断（属 T4；SB6 独占 `run_code` 截断、`run_code` 经 `self_truncates` 对 T4 豁免，二者各管各的工具）。
- 不改 `SandboxClient.exec` 的返回值本身（截断发生在 `tools.py` 拼装侧，`ExecResult` 不变）。
- 不改 SB9 trace 的字节口径、不改 AR5 的 `sandbox_oom` / `sandbox_timeout` 判定。
- 不实现 scope（SB2）、mode（SB3）、密钥过滤（SB5）、资源限制（SB1）、孤儿清理（SB8）。
- 不引入新依赖、不引入 `Settings` 强制字段。

## Decisions

### D1：截断在 `run_code` 拼装侧、纯函数实现，stdout/stderr 各自阈值

新增 `src/fleetent/sandbox_output_truncation.py`（import → 常量 → 函数）：
- 模块级 `MAX_STDOUT_BYTES: int = 50 * 1024`、`MAX_STDERR_BYTES: int = 10 * 1024`（安全默认，可 `monkeypatch`）作为两条流各自的单一阈值事实来源。
- `truncate_stream(text: str, max_bytes: int | None = None) -> str`：`max_bytes is None` 时由调用方按流别传入对应常量；超阈值则头尾保留 + 中间省略。
- 在 `tools.py` 的 `run_code` 拼装前调用：`stdout` 用 `MAX_STDOUT_BYTES`、`stderr` 用 `MAX_STDERR_BYTES` 分别截断，再进 `parts`。

**为何**：截断在 `run_code` 拼装侧（而非 `SandboxClient.exec` 内）——`exec` 是底层执行原语，其 `ExecResult` 还供 trace 记原始字节（行 220-221）、未来其他消费者使用，在 `exec` 内截断会改变这些下游看到的内容、越权；截断只该作用于「返回给 AI 的拼装结果」这一副本。stdout 与 stderr 量级不同（stdout 常是数据输出、stderr 常是错误堆栈），sandbox.md 给了不同上限，故两条流**各自独立**按各自阈值截断，而非合并后用单一阈值。纯函数无副作用、易测、阈值可注入。
**Alternatives**：①在 `SandboxClient.exec` 内截断——被否，污染 trace 原始字节口径与其他 `ExecResult` 消费者，且把「面向 AI 的呈现策略」下沉到执行原语层，违背 `sandbox_client` 只负责执行、`tools.py` 负责拼装的职责边界。②stdout/stderr 合并后用单一总阈值——被否，sandbox.md 明确两条流不同上限，合并会让一条海量流挤掉另一条的配额。

### D2：截断策略 = 头尾保留 + 中间省略说明（非摘要），与 T4 同形

超过 `max_bytes` 时：保留头部 `head_bytes` 与尾部 `tail_bytes`（按 UTF-8 字节切，不切碎多字节字符），中间替换为单行说明：
```
[...沙箱输出已截断：原始 {orig} 字节，省略中间 {omitted} 字节...]
```
- 头尾字节预算之和 + 说明字节数 SHALL ≤ `max_bytes`（截断后该流不反超其阈值）。
- 按字节切若落在多字节字符中段，回退到上一个完整字符边界，绝不产出非法 UTF-8（对应 sandbox.md「非 UTF-8 字符安全处理」）。

**为何**：头尾保留兼顾「开头通常含程序起始输出/进度」与「结尾通常含最终结果/错误堆栈」，对长日志尤其重要（纯尾切会丢开头、纯头切会丢结论）；说明用明确字节数告知 AI「这条流被截断了多少」，避免 AI 误以为输出完整。纯规则零 LLM 保证毫秒级、不增成本、不引失败点（摘要会引 LLM 调用与降级，且与 AR12 历史压缩职责重叠）。截断策略与 T4 同形（头尾 + breadcrumb），两 change 行为风格一致，便于运维理解。
**Alternatives**：①只保留头部直接硬切尾部——被否，丢掉 stderr 结尾的错误堆栈结论、stdout 结尾的最终结果，对调试有害。②LLM 摘要——被否，违反「源头截断零 LLM」目标。

### D3：字节口径 `len(s.encode("utf-8"))`，与 T4 一致为好习惯；run_code 对 T4 豁免

阈值与切分一律按 UTF-8 字节 `len(s.encode("utf-8"))`，不按字符数、不按 token。

**为何**：与 `tools.py` 行 220-221、`sandbox_client.py` 既有字节计量一致，且与兄弟 change T4 同口径——这是**跨 change 一致性好习惯**（万一将来出现别的自截断工具，口径统一便于运维理解）。字节是确定性、无依赖、跨 change 一致的度量。

**与 T4 的关系（豁免，非叠加）**：SB6 **独占** `run_code` 输出的截断。`run_code` 经 T4 的 `self_truncates` opt-out **对 T4 豁免**——T4 跳过它，`run_code` 输出**根本不经 T4**，故不存在二次截断、不存在两道关卡口径冲突、也不存在「T4 阈值需 ≥ SB6 两流之和」这种阈值耦合前提（该前提本就不成立：T4 默认阈值 ~40KB < SB6 两流之和 60KB，且 T4 二次截 `run_code` 会产生双 breadcrumb 并违反 sandbox.md 的 50KB stdout 承诺——故采豁免而非兜底）。T4 只管其余工具。字节口径的一致性此处**不**承担「防 SB6 后被 T4 二次截」的职责。
**Alternatives**：①按字符数 `len(s)`——被否，与既有 trace 字节口径不一致。②按 token 估算——被否，引入 tokenizer 依赖且与字节口径冲突，token 度量留给 AR12。③让 `run_code` 仍经 T4 通用兜底——被否，T4 默认阈值小于 SB6 两流之和会导致二次截断 / 双 breadcrumb / 违反 sandbox.md 承诺；故 `run_code` 经 `self_truncates` 对 T4 豁免。

### D4：截断只作用于返回 AI 的副本，trace 记原始字节不被削减

截断函数返回新字符串，**不改** `ExecResult`。`run_code` 的 trace 记录（`tools.py` 行 220-221）继续用 `len(result.stdout.encode("utf-8"))` / `len(result.stderr.encode("utf-8"))` 记**原始**字节大小，本 change 不在 trace 侧引入截断。

**为何**：返回 AI 的结果占 context、需省；trace 是审计载体、应记真实原始规模（运维事后可知「这次 run_code 实际产出了多少输出、被截了多少」）。两者目标相反，分别处理。trace 记原始字节、AI 收截断副本，二者解耦。
**Trade-off**：trace 的 `stdout_bytes` / `stderr_bytes` 是大小数值（非完整内容），不会因原始很大而让 trace 体积爆炸；若未来要在 trace 留完整原文需另议（见 Open Questions），本 change 维持现状仅记字节数。

## Risks / Trade-offs

- [按字节硬切割碎多字节字符产生非法 UTF-8] → 切分回退到完整字符边界（D2，对应 sandbox.md「非 UTF-8 安全处理」）；spec scenario 覆盖「多字节字符不被切碎」。
- [说明串自身 + 头尾预算反超该流阈值] → 预算分配保证「头 + 尾 + 说明 ≤ max_bytes」（D2）；spec scenario 断言截断后字节数不超过该流阈值。
- [与 T4 关系误解为「叠加 / 兜底」导致双重截断] → `run_code` 经 T4 的 `self_truncates` opt-out **对 T4 豁免**、不会被 T4 二次截断（D3）；字节口径与 T4 一致仅为跨 change 一致性好习惯，不承担「防二次截」职责；测试断言 `run_code` 结果不经 T4。
- [在 `exec` 内截断会污染 trace 原始字节与其他消费者] → 已选择只在 `run_code` 拼装侧截断（D1/D4），`ExecResult` 不变、trace 记原始字节；测试断言 trace 字节为原始大小、`ExecResult.stdout` 未被改。
- [stdout/stderr 阈值取值不当（过小截掉有用 / 过大失去意义）] → 阈值可注入、默认取 sandbox.md 的 50KB/10KB；运维可按部署 `monkeypatch` / 配置调整。

## Open Questions

- 头尾预算如何分配（如各 45% / 说明留余量），是否对 stdout 与 stderr 用同一比例？本 change 倾向同一比例、说明串预留固定余量。
- `[stderr]` 前缀与 `[exit N]` 等拼装固定串是否计入截断预算？本 change 倾向截断只针对 stdout/stderr 正文，拼装固定串极短不计入（量级可忽略；`run_code` 对 T4 豁免，无 T4 兜底，故 SB6 自身需把两条流各自压到阈值内）。
- 是否需要把原始完整 stdout/stderr 落到 trace 的内容字段（而非仅字节数）以便完整回放？本 change 维持现状仅记字节数，完整原文落点待后续与 SB9 协商。
- 截断阈值是否接入 `sandbox` 配置段（与 SB1 资源配置同段）还是仅模块级常量可注入即可？本 change 至少保证模块级常量可 `monkeypatch`。
