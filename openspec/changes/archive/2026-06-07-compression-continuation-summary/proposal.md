## Why

压缩摘要当前是英文自由文本（仅"user goals + completed actions"），丢失"进行中/未完成/下一步"，长任务（企业多步工单）压缩后容易丢目标无法续跑。C2 已把 todo 持久化到 `{sid}.todo`，但压缩时不会把未完成项保留进上下文——压缩掉中段后模型"看不见"未完成任务。

## What Changes

- **结构化摘要模板**：`_build_summary_prompt` 产出带固定分节（Goal / Completed / In Progress·Pending / Key Findings & Files / Next Steps）的结构化摘要，显式要求**逐字保留未完成工作与下一步**；首次摘要与增量合并（`prev_summary`）两分支同结构。
- **active-task 续跑块**：当压缩丢弃中段（summarized / degraded 路径）时，把该 session 的未完成 todo（`pending`/`in_progress`，读自 C2 的 `{sid}.todo`）作为**逐字保留的 system 块**注入压缩结果，顺序为 `[head, active-task, summary, tail]`，使压缩后模型仍能看到未完成任务并续跑。其 token 计入尾部保留预算投影。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `compression-incremental-summary`: 新增"摘要采用结构化模板并保留续跑要素"需求（ADDED）。
- `compression-layered-retention`: 新增"未完成任务在压缩后逐字保留（active-task 续跑块）"需求（ADDED）。

## Impact

- **修改文件**：`src/fleetent/runtime/context.py`（`_build_summary_prompt` 重写为结构化；`_compress` 注入 active-task 块；`_select_tail` 投影计入其 token）。
- **依赖**：C2 的 `session_mgr.read_todo`（已在 main）。读 `.todo` 失败/无 session 时安全退化（不注入、不报错）。
- **解耦合规**：纯 `runtime/`，无新依赖、无 platform、无新持久化结构。active-task 块仅在有未完成 todo 且有 session_id 时出现，零 session 时行为不变（零惊吓）。
