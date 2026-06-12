## Context

地基(`sandbox-isolation-foundation`)已落地:容器名/workspace 子目录无碰撞 key 派生、运行时封闭性门控(`sandbox_capable` 反映 effective_mode)、workspace GC,并在其 design 明确把「uploads·generated 迁入 / 不加 sandbox_exec」留给本 change。

当前执行世界存在三层坐标系分裂(详见 proposal Why):
- skill 清单向模型暴露宿主绝对路径(`registry.py:551` 渲染 `entry.path`),却引导用容器内 `run_code` 执行;
- 宿主 skills 目录从未进容器(`docker.py` 只 bind `/workspace`);
- `generate_image`(`builtin_tools.py:85,101` `GENERATED_DIR`)、入站图片(`:90,113` `UPLOADS_DIR` + `:127 _read_upload` 宿主绝对回读)落在 workspace 之外,与「入站非图片文件已落 per-session workspace、返回相对引用」(`normalizer.py:216 _save_file_to_workspace`)分裂。

既有可复用机制:`file_sandbox_io.resolve_ws_path`(容器内相对 `/workspace` 解析)与 `resolve_host_path`(宿主围栏)已实现相对路径不变式的两半;`workspace_host_path(scope, session_id, agent_name)` 是 acquire 与 host-degrade 共用的单一 workspace 目录解析点;`config_hash` 已把 workspace 挂载源纳入;`is_blocked_mount` 已护栏挂载源。

## Goals / Non-Goals

**Goals**
- 模型只见单根 `/workspace`,工具路径输入为 workspace 相对路径,物理解析交后端;容器/降级对同一相对路径解析到同一物理文件。
- 宿主 skills 目录挂入容器 `/workspace/skills`(ro 默认、可配),注入 `SKILLS_DIR`;挂载源纳入 config_hash、过 is_blocked_mount;解决双物理根。
- 采纳执行面收敛(C):run_code 是容器内**唯一**执行面,**不新增 sandbox_exec** 或任何第二个执行工具;skill 脚本经 run_code 内 subprocess 运行。
- generate_image/uploads 迁入 `/workspace`,以相对引用流转;analyze_image 回读契约不破坏。
- 指令层根治世界观分裂(bash_exec 首行、read_skill/目录渲染指引)。

**Non-Goals**
- 不改 `resolve_action_mode` 契约、不改 registry risk 常量(免审批正当性绑封闭,归「放松管制」change)。
- 不动 scope 语义、不拆 scope(独立高风险重构)。
- 不动 workspace rooting(`data_dir()` 在 standalone 已重定向到 agent home,地基已确认)。
- 不动 `sandbox-lifecycle` 命名/碰撞块(地基所有);本 change 不碰 action-gate/approval spec。
- **不新增 `sandbox_exec` 或任何第二个容器内执行工具**;run_code 是唯一执行面。

## Decisions

### D1:单根 /workspace + 相对路径不变式 —— 复用 resolve_ws_path / resolve_host_path
模型只见 `/workspace`;工具路径输入解释为 workspace 相对路径。容器模式经 `resolve_ws_path`(相对 `/workspace`)、降级模式经 `resolve_host_path(workspace_host_path(...), path)` —— 两者已分别实现不变式的两半,且共用 `workspace_host_path` 这一单一目录解析点,故同一相对路径在两模式落同一宿主物理文件。generated/uploads 迁入后复用这同一对解析函数,而非另起路径逻辑。
- **备选**:让模型继续用宿主绝对路径、由工具反向映射。否决——双坐标系正是 AAA-8053 根因,反向映射在降级/容器切换时仍漏。

### D2:skills 挂载 —— docker `-v <src>:/workspace/skills:ro` + SKILLS_DIR env + config_hash + is_blocked_mount
在 `DockerBackend` 增 `_skill_mount_flags(skill_mount)` 产出 `-v <host_src>:/workspace/skills:ro`(read_only=false 时去掉 `:ro`),并把 `SKILLS_DIR=/workspace/skills` 经既有 `_env_flags` 注入(与 `sandbox_env` 并存)。`BaseSandboxBackend.create_workspace` 追加可选 `skill_mount`(默认 None 向后兼容)。`manager.acquire` 解析 skills 宿主源(经 `is_blocked_mount` 校验)→ 传入 `create_workspace` → 同时把 `(src, read_only)` 纳入 `config_hash`(扩 `hardening.config_hash` 入参或在 manager 端把其拼入 env/host 摘要),使挂载源/模式变更触发复用失配重建。
- **备选**:把 skills 复制进每个 workspace(物化)。否决作为容器模式默认——重复拷贝、与 ro 资产语义不符;但物化作为**降级态兜底**保留(见 D4)。

### D3:双物理根 —— 单一有效根 = 用户 skills 根,builtin 经物化兜底
`/workspace/skills` 只能 bind 一个宿主目录,而索引来自包内 `BUILTIN_SKILLS_DIR`(`registry.py:22`)与用户根(`_resolve_skills_dir`)。决策:挂**用户根**(运营可写、可定制,且 `write_skill` 已落用户根)。包内 builtin skill(当前 `getting-started`)若带脚本资源,在挂载/启动前把其目录物化(复制)进用户根的同名目录(幂等,用户同名 skill 已覆盖时不覆盖),保证 `$SKILLS_DIR/<name>/` 在容器内可达。`<available_skills>` 的 `location` 渲染相应改为以 `$SKILLS_DIR` 为根的形态(指令层),不再渲染宿主绝对路径。
- **备选**:两根合并挂载(overlay/多 bind)。否决——docker 单点 bind 简单可靠,overlay 引入 uid/写层复杂度;两根挂两个不同容器路径则又把双坐标系带回模型。

