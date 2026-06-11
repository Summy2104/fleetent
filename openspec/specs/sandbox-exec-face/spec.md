# sandbox-exec-face Specification

## Purpose
TBD - created by archiving change sandbox-execution-world. Update Purpose after archive.
## Requirements
### Requirement: run_code 为容器内唯一执行面，不新增第二个执行工具

`run_code` SHALL 是容器内**唯一**的执行面:agent 经它在隔离容器内执行代码,并可在其中经 subprocess 调起任意脚本、`bash`、`node` 等解释器以运行 skill 脚本(`run_code` 是「在容器内执行任意语言」的严格超集)。系统 **MUST NOT** 新增 `sandbox_exec` 或任何第二个完成「容器获取 + 容器内执行」的工具——所有容器内执行 MUST 经 `run_code` 所用的同一 `SandboxManager` 与降级路径。

理由(写入约束的动机):一个执行面消除两类风险——(1) 两个执行工具 `risk_level` 不一致时,模型用更低 risk 的那个绕过另一个经 action-gate 的封闭性门控(审批后门);(2) 截断 / redaction / liveness 等逻辑两份代码需同步、指令层负担翻倍。免审批由 action-gate(`action_gate_medium_mode` + 运行时封闭性)统一裁决,`run_code` 保持既有 `risk_level`(medium),不因引入第二工具而出现 risk 不一致的旁路。

#### Scenario: skill 脚本经 run_code 运行
- **WHEN** agent 要运行某 skill 的脚本(bash / python / node 任一语言)
- **THEN** 它经 `run_code` 执行的代码内用 subprocess 调起该脚本,脚本在同一隔离容器的 `/workspace` 世界内执行,使用与 `run_code` 一致的容器与封闭性保证

#### Scenario: 不存在第二个容器内执行工具
- **WHEN** 审视工具集中与「容器内执行」相关的工具
- **THEN** 仅 `run_code` 一个;不存在 `sandbox_exec` 或其他独立完成容器获取+容器内执行的工具;任何容器内执行都经 `run_code` 的 `SandboxManager` 路径

#### Scenario: 免审批不因执行面引入 risk 旁路
- **WHEN** 部署将 `action_gate_medium_mode` 配置为 `sandbox`，使封闭态下的 `run_code`(medium)免审批直跑
- **THEN** 不存在另一个 `risk_level` 更低、可绕过该门控完成等价容器内执行的工具;免审批边界完全由 action-gate 的风险等级 + 运行时封闭性决定

