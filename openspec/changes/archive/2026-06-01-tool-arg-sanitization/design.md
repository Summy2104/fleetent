## Context

`tool_registry.dispatch`（`tool_registry.py` 行 127-183）是工具参数进入执行的唯一入口，全程不对 LLM 给出的参数做消毒。最初设想在此集中「消毒 + 脱敏」，但重新审视后发现两个根本事实推翻了这个落点：

**事实一：dispatch 是参数语义盲的。** dispatch 拿到的是反序列化后的 `kwargs`，但它分不清某个字符串参数是路径、是代码、是正则还是散文。因此任何在 dispatch 做的一刀切**结构校验**（黑名单元字符、`..` 段），要么太宽——误杀 run_code 的 code、shell 工具、正则、含 `..` 的合法相对路径等大量合法参数；要么太窄——无意义。结构校验天然需要「值含义」，只能在懂语义的地方（工具自身 / 工具 schema）做。

**事实二：真实泄漏向量是 trace，dispatch 碰不到。** 密钥经工具参数泄漏到磁盘的实际路径是：LLM 产出的 assistant 消息里的 `tool_calls[].function.arguments`（原始 JSON 字符串）经 `agent_loop`（行 601 `messages.append(msg.model_dump())`）进入 `messages` 列表，再由 `log_run`（行 697-700）把整个 `messages` 交给 `eval_logger._serialize` 逐条序列化落 append-only trace（`eval_logger.py` 行 44 / 94）。**dispatch 从不经手这份写 trace 的消息 JSON**——它只拿 `tc.function.arguments` 做调用。所以原设计「在 dispatch 造一份脱敏副本」**没有任何消费者**：副本既不会被 trace 读取、也不会替换落盘的消息，是空转。

由此区分两类问题，各归其位：
- **脱敏**（看**键名**、语义无关）：适合集中做，且该做在 trace 写入点 `eval_logger`。
- **结构校验**（看**值含义**）：必须在懂语义的工具 / schema 处做，不在 dispatch。

SB5 已落地名称过滤范式：`sandbox_secrets.is_sensitive_name(name)` 用大小写不敏感的子串黑名单（`SENSITIVE_TOKENS = TOKEN/KEY/SECRET/PASSWORD/PASSWD/CREDENTIAL/PRIVATE/AUTH`）判定一个**名字**是否敏感，常量为模块级、可 monkeypatch，并显式声明「保守、非穷举」「仅名过滤、值内嵌扫不到」的局限。`eval_logger` 已有 `_placeholder_images` 在序列化层把 base64 图片替换为占位文本——这是本 change 脱敏要复用的**同一范式、同一层**。

约束（CLAUDE.md）：无 AI 框架；无 ORM；禁止全局可变状态（敏感名规则为可注入常量，不在本模块复制）；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock LLM、路径隔离 tmp_path（monkeypatch `eval_logger.TRACE_PATH`）、不发真实外部请求；不吞异常。

**本 change 仅产出 spec 文档，不实现代码、不碰 `src/`。**

## Goals / Non-Goals

**Goals:**
- 在 `eval_logger` 序列化层（与 `_placeholder_images` 同层）新增 tool_call 参数脱敏：序列化 assistant `tool_calls` 时解析 `function.arguments`，键名命中敏感名判定的值替换为占位符。
- 脱敏**复用** `sandbox_secrets.is_sensitive_name`，不另造规则、不复制常量。
- 钉死作用域：脱敏仅作用于 trace 落盘表示；session 工作上下文与传给工具的运行时参数均不脱敏。
- 明确承认仅名过滤局限（值内嵌密钥扫不到，同 SB5）。

**Non-Goals:**
- **不在 dispatch 做任何结构黑名单**（dispatch 语义盲，见 D2）。
- **不做注入元字符拒绝**（`;` / `|` / `$()` / 反引号——见 D2，沙箱兜底）。
- **不实现各工具的 `safe_path()` 路径穿越保护**（正确归属是处理路径的工具，本 change 仅重定向，见 D3）。
- **不做参数 schema 一致性校验**（dispatch 层正确的「参数校验」形态，但属独立子能力，defer，见 D4）。
- 不做参数**值内容**的密钥扫描（值内嵌 token 扫不到，局限同 SB5）。
- 不脱敏 session JSON；不改 dispatch 既有行为；不引入新依赖；不实现代码（本 change 为 spec 设计阶段）。

## Decisions

### D1：脱敏落 `eval_logger` trace 序列化层，与 `_placeholder_images` 同范式
在 `eval_logger` 序列化消息处扩展：当一条 assistant 消息含 `tool_calls` 时，解析每个 `function.arguments`（原始 JSON 字符串），对其中键名命中 `sandbox_secrets.is_sensitive_name` 的值替换为占位符，仅改写**将落盘的 trace 表示**。这与既有 `_placeholder_images`（把 base64 图片块替换为 `[图片：...]`）是同一层、同一范式——序列化时对敏感内容做不可逆占位，绝不改写传入的原始消息对象。

