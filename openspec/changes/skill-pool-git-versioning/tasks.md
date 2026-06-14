# Tasks

> TDD hard gate：测试任务在实现任务之前，先见红再见绿（最窄命令 `uv run pytest <file>::<test> -x -q`）。
> 本 change 无 schema 迁移；几乎全为 integration（真实 git 仓 + 文件 IO + 池写），放 `tests/integration/`。
> 实现层用 dulwich（纯 Python git）；新增依赖经 `uv` 加入。

## 1. 池 git 底座模块（init / commit / 串行化）

- [ ] 1.1 写测试（integration）：非 git 池目录经 init → 成为 git 仓 + 当前内容为一个初始 commit；已是 git 仓不重复 init/不产多余 commit——先见红
- [ ] 1.2 写测试（integration）：写路径提交一次可归因 commit（message 含操作 + skill、author=操作者/system）；无变化 seed 不产空 commit——先见红
- [ ] 1.3 写测试（integration）：并发两次写串行化、池仓不损坏、各成一个 commit（跨进程文件锁）——先见红
- [ ] 1.4 实现池 git 模块（如 `skill_management/pool_git.py`）：dulwich init/commit/log/diff/show + 文件锁串行化 + 幂等 init/seed——跑 1.1–1.3 见绿
- [ ] 1.5 加 dulwich 依赖（`uv add dulwich`）并确认 lock 更新

## 2. per-skill 版本 + current_version 填充

- [ ] 2.1 写测试（integration）：某 skill 版本 = 子树最后 commit；改 A 不动 B 的版本标识——先见红
- [ ] 2.2 写测试（integration）：编辑池 skill 后 `skills.current_version` 前移到新 commit；升级初始化时为每个 skill backfill current_version——先见红
- [ ] 2.3 实现：`pool_version_for_skill(name)` + 写路径提交后刷新 `skills.current_version`；升级 init 后 backfill——跑 2.1–2.2 见绿
- [ ] 2.4 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`：池 git 全在 platform、agent→platform 反向依赖仍为零

## 3. base_version 升级为 git 标识 + 存量过渡

- [ ] 3.1 写测试（integration）：materialize 写的 base_version 为 git 标识——先见红
- [ ] 3.2 写测试（integration）：存量 content-hash base 在升级后首次物化、home 未改 → 不误判 drift 且 re-baseline 为 git 标识——先见红
- [ ] 3.3 写测试（integration）：re-baseline 后按 home 内容 vs 池该 git 版本内容判定 drift——先见红
- [ ] 3.4 写测试（integration）：copytree 池→agent home 不带入 `.git`（断言 home 无 `.git`）——先见红
- [ ] 3.5 实现 materialize 改造：base_version 写 git 标识 + D4 过渡/re-baseline + 遍历排除 `.git`——跑 3.1–3.4 见绿

## 4. 只读版本历史 / diff API

- [ ] 4.1 写测试（integration）：`GET /admin/skills/{name}/versions` 返回倒序 commit 列表（标识/时间/author/信息）——先见红
- [ ] 4.2 写测试（integration）：`GET /admin/skills/{name}/versions/{ref}/diff` 返回文本 diff；超大 diff 降级为变更文件名清单 + 告警、不静默截断——先见红
- [ ] 4.3 实现两个只读端点 + 鉴权（与现有 `_current_user`/`_require_admin` 一致；历史对 viewer 只读）——跑 4.1–4.2 见绿

## 5. 收尾

- [ ] 5.1 `make test-pr` 全绿
- [ ] 5.2 `uv run pytest tests/integration -q`（不带 `-x`，对照 main 基线）：本 change 涉及的 pool-git/materialize/skill-api integration 无新增失败
- [ ] 5.3 `uv run mypy src` + `uv run ruff check src tests`：改动文件无新增告警
