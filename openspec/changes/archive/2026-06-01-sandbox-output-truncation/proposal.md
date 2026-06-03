## Why

`run_code`（`tools.py` 行 227-234）把沙箱执行结果原样拼装回 AI：`result.stdout` / `result.stderr` 直接 `rstrip()` 后 join，无任何长度约束。`SandboxClient.exec`（`sandbox_client.py` 行 235-252）返回的 `ExecResult.stdout` / `stderr` 也未做大小限制。一段打印海量数据的代码（如 `for i in range(10**7): print(i)`、`dd` 出来的二进制、整页抓取）会让 stdout 膨胀到数 MB，一次性塞进上下文，挤占后续轮次空间、甚至单次就触发 `context_overflow`（AR5）。

`docs/capabilities/sandbox.md` 的「输出截断」要求：

> - stdout 上限 50KB，stderr 上限 10KB
> - 超限时保留开头 + 结尾，中间插入截断说明
> - 非 UTF-8 字符做安全转义

`tools.py` 拼装 trace 时已用 `len(result.stdout.encode("utf-8"))` / `len(result.stderr.encode("utf-8"))` 作字节口径（行 220-221），`sandbox_client.py` 同样以 UTF-8 字节计量。本 change 把「输出截断」落为 spec：在沙箱 `run_code` 的 stdout/stderr **返回给 AI 之前**，于沙箱层按字节阈值（stdout 50KB、stderr 10KB）做「头尾保留 + 中间省略 + 标明原始大小」截断。SB6 **独占** `run_code` 输出的截断职责；`run_code` 经工具层通用截断（T4）的 `self_truncates` opt-out **对 T4 豁免**（T4 跳过它），故 `run_code` 输出不经 T4、不存在二次截断。

## What Changes

- 引入**沙箱输出截断**：对 `run_code` 产出的 stdout / stderr，在拼装成工具结果返回给 AI 之前，分别按各自字节阈值（stdout `MAX_STDOUT_BYTES`、stderr `MAX_STDERR_BYTES`）做「头部保留 + 中间省略 + 尾部保留」截断，省略处插入截断说明（标明该流原始字节数与被省略字节数）。
- 阈值以**字节口径** `len(s.encode("utf-8"))` 定义，与兄弟 change `tool-result-truncation`（T4）以及 `sandbox_client.py` / `tools.py` 既有字节计量保持一致（跨 change 一致性好习惯，万一将来出现别的自截断工具）；stdout 默认 50KB、stderr 默认 10KB（对应 sandbox.md）。该口径**不再**承担「防 SB6 后被 T4 二次截」的职责——`run_code` 经 `self_truncates` opt-out 对 T4 豁免，根本不经 T4。
- 截断策略为**头尾保留 + 中间省略**的纯规则实现，零 LLM 调用、毫秒级（与 T4 同性质）；非法 UTF-8 / 多字节字符切点做安全处理，绝不产出半个字符。
- stdout 与 stderr **各自独立**按各自阈值截断（两条流量级不同，分别限额），截断只影响返回给 AI 的副本；trace 记录的 `stdout_bytes` / `stderr_bytes`（`tools.py` 行 220-221）记录**原始**字节大小，不被本能力削减。
- 阈值可注入（模块级常量，可 `monkeypatch`），未配置时回退安全默认（50KB / 10KB）；不引入全局可变状态。

## Capabilities

### New Capabilities
- `sandbox-output-truncation`: SB6 独占沙箱 `run_code` 的 stdout/stderr 截断——在返回给 AI 前于沙箱层按各自字节阈值（默认 50KB/10KB）做头尾保留 + 中间省略截断并标明原始大小；`run_code` 经 `self_truncates` opt-out 对 T4 豁免，输出不经 T4。字节口径 `len(s.encode("utf-8"))` 与 T4 一致（好习惯），纯规则零 LLM，原始大小仍可经 trace 审计。

