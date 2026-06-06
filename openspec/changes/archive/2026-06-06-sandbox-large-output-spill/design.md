## Context

`run_code`（`builtin_tools.py`）当前对每个流做 `truncate_stream(redact_secrets(raw), budget)`：脱敏后保留头+尾、丢弃中段。`builtin_tools` 已有落盘约定：`GENERATED_DIR`/`UPLOADS_DIR = paths.data_dir() / "..."`（注入式模块常量、`uuid4` 文件名）。`output_truncation.truncate_stream` 产出带说明的 head+tail。

## Goals / Non-Goals

**Goals:**
- 超预算输出不再丢中段：完整（脱敏后）输出落盘，返回预览 + 文件引用，模型可 `read_file` 取全文。
- 密钥不落盘（落盘前已脱敏）。
- 落盘目录有界（保留期自清理），零新依赖、零调度器。

**Non-Goals:**
- 不改截断（仍用于生成预览）、不改脱敏、不改 trace 大小语义。
- 不实现后台定时清理任务（机会式 write-triggered 即可）。
- 不改 `read_file` 工具（模型用既有 `read_file` 读取落盘路径，与 `analyze_image` 读 `UPLOADS_DIR` 引用同模式）。

## Decisions

**D1：新模块 `output_spill.py`，与 `output_truncation` 并列、复用其预览生成。** `cap_or_spill(text, max_bytes, *, label)`：`len(utf8) <= max_bytes` → 原样返回；否则写 `SANDBOX_OUTPUT_DIR/{uuid}.txt`（全文），返回 `truncate_stream(text, max_bytes)` 预览 + 引用提示行。截断仍是预览来源（不重复造轮子）。

**D2：落盘前必须已脱敏——调用点保持 `cap_or_spill(redact_secrets(raw), ...)`。** redaction 在 spill 之前，落盘文件即脱敏后文本，密钥不落磁盘（数据主权）。这是 D 级硬约束，不是顺手：顺序写在 run_code 调用点，并由「落盘内容已脱敏」场景测试守护。

**D3：落盘目录沿用 `builtin_tools` 约定。** `SANDBOX_OUTPUT_DIR = paths.data_dir() / "sandbox_output"`，注入式模块常量（测试 monkeypatch 到 tmp_path），`uuid4().hex + ".txt"` 文件名——与 `GENERATED_DIR`/`UPLOADS_DIR` 一致，落在 gitignored 的 `data/` 下、不出内网。

**D4：保留期清理机会式触发、不依赖调度器。** 写新文件前扫描落盘目录、删除 mtime 早于保留期（默认 7 天）的 `*.txt`。与 cron_scheduler 解耦（同 session/sweep 既有取向）；清理失败仅记录、不阻断写入。机会式（write-triggered）的取舍：落盘停止后旧文件可能滞留，但每文件体量有界、且下次落盘即清理，接受此权衡（不引入后台任务）。

**D5：返回值是预览 + 引用，略超 budget 可接受。** `run_code` 声明 `self_truncates`、豁免 T4，预览（≤budget）+ 一行引用提示的轻微超出与现状（`[stderr] ` 前缀）同量级，可接受。

## Risks / Trace-offs

- **[模型拿到路径却不会 read_file]** → 引用提示明确写「可用 `read_file` 读取」；与 `analyze_image` 读 `UPLOADS_DIR` 引用同模式，模型已具备该用法。
- **[落盘目录无界增长]** → 保留期清理（默认 7 天，可配置）；机会式触发在 write 时，常态足够。
- **[把密钥写盘]** → 调用点 redact-在前 + 「落盘内容已脱敏」场景测试守护。
- **[并发写文件名碰撞]** → `uuid4` 文件名，碰撞概率可忽略（同 `GENERATED_DIR`）。

## Migration Plan

纯加性，新增 `data/sandbox_output/` 目录（按需创建、自清理）。无数据迁移。回退：run_code 调用点改回 `truncate_stream` 即恢复旧（丢中段）行为。
