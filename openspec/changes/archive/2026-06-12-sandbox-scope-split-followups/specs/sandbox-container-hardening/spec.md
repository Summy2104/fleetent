## MODIFIED Requirements

### Requirement: 加固参数按 scope 分层

session scope 与 agent scope SHALL 使用**同一最严加固档位**:丢弃全部 Linux capability(`--cap-drop ALL`)且不补充任何 capability、以非 root 用户运行、`read_only` rootfs。两档位其余加固标志(pids-limit、tmpfs、no-new-privileges、init)亦一致。

> 历史背景:agent scope 曾为"容器内安装依赖(pip)"保留最小 capability(`CHOWN`/`DAC_OVERRIDE`/`FOWNER`/`SETUID`/`SETGID`)、以 root 运行、可写 rootfs。自依赖安装移至**声明式离线 build 期不可变镜像**(见 `sandbox-image-persistence`:禁止从运行容器固化镜像、依赖在 build 期烤入只读镜像)后,运行期不再安装依赖,该放松的理由不复存在,故 agent scope 收紧为与 session 同档。agent 的工作数据写入经 bind-mount 的可写 `/workspace`(不受 rootfs `read_only` 影响),收紧后 agent 仍可正常读写工作区。

#### Scenario: session 档位不补能力且非 root
- **WHEN** 以 session 档位创建容器
- **THEN** `docker run` 含 `--cap-drop ALL`、不含任何 `--cap-add`、且含 `--user 65534:65534`

#### Scenario: agent 档位与 session 同档(不补能力、非 root、只读 rootfs)
- **WHEN** 以 agent 档位创建容器
- **THEN** `docker run` 含 `--cap-drop ALL`、**不含任何 `--cap-add`**、含 `--user 65534:65534`(非 root)、含 `--read-only`;agent 的依赖来自 build 期不可变镜像而非运行期安装

#### Scenario: agent 收紧后工作区仍可写
- **WHEN** agent 档位容器(只读 rootfs)运行,agent 向 `/workspace` 下写文件
- **THEN** 写入成功(`/workspace` 为可写 bind mount),只读 rootfs 仅阻止写容器系统目录
