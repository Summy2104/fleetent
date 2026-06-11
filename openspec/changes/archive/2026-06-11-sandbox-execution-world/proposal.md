## Why

skill 脚本在「沙箱优先」序列里跑不起来,根因有三(AAA-8053):

1. **模型看到两套坐标系**:模型被告知 skill 在宿主某绝对路径(`<available_skills>` 的 `<location>` 渲染 `entry.path`,即宿主 `skills/<name>/SKILL.md`),却被引导用容器内的 `run_code` 执行——脚本一进容器,`/etc`、宿主项目源码、宿主 skills 目录全不可达(mount namespace 物理隔离),脚本按宿主路径找文件必然 `FileNotFoundError`。模型没有「我在 /workspace 这个单根世界里」的统一心智。
2. **skills 目录从未进容器**:`run_code` 容器只 bind 了 `/workspace`(per-scope workspace),宿主 skills 目录(无论包内 `builtin_skills/` 还是用户 `skills/`)都不在容器内;skill 脚本所依赖的同目录资源(数据文件、子脚本)在容器里根本不存在。
3. **uploads / generated 落在 workspace 之外**:`generate_image` 写宿主绝对路径 `data_dir()/generated/`,返回宿主绝对引用;入站图片 `_save_upload` 写 `data_dir()/uploads/`、`analyze_image` 按宿主绝对路径回读——这些产物既不在 `/workspace` 内、引用又是宿主绝对路径,容器里的脚本/文件工具读不到,且与「非图片入站文件已落 per-session workspace 并返回 workspace 相对引用」(`im_gateway/normalizer._save_file_to_workspace` 已落地)形成坐标系分裂。

地基(`sandbox-isolation-foundation`)已修好容器/workspace 的碰撞与封闭性门控,并明确把「uploads·generated 迁入 / sandbox_exec」留给本 change。本 change 在地基之上把执行世界统一为**单根 /workspace 坐标系**,让 skill 脚本在容器内正确执行,根治 AAA-8053。

## What Changes

- **单根 /workspace 坐标系(相对路径不变式)**:模型只见单根 `/workspace`;所有文件类工具的路径输入解释为 **workspace 相对路径**,物理解析交后端;**容器模式与无-docker 降级模式对同一相对路径 MUST 解析到同一物理文件**。降级态(OFF)MUST 为 skills 单独供给(物化 skills 到 workspace 或把 `SKILLS_DIR` 改指真实可达目录),不得让 skill 脚本在 OFF 态找不到目录。
- **skills 挂载进容器**:宿主 skills 目录 bind 到容器 `/workspace/skills`(默认 **ro**、可配),注入环境变量 `SKILLS_DIR=/workspace/skills`;挂载源路径纳入 `config_hash` 且过 `is_blocked_mount`;处理 **builtin_skills(包内根)与用户 skills(`FLEETENT_SKILLS_DIR`/默认根)两个物理根只能挂一个**的现实——采纳「单一有效根」策略:挂用户根(运营可写、可定制),包内 builtin skill 在降级/挂载前由扫描态可见但其脚本资源经物化兜底(见 design)。
- **采纳执行面收敛(C)**:`run_code` 是容器内**唯一执行面**(它是「在容器内执行任意语言」的严格超集——skill 脚本经 subprocess 调 python/bash/node 运行)。**不新增 `sandbox_exec` 或任何第二个容器内执行工具**——避免两工具 risk 不一致的审批后门、指令层翻倍、两份代码同步。免审批由 action-gate(`action_gate_medium_mode`=sandbox + 运行时封闭性)统一裁决,`run_code` 保持 `risk_level=medium`。
- **uploads / generated 迁入 /workspace**:`generate_image` 产物写入 per-scope `/workspace/generated/`,工具返回 **workspace 相对引用**(`generated/<name>.png`);入站图片暂存与 `analyze_image` 回读迁入 per-scope `/workspace/uploads/` 并以 workspace 相对引用流转——与 `normalizer._save_file_to_workspace` 已有的相对引用范式对齐。**`analyze_image` 回读契约不得破坏**:回读经 workspace 解析(容器 / 宿主降级同址),不再依赖宿主绝对路径。
- **指令层根治世界观分裂**:
  - `bash_exec` 模型可见描述**首行**写明「在宿主执行,看不到 /workspace 与会话文件;处理会话文件请用容器内执行工具(run_code)」(schema_builder 只取 docstring 首行,已核实 `schema_builder.py:24`)。
  - `read_skill` 返回值与 `<available_skills>` 目录渲染注入指引:「skill 脚本用容器内执行面(run_code)运行,脚本内路径以 `$SKILLS_DIR` 为根」。

## Capabilities

### New Capabilities
- `sandbox-workspace-root`: 单根 /workspace 坐标系 + 相对路径不变式 + 降级态 skills 供给契约。
- `sandbox-skill-mount`: 宿主 skills 目录挂载到容器 `/workspace/skills`(ro 默认、可配)+ `SKILLS_DIR` 注入 + 挂载源纳入 config_hash 且过 is_blocked_mount + 双物理根策略。
- `sandbox-exec-face`: 执行面收敛——run_code 是容器内唯一执行面,不新增 sandbox_exec 或任何第二个执行工具;skill 脚本经 run_code 内 subprocess 运行。

