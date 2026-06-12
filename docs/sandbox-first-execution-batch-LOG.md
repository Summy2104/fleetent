# 沙箱优先执行模型 — 批次执行日志

> 自主执行记录(2026-06-11 夜起)。张洋下班期间全自动实现 6 个 OpenSpec change,问题与决策记录于此,供次日审核。

## 执行模型(决策 D0)

**集成基础分支 + 栈式叠加,而非逐 change merge 到 main。**

- 基础分支 `feat/sandbox-first-execution`(off 最新 main)= 6 个 change 的集成线。
- 每个 change 按序栈式叠加在基础分支上:一组干净提交(`docs(openspec): propose <name>` → 实现提交 → `docs(openspec): archive <name>`)。后一个 change 从基础分支当前状态起步,自带前面成果。
- **理由**:逐 change merge-to-main 的 CI 门控对无人值守过夜执行是脆弱的——某个 PR 的 CI 阻塞会卡住后续全部。基础分支保证 6 个 change 无论 CI/main 合并时机如何都能彼此叠加构建并整体通过测试,符合张洋指示「CI 不影响后续执行」「失败后 spec 合并到基础分支」。per-change 提交分组保留逐 change 可审查性。
- **PR**:最后推基础分支到 origin(Bitbucket),建一个 `feat/sandbox-first-execution → main` 的 PR,**不自动合并**,留张洋审批。CI 按 2min/30min 非阻塞轮询。
- 推送目标仅 **origin**(Bitbucket),不推 github。

## 执行顺序

1. sandbox-isolation-foundation(地基:碰撞修复 + 封闭门控 + workspace GC)
2. sandbox-execution-world(单根 /workspace + skills/SKILLS_DIR + run_code 唯一执行面 + 指令层)
3. sandbox-file-egress(send_file + Telegram 出站 + 废正则回流)
4. sandbox-workspace-scope-split(高风险:workspace_scope/镜像解耦 + 声明式 build + 删 agent 数据档)
5. sandbox-approval-relaxation(免审批兑现 + bash_exec 默认移除,最后)
6. skill-frontmatter-agentskills-compliance(独立)

## 进度

| # | change | 实现 | 门禁 | archive | 状态 |
|---|--------|------|------|---------|------|
| 1 | sandbox-isolation-foundation | ✅ | ✅ | ✅ | **完成** |
| 2 | sandbox-execution-world | ✅ | ✅ | ✅ | **完成** |
| 3 | sandbox-file-egress | ✅ | ✅ | ✅ | **完成** |
| 4 | sandbox-workspace-scope-split | ✅ | ✅ | ✅ | **完成(2 个后续项见下)** |
| 5 | sandbox-approval-relaxation | ✅ | ✅ | ✅ | **完成** |
| 6 | skill-frontmatter-agentskills-compliance | ✅ | ✅ | ✅ | **完成** |

## 决策与问题日志

### D0(上述执行模型)— 2026-06-11
基础分支栈式叠加,不逐 change merge to main。理由见上。

### #1 sandbox-isolation-foundation — 完成 2026-06-11
- 实现:`_name_key`(manager.py)收口 key 派生——短 key 原样直通(保可读+不破既有断言),sanitised 超 47 字符 budget 才截断+追加完整 key 的 sha256 hex 后缀(12 字符);`_container_name`/`_agent_image_tag`/`workspace_host_path` 三处共用。`runtime_sandbox_capable`(loop.py)= is_sandbox_backed ∧ mode!=OFF ∧ 容器内执行(workspace_mount);run_code 只需 mode!=OFF,文件工具额外需 mount(与 _select_backend 降级同源);复用 action_gate fail-closed,未改其契约。新 `workspace_gc.py`:gc_session_workspace(整目录 rmtree)/gc_agent_workspace(mtime 清理),双护栏 is_blocked_mount+realpath-in-root。session/manager.py 经 public API 接入 session GC。
- **决策 D1**:GC 由调用方按 scope 显式触发(session/agent workspace 目录名无 scope 前缀无法仅凭名区分),session GC 接 release/TTL 点、agent GC 接 idle sweep。
- **决策 D2**:manager↔workspace_gc 循环导入 → manager 内懒导入 workspace_gc。
- 验证:模块边界 EXIT 0;新改 54 unit + 79 integration 全绿;`make test-pr` 2767 passed,唯一失败 `test_intelligence_directory_shim_removed` 与本 change 无关(diff 不碰 intelligence/,预先存在);mypy 90→87 无新增。
- 已 archive,specs 同步(新 cap sandbox-containment-gating/sandbox-workspace-gc;改 sandbox-lifecycle/sandbox-workspace-mount)。

