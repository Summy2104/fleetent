# sandbox-output-truncation Specification

## Purpose
TBD - created by archiving change sandbox-output-truncation. Update Purpose after archive.
## Requirements

### Requirement: 沙箱输出超阈值时返回前被截断

`run_code` 产出的 stdout 与 stderr 在拼装为工具结果返回给 AI 之前，当其大小超过各自字节阈值时 SHALL 被截断；截断后返回的内容 MUST NOT 超过该流的字节阈值。大小度量 MUST 采用 UTF-8 字节口径 `len(s.encode("utf-8"))`，与工具结果通用截断（T4）的字节口径一致。截断 MUST NOT 调用 LLM（纯规则、毫秒级）。

> 归属说明：本需求首次以 spec 表达 docs 规划项「输出截断」，落在本 change 的新 capability `sandbox-output-truncation` 下以 ADDED 表达。SB6 **独占**沙箱 `run_code` 输出的截断；工具层通用结果截断属 T4（`tool-result-truncation`），`run_code` 经 T4 的 `self_truncates` opt-out **对 T4 豁免**（T4 跳过它），故 `run_code` 输出不经 T4。两者字节口径一致仅为跨 change 一致性好习惯，各管各的工具、不叠加。

#### Scenario: stdout 超过阈值被截断
- **WHEN** `run_code` 的 stdout 字节数超过 stdout 阈值
- **THEN** 返回给 AI 的 stdout 内容被截断，其字节数不超过 stdout 阈值

#### Scenario: stderr 超过阈值被截断
- **WHEN** `run_code` 的 stderr 字节数超过 stderr 阈值
- **THEN** 返回给 AI 的 stderr 内容被截断，其字节数不超过 stderr 阈值

#### Scenario: 输出在阈值内原样保留
- **WHEN** stdout 或 stderr 的字节数不超过其阈值
- **THEN** 返回给 AI 的该流内容与原始输出一致，不被修改

#### Scenario: 字节口径与 T4 一致
- **WHEN** 判断某条流是否超阈值
- **THEN** 以 `len(s.encode("utf-8"))` 计算字节数（与工具结果通用截断 T4 同口径），不按字符数或 token 计

### Requirement: stdout 与 stderr 各自独立按各自阈值截断

stdout 与 stderr SHALL 分别按各自的字节阈值独立截断，不合并为单一阈值。任一字段未配置时 SHALL 回退安全默认值：stdout 默认 `50 * 1024` 字节（50KB）、stderr 默认 `10 * 1024` 字节（10KB）。一条流被截断 MUST NOT 影响另一条流的配额。

#### Scenario: 两条流各用各自阈值
- **WHEN** stdout 超过 stdout 阈值而 stderr 在 stderr 阈值内
- **THEN** stdout 被截断、stderr 原样保留，互不影响

#### Scenario: 未配置取安全默认阈值
- **WHEN** 未显式配置阈值
- **THEN** stdout 以 50KB、stderr 以 10KB 作为字节阈值进行判断与截断

### Requirement: 截断采用头尾保留并标明原始大小

截断 SHALL 采用「头部保留 + 中间省略 + 尾部保留」策略：保留该流的开头与结尾各一段，中间被省略的部分 MUST 由一条截断说明占位替换。截断说明 MUST 标明该流原始字节数与被省略的字节数，使 AI 可知输出不完整及被省略的规模。头部预算、尾部预算与截断说明之和 MUST NOT 超过该流的字节阈值。

#### Scenario: 截断结果保留头尾并含说明
- **WHEN** 一条远超阈值的流被截断
- **THEN** 返回的该流内容以原始头部开始、以原始尾部结束，中间含一条标明原始字节数与省略字节数的截断说明

#### Scenario: 截断后总大小不反超该流阈值
- **WHEN** 头尾保留与截断说明组合后返回
- **THEN** 该流内容的字节数不超过其阈值（头 + 尾 + 说明已在预算内）

### Requirement: 多字节字符不被截断破坏

按 UTF-8 字节切分头尾时，切点 MUST NOT 落在多字节字符中段；若字节预算边界落在某字符内部，切点 SHALL 回退到上一个完整字符边界。截断后的内容 MUST 为合法 UTF-8 字符串（对应 sandbox.md「非 UTF-8 字符安全处理」）。

#### Scenario: 字节边界落在多字节字符内回退
- **WHEN** 头部或尾部字节预算的边界恰好落在一个多字节字符（如中文）的中间
- **THEN** 切点回退到该字符之前的完整边界，截断结果为合法 UTF-8，不含半个字符

### Requirement: 字节阈值可注入且不依赖全局可变状态

stdout 与 stderr 的字节阈值 SHALL 来自可注入的单一事实来源（模块级常量，测试可 `monkeypatch`），未显式配置时 MUST 回退到安全默认值。截断函数 SHALL 支持按次传入阈值覆盖默认值。系统 MUST NOT 依赖全局可变状态来持有阈值。

#### Scenario: 未传阈值取模块级默认
- **WHEN** 调用截断且未按次传入阈值
- **THEN** 使用模块级安全默认阈值（stdout 50KB、stderr 10KB）进行判断与截断

#### Scenario: 按次传入阈值覆盖默认
- **WHEN** 调用截断时显式传入一个更小的阈值
- **THEN** 以传入阈值判断与截断，不使用默认阈值

### Requirement: 截断只作用于返回 AI 的副本不削减 trace 与执行结果

截断 SHALL 只作用于返回给 AI 的拼装结果副本；`SandboxClient.exec` 返回的 `ExecResult` MUST NOT 被本能力修改。运行日志（trace）记录的 stdout/stderr 字节大小 MUST 为原始字节数（`len(result.stdout.encode("utf-8"))` / `len(result.stderr.encode("utf-8"))`），不被本能力削减，以便事后审计真实输出规模。`run_code` 输出经工具层通用截断（T4）的 `self_truncates` opt-out 对 T4 **豁免**——T4 跳过 `run_code`，故 `run_code` 输出 MUST NOT 经 T4 被二次截断。

#### Scenario: ExecResult 不被截断
- **WHEN** 沙箱输出超阈值并在返回 AI 前被截断
- **THEN** `SandboxClient.exec` 返回的 `ExecResult.stdout` / `stderr` 保持完整不变

#### Scenario: trace 记原始字节大小
- **WHEN** 一次产出超大输出的 `run_code` 被写入 trace
- **THEN** trace 记录的 stdout/stderr 字节大小为截断前的原始字节数，不被本能力削减

#### Scenario: run_code 经 self_truncates 对 T4 豁免不被二次截断
- **WHEN** 经本能力截断后的 `run_code` 结果作为工具结果交给工具层通用截断（T4）
- **THEN** `run_code` 经 T4 的 `self_truncates` opt-out 被 T4 跳过，输出不经 T4，不存在二次截断
