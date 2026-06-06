# sandbox 改进批次（容器加固 / 生命周期接线 / 输出脱敏 / 大输出落盘）

> 本文是一次 sandbox 专项改进的**贯穿性记录**：四个参考项目的对比结论、识别出的缺口、本批 4 个 OpenSpec change 的决策与取舍、以及实施过程中遇到的问题。供整体审核。
> 各 change 自身的 `proposal.md` / `design.md` / `specs/` / `tasks.md` 是权威的需求与实现契约；本文是横切视图，不重复其全文。

## 背景

fleetent 的 sandbox 使命是「在隔离容器内运行 agent 触发的代码，**保护主机系统不受恶意或失控代码影响**」。本批以 **Docker 沙箱模式为准**，对照四个外部 agent 项目的 sandbox 机制，补齐 fleetent 在 Docker 后端上的缺口。

参考项目：
- `NousResearch/hermes-agent`（Python，Docker/SSH/Modal/Daytona 多后端）
- `anthropics/claude-code`（公开分发物，文档/策略为主，CLI 本体未开源）
- `openclaw/openclaw`（TS 单仓，Docker/SSH 后端）
- `anomalyco/opencode`（TS 单仓，无 OS 级隔离，纯权限门控）

## 四项目对比结论（Docker 加固维度）

| 维度 | fleetent（改前） | hermes | openclaw | claude-code | opencode |
|---|---|---|---|---|---|
| 隔离机制 | Docker | Docker+本地+远程 | Docker+SSH | OS sandbox（seatbelt/bwrap） | child_process（无隔离） |
| `--cap-drop ALL` | ❌ | ✅ +最小 cap-add | ✅ | OS 级 | n/a |
| `no-new-privileges` | ❌ | ✅ | ✅ 总是 | — | n/a |
| `--pids-limit` | ❌ | ✅ 256 | ✅ | — | n/a |
| tmpfs 限大小/nosuid | ❌（无上限，RAM-backed） | ✅ size+nosuid+noexec | ✅ | — | n/a |
| `--init` 回收僵尸 | ❌ | ✅ | ? | — | n/a |
| 非 root 运行 | ❌（root） | ✅ 可选 | ✅ uid1000 | — | n/a |
| 资源限额 mem/cpu | ✅ | ✅ | ✅ | ❌ | ❌ |
| exec 超时 | ✅（已接线，见下） | ✅ | ❌ 无 per-exec | ✅ | ✅ |
| 出站输出密钥脱敏 | ❌ | ✅ `redact_sensitive_text` | ❌ | ❌ | ❌ |
| 大输出落盘引用 | ❌（中段直接丢弃） | ❌ | ✅ | ✅ | ✅ |
| 孤儿容器清理 | ⚠️ 有实现+spec+测试，**生产未接线** | — | ✅ prune | — | n/a |
| 闲置回收 | ⚠️ 有实现+spec+测试，**从未调度** | ✅ idle reaper | ✅ idle+maxAge | — | n/a |

**结论**：fleetent 的 Docker 后端在「资源限额可配置 / scope 生命周期 / 入站 env 过滤 / 输出截断 / exec 超时」上已较扎实，但**容器加固几乎全缺**（cap/pids/tmpfs 限额/非 root/init），且**孤儿清理与闲置回收虽已实现却未接入 agent 运行时**。出站输出脱敏与大输出落盘两项体验/安全增强亦缺。

## 识别的缺口与本批范围

| # | change | 类别 | 缺口 |
|---|---|---|---|
| 1 | `sandbox-container-hardening` | 主机防护 | 无 cap-drop / no-new-privileges / pids-limit / tmpfs 限额 / init / 非 root |
| 2 | `sandbox-runtime-lifecycle-wiring` | 可靠性 | `cleanup_orphans`、`sweep_idle` 有实现但 agent 运行时无调用点 |
| 3 | `sandbox-output-redaction` | 数据主权 | 仅过滤入站 env 名，出站 stdout/stderr 零脱敏 |
| 4 | `sandbox-large-output-spill` | 体验/能力 | 超限输出中段丢弃，未落盘留引用 |

**延后项**（复杂 / 环境脆弱 / ROI 低，本批不做）：网络出站白名单与 `public_only` 实装、磁盘配额 `--storage-opt`（仅 overlay2+XFS pquota）、自定义 seccomp/AppArmor profile、符号链接攻击防护、per-command 命令前缀门控（opencode 路线）。

## 各 change 的决策与取舍

### Change 1：sandbox-container-hardening ✅（本分支已实现）

为 `docker run` 补齐按 scope 分层的加固标志，扩展 `SandboxResources` + `client._resource_flags`，全部可配置、非法回退安全默认。

新增 `docker run` 标志：`--pids-limit`、`--tmpfs /tmp:rw,nosuid,size=<n>m`、`--cap-drop ALL`、`--cap-add <最小集>`（仅 agent 档）、`--security-opt no-new-privileges`、`--init`、`--user`（session 档非 root）。

