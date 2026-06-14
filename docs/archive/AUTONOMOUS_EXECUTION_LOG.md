# 自主执行决策日志 — 2026-06-10

> 用户授权全程无人值守执行两个 OpenSpec change（apply → archive → push → PR → merge to main），问题与决策点记录于此供最后审核。
> CI 轮询约定：每轮 60s，超时 10min；探测不到 CI 不停任务，继续开发直至全部完成，最后再尝试合并。

## 范围

- **Change A**：`approvals-schema-drift-hotfix`（governance/approval_store.py 自愈补列 + 回填）— 生产止血，先行。
- **Change B**：`sandbox-memory-hard-limit`（integrations/sandbox 默认禁 swap + 可配置）。

## 环境基线

- 仓库：`/opt/gopath/src/github.com/youngz/fleetent`，main 分支，remote = Bitbucket `antalphadev/fleetent`。
- Docker Desktop 28.5.1 运行中（integration sandbox 测试需要）。
- git user：yang.zhang。
- 已知预存失败（AGENTS.md 记载，owner 非本次改动者）：约 2 unit + 19 integration；`make test-pr` 已 `--deselect` quarantine 2 个 flaky unit。门禁判据 = **无新增失败**。

## 时间线与决策点

### T0 启动
- 确认两个 change 的 OpenSpec 设计已 `--strict` 通过，artifacts 4/4。
- 决策：Change A 先行（生产 bug 止血）；A 合并后从更新的 main 切 B（两者无文件重叠，但顺序化降风险）。
- 决策：worktree 法（AGENTS.md 强制）。openspec change 目录在 main 为 untracked，新 worktree 不带 untracked 文件 → 在各自 worktree 内从 main 工作区 `cp -r` 对应 change 目录后作为 propose commit。

### T1 测试基线
- integration 基线（main worktree）：**2 failed**（`test_deployment_docs.py::test_global_config_example_templates_removed` / `::test_config_directory_is_not_a_runtime_or_template_namespace`），1716 passed。两者因 main 工作区存在 `config/` 目录而失败，与本次改动无关。
- 判据：feature 分支 integration 失败数 ≤ 基线同名失败 + 自有新测试全绿。

### T2 Change A 实现（approvals-schema-drift-hotfix）
- TDD：新增 `tests/integration/test_approval_store_schema_drift.py`（9 用例，覆盖旧/新/双列三形态 + 幂等 + 并发吞错 + 非预期异常照常抛），先红后绿。
- 实现：`approval_store.ensure_schema` 探测 `approver_actor` 缺列→`ALTER ADD`→仅在 `approver_user_id` 存在时回填；`duplicate column` 视为并发已自愈吞掉，其它 `OperationalError` re-raise。抽出 `_approvals_has_column` / `_add_approver_actor_column` 便于测试注入。
- **决策点 D-A1（lint）**：`make test-pr` 的 ruff 整文件扫描改动文件，暴露 `insert_approval` 内 **预存** 两行 E501（SQL 字面量，非我新增）。决定顺手折行修复（同文件内 lint 改进，未改语义），记此点。
- 收尾：`make test-pr` 全绿（2671 passed + 层边界 + ruff）；feature worktree 全量 integration **0 failed**（1726 passed，因 worktree 无 `config/`，基线那 2 个 deployment_docs 失败不出现）；mypy 通过。
- 归档：`openspec archive -y` 成功，`standalone-agent-approval` spec +1 requirement，change 移入 `archive/2026-06-10-approvals-schema-drift-hotfix`，单独 `validate --strict` 通过。
- 提交：3 commit（propose / fix / archive），worktree 干净。

<!-- 后续条目追加于此 -->

### T3 PR A 创建与 CI
- 推送 `feat/approvals-schema-drift-hotfix`，建 **PR #225**（→ main，close_source_branch），admin 已 approve。
- CI 可探测：Pipeline #507 INPROGRESS（commit 2d9f0709）。
- **决策点 D-A2（节奏）**：CI 运行中，按授权不阻塞等待，转去开发 Change B；最后统一轮询合并两 PR。A、B 无文件/spec 重叠，B 从当前 main 切不冲突。

### T4 Change B 开工（sandbox-memory-hard-limit）

