## Why

`tool_registry.dispatch`（`tool_registry.py` 行 127-183）是所有工具参数进入执行体的唯一入口：LLM 给出的 `arguments_json` 反序列化为 `kwargs` 后直接 `fn(**kwargs)`，dispatch 全程不对参数做任何消毒。最初设想在此集中「消毒」，但**重新审视真实泄漏向量后，这个落点站不住**：

1. **真实泄漏向量是 trace，不是 dispatch**：密钥经工具参数泄漏进磁盘的实际路径是——LLM 产出的 assistant 消息中的 `tool_calls[].function.arguments`（原始 JSON）经 `agent_loop`（行 601 `messages.append(msg.model_dump())`）进入 `messages`，再由 `log_run`（行 697-700）整体交给 `eval_logger._serialize` 落 trace。**这条路径 dispatch 根本碰不到**：dispatch 只拿到 `tc.function.arguments` 做调用，从不经手写 trace 的那份消息 JSON。因此原设计「在 dispatch 造一份脱敏副本」**没有任何消费者**——脱敏副本既不会被 trace 读取、也不会替换落盘的消息，纯属空转。
2. **dispatch 是参数语义盲的**：dispatch 分不清一个字符串参数是路径、是代码还是散文，因此任何在 dispatch 做的一刀切结构校验，要么太宽误杀（废掉 run_code 等工具），要么无意义。脱敏（看**键名**、语义无关）适合集中做、且应该做在 trace 写入点；结构校验（看**值含义**）必须在懂语义的地方（工具 / schema）做。

故本 change 重设计范围：**把 secret 脱敏移到 trace 序列化层 `eval_logger`**（真实泄漏点、且与既有图片占位同范式），并**砍掉 / 下沉 / defer 原本压在 dispatch 上的结构校验**。

## What Changes

- **Secret 脱敏移到 trace 序列化层 `eval_logger`（不在 dispatch）**：在 `eval_logger` 序列化消息处（与既有 `_serialize` / `_placeholder_images` 占位 base64 图片**同一层、同一范式**）扩展：序列化 assistant 消息的 `tool_calls` 时解析 `function.arguments`，把**键名命中 `sandbox_secrets.is_sensitive_name`** 的值替换为占位符。
  - **作用域 = trace only**。session JSON **不脱敏**——它是 LLM 每轮要回读的工作上下文，脱了会丢上下文、破坏连续性；密钥出现在对话里属对话本身。传给工具的运行时参数同样不动。
  - 复用 `sandbox_secrets.is_sensitive_name` / `SENSITIVE_TOKENS`，单一事实来源，与沙箱 env 过滤同一套规则。
- **删除「dispatch 造脱敏副本」**：原设计的 dispatch 脱敏副本没有消费者，删除。
- **砍掉注入元字符黑名单**：`;` / `|` / `$()` / 反引号在合法参数（run_code 的 code、shell 工具、正则、散文）里太普遍，dispatch 语义盲、一刀切会废掉 run_code 等工具；真要执行代码的 containment 是沙箱（Docker `--network none`），dispatch 拒元字符既有害又冗余。
- **路径穿越保护下沉到「处理路径的工具」**：正确归属是用一个共享 `safe_path()` helper，在真正 `open(path)` 处 fail-closed（只有 read_file / write_file 这类工具知道自己参数是路径）。本 change 仅**注明这是正确归属**（design 说明 + 列为 Non-Goal / 重定向），不在 dispatch 做、也不在本 change 实现各工具的 safe_path。
- **参数 schema 一致性校验保持 defer**：dispatch 层唯一站得住的「参数校验」正确形态，是用每个工具自己的 schema 做类型 / 必填 / 枚举一致性校验（语义感知、低误杀），而非启发式黑名单；它是独立子能力，不在本 change。
- **承认仅名过滤的局限**：与 SB5 一致，敏感名判定只看参数**名**；值内嵌的密钥扫不到——不做值内容扫描（避免误杀与正则军备竞赛），spec / design 显式标注。

## Capabilities

### New Capabilities
- `tool-arg-secret-redaction`: trace 序列化层（`eval_logger`）在序列化 assistant 消息时，对 `tool_calls[].function.arguments` 中键名命中敏感名判定的值脱敏为占位符——复用 SB5 `sandbox_secrets.is_sensitive_name` 规则，与既有 base64 图片占位同范式；仅作用于 trace（session 工作上下文与运行时参数不脱敏），仅名过滤、不扫值内容（局限同 SB5）。

### Modified Capabilities
<!-- 不修改既有 spec。本 change 在 eval_logger 序列化管线中新增 tool_call 敏感名参数脱敏，属新增能力，落在新 capability `tool-arg-secret-redaction` 下以 ADDED 表达。dispatch 不再被本 change 改动。 -->

## Impact

- **代码**（本 change 仅产出 openspec 文档，不实现）：
  - 扩展 `src/fleetent/eval_logger.py` 的序列化路径：序列化 assistant `tool_calls` 时解析 `function.arguments`，对键名命中 `sandbox_secrets.is_sensitive_name` 的值脱敏为占位符（与 `_placeholder_images` 同层同范式）。
  - 复用 `src/fleetent/sandbox_secrets.py` 的 `is_sensitive_name` 与 `SENSITIVE_TOKENS`（不复制、不另立规则）。
  - **不改动** `tool_registry.dispatch`：不在 dispatch 做脱敏副本、不做注入元字符黑名单、不做路径穿越校验。
- **测试**：新增 `tests/test_eval_logger.py` 用例（或扩展既有）：tool_call 敏感名参数值在 trace 中被脱敏、非敏感名不变、无 tool_calls 消息序列化不受影响、运行时对象不被污染、monkeypatch `SENSITIVE_TOKENS` 验证同源、值内嵌密钥不被脱敏（局限）。LLM 调用全程 mock，trace 路径隔离 tmp_path（monkeypatch `eval_logger.TRACE_PATH`）。
- **不影响**：`tool_registry.dispatch` 既有行为（访问控制、connector 注入、cancel_token/tool_context 注入、「返回错误而非抛异常」契约）；session 持久化内容；不引入新依赖。

## Dependencies

- `eval_logger`（**已实现**）：trace 序列化落点；脱敏与 `_placeholder_images` 同层、同范式。
- `sandbox_secrets`（**SB5 已实现**）：复用 `is_sensitive_name` 敏感名判定与 `SENSITIVE_TOKENS` 可注入常量——同一套规则、同一局限（仅名过滤）。
- `agent_loop`（**已实现**）：trace 写入路径——assistant 消息（含 `tool_calls[].function.arguments`）经 `messages.append(msg.model_dump())` 进入 `messages` 并由 `log_run` 整体落 trace；这条路径是真实泄漏向量，也是脱敏必须覆盖的输入形态。