### Modified Capabilities
- `image-generation-tool`: `generate_image` 产物从 `data/generated/` 迁入 `/workspace/generated`,返回 workspace 相对引用。
- `vision-as-tool`: 入站图片存盘与 `analyze_image` 回读迁入 `/workspace/uploads`,以 workspace 相对引用回读;回读契约不破坏。
- `builtin-shell-tool`: `bash_exec` 模型可见描述首行写明「宿主执行、看不到 /workspace、会话文件请用容器内执行工具」。
- `skill-read-on-demand`: `read_skill` 与目录渲染注入「脚本用容器内执行面、路径以 `$SKILLS_DIR` 为根」指引。

## Impact

- **代码**:
  - `integrations/sandbox/manager.py`(acquire 增加 skills 只读挂载源解析、纳入 config_hash);`integrations/sandbox/backends/docker.py`(`_skill_mount_flags` 追加 `-v <skills_host>:/workspace/skills:ro`、`SKILLS_DIR` env);`integrations/sandbox/backend.py`(`create_workspace` 签名追加可选 `skill_mount` 形参,默认 None 向后兼容);`integrations/sandbox/hardening.py`(`config_hash` 把 skills 挂载源纳入摘要;`is_blocked_mount` 复用于 skills 源)。
  - `tools/builtin_tools.py`(`generate_image` 落盘改 per-scope `/workspace/generated`、返回相对引用;`_save_upload`/`_read_upload`/`UPLOADS_DIR`/`GENERATED_DIR` 迁为 workspace 解析或退役为 normalizer 路径复用;`bash_exec` docstring 首行;**不新增 sandbox_exec**)。
  - `tools/file_tools.py` / `tools/file_sandbox_io.py`(复用既有 `resolve_ws_path`/`resolve_host_path` 的相对路径不变式;generated/uploads 解析复用同一 fence)。
  - `im_gateway/normalizer.py`(入站图片 `_save_upload` 调用点改为 per-session workspace 落盘,与 `_save_file_to_workspace` 对齐)。
  - `skills/registry.py`(`available_skills_prompt` 目录渲染追加 `$SKILLS_DIR` 根指引;`read_skill` 返回拼接执行面/路径指引;降级态 skills 供给——物化或 `SKILLS_DIR` 改指)。
- **owning package**:`integrations/sandbox`(skills 挂载、config_hash)、`tools`(执行面、generate_image/analyze_image 落盘、bash_exec 描述)、`skills`(指令层渲染)、`im_gateway`(入站图片落盘对齐)。
- **public API surface**:`SandboxManager.acquire`(新增可选 skills 挂载参数,默认行为不变);`BaseSandboxBackend.create_workspace`(新增可选 `skill_mount` 形参,默认 None);`builtin_tools.run_code`(签名不变,唯一执行面);`available_skills_prompt` / `read_skill`(返回文本追加指引,签名不变)。`_save_image`/`_save_upload`/`_read_upload`/`_skill_mount_flags` 为 internal。
- **owned tables**:无(workspace / skills 为文件系统;skill_hit / 审计仍走既有 agent 侧 trace,不新增表)。
- **config namespace**:`sandbox.skill_mount`(新增,归属 `SandboxSettings` per-agent 与 platform `sandbox.*`):`enabled`(默认 true)、`read_only`(默认 true)、可选 `source`(默认解析用户 skills 根)。复用既有 `sandbox.*`、`governance.action_gate_*`(不新增 governance 配置)。
- **cross-module dependencies**:`tools` / `im_gateway` / `skills` 调用 `integrations/sandbox` 与 `paths` 的 public API;`integrations/sandbox` 读 `paths`。**owning 模块均为 agent 运行时模块,MUST NOT `import fleetent.platform.*`**(已核实当前 `tools`/`integrations.sandbox`/`skills` 无 platform import);agent 须仍能在无 platform、platform 表不存在环境下 `fleetent agent run` 并跑通含 skill 脚本的对话。不改 `resolve_action_mode` 契约、不改 registry risk 常量。
- **migration / shim plan**:`GENERATED_DIR`/`UPLOADS_DIR` 由宿主绝对落点迁为 workspace 解析——存量 `data/generated/`、`data/uploads/` 旧文件成低危孤儿(临时性产物),由 `sandbox-workspace-gc` 或一次性运维清理兜底,不需 re-export shim;旧绝对引用仅存活于历史 session,新生成一律相对引用。`_save_image`/`_save_upload` 若签名变更,保留同名 internal 函数(非跨包 public,无需 shim)。`SKILLS_DIR` env 为新增注入,旧 `FLEETENT_SKILLS_DIR`(宿主侧扫描用)语义不变、与容器内 `SKILLS_DIR` 正交。

## 依赖

- `sandbox-isolation-foundation`(已完成):容器/workspace 无碰撞 key 派生、运行时封闭性门控、workspace GC。本 change 的 skills 挂载源与 generated/uploads 落点都建在地基的 per-scope workspace 之上。
- 基线既有:`sandbox-workspace-mount`、`file-tools-sandbox-execution`、`skill-read-on-demand`、`skill-env-var`、`image-generation-tool`、`vision-as-tool`、`multimodal-input`、`action-gate`。