### #2 sandbox-execution-world — 完成 2026-06-11
- 实现:backend.SkillMount + create_workspace 加可选 skill_mount;docker `_skill_mount_flags`(-v src:/workspace/skills[:ro])+ SKILLS_DIR 注入(平台优先);hardening.config_hash 纳入 skill_mount(None 时字节兼容旧容器);manager._resolve_skill_mount(有效根→物化 builtin→is_blocked_mount→SkillMount);skills/registry effective_skill_root + materialize_builtin_skills(幂等不覆盖)+ location 渲染改 $SKILLS_DIR + run_code/路径指引;builtin_tools generate_image 落 /workspace/generated 返相对引用、_save/_read_upload 改 workspace 解析(历史绝对兜底)、read_skill 拼指引;shell_tool bash_exec docstring 首行改宿主世界观;normalizer 入站图片 per-session workspace。
- **决策 D3**:执行面收敛锁定——run_code 唯一执行面,**不新增 sandbox_exec**(用户拍板)。
- **决策 D4(迁移)**:analyze_image 选择迁入 /workspace/uploads,回读经 workspace 解析 + 历史绝对引用兜底,契约不破。
- **AAA-8053 根因验证**:实测 skill 脚本经 $SKILLS_DIR 在容器内运行成功(exit 0)。
- 验证:模块边界/测试层 OK;make test-pr 2812 passed(唯一失败 intelligence shim,预存无关);本 change 10 integration 全绿;mypy 改动文件零 error。
- archive,specs 同步(新 cap sandbox-workspace-root/sandbox-skill-mount/sandbox-exec-face;改 image-generation-tool/vision-as-tool/builtin-shell-tool/skill-read-on-demand)。

