# Tasks

> TDD hard gate：测试在实现之前，先红后绿（最窄命令 `uv run pytest <file>::<test> -x -q`）。
> 全为 integration（真实池 git + DB + materialize + 文件 IO），放 `tests/integration/`。
> 迁移号 apply 时按 alembic head 现取、不写死。

## 1. schema：agent_skills.base_commit + backflow_proposals bundle 化

- [x] 1.1 写迁移测试（integration）：升级后 `agent_skills` 有 `base_commit`（NULL 默认）；`backflow_proposals` 有 `base_commit` + bundle 内容列；存量 `proposed_content` 迁为 `{"SKILL.md": <旧值>}`——先见红
- [x] 1.2 写 forward 迁移（号现取）：两表加 `base_commit`、内容列转 bundle（relpath→content JSON）、存量转换；写 downgrade——跑 1.1 见绿
- [x] 1.3 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`：仍在 platform、agent→platform 反向依赖为零

## 2. materialize 记录 base_commit

- [x] 2.1 写测试（integration）：未漂移副本物化后 `agent_skills.base_commit` = 池中该 skill 当前 git commit；`base_version` 仍为内容 hash——先见红
- [x] 2.2 写测试（integration）：pool 更新后重新物化不误判 drift（base_version 内容比对路径不受 base_commit 影响）；漂移副本被保护时 base_commit 不变——先见红
- [x] 2.3 实现 materialize：覆盖副本时 `set_base_commit = pool_version_for_skill(skill)`，与现有 base_version 写入并列——跑 2.1–2.2 见绿

## 3. 回流提名：捕获 base_commit + 完整 bundle

- [x] 3.1 写测试（integration）：提名多文件 skill（SKILL.md + scripts/）→ 提案 bundle 含全部文件、记录 base_commit 与 base_version；未漂移拒绝提名——先见红
- [x] 3.2 实现 `backflow_store.create_proposal`：rglob 捕获 home 副本全 bundle（排除 `.git`）+ 快照 base_commit；超大走文件名清单降级 + 告警——跑 3.1 见绿

## 4. diff_vs_base 重建真实 base（修 bug）

- [x] 4.1 写**强断言**回归测试（integration）：base=A、evolved=B（A→B 具体行级改动）→ `diff_vs_base` 含真实 A→B 增量（断言具体变化，不只断言非空）；明确覆盖「内容 hash 不再被当 git ref」——先见红（在旧实现上必红，证明捕获了 bug）
- [x] 4.2 写测试（integration）：`base_commit` 为空 → `diff_vs_base` 优雅降级（标注 base 未知、仅 vs head）、不报错、不把全份误报新增——先见红
- [x] 4.3 写测试（integration）：`diff_vs_head` 与冲突检测仍正确（不回归）——先见红/确认
- [x] 4.4 实现 `get_proposal_diff`：用 `base_commit`（git ref）经 `pool_content_at` 重建真实 base；NULL 降级；多文件 bundle diff（SKILL.md 文本 diff + 其余文件增删改清单）——跑 4.1–4.3 见绿

## 5. accept / fork 写回完整 bundle

- [x] 5.1 写测试（integration）：accept 多文件回流 → 池该 skill 全部文件（含 scripts/）更新为 bundle、被删文件不残留、产生新 commit、current_version 前移、清来源 drift；他 agent 重新物化拿到全 bundle——先见红
- [x] 5.2 写测试（integration）：fork 多文件回流 → 新命名 skill 含完整 bundle、权威 skill 不变、来源绑定指向 fork——先见红
- [x] 5.3 实现 accept/fork：写回完整 bundle（先清目录再原子落盘，沿用 .tmp→rename 范式）+ commit_pool——跑 5.1–5.2 见绿

## 6. 收尾

- [x] 6.1 `make test-pr` 全绿
- [x] 6.2 `uv run pytest tests/integration -q`（不带 `-x`，对照 main 基线）：backflow/materialize/pool/migration integration 无新增失败；确认旧的弱断言测试已被强断言替换/补强
- [x] 6.3 `uv run mypy src` + `uv run ruff check src tests`：改动文件无新增告警
