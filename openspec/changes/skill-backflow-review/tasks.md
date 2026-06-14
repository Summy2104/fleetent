# Tasks

> 依赖第 2 期 `skill-pool-git-versioning` 已落地并 sync。**apply 前先 `opsx:validate` 复核本 change 对 git-pool 能力的 prose 引用与已 sync 的 base 一致。**
> TDD hard gate：测试在实现之前，先红后绿（最窄命令 `uv run pytest <file>::<test> -x -q`）。
> 回流涉及真实池 git + DB + materialize，几乎全为 integration，放 `tests/integration/`。
> 迁移号 apply 时定、不写死。

## 1. 回流提案存储（复用 reflection skill_proposals）

- [ ] 1.1 写测试（integration）：`skill_proposals` 支持 `backflow` kind + 来源 agent / `base_version` 字段；提名漂移副本生成 backflow 提案、未漂移副本拒绝提名——先见红
- [ ] 1.2 评估复用契合度后写轻量 Alembic 迁移（号 apply 时定）加 kind/字段；若不契合改独立表（同样测试先行）——跑 1.1 见绿
- [ ] 1.3 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`：回流流程在 platform、agent→platform 反向依赖仍为零

## 2. 回流 diff（相对 base 与 head）

- [ ] 2.1 写测试（integration）：回流提案返回「进化副本 vs base_version」与「进化副本 vs 池 head」两个 diff（调第 2 期 `pool_diff`/`pool_content_at`）——先见红
- [ ] 2.2 实现回流 diff 读取，复用第 2 期池 git 读能力——跑 2.1 见绿

## 3. 平台治理审批 + 三种决策

- [ ] 3.1 写测试（integration）：回流经 admin 治理鉴权审批并审计；agent-owned DM 路径不处理 backflow 提案——先见红
- [ ] 3.2 写测试（integration）：accept → 进化内容写池 + `commit_pool` 新 commit + `current_version` 前移 + 清来源 drift；他 agent 重新物化拿新版本——先见红
- [ ] 3.3 写测试（integration）：reject → 池不变 + 提案关闭 + 清 drift + 下次物化覆盖该副本——先见红
- [ ] 3.4 写测试（integration）：fork → 新命名 skill 落池提交 + 来源绑定指向 fork + 权威 skill 不变——先见红
- [ ] 3.5 实现 accept/reject/fork 决策端点 + 治理鉴权 + 审计 + 接第 2 期 commit_pool + 清 drift + 触发重新物化——跑 3.1–3.4 见绿

## 4. 冲突显式暴露

- [ ] 4.1 写测试（integration）：`base_version` ≠ 池 head → review 标记冲突态 + 展示相对 head diff、不自动 merge——先见红
- [ ] 4.2 写测试（integration）：冲突态覆盖 head 需显式确认、记录被覆盖 head 版本——先见红
- [ ] 4.3 实现冲突检测（比对提案 base_version 与池 head）+ 确认门 + 覆盖记录——跑 4.1–4.2 见绿

## 5. 命名正名 + 收尾

- [ ] 5.1 `git grep -ni askit` 审计残留 askit 品牌：仅正名「机制被误挂」者；保留合法 askit-facing 命名（`askit_console` agent apply API）——逐项记录去留理由
- [ ] 5.2 `make test-pr` 全绿
- [ ] 5.3 `uv run pytest tests/integration -q`（不带 `-x`，对照 main 基线）：本 change 涉及的 backflow/pool/materialize integration 无新增失败
- [ ] 5.4 `uv run mypy src` + `uv run ruff check src tests`：改动文件无新增告警
