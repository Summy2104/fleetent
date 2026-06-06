## Why

`run_code` 当前对超预算输出用 `truncate_stream` 保留**头+尾**、**直接丢弃中段**。对数据分析、日志排查类任务，中段往往正是关键信息（如某行报错、某条数据），丢弃后模型无法找回，只能让用户重跑。

四个参考项目里 claude-code、openclaw、opencode（3/4）都采用更优做法：超限输出**落盘**、返回一个**引用**（文件路径 + 预览），模型按需用文件读取完整内容、且不撑爆对话上下文。fleetent 缺这一步。

本 change 把「中段丢弃」升级为「落盘 + 引用」：完整输出（**脱敏后**，不把密钥写盘）写入落盘文件，返回值给出 head+tail 预览 + 文件引用，模型可用 `read_file` 读取完整内容。

## What Changes

- 新增 `src/fleetent/integrations/sandbox/output_spill.py`：
  - `SANDBOX_OUTPUT_DIR`（`paths.data_dir() / "sandbox_output"`，注入式模块常量，沿用 `builtin_tools.GENERATED_DIR`/`UPLOADS_DIR` 约定）。
  - `cap_or_spill(text, max_bytes, *, label) -> str`：未超预算→原样返回（不落盘）；超预算→把完整 `text` 写入 `SANDBOX_OUTPUT_DIR/{uuid}.txt`，返回「head+tail 预览（`truncate_stream`）+ 引用提示（路径、原始字节数、可用 `read_file` 读取）」。
  - 写入时机会式按保留期清理旧落盘文件（默认 7 天，不依赖调度器）。
- `run_code`（`tools/builtin_tools.py`）输出组装处：把 `truncate_stream(redact_secrets(raw), budget)` 替换为 `cap_or_spill(redact_secrets(raw), budget, label=...)`。**保持 redact 在前**——落盘的是脱敏后文本，密钥不落盘。
- sandbox 包 `__init__` 导出 `cap_or_spill`。

## Capabilities

### New Capabilities
- `sandbox-large-output-spill`: `run_code` 某输出流经脱敏后仍超字节预算时，SHALL 将完整（脱敏后）输出落盘并在返回值中给出预览 + 文件引用（替代中段丢弃）；未超预算时不落盘、原样返回；落盘文件按保留期清理。

### Modified Capabilities
<!-- 不 MODIFIED。`sandbox-output-truncation`（头尾截断）仍用于「预览」生成、行为不变；
     `sandbox-output-redaction` 不变（落盘前仍先脱敏）。落盘+引用是与二者并列的新关注点，以 ADDED 表达。 -->

## Impact

- **代码**：新增 `integrations/sandbox/output_spill.py`；`tools/builtin_tools.py` `run_code` 两处流处理改用 `cap_or_spill`；`integrations/sandbox/__init__.py` 导出。
- **数据目录**：新增 `data/sandbox_output/`（落盘文件，gitignored 的 data 下；按保留期自清理）。
- **测试**：新增 `tests/unit/test_sandbox_output_spill.py`（未超→不落盘原样；超→落盘+预览+引用；落盘内容=完整脱敏文本；保留期清理；导出）；在 `tests/unit/test_tools.py` run_code 段加「超大输出→落盘引用且预览中无密钥、落盘内容已脱敏」用例。`SANDBOX_OUTPUT_DIR` monkeypatch 到 tmp_path（可注入文件边界，unit）。
- **不影响**：脱敏、截断、trace 大小语义、exec/超时/生命周期；不引入新依赖。