关键决策：
- **D1 新建独立 capability**，不改 `sandbox-resource-limits` 既有需求（加固与资源限额是并列关注点）。
- **D2 scope 分层默认由 `build_resources_by_scope` 设定**，client 保持「按次照单构造 flags」的无状态语义，不在最低层按 scope 分支。
- **D3 非 root 仅 session 档；agent 档留 root**——agent 档要 `pip install` 写系统 site-packages 并 `docker commit` 固化依赖，非 root 会复杂化且与既有 commit 流程冲突。`run_as_user` 可配置（置 `null` 回退 root）。
- **D4 `/tmp` 加 `nosuid,size=`，不加 `noexec`**——`nosuid`+`size` 零副作用挡提权与内存耗尽；`noexec` 会破坏 pip/构建工具从 /tmp 执行的行为。默认 `tmpfs_size_mb=64`。
- **D5 agent cap_add 取最小依赖安装集** `CHOWN/DAC_OVERRIDE/FOWNER/SETUID/SETGID`（与 hermes「以 root 启动」放行集一致）；session 档不补任何 cap。
- **D6 默认值保守安全档**：`pids_limit=256`、`cap_drop_all/no_new_privileges/init=True`、session `run_as_user="65534:65534"`（nobody）。

风险与缓解：见 `change/design.md` 的 Risks 段（核心：非 root 破坏个别 session 工作负载 → `run_as_user` 可配置；cap-drop 破坏 agent pip → agent 档补最小 cap 并有测试断言）。

内部 BREAKING：默认 `docker run` 命令变更（更安全），已同步更新 `test_sandbox_client` 既有断言；`run_code` 对外契约不变。

### Change 2：sandbox-runtime-lifecycle-wiring ⏳（计划）

把 `cleanup_orphans` 接入 `runtime/agent_app._start_infra` 启动；新增后台任务定时调度 `manager.sweep_idle`（仿 `session_mgr.start_session_maintenance` 的后台维护模式）。决策与取舍在该 change 落地时补录于此。

### Change 3：sandbox-output-redaction ⏳（计划）

新增脱敏模块，`run_code` 的 stdout/stderr 在返回 LLM 与写 trace 前按模式脱敏（API key / JWT / 连接串 / 私钥 / Authorization 等）。参考 hermes `redact_sensitive_text`。决策落地时补录。

### Change 4：sandbox-large-output-spill ⏳（计划）

超限输出落盘返回引用路径，替代当前中段直接丢弃；与现有 `output_truncation` 协作。3/4 参考项目（claude-code/openclaw/opencode）均如此。决策落地时补录。

## 实施过程中的问题与决策记录

- **exec_timeout 并非缺口**：初判可能缺超时强制终止，核实后发现 `run_code`（`tools/builtin_tools.py`）已把 `exec_timeout` deadline 与外部 cancel token 合并、超时走 `kill_workspace`（SIGTERM→5s→SIGKILL）。故不重复实现，仅在对比表标注「已接线」。
- **真实"接线缺口"**：`cleanup_orphans` 与 `sweep_idle` 有实现、归档 spec、通过单测，但在 platform/runtime 拆分（`server.py` 不再跑 sandbox，agent 执行移入 `fleetent agent run`）后，`agent_app._start_infra` 既未调用孤儿清理也未调度闲置回收 → 列为 change 2。`session` scope 容器经 `session_mgr` 的 `release_session` 已接线，仅 `agent` scope 回收与孤儿清理缺失。
- **容器以 root 运行**：sandbox 直接用 `python:3.12-slim`（默认 root），无 `--user` → change 1 修复（session 档非 root）。无专用 sandbox 基镜像（仓库 `Dockerfile` 是平台镜像）。
- **opencode 不走容器**：纯 `child_process` + 权限门控，在容器加固维度全 n/a；其「大输出落盘 + 引用」思路支撑 change 4，「AST 命令前缀门控」属另一条路线（fleetent 已有 `permission_gate`+`agent_policy` 粗粒度门控），列入延后。
- **文档漂移**：`docs/capabilities/sandbox.md` 把已实现项（资源可配置、生命周期、密钥过滤、输出截断、超时、孤儿清理、trace）仍标为「规划中 [ ]」，且「现状」称资源限制「硬编码」（实际 SB4 已外置）→ 本批一并校正。
- **既有 debt（与本批无关，按"一次 commit 不混入不相关改动"原则不在本批修）**：
  - 本机 `uv run pytest tests/unit` 有 **4 个既有失败**——`test_config_paths` / `test_db_session_paths` / `test_misc_config_paths` / `test_paths_wiring` 的「常量从 paths 派生」族。根因：路径常量「导入期冻结 vs 测试期重解析」在本机环境（`FLEETENT_HOME` 未设 → 回退 `~/.fleetent`）下不一致。用 `git stash` 暂存本改动后复跑、以及在 main checkout 复跑，**均同样失败**，证实与本改动无关。
  - `ruff check src tests` 9 个错误全在 `tools/file_tools.py`；`mypy src` 7 个错误在 4 个非 sandbox 文件；`check_test_layers` 1 处违规在 `test_config.py`——均既有。
  - **CI 门禁**（`bitbucket-pipelines.yml`）PR 仅跑 `make test-unit-ci`（`pytest tests/unit` + 75% 覆盖率，带 `ANTHROPIC_API_KEY=test-key` 与 `alembic upgrade head`），**不含 ruff/mypy**；上述 4 个 path 测试在 CI 纯净容器中不复现。本改动的 sandbox 测试（79）、`ruff`/`mypy`（本文件）均绿。

## 验收（本 change）

- `tests/unit/test_sandbox_config.py`、`tests/unit/test_sandbox_client.py` 全绿；docker CLI 全 mock，配置路径 `monkeypatch` 到 tmp_path，属 unit 层。
- 加固标志按 scope 正确出现/缺省；非法值回退安全默认；单项加固可关闭。