### Modified Capabilities
<!-- 不修改既有 spec。sandbox 能力的「输出截断」此前仅为 docs 规划项（无对应 spec 需求），本 change 首次以 spec 表达，落在新 capability `sandbox-output-truncation` 下以 ADDED 表达，不对 sandbox-client 主 spec 做 MODIFIED（否则 archive sync 找不到同名既有需求）。 -->

### 边界与共享引用
- **与 T4（`tool-result-truncation`）的边界**：SB6 **独占** `run_code` 输出（stdout/stderr）的截断，发生在沙箱执行结果产出处、拼装为工具结果之前，按两条流各自的阈值（各 50KB / 10KB）分别限额。`run_code` 经 T4 的 `self_truncates` opt-out **对 T4 豁免**——T4 跳过它，故 `run_code` 输出**不经 T4、不存在二次截断**。T4 管所有其他工具结果。SB6 与 T4 **各管各的工具、不叠加、无阈值耦合**。两者字节口径同为 `len(s.encode("utf-8"))`，仅为跨 change 一致性好习惯（`run_code` 根本不经 T4，不存在口径双重截断问题）。
- **与 AR5（`agent-error-classification`）的协同**：沙箱层先截断降低单次 `run_code` 结果触发 `context_overflow` 的概率；本 change 不改 AR5，仅在 design 说明协同（截断不改变 `sandbox_oom` / `sandbox_timeout` 的判定）。

## Impact

- **代码**：
  - 新增截断逻辑（建议 `src/fleetent/sandbox_output_truncation.py`，import → 常量 → 函数）：`truncate_stream(text: str, max_bytes: int | None = None) -> str`，字节口径 `len(s.encode("utf-8"))`，超阈值头尾保留 + 截断说明；模块级 `MAX_STDOUT_BYTES=50*1024` / `MAX_STDERR_BYTES=10*1024`（可 `monkeypatch`）。
  - 修改 `src/fleetent/tools.py` 的 `run_code`（行 227-234）：拼装前对 `result.stdout` / `result.stderr` 分别调用截断（stdout 用 stdout 阈值、stderr 用 stderr 阈值）；trace 记录（行 220-221）仍记原始字节大小，不变。
- **配置**：阈值常量可注入（模块级，可 `monkeypatch`）；接入 `Settings` / `sandbox` 配置段为可选增强，缺省安全默认。
- **测试**：新增 `tests/test_sandbox_output_truncation.py`（阈值内不变 / 超阈值头尾保留 + 说明 / 多字节字符不切碎 / 边界值 / stdout 与 stderr 各自阈值 / 阈值可注入）；扩充 `tests/test_tools.py` 断言 `run_code` 返回的 stdout/stderr 已截断、trace 仍记原始字节。Docker CLI 全程 mock，路径隔离 tmp_path。
- **不影响**：T4 通用截断逻辑（`run_code` 经 `self_truncates` opt-out 被 T4 跳过，其余工具仍由 T4 处理）、`SandboxClient.exec` 返回值本身（截断在 `tools.py` 拼装侧）、SB2 生命周期 / SB3 enablement / SB5 密钥过滤 / SB9 trace 字节口径、`exit_code` 判定。
- **不引入新依赖**（仅标准库）。

## Dependencies

- `sandbox_client`（`SandboxClient.exec` 返回 `ExecResult.stdout` / `stderr`，已用 `len(s.encode("utf-8"))` 字节口径——本 change 截断对象的来源）/ `tools.py`（`run_code` 拼装 stdout/stderr 为工具结果的点、trace 已记字节大小——截断接入点）。
- `agent-error-classification`（AR5，`openspec/specs/agent-error-classification/spec.md`）——沙箱层截断降低单次结果触发 `context_overflow` 的概率；本 change 不改 AR5，仅在 design 说明协同。
- 兄弟 change `tool-result-truncation`（T4）——`run_code` 经 T4 的 `self_truncates` opt-out 豁免（T4 跳过它），SB6 独占 `run_code` 截断；T4 管其余工具。二者各管各的工具、不叠加。字节口径同为 `len(s.encode("utf-8"))` 仅为跨 change 一致性好习惯。