### ⚠️ 全局 gotcha(影响所有 change 的验证)
实现 agent 易跑 `ruff format src tests`(格式化**全树**),误改大量无关文件的存量风格漂移(#2 时误改 22 个,含 platform/ 文件,可能与在途 schema-residue-cleanup 冲突)。**我在每个 change 提交前核查 diff、回退所有范围外纯格式化改动**,只保留本 change 真正触碰的文件。#3+ 的 agent 指令已加「只格式化自己改的文件」。

### #3 sandbox-file-egress — 完成 2026-06-11
- 实现:outbound.send_file_to(平台分派统一原语:Slack files_upload_v2 / Telegram send_document)+ im_gateway/outbound shim re-export;builtin_tools.send_file 工具(risk=none,schema 仅 path,收件人从 session_context 固定,免审批⟺session∧dm∧context非空否则 fail-closed,无连接器/不可达/缺文件/投递失败均返说明文本不抛);normalizer 退役正则回流(_extract_generated_image_paths 删),改 _turn_has_generated_product + 显式 _EGRESS_NOTICE;slack._make_upload_func 收敛到原语。
- **决策**:send_file 体内不可直接调 _get_manager()——会触发 #2 的 exec-face 护栏(字符串匹配 `_get_manager(`),抽到非工具辅助 `_workspace_scope_and_root`。Telegram bot 本在 outbound_connectors,send_document 自动接通,telegram.py 无需改。
- 验证:边界/层 OK;32 本 change 测试绿;make test-pr 2824 passed(仅预存 intelligence 失败);mypy 87=基线无新增;agent 遵守「只格式化自己文件」,无全树污染。
- archive,specs 同步(新 cap sandbox-file-send;改 im-generated-image-upload)。

### #4 sandbox-workspace-scope-split — 完成 2026-06-11(高风险重构)
- 实现:`Scope`→`WorkspaceScope` 正名 + `Scope = WorkspaceScope` 模块别名(#1/#2/#3 全部 `Scope.SESSION` 引用不破,已实证 send_file scope 判定/run_code/containment/workspace_gc 全绿);`_image_for(agent_name)` 解耦——镜像选择恒以 agent_name 为键、只看 image_persistence 开关+后端 persist_workspace,结构上保证镜像不随 workspace_scope 变;**sweep_idle 移除 commit_workspace**(docker-commit-from-running 禁令落实,commit_workspace 留存但退热路径);新增 `backend.build_deps_image`(docker build -t … - 从 stdin 离线构建 FROM base/RUN setup_command 的不可变镜像,microsandbox 继承 NotImplementedError 不静默);`resolve_workspace_scope(configured, multi_user)` 护栏 multi_user∧agent→session+warn;manager 加 `multi_user=False` 安全默认,init_sandbox_manager(standalone)显式 False。
- 验证:边界/层 OK;make test-pr 2842 passed(仅预存失败);**sandbox 全量 integration 126 passed 无回归**;mypy 87=基线;无全树格式化污染。
- archive,specs 同步(新 cap sandbox-workspace-scope/sandbox-image-persistence;改 sandbox-lifecycle 另 3 块)。

> **⚠️ #4 两个后续项(非阻断,需你知悉/后续处理)**:
> 1. **multi_user 平台接线未完成**:`resolve_workspace_scope` 护栏已落地+单元测试,standalone(`fleetent agent run`)已接线安全默认 `multi_user=False`。但 **platform 共享 IM 入口传 `multi_user=True` 的接线点未实装**(属 platform 侧改动,agent-runtime 不得碰 platform)。后果:多用户 bot 用**默认 session scope 安全**;仅当部署者**显式**给多用户 bot 配 `workspace_scope=agent` 且 platform 未传 multi_user=True 时,护栏不触发→跨用户数据共享仍可能。**需后续在 platform 侧把多用户入口传 multi_user=True**。核心镜像投毒泄露已由「移除 commit + 声明式不可变镜像」根除。
> 2. **agent-tier 运行期 read_only rootfs 未翻转**:spec 提及但 tasks.md 未列;agent 刻意保留资源 tier 不变避免范围蔓延+破坏无关 hardening 测试。核心「依赖来源与会话数据物理隔离」由声明式不可变镜像满足;运行期 read_only 属 defense-in-depth,留作后续 hardening。
> 3. microsandbox 声明式 build 端到端未真跑(环境未装 runtime),契约由 unit 覆盖。

### #5 sandbox-approval-relaxation — 完成 2026-06-11(免审批兑现)
- 实现:**免审批是显式部署选择**——`action_gate_medium_mode` 代码默认仍 `approval`(snapshot.py/agent_config.py 未改默认),example/文档给出「封闭部署推荐 sandbox」指引。bash_exec 默认移除落在**工具可见性解析层**:新 governance.agent_policy `OPT_IN_TOOLS={"bash_exec"}` + `is_tool_visible`,统一 snapshot.filter_tool_schemas/registry.dispatch/loop schema 组装,使 opt-in 工具即便在 allow-all(None)下也不默认暴露,schema 可见性与 dispatch 放行同源;运维 agent 经 allowed_tools 显式具名 opt-in 才有。docs/capabilities/governance.md 新增 Action Gate 章(mode 表+选型+迁移)。
- **未改 resolve_action_mode 契约/risk 常量/SANDBOX_BACKED_TOOLS**(锁定测试:test_sandbox_backed_tools_constant_unchanged、test_high_not_relaxed_with_medium_sandbox、test_code_default_medium_mode_remains_approval 全绿)。
- 验证:边界/层 OK;make test-pr 2856 passed(仅预存失败);工具可见性/access 回归 112 passed;#1-#4 既有测试全绿(107);mypy 87=基线;无全树污染。
- archive,specs 同步(改 approval-minimization/tool-access-control/sandbox-enablement-control)。

### #6 skill-frontmatter-agentskills-compliance — 完成 2026-06-11(独立)
- 实现:skills/registry.py 新增 string→type 归一化 helper + `_build_entry` 集中「metadata.fleetent-<key>(权威)→ 旧顶层(回落)→ 缺省」解析顺序;SkillEntry 加可选 compatibility 字段;迁移唯一内置 skill getting-started/SKILL.md 到标准形态(tags/version/enabled_by_default → metadata.fleetent-*)。旧顶层写法仍兼容读取(现有文件零改动生效),未知 metadata 被忽略不报错(优雅降级)。不含 requires-bins 沙箱门控(不耦合执行世界)。
- 验证:边界/层 OK;skill registry 112 测试绿;make test-pr 2867 passed(仅预存失败);mypy registry.py 零 error;无全树污染。
- archive,specs 同步(改 skill-yaml-frontmatter)。

---

## 最终汇总(2026-06-11 夜 → 06-12 晨)

**6 个 change 全部完成:实现 + TDD + 门禁 + archive + specs 同步,全部叠加在基础分支 `feat/sandbox-first-execution`。**

- 每个 change 均经:严格 TDD(红→绿)、模块边界 EXIT 0、测试层 EXIT 0、ruff(仅自身文件)、mypy 无新增、`make test-pr` 无新增失败(唯一持续失败 `test_intelligence_directory_shim_removed` 为 main 预存基线、与本批无关)、sandbox 全量 integration 无回归。
- 我对每个 agent 产出独立核验(自跑门禁 + 审 diff),并**回退了 #2 时 `ruff format src tests` 误改的 22 个无关文件**;#3-#6 agent 已遵守「只格式化自己文件」。
- 安全核心达成:碰撞修复(默认部署 P0 跨用户泄露根除)、无 docker=不免审批(fail-closed)、单根 /workspace + 路径对应(AAA-8053 实测根除)、send_file 收件人 harness 固定、run_code 唯一执行面(无审批后门)、docker-commit 投毒泄露根除(声明式不可变镜像)、免审批为显式部署选择(默认仍 approval)。

### #7 sandbox-scope-split-followups — 完成 2026-06-12(#4 两个后续项收尾)
应张洋要求补齐 #4 留的两个后续项:
- **A multi_user 信号接线(原后续项 1)已解决**:agent.yaml 新增 `sandbox.multi_user`(bool 默认 false),init_sandbox_manager 读它传入 SandboxManager,既有护栏由此真正生效(多用户配 agent→纠正 session+告警)。纯配置,无反向依赖;platform 生成多用户共享 agent 配置时写 true 即可。
- **B agent-tier read_only 收紧(原后续项 2)已解决**:#4 移除 docker-commit 后 agent 档"装依赖"理由失效,build_resources_by_scope agent 档收紧为与 session 同档(read_only=True/非 root 65534/cap_add 空),删 `_AGENT_CAP_ADD`、清陈旧注释;依赖来自 build 期不可变镜像,/workspace 仍可写。
- 实现 agent 抓到并修了一处测试污染(新测试 patch `_MANAGER` 全局泄漏,加 autouse fixture 恢复)。
- 验证:边界/层 OK;make test-pr 2874 passed(仅预存失败,无污染残留);sandbox integration 111 passed 无回归(#1-#5 不破);未全树污染。
- archive,specs 同步(改 sandbox-workspace-scope/sandbox-container-hardening)。

## 合并到 main(2026-06-12,张洋授权)
全部 7 个 change(6 批次 + 收尾)验证通过,张洋审完两个后续项后授权**整分支合并 main**。经 PR #235 合并(yang.zhang PR + admin 合并 + CI 轮询)。

**剩余后续项(非阻断)**:
- microsandbox 声明式 build 端到端未真跑(环境未装 runtime),契约由 unit 覆盖。
- platform 侧:生成多用户共享 agent 的 agent.yaml 时记得写 `sandbox.multi_user: true`(agent-runtime 已就绪,接收即生效)。
