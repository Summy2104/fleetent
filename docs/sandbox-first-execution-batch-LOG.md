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
| 2 | sandbox-execution-world | ⏳ | - | - | 进行中 |
| 3 | sandbox-file-egress | - | - | - | 待 |
| 4 | sandbox-workspace-scope-split | - | - | - | 待 |
| 5 | sandbox-approval-relaxation | - | - | - | 待 |
| 6 | skill-frontmatter-agentskills-compliance | - | - | - | 待 |

## 决策与问题日志

### D0(上述执行模型)— 2026-06-11
基础分支栈式叠加,不逐 change merge to main。理由见上。

### #1 sandbox-isolation-foundation — 完成 2026-06-11
- 实现:`_name_key`(manager.py)收口 key 派生——短 key 原样直通(保可读+不破既有断言),sanitised 超 47 字符 budget 才截断+追加完整 key 的 sha256 hex 后缀(12 字符);`_container_name`/`_agent_image_tag`/`workspace_host_path` 三处共用。`runtime_sandbox_capable`(loop.py)= is_sandbox_backed ∧ mode!=OFF ∧ 容器内执行(workspace_mount);run_code 只需 mode!=OFF,文件工具额外需 mount(与 _select_backend 降级同源);复用 action_gate fail-closed,未改其契约。新 `workspace_gc.py`:gc_session_workspace(整目录 rmtree)/gc_agent_workspace(mtime 清理),双护栏 is_blocked_mount+realpath-in-root。session/manager.py 经 public API 接入 session GC。
- **决策 D1**:GC 由调用方按 scope 显式触发(session/agent workspace 目录名无 scope 前缀无法仅凭名区分),session GC 接 release/TTL 点、agent GC 接 idle sweep。
- **决策 D2**:manager↔workspace_gc 循环导入 → manager 内懒导入 workspace_gc。
- 验证:模块边界 EXIT 0;新改 54 unit + 79 integration 全绿;`make test-pr` 2767 passed,唯一失败 `test_intelligence_directory_shim_removed` 与本 change 无关(diff 不碰 intelligence/,预先存在);mypy 90→87 无新增。
- 已 archive,specs 同步(新 cap sandbox-containment-gating/sandbox-workspace-gc;改 sandbox-lifecycle/sandbox-workspace-mount)。

<!-- 后续每个 change 的决策、遇到的问题、解决方式追加于此 -->
