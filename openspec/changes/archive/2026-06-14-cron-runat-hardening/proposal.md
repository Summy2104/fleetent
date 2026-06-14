## Why

一条 `once` 调度任务的 `run_at` 被存成 `'2026-06-14 08:07:19 UTC'`（带 ` UTC` 后缀），导致 agent **每次启动都在 `cron_scheduler.start()` 崩溃**——`_parse_run_at` 用 `datetime.fromisoformat` 解析失败抛 `ValueError`，整个 boot 挂掉（MCP 已注册、Bolt 未起）。根因有二：(1) `schedule` 工具把模型给的 `run_at` 原样落库、不规范化；(2) `start()` 对单条任务的注册异常无防护，一条坏数据即拖垮整个 agent。这是个**重启地雷**：任何带 ` UTC`/时区名后缀的 once 任务都会让 agent 无法启动。

## What Changes

- **启动韧性（核心安全修复）**：`cron_scheduler.start()` 注册每条任务时 MUST 舱壁化（独立 try/except）——单条任务注册失败 SHALL 记录 warning + 自动 disable 该任务 + 跳过，**MUST NOT** 中断 boot 或波及其它任务的注册。一条坏数据不再能让 agent 无法启动。
- **`run_at` 解析鲁棒性**：`_parse_run_at` SHALL 容忍常见非严格 ISO 形态——尾部 ` UTC`/`Z`/时区名后缀、空格分隔（`YYYY-MM-DD HH:MM:SS`）——归一化后再解析；仍支持严格 ISO 与相对时长（`+30m`/`2h`）。无法解析时抛明确错误（由上层韧性兜底）。
- **写入端规范化（防复发）**：`schedule` 工具创建 `once` 任务时 SHALL 用同一解析器把 `run_at` 规范化为 canonical ISO（带 tz 的 `…+00:00`）后再落库，使新任务永远是干净格式；无法解析的 `run_at` 在创建时即返回明确错误，不落库。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `cron-scheduled-tasks`: 「Dynamic tasks survive server restart」新增启动韧性要求（单任务注册失败不崩 boot、自动 disable+跳过）；「Schedule kinds cron, one-shot, and interval」的 `once` 新增 `run_at` 解析鲁棒性 + 创建时规范化。

## Impact

- **owning package**：top-level 基础设施 `cron_scheduler.py`（`_parse_run_at` + `start`）、`schedule_store.py`（不变，仅被写入端调用）、`tools/builtin_tools.py`（`schedule` 工具创建路径规范化）。
- **public API surface**：`cron_scheduler._parse_run_at` 行为放宽（向后兼容：原 ISO/相对仍工作）；新增不导出的归一化辅助。无签名变更。
- **owned tables**：无（`scheduled_tasks` schema 不变）。
- **config namespace**：无。
- **cross-module dependencies**：不新增；`schedule` 工具复用 `cron_scheduler` 的解析器（tools→top-level，已存在方向）。MUST NOT import platform。
- **migration / shim plan**：无 schema 迁移。存量坏行经启动韧性自动 disable（不删数据）；可选一次性修复脚本不在范围。
