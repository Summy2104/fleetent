# Skill GitOps：外部 git 作为 skill 权威源

把 skill 内容的权威源从 platform 内部 pool 改为外部 git 仓库。platform 定时 / webhook 从外部 git 镜像进 pool，再经现有分发链路下发 agent；后台 UI 转只读。agent 运行时改 skill 的回流（→ git PR）见后续 change `skill-backflow-git-pr`。

## 数据流

```
外部 git repo (main = 权威) ──fetch + reset --hard──▶ platform pool（只读镜像）
                                                          │ 现有 skill_manifests / bundle（零改动）
                                                          ▼
                                                    node ──▶ agent
```

git 交互**只在 platform 侧**（`pool_sync` / `skill_git_webhook_api`）；node 与 agent 零 git 依赖。

## 外部仓库布局

仓库根直接放 skill 目录，每个 skill 一个目录 + `SKILL.md`（+ 可选 `scripts/` / `references/`）。

若外部仓库是 **monorepo**（skill 只占其中一个子目录，同级还有其它无关目录，如 `skills/` 旁边有 `claude/` `codex/`），配置 `skills_subdir`（如 `"skills"`）即可：git 仓根仍**整仓镜像**（fetch + reset --hard 不变，纯 dulwich、不用宿主 git 的 sparse-checkout），但 fleetent 只扫描/分发 `skills_subdir` 子目录下的内容，子目录之外的其它顶层目录不会被当成 skill。留空则维持「仓库根即 skill 目录」的现状，完全向后兼容。

## 平台侧目录布局（推荐）

给镜像仓一个**独立目录**（如 `<FLEETENT_HOME>/skill-source`），池目录指到它的 skill 子目录；开不开 GitOps 都读同一个池路径，开关只决定内容归谁管：

```
<FLEETENT_HOME>/
├── skill-source/          ← git 仓根（镜像）。启用 GitOps 后 = 外部仓复印件
│   └── skills/            ← FLEETENT_SKILLS_DIR（池），两种模式路径不变
├── skill-bundles/
├── management.db
└── tenants/...
```

对应配置：`FLEETENT_SKILLS_DIR=<home>/skill-source/skills` + `skills_subdir="skills"`。**不要**把镜像直接铺在 `FLEETENT_HOME` 根（即不要让家目录本身当 git 仓根）：reset --hard 会把外部仓的其它顶层目录全部物化进家目录，与 `management.db`、`tenants/` 混住且有撞名风险。

## 配置（管理库 `skill_git_source` 单行表）

| 字段 | 说明 |
|---|---|
| `provider` | `bitbucket` / `gitea` / `gitlab` |
| `remote_url` / `branch` | git 协议地址 + 权威分支（默认 `main`） |
| `skills_subdir` | 可选。monorepo 场景下 skill 所在的子目录（如 `"skills"`）；留空 = 仓库根即 skill 目录 |
| `username_env` / `token_env` / `webhook_secret_env` | 凭证的 **env 变量名**（值经 `secret_store`/`agent_secrets` 注入，不入库明文、不进 git/yaml/日志） |
| `sync_interval_seconds` | 覆盖默认 `scheduling.skill_git_sync_interval_seconds`（300） |

凭证注入：`secret_store.set(None, <env_name>, <value>)`（shared scope）。

## 启用（一次性 bootstrap）

```bash
python scripts/bootstrap_skill_git.py <remote_url> [branch] --username <U> --password <TOKEN>
```

- 把现有 pool 推到外部**空仓**（远端已有该分支则拒绝，不覆盖权威源）
- 成功后 `set_config(enabled=1)`，入站 sweep 接管

> push auth 经 dulwich `porcelain.push` 的 kwargs 传递，请先对真实 remote 验证；若 transport 需要不同 auth，手动 `git push` 到空仓后改用管理 API 启用。

## 触发同步

- **定时**：platform maintenance scheduler（job `__skill_git_sync_sweep__`，间隔可配）
- **webhook**：`POST /admin/skills/git/webhook`（HMAC-SHA256，`X-Hub-Signature-256`，secret = `webhook_secret_env`；**强制配 secret 否则拒收**；payload 不被信任，仅触发 fetch，内容一律以 fetch 结果为准）
- **手动**：`POST /admin/skills/git/sync`（admin）
- **状态**：`GET /admin/skills/git/status`（凭证脱敏，仅返回 env 名）

## CI 校验（外部仓库）

外部 skill 仓库的 PR CI 跑 `scripts/validate_skills.py`：frontmatter + safe name + 注入审计（复用 `fleetent.skills.audit`，与 platform 入站审计**同一套规则**）。非零退出阻断合并。

`bitbucket-pipelines.yml` 模板片段：

```yaml
pipelines:
  pull-requests:
    '**':
      - step:
          name: validate-skills
          image: python:3.12
          script:
            - pip install pyyaml
            # vendor audit.py next to validate_skills.py, or `pip install fleetent`
            - python validate_skills.py .
```

## 回流（出站：只推备份分支，采纳靠人 PR）

单向原则：**git → 平台**是唯一的权威写入方向，平台**从不**往 git 权威分支写。agent 在自己 home 改了 skill 后：

```
agent 改 skill → node 上报漂移 → 平台记录 pending 回流提案（存进化副本 bundle）
   → backflow_pr_sweep 把副本推成备份分支 backflow/<agent>/<skill>（定时 + 手动 sync-backflow）
   → 人在 git host 对备份分支开 PR 合并到权威分支   ← 平台不代劳
   → 合并后入站同步（fetch + reset）自然把新内容拉回池 → 下发 agent
```

- 平台**只**推备份分支（非权威主分支），**从不**开 / 合并 PR。备份分支名按 `(agent, skill)` 稳定。
- 后台定时 sweep（`__skill_backflow_pr_sweep__`）自动推备份分支；后台 UI 的「Sync backflow」手动触发一轮 sweep（同样只推备份分支）。
- **平台不审核回流**：不提供 accept / reject / fork / open-pr——采纳与否完全是你在 git host 的动作（对备份分支开 PR 合并）。平台侧回流 UI 是**只读**的：看有哪些回流、备份到哪个分支、diff（相对 base / 相对 head，含冲突标记）。
- 为什么去掉审核：「先自动推备份、后人工审」有矛盾——reject 只撤 agent 运行时副本，管不到已推的备份分支，若该分支被合并则改动复活；且与「git 唯一权威、平台只读」冲突。故采纳统一收敛为人在 git host 的 PR。

## 行为变化

- 启用外部源后，后台 UI 的 skill 内容写端点（create / edit / upload / archive / restore / force-publish）返 **409**——改 skill 去 git 提 PR。
- 保留：绑定矩阵、全局启停、版本 / diff 查看、reload、git 同步状态卡片。
- 入站审计兜底：severe 注入的 skill 被 quarantine（不分发）；外部删除的 skill 软删 archived。
- 内置 skill 随安装包；`reset --hard` 后自动 re-materialize（不在外部仓库里）。

## 回滚

- platform 版本钉选（让 agent 部署指定旧 commit），或外部 git `revert` 后等下次同步。