### T5 Change B 完成（sandbox-memory-hard-limit）
- TDD：`tests/unit/test_sandbox_memory_swap.py`（10 用例）先红后绿；`tests/integration/test_sandbox_memory_swap.py`（真实 docker，400MB OOM）绿。
- 实现：`SandboxResources.memory_swap_mb`（None=禁 swap）；`_resource_flags` 始终输出 `--memory-swap`，钳制 `max(swap, memory)` + warn；`config` 两段经新 helper `_load_optional_positive_int` 载入校验。
- 收尾：`make test-pr` 全绿（2681 passed）；feature worktree 全量 integration 0 failed（1719 passed）；mypy 通过。归档 + spec（sandbox-resource-limits +1 added ~1 modified）+ validate 通过。

### T6 合并阻塞与处理（决策点 D-M1）
- **问题**：PR #225（A）merge 被门禁拒：「At most 3 commits behind destination」。期间 main 活跃推进（PR #224 per-agent-memory-lib、#226 slack-outbound 合入），A 落后 16 → 后 origin/main 再进到 0bbc1820。
- **处理**：把 origin/main 合并进 A 与 B（均无冲突）；A 最终落后 2（≤3，过检），B 重新合并到最新。
- **决策点 D-M2（make test-pr 假阳性）**：合并后首跑 `make test-pr` ruff 报 PR #224 带入的 `test_long_term_ctx.py`/`test_memory_agent_scope.py` 需 reformat。**根因**：`make test-pr` 用 `git diff main...HEAD`，而本地 `main` ref 陈旧（停在旧 base），把合并带入的他人文件算作 changed。`git pull` 更新本地 main 后，changed 集合回归仅本人文件，门禁通过。非真实问题，未改他人文件。
- 两分支各重跑 `make test-pr` 全绿（仅扫本人改动文件），推送合并提交（A=d1772965, B=979409e2），触发 CI 重跑。

### T7 PR A 合并
- A CI #511 SUCCESSFUL（60s 轮询第 1 轮）。
- **决策点 D-M3**：merge 先报「At least 1 approval」——推送合并提交后 Bitbucket 重置了审批。重新 admin approve 后合并成功。
- **PR #225 已 MERGED**（merge_hash 966fdd13）。

### T8 PR B 合并与收尾
- B 重新合并最新 main（含 A，无冲突），`make test-pr` 全绿，推送 abd97b25，admin 重新 approve。
- B CI #514 SUCCESSFUL（60s 轮询第 2 轮）。
- **PR #227 已 MERGED**（merge_hash 492a7469）。
- 收尾：本地 main 更新至 492a7469；验证 `memory_swap_mb`（B）与 `_add_approver_actor_column`（A）均在 main；两 change 均归档于 `openspec/changes/archive/2026-06-10-*`。
- 清理：移除两 worktree、删除两本地功能分支、删除主工作区冗余未跟踪 change 目录（已归档）。

## 最终结论

✅ **两个 OpenSpec change 全部完成并合并到 main**：
- PR #225 `approvals-schema-drift-hotfix` → merged 966fdd13
- PR #227 `sandbox-memory-hard-limit` → merged 492a7469

均经 TDD（红→绿）、`make test-pr` 全绿、真实 docker integration 验证、`openspec archive` + spec 同步 + `validate --strict`、Bitbucket CI SUCCESSFUL、admin approve + merge_commit。

### 需用户知晓 / 后续
1. **本地 my-bot 部署仍跑旧 v0.2.0 binary**：approvals 修复在 main/仓库，未自动到部署。我此前对 `~/.fleetent/data/fleetent.db` 的手动 `ALTER`（加 approver_actor 列）让线上 bot 暂时可用；正式生效需重新部署（`uv tool install` 更新 binary）。
2. **CI 轮询实际未触发超时**：两轮 60s 内即 SUCCESSFUL，10min 超时与「探测不到继续开发」分支未被用到。
3. **主工作区遗留** `AUTONOMOUS_EXECUTION_LOG.md`（本文件，未跟踪）供审核；审核后可删。
4. 制度性根因（approvals 双权威 / 漂移护栏盲区、sandbox swap 配置文档）留给既有 pending change `per-agent-approvals-lib`（3b-4）与运维配置，本次未扩范围。
