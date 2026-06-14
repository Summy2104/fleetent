# Tasks

> TDD hard gate：每个实现任务前的测试任务必须先写、先见红，再实现见绿。迁移号 apply 时再定，不写死。
> 受影响层多为 integration（真实 SQLite / Alembic / materialize 文件 IO），按测试分层放 `tests/integration/`。

## 1. 数据迁移：新建 `skills` 主表 + 扩展 `agent_skills` + 删 `skill_provenance`

- [x] 1.1 写迁移测试（integration）：升级后 `skills` 表存在且含全部规定列；`agent_skills` 新增 `base_version`/`drift`(default 0)/`drift_at`；`skill_provenance` 表已删除——先见红
- [x] 1.2 写迁移测试（integration）：backfill 对账——`skills` 行集 == 迁移前 `skill_admin_state` ∪ `skill_provenance` 的 skill 名集合；`source`/`immutable_fields` 按 skill_name 正确并入；缺 provenance 行的 skill `source` 默认 `adhoc`——先见红
- [x] 1.3 写迁移测试（integration）：`agent_skills.drift` 一律初始化为 0、`last_deploy_at` 不复存在；FK→`agents.id` CASCADE 保留——先见红
- [x] 1.4 编写 Alembic forward 迁移（号 apply 时定）：建 `skills`、从 `skill_admin_state`+`skill_provenance` backfill、`agent_skills` 加列、最后 drop `skill_provenance`——跑 1.1–1.3 见绿
- [x] 1.5 评估存量 `agent_skills.skill_name` 脏值后决定是否启用 `FK→skills.name`；写对应迁移测试并实现——红/绿
- [x] 1.6 编写反向（downgrade）迁移并测试：重建 `skill_provenance`、回填 `source`/`immutable_fields`、摘除 `agent_skills` 新列——红/绿

## 2. store 层：读写切到新结构

- [x] 2.1 写 store 测试（integration）：`get_state`/`set_*` 治理读写命中 `skills` 表；缺行返回 active/global_enabled 默认——先见红
- [x] 2.2 写 store 测试（integration）：`source`/`immutable_fields` 经 `skills` 读写；scan/seed upsert 为池内 skill 补齐 catalog 行——先见红
- [x] 2.3 写 store 测试（integration）：per-agent drift 读写——`set_drift(agent_id, skill_name)` / `get_drift` 命中 `agent_skills`；A 漂移不影响 B——先见红
- [x] 2.4 实现 store 改造：治理/`source`/`immutable_fields` 读写改 `skills`；新增 per-agent drift 读写 + `base_version` 读写；删除 `set_provenance`/`get_provenance`/`mark_drift`/`clear_drift`/`_set_drift`/`is_immutable_change`（包内私有，无 shim）——跑 2.1–2.3 见绿
- [x] 2.5 跑模块边界检查 `scripts/check_module_boundaries.py`：确认无新增跨包 internal import、agent→platform 反向依赖仍为零

## 3. materialize：drift 感知部署保护 + base_version

- [x] 3.1 写 materialize 测试（integration）：`(agent, skill) drift=1` 时该 skill 子目录不被覆盖、进化内容保留、写审计日志——先见红
- [x] 3.2 写 materialize 测试（integration）：`drift=0` 子目录正常覆盖刷新并更新 `base_version`=当前 `current_version`——先见红
- [x] 3.3 写 materialize 测试（integration）：同 agent 下漂移 skill 被保护、未漂移 skill 被刷新，子目录粒度互不连带——先见红
- [x] 3.4 写 materialize 测试（integration）：平台读 agent home 产物判定 drift（frontmatter 痕迹或内容哈希），全程不写 agent 侧、agent 运行时未写平台表——先见红
- [x] 3.5 实现 `_copy_skills` 改造：整目录 copytree → 按 skill 子目录逐个判定（drift 跳过 + 审计，否则覆盖 + 写 base_version）；接入平台侧 drift 判定读取路径——跑 3.1–3.4 见绿

## 4. API：list 响应形变 + 移除 inert 调和端点

- [x] 4.1 写 API 测试（integration）：`GET /admin/skills` 每项含 `source`（读 `skills`）与 per-agent drift 聚合（drifted agents）；不再有 per-skill drift 单标志——先见红
- [x] 4.2 写 API 测试（integration）：`POST /admin/skills/{name}/provenance/{promote,discard}` 已移除（404/不存在）；`askit_override` 不再可调用——先见红
- [x] 4.3 写 API 测试（integration）：`create_skill`/import 的 `source` 写入 `skills.source`；`_publish` 不再带未用的 `source` 形参；`edit_skill` 不再返回 `immutable_warning`/per-skill `drift`——先见红
- [x] 4.4 实现 `skill_admin_api` 改造：删 `askit_override` + promote/discard 两端点；`list_skills` 改读 `skills.source` + per-agent drift 聚合；`create_skill`/`_import_skill_dir`/`_publish`/`edit_skill` 的 source/drift 管线调整——跑 4.1–4.3 见绿

## 5. 前端清理（若存在）+ 收尾

- [x] 5.1 admin console 前端若有 provenance promote/discard 按钮与 per-skill drift badge，随端点移除清理；drift 展示改为 per-agent（无前端代码则跳过并记录）
- [x] 5.2 跑 `make test-pr`（unit + 层边界 + 改动文件 ruff）全绿
- [x] 5.3 跑 `uv run pytest tests/integration -q`（不带 `-x`，对照 main 基线）：本 change 涉及的 skill/materialize/migration integration 无新增失败
- [x] 5.4 跑 `uv run mypy src` 与 `uv run ruff check src tests`：改动文件无新增告警
