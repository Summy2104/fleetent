## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `skill_registry.available_skills_prompt`（行 319）的 entries 构建点（行 333-337，`if _disabled_reason(...) is None`）与 `_disabled_reason` 谓词（行 281），确认收窄应作为该过滤点的额外 AND 条件叠加、不改谓词内部
- [x] 1.2 核实 `available_skills_prompt` 的三处调用点（`agent_loop.py:1179` run_sync、`agent_loop.py:1235` run_stream、`im_gateway/normalizer.py:141`）与 `run()` / `run_stream()` 透传现状（参照 `agent_features` / `sandbox_mode`），确认 catalog 在 run_stream 内构建、在 normalizer 调 run() 前构建、CLI 无 agent 绑定
- [x] 1.3 核实 `agent_store.Agent` 字段与 `agents` 表 DDL、`plugins` 经 alembic 003 + `_init_db` 内联的加列方式（agent_store.py:14-86、171-188；migrations/versions/003），据此定 `allowed_skills` 照同款加列（alembic 004 + 内联，非裸 ALTER）
- [x] 1.4 核实最新迁移为 003、`tests/test_migrations.py` 的断言结构，确认 004 的 `down_revision="003"` 与列断言点

## 2. skill_registry 收窄（available_skills_prompt）

- [x] 2.1 Write failing tests in `tests/test_skill_registry.py`：`available_skills_prompt(allowed_skills=None)` 与 `allowed_skills=[]` → 全部已启用技能可见（=现状）；`allowed_skills=["weather"]` → 清单只含 `weather`、不含其它已启用技能；被禁用的技能即便在 `allowed_skills` 中也不出现（与 `_disabled_reason` 叠加，禁用优先）。技能 index 用 monkeypatch / 隔离造。运行 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 看到红
- [x] 2.2 Implement `available_skills_prompt` 加 `allowed_skills: list[str] | None = None` 参数，在 entries 过滤点叠加收窄（`allowed_skills` 非空时额外要求 `name in set(allowed_skills)`），更新 docstring，看到绿

## 3. agent_store 字段与迁移（allowed_skills）

- [x] 3.1 Write failing tests in `tests/test_agent_store.py`：`create_agent(..., allowed_skills=["weather"])` 后读回 `allowed_skills == ["weather"]`；不传时默认 `[]`；旧库（无 allowed_skills 列）读取兜底 `[]` 向后兼容。`monkeypatch agent_store.DB_PATH` 隔离 `tmp_path`。看到红
- [x] 3.2 Implement `Agent` 加 `allowed_skills: list[str] = field(default_factory=list)`（docstring 标注：空 = 不限制，与 plugins 相反）；`agents` 表 `CREATE TABLE` 内联加 `allowed_skills TEXT NOT NULL DEFAULT '[]'`；`create_agent` 加入参、`_SELECT_COLS` 追加列、`_row_to_agent` 用 `json.loads(row[6] or "[]")` 兜底。看到绿
- [x] 3.3 Write failing test in `tests/test_migrations.py`：alembic 升到 head 后 `agents` 表含 `allowed_skills` 列。看到红
- [x] 3.4 Implement `migrations/versions/004_add_agent_allowed_skills.py`（`op.add_column("agents", sa.Column("allowed_skills", sa.Text(), nullable=False, server_default="[]"))`，`down_revision="003"`，downgrade `op.drop_column`），看到绿

## 4. run / run_stream 透传 + 调用方接线

- [x] 4.1 Write failing tests：`run_stream(..., allowed_skills=["weather"])` 时渲染的 system prompt 清单只含 `weather`（patch `available_skills_prompt` 或断言其入参 / 输出）；`allowed_skills=None` 时不收窄。LLM mock、技能 index 隔离。看到红
- [x] 4.2 Implement `run()` / `run_stream()` 加 `allowed_skills: list[str] | None = None` 入参；`run_stream` 内 catalog 构建处 `available_skills_prompt(allowed_skills=allowed_skills)`；`run()` 入参 docstring 标注「catalog 由调用方预组装，现状不重复过滤，API 对称 / 预留」。看到绿
- [x] 4.3 Write failing tests for 调用方接线：server.py 从 `agent.allowed_skills`（无 agent → None）经 kwargs 传 `run_stream`；normalizer 在构建 catalog 时传 `agent.allowed_skills if agent else None` 给 `available_skills_prompt`。看到红
- [x] 4.4 Implement server.py（`run_stream` kwargs 加 `allowed_skills`）与 `im_gateway/normalizer.py`（catalog 构建传 `allowed_skills`）接线，看到绿

## 5. 收尾

- [x] 5.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`，无回归（基线 1400 + 新增）
- [x] 5.2 改/建文件 `uv run ruff format` + `uv run ruff check` 全绿
- [x] 5.3 `uv run mypy src` 无新增错误模式（基线 79）
- [x] 5.4 `docs/capabilities/wave2-apply-decisions.md` 末尾追加 `## [follow-up] agent-skill-scoping` 决策记录
