## MODIFIED Requirements

### Requirement: 加固参数可配置且非法值回退安全默认

所有加固参数 SHALL 可经 **per-agent `agent.yaml` 的 `sandbox.resources`** 配置声明（每个 agent 独享一份加固档，不再有 `sandbox.agent_scope` 覆盖，也不再从机器共享 `platform.yaml` 读取）。任一字段未配置时 MUST 回退安全默认值（`pids_limit=256`、`tmpfs_size_mb=64`、`cap_drop_all=True`、`no_new_privileges=True`、`init=True`、`run_as_user="65534:65534"`）。非法值（如 `pids_limit` / `tmpfs_size_mb` 非正整数）MUST NOT 被静默接受，SHALL 记录告警后回退该字段默认值，不以非法值构造命令。

#### Scenario: 缺字段逐项回退默认
- **WHEN** 配置未声明任何加固字段
- **THEN** 创建命令使用全部安全默认加固值（pids 256 / tmpfs 64m+nosuid / cap-drop ALL / no-new-privileges / init）

#### Scenario: 非法 pids_limit 回退默认
- **WHEN** 配置 `sandbox.resources.pids_limit=0`（或负数 / 非整数）
- **THEN** 系统记录告警并回退默认 `256`，不以非法值构造命令

#### Scenario: 可显式关闭单项加固
- **WHEN** 配置 `sandbox.resources.no_new_privileges=false`
- **THEN** 创建命令不包含 `--security-opt no-new-privileges`（运维显式承担风险），其余加固标志不受影响
