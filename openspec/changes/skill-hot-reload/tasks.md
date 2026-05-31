## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `scan()` 现状用 `_index.clear()` 就地清空后填充（skill_registry.py 行 31-56），确认运行期重扫不可直接复用（半空窗口 + 失败无回滚）
- [ ] 1.2 核实 `scan()` 的启动/CLI 触发时机（server.py 行 68 lifespan、agent_loop.py 行 408 `run_sync()` 内 `scan_skills()`；`run()` 行 234 不扫描），确认本 change 只增运行期重扫、不改触发时机
- [ ] 1.3 核实各读取函数（`match`/`load`/`list_skills` 等）对 `_index` 的引用方式，确认原子整体替换后读取可见新索引（必要时调整为经当前模块级索引访问）

## 2. 抽出纯构建逻辑（_build_index）

- [ ] 2.1 Write failing tests for `_build_index(skills_dir)`：`tests/test_skill_registry.py` 断言其返回一个新的 `dict[str, SkillEntry]`，内容反映目录中的 Skill，且**不**修改全局 `_index`（调用前后全局索引不变）；并断言其**覆盖 builtin（`BUILTIN_SKILLS_DIR`）+ 用户两源**——返回 dict 同时含 builtin Skill 与用户 `skills/` 下的 Skill（与 `scan` 现有两源覆盖一致）。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `_build_index`：从 `scan` 抽出「遍历+解析+组装」逻辑，对 builtin 与用户目录各扫一遍合并成同一个新 dict，返回该 dict，不触碰全局 `_index`；`scan` 改为调用它再落到全局。看到绿

## 3. reload() 原子整体替换

- [ ] 3.1 Write failing tests：`reload()` 后新增的 Skill 出现在索引、删除的 Skill 从索引消失；替换为整体赋值（断言重扫不经历半空中间态——构建在替换前完成）。skills 目录隔离 `tmp_path`。看到红
- [ ] 3.2 Implement `reload(skills_dir=None)`：调 `_build_index` 得新索引，成功后原子整体替换模块级索引引用。看到绿

## 4. 重扫失败保留旧索引并告警

- [ ] 4.1 Write failing tests：重扫遇不可恢复错误（如目录消失/构建抛错）时，旧索引保持不变（仍能 `match`/`load` 旧 Skill），并产生结构化 warning。看到红
- [ ] 4.2 Implement：`reload()` 在 `_build_index` 失败时不替换索引、记 warning、返回失败摘要。看到绿

## 5. in-flight 任务用旧版 Skill

- [ ] 5.1 Write failing tests：模拟「请求在 `run_sync()`（行 408-415）/ `run_stream()`（行 451-453）早期已取用并注入 Skill 后再 `reload()`」，断言该请求已注入的 system prompt 内容不被重扫改变（用旧版）。mock `get_async_client_and_config`，skills 目录隔离 `tmp_path`。看到红
- [ ] 5.2 Implement / 确认：注入在请求早期一次性取用，原子替换不回改已注入内容。看到绿

## 6. 触发通道（admin CLI / 可选管理 API）

- [ ] 6.1 Write failing tests：`reload-skills` admin 子命令触发 `reload()` 并返回/打印结果摘要（成功/失败）。看到红
- [ ] 6.2 Implement：`admin.py` 新增 `reload-skills` 子命令（沿用 `add_parser` 模式）；如纳入管理 API 则加 Bearer 认证端点触发同一 `reload()`。看到绿

## 7. 收尾

- [ ] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 7.3 `uv run mypy src` 无新增错误
