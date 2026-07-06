# Design — skill-backflow-git-pr

## 设计概述（出站数据流）

agent 临场改 skill → node 报漂移 → platform 提名 proposal 存 bundle（**复用老逻辑，零 git**）。platform 一个独立定时任务 `backflow_pr_sweep` 把待审提案**先推备份分支保命**（非 main），再（按 `auto_open_pr`）开 PR；人在 git 平台 review，admin 在后台决策。git 操作全部经 `integrations/git_platform` 在 platform 侧完成。

```
agent 改 skill → home 漂移
   │ node 报漂移（不碰 git）
   ▼
backflow_store.nominate：存 proposed_bundle（不碰 git）        ← 复用老逻辑
   │ ── backflow_pr_sweep（platform 独立定时，类比 kb_connector_sweep）──
   ▼
① push_branch 推备份分支 backflow/<agent>/<skill>（非 main，即时保命）→ pr_state=backed_up
② auto_open_pr 开 → open_pull_request → pr_state=pr_open
   │ git 不可达 → pr_state=deferred，下轮重试（舱壁化不崩）
   ▼
admin 治理：accept=合并 PR → align_pool_to_remote 对齐 pool → bump epoch
            reject=关 PR（pool 不动）；fork=新分支+PR+改绑
   ▼
合并 main 后 → 复用入站 fetch+reset 把 pool 对齐主线 → node 强制对齐
```

## 关键技术决策

1. **git 操作全在 platform 侧，从 node 路径剥离**：node 上报与 `nominate` 只存 bundle、零 git 依赖（**不重新引入**曾被删除的「提名即开 PR」挂 node 路径钩子）。所有 push/PR 收进 platform 独立 sweep + 治理端点。`integrations/git_platform` 不反依赖 platform（仿 `integrations/sandbox`）。

2. **可插拔 git 平台抽象（仿 sandbox）**：`BaseGitPlatformBackend` mandatory `available()`（探活永不抛）+ `push_branch(*, branch, bundle, subdir, base_ref, message, author)→str`（唯一走 dulwich git 协议，推备份/fork 分支）；capability-gated `open/get/merge/close_pull_request`（走平台 REST，基类抛 `NotImplementedError`）。`@dataclass(frozen=True) GitPlatformCapabilities`（open_pr/merge_pr/close_pr/query_pr/server_side_merge/delete_source_branch）+ `PullRequestRef`（pr_id/url/state/source_branch/merge_commit）+ `GitPlatformUnavailable(RuntimeError)`。调用方按布尔 gate，**不 isinstance**。`factory.create_git_platform(*, config)` 未知 provider 记 warn 并**抛**（写错权威 git 后果严重，不 fallback）；config 由调用方从 `skill_git_source` 读出传入。

3. **备份优先（保命）**：sweep 间隔默认 120s（比入站 300s 短），proposal 提名后尽快推**备份分支**（非 main）——即使 PR 被拒/关，备份分支仍留痕、agent 改动不丢。开 PR、合并是后续治理动作。分支名按 `<branch_prefix>/<agent>/<skill>` 稳定，`nominate_if_absent` 去重压制短命分支。

4. **accept 不再直写 pool，改为合并 PR + 对齐**：消除入站「外部 git 为权威、reset 会丢直写」的双写冲突。`accept` = `merge_pull_request` → **复用 `pool_sync.align_pool_to_remote`**（fetch+reset 把 pool 对齐主线）→ `pool_version_for_skill` 取新 sha → `set_current_version`/`set_drift(False)`/`bump_resync_epoch`。冲突（`base_version`≠head）+ `X-Confirm` 门控保留。

5. **合并后回路（最大风险）**：accept=「合并 → align → bump epoch」。对齐失败 → 「PR 已合并但 pool 未更新」→ 不 bump epoch、留 pending+hint、幂等重试（merge 对已合并 PR 幂等；align 走 fetch+reset 保证 pool=主线）。

6. **降级与舱壁化**：sweep 每步独立 try/except；git 不可达 → `set_pr_state("deferred")` 下轮/手动重试，不崩 cron/boot；治理端点 git 调用包 `GitPlatformUnavailable` → deferred + 503，**不碰 drift/epoch**（避免「以为成功清了 drift 实则没推上去」）。boot 不接外部网络。

7. **凭证**：复用入站 `skill_git_source` 配置（remote/branch/branch_prefix/auto_open_pr）+ `agent_secrets`（env 名引用）；push/PR token 与入站 fetch 共用此体系；token-in-url 日志脱敏。

## 与现状 / 入站 change 的衔接

- 现状（已核实）：`backflow_store` 有 nominate/list/diff/set_status/`_detect_conflict`；`backflow_api` 有 list/diff/accept(`_write_bundle_atomic`+`commit_pool`)/reject/fork；`node_desired_state_api` 仅 import `pool_version_for_skill`（读），**无 git 钩子**（符合预期）。
- 入站 115 迁移**已建** `skill_git_source` 全列（含 `branch_prefix`/`auto_open_pr`/`base_url`/`project`/`repo`/凭证 env 名）→ F 配置侧零迁移，只给 `backflow_proposals` 加 PR 列（迁移 116）。
- 复用入站：`pool_sync.align_pool_to_remote`（accept/fork 合并后对齐）、`git_source_store.get_config`、`pool_sync.set_secret_resolver` 注入的凭证解析。
- **删除出站旧设计的 `git_platform/remote_sync.py`**：pool 对齐统一复用 `pool_sync`，`git_platform` 只管「平台 REST 的 PR 生命周期 + 推分支」。

## 模块边界

见 proposal.md「Impact」。要点：新增 `integrations/git_platform`（不依赖 platform）；改动只在 platform 侧 + config + 前端；**agent runtime / node 零改动、零 git 依赖，node 不引入 DB**；`node_desired_state_api` 仍零 git 钩子；新表列经 Alembic 116；凭证走 agent_secrets。`scripts/check_module_boundaries.py` 与 plane boundary guardrail 须仍通过（`backflow_pr_sweep`/`backflow_api` 经注入解耦，不 import agent_lifecycle face）。

## 测试策略

- **unit**（mock / respx）：`git_platform` 选型（未知 provider 抛）+ capability 门控；`bitbucket` backend（respx 断 REST + dulwich push 往返）；`backflow_pr_sweep`（推备份分支断言分支非 main + pr_state=backed_up；auto 开 PR=pr_open；offline→deferred）；`backflow_api` accept/reject/fork（FakeGitPlatformBackend 注入 seam，复用既有治理断言，accept 复用 align_pool_to_remote、offline→503 不碰 drift/epoch）；前端回流区 PR 态 + 手动控件。
- **integration**（真实 dulwich + SQLite + Alembic）：迁移 116 加列 + `set_pr_link`/`set_pr_state`/状态查询；FakeGitPlatformBackend 注入下 sweep → accept 全链路（merged→对齐→current_version/drift/epoch 正确）；fork 改绑 + epoch。
- **边界回归**：断言 `node_desired_state_api` / node / agent 代码路径无任何 `git_platform` / dulwich-remote 调用；`node/test_skill_deployer.py` resync 路径不变。
