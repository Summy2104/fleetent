# sandbox-container-hardening Specification

## Purpose
TBD - created by archiving change sandbox-container-hardening. Update Purpose after archive.
## Requirements
### Requirement: 沙箱容器创建应用安全加固标志

Docker 沙箱容器创建命令 SHALL 默认应用以下容器加固标志，以收敛恶意/失控代码对宿主机的影响面：进程数上限（`--pids-limit`）、`/tmp` 临时文件系统限大小且禁 setuid（`--tmpfs /tmp:rw,nosuid,size=<n>m`）、丢弃全部 Linux capability（`--cap-drop ALL`）、禁止提权（`--security-opt no-new-privileges`）、注入 init 进程回收僵尸子进程（`--init`）。这些标志 MUST 与既有 `--memory` / `--cpus` / `--network` / `--read-only` 标志共存，且 `/tmp` 可写临时目录的行为保持不变（仅升级为带 `nosuid,size=` 选项）。

#### Scenario: 默认创建含进程数上限
- **WHEN** 以默认资源档位创建沙箱容器
- **THEN** `docker run` 命令包含 `--pids-limit 256`

#### Scenario: tmpfs 限大小且 nosuid
- **WHEN** 以默认资源档位（`tmpfs_size_mb=64`）创建容器
- **THEN** `docker run` 的 tmpfs 标志为 `--tmpfs /tmp:rw,nosuid,size=64m`，不再是无选项的 `--tmpfs /tmp`

#### Scenario: 默认丢弃全部能力并禁止提权
- **WHEN** 以默认资源档位创建容器
- **THEN** `docker run` 命令同时包含 `--cap-drop ALL` 与 `--security-opt no-new-privileges`

#### Scenario: 默认注入 init 进程
- **WHEN** 以默认资源档位创建容器
- **THEN** `docker run` 命令包含 `--init`

### Requirement: 加固参数按 scope 分层

session scope 与 agent scope SHALL 使用不同的加固档位。session scope 丢弃全部能力且不补充任何 capability、以非 root 用户运行（最严档）。agent scope 需在容器内安装依赖（pip），故 SHALL 为其保留最小必要 capability（`CHOWN`、`DAC_OVERRIDE`、`FOWNER`、`SETUID`、`SETGID`）并以 root 运行。两档位其余加固标志（pids-limit、tmpfs、no-new-privileges、init）一致。

#### Scenario: session 档位不补能力且非 root
- **WHEN** 以 session 档位创建容器
- **THEN** `docker run` 含 `--cap-drop ALL`、不含任何 `--cap-add`、且含 `--user 65534:65534`

#### Scenario: agent 档位补最小能力且以 root 运行
- **WHEN** 以 agent 档位创建容器
- **THEN** `docker run` 含 `--cap-drop ALL` 与 `--cap-add CHOWN` / `DAC_OVERRIDE` / `FOWNER` / `SETUID` / `SETGID`，且不含 `--user`（以容器默认 root 运行）

### Requirement: 加固参数可配置且非法值回退安全默认

所有加固参数 SHALL 可经 `sandbox.resources`（基础 / session 档）与 `sandbox.agent_scope`（agent 覆盖）配置声明。任一字段未配置时 MUST 回退安全默认值（`pids_limit=256`、`tmpfs_size_mb=64`、`cap_drop_all=True`、`no_new_privileges=True`、`init=True`、session `run_as_user="65534:65534"`）。非法值（如 `pids_limit` / `tmpfs_size_mb` 非正整数）MUST NOT 被静默接受，SHALL 记录告警后回退该字段默认值，不以非法值构造命令。

#### Scenario: 缺字段逐项回退默认
- **WHEN** 配置未声明任何加固字段
- **THEN** 创建命令使用全部安全默认加固值（pids 256 / tmpfs 64m+nosuid / cap-drop ALL / no-new-privileges / init）

#### Scenario: 非法 pids_limit 回退默认
- **WHEN** 配置 `sandbox.resources.pids_limit=0`（或负数 / 非整数）
- **THEN** 系统记录告警并回退默认 `256`，不以非法值构造命令

#### Scenario: 可显式关闭单项加固
- **WHEN** 配置 `sandbox.resources.no_new_privileges=false`
- **THEN** 创建命令不包含 `--security-opt no-new-privileges`（运维显式承担风险），其余加固标志不受影响