- **作用域 = trace only**：脱敏只发生在 `eval_logger` 落盘序列化时。
- **session 不脱敏**：session 是 LLM 每轮要回读的工作上下文，脱敏会丢上下文、破坏对话连续性；密钥出现在对话里属于对话本身。
- **运行时不污染**：序列化产出新表示，不改写传入的消息 dict / 对象，运行时工作上下文与传给工具的参数均为原值（与 `_placeholder_images` 用 `{**msg, ...}` 新建一致）。

**为何**：这是真实泄漏向量所在（assistant tool_call args → `messages` → `log_run` 落 trace），也是脱敏唯一有消费者的落点。复用既有序列化范式，零新增管线、零新增依赖方向。
**Alternatives**：①在 dispatch 造脱敏副本——被否，dispatch 碰不到写 trace 的那份消息，副本无消费者（原设计的根本缺陷）；②脱敏 session + trace 二者——被否，session 脱敏会让 LLM 下一轮丢失自己刚产出的上下文，破坏连续性。

### D2：砍掉注入元字符黑名单
不在 dispatch（或任何集中点）对参数做 `;` / `|` / `$()` / 反引号等注入元字符黑名单拒绝。

**为何**：dispatch 语义盲，这些元字符在大量合法参数里普遍存在——run_code 的 Python code、shell 工具的命令、正则表达式、自然语言散文都会含分号、管道、反引号。一刀切拒绝会直接废掉 run_code 等工具，误杀远大于收益。真正需要 containment 的「执行任意代码」场景，其防线是沙箱（Docker `--network none` + 资源隔离，SB 系列），而非在 dispatch 拒元字符——后者既有害（误杀）又冗余（沙箱已兜底）。
**Alternatives**：保留一个「保守」黑名单——被否，任何黑名单在语义盲的位置都无法区分攻击载荷与合法值，「保守」即「无效或误杀」。

### D3：路径穿越保护下沉到「处理路径的工具」（safe_path），本 change 仅重定向
路径穿越（`..` 段、越权绝对路径）保护的正确归属，是一个共享 `safe_path()` helper，在真正 `open(path)` 的工具（read_file / write_file 等）里、在危险操作真正发生处 fail-closed。只有这些工具知道自己的某个参数**是路径**——dispatch 不知道。本 change **不**在 dispatch 做、**不**实现各工具的 safe_path，仅在文档中注明这是正确归属，列为 Non-Goal / 重定向（可作为后续 change，或由各路径工具自带）。

**为何**：路径校验是值语义校验，必须在懂「这是路径」的地方做；放 dispatch 会把含 `..` 的合法相对路径一并误杀，且仍漏掉以绝对路径或符号链接越权的情形。fail-closed 在 `open()` 处才是真正的 containment 点。
**Alternatives**：dispatch 统一拒 `..`——被否，语义盲 + 误杀 + 不完备。

### D4：schema 一致性校验是 dispatch 层正确的「参数校验」形态，但属 defer 的独立子能力
dispatch 层若要做「参数校验」，唯一站得住的正确形态是：用**每个工具自己的 schema** 做类型 / 必填 / 枚举一致性校验（语义感知、低误杀）——因为 schema 携带了「该参数是什么类型 / 是否必填 / 允许哪些枚举值」的语义，而启发式黑名单没有。这与本 change 的脱敏是两件独立的事，本 change **不**实现它，列为 defer。

**为何**：schema 校验需要遍历每个工具 schema、处理类型与可选性、与现有「返回错误而非抛异常」契约对齐，体量与关注点都独立，强行并入会模糊本 change 的脱敏聚焦。
**Alternatives**：本 change 顺带做 schema 校验——被否，关注点混杂、范围膨胀；独立 change 更清晰。

## Risks / Trade-offs

- [仅名过滤，值内嵌密钥扫不到] → 与 SB5 同一已知局限；design / spec 显式承认，不做值内容扫描（避免误杀与正则军备竞赛）。spec 用 scenario 固化「值内嵌密钥不被脱敏」边界，防止误认为已覆盖。
- [session 不脱敏，密钥仍以明文存在于 session JSON] → 这是有意取舍：session 是 LLM 工作上下文，脱敏会破坏连续性；密钥属对话本身，且 session 不是 append-only 审计面。trace（审计 / 长期沉淀面）才是必须脱敏的落点。
- [tool_call 参数脱敏依赖解析 `function.arguments` JSON] → LLM 偶尔产出非法 JSON；序列化层须容错（解析失败时退化为既有行为、不抛异常、不吞错），由 spec scenario「无 tool_calls / 异常形态按既有方式序列化」与实现期容错共同约束。
- [复用 `sandbox_secrets` 引入 `eval_logger` → `sandbox_secrets` 依赖方向] → `sandbox_secrets` 是无状态纯函数模块、无反向依赖，方向安全；规则常量可注入便于测试隔离。

## Open Questions

- 脱敏占位符形态（`***` / `[REDACTED]` / 保留前后缀如 `ab***yz`）是否统一为平台级常量，便于 trace 阅读？倾向与 `_placeholder_images` 的占位风格保持一致。
- 是否在 trace entry 上加一个「该消息发生过 tool_call 参数脱敏」的布尔标记，便于审计「曾出现敏感参数」而不泄漏值本身？倾向需要，归属可在实现期与 trace owner 对齐。
- 路径穿越 `safe_path()` 后续作为独立 change，还是由各路径工具在自身实现里自带？本 change 仅重定向，不锁定后续形态。