### D4:降级态(OFF)skills 供给 —— SKILLS_DIR 改指真实宿主根 或 物化到宿主 workspace/skills
docker 不可用时 file tools 已降级宿主围栏(根 = `workspace_host_path`)。此时 `/workspace/skills` 不存在,但 skill 脚本仍需 `$SKILLS_DIR` 可达。决策:降级态把脚本可见的 `SKILLS_DIR` 改指**宿主上真实存在**的有效 skills 根(用户根),或把 skills 物化到宿主 `workspace/skills/` 后令 `SKILLS_DIR` 指它。二者皆保证 `$SKILLS_DIR` 在宿主真实存在——杜绝「OFF 态指向容器内才有的路径」。
- **备选**:OFF 态不供给 skills(脚本自负)。否决——直接复发 AAA-8053 的 FileNotFoundError。

### D5:执行面收敛(C)—— run_code 唯一执行面,不新增 sandbox_exec
run_code 已是唯一经 `SandboxManager.acquire` 的容器执行面,且是「在容器内执行任意语言」的严格超集(skill 脚本 = `subprocess.run(["python3"/"bash"/"node", f"{SKILLS_DIR}/...", ...])`)。本 change 确立:容器内执行只此一个工具,**不新增 sandbox_exec**。免审批由 action-gate(`action_gate_medium_mode`=sandbox + 运行时封闭性)统一裁决,run_code 保持 `risk_level="medium"`。
- **备选 1**:独立 `sandbox_exec(cmd)` 直连后端 exec。否决——独立全链路 + 可能更低 risk = 审批后门。
- **备选 2**:`sandbox_exec` 作为 run_code 薄封装(评审的退路)。**亦否决**——多一个工具=模型选择困惑 + 指令层负担翻倍 + 两份代码(截断/redaction/liveness)需同步,收益仅「便捷 shell」,而 run_code + subprocess 已完全覆盖。一个工具最简、且彻底消除 risk 旁路。

### D6:generate_image / uploads 迁入 —— per-scope workspace 子目录,相对引用
`generate_image` 落盘改为 per-scope `/workspace/generated/<uuid>.png`(经 tool_context 定位 scope workspace,复用 run_code/file_tools 的 session_id/agent_name key),返回相对引用 `generated/<name>.png`。入站图片暂存改走 per-session workspace `uploads/`(对齐 `normalizer._save_file_to_workspace`),`analyze_image` 经 workspace 解析回读(容器 `/workspace/uploads/...` 或宿主围栏同址)。**回读契约保持**:有效引用可回读、无效引用返回错误文本不抛异常。
- **二选一说明(图片是否迁移)**:任务给出「迁移不得破坏 analyze_image 回读;必要时图片保持现状不迁」的二选一。**选择迁移**——因为 analyze_image 回读经 workspace 解析后(宿主 workspace 围栏 = 容器 `/workspace` 同址)契约可完整保持,且统一坐标系才根治分裂;入站非图片文件早已落 workspace 并相对引用,图片不迁反而是坐标系孤岛。保留 `_read_upload` 同名 internal 但改为 workspace 解析(向后兼容历史绝对引用:历史 session 的绝对路径仍可被 `Path(ref)` 兜底读到,新生成一律相对)。

### D7:指令层 —— bash_exec docstring 首行 + 渲染指引
`schema_builder.py:24` 只取 docstring 首行作 description(已核实)。故把 bash_exec 世界观压进**首行**:「在宿主执行,看不到 /workspace 与会话文件;处理会话文件用 run_code」。`available_skills_prompt` 的固定指令段与 `read_skill` 返回拼入「脚本经 run_code 运行、路径以 $SKILLS_DIR 为根」——固定文本不破坏 skill 清单稳定前缀的字节稳定性(`skill-read-on-demand` 既有约束)。

## Risks / Trade-offs

- **挂载源 uid/权限**:用户 skills 根 ro 挂入,容器内只读不改;agent 写场景由 read_only=false 配置开,运营自担。
- **物化 builtin 的时机/幂等**:物化须幂等且不覆盖用户同名 skill(沿用 registry 的「用户覆盖 builtin」语义);失败须 log 不静默,降级仍保证 SKILLS_DIR 可达。
- **历史绝对引用**:旧 session 里的 `data/generated/...`、`data/uploads/...` 绝对引用在迁移后由 `Path(ref)` 兜底读;旧文件成低危孤儿,交 `sandbox-workspace-gc`/运维清理。
- **config_hash 扩面**:把 skills 源纳入 hash 会让首次部署后变更挂载源触发一次重建(预期、安全)。
- **SKILLS_DIR 与 sandbox_env 冲突**:平台注入优先并记录,避免 agent 用 sandbox_env 覆盖 SKILLS_DIR 制造混乱。

## Migration Plan

1. 后端/manager 先落 skills 挂载 + config_hash + SKILLS_DIR(向后兼容默认 None,不影响既有容器)。
2. generate_image/uploads 落盘迁 workspace、相对引用;`_read_upload` 改 workspace 解析 + 历史绝对兜底。
3. 指令层(bash_exec 首行、渲染指引)。
4. 降级态 skills 供给(物化/SKILLS_DIR 改指)。
5. 存量 `data/generated`、`data/uploads` 旧文件交 GC/运维,不需 shim。

## Open Questions

- builtin skills 物化的触发点放扫描期(scan)还是容器创建前(acquire)更稳?倾向 acquire 前按需物化(只物化将被挂载的有效根),避免无谓拷贝——实现期定。
- `SKILLS_DIR` 在降级态指「真实宿主用户根」还是「物化到 workspace/skills」二选一,是否需要按 read_only 配置一致化(ro 时指真实根、需写时物化)?实现期按最简且不破坏相对路径不变式择一。
