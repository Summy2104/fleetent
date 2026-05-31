## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 确认依赖 SK2（`skill-yaml-frontmatter`）已合入：`skill_registry` 索引承载结构化元数据、Skill 名（frontmatter `name`）作为白名单匹配键稳定；若 SK2 未就绪则本 change 阻塞
- [x] 1.2 核对工具维度先例：`run()` 的 `allowed_tools` 透传位置（agent_loop 行 141/163-164）与 `agent_policy.check_tool_access` 的 fnmatch 语义（行 4-5），确定 Skill 侧白/黑名单复用同款判定
- [x] 1.3 核对 Skill 注入链三处入口：`run_sync`（行 280-287）、`run_stream`（行 319-321）的 `match→load`，确认过滤层插入点（match 之后、load 之前）
- [x] 1.4 与张亮（governance 域）确认 `agent_store` 的 `allowed_skills` / `blocked_skills` 字段命名与缺省语义（`None` = opt-in 不注入）——跨域协调，结论记入 design 跨域协调点

## 2. Skill 名白/黑名单判定（agent_policy 风格的纯函数）

- [x] 2.1 Write failing tests：白名单判定（fnmatch 命中返回 True、未命中 False、`None` 表示未声明）与黑名单镜像判定（命中即排除、`None`/`[]` 视为无排除）；含连字符的 Skill 名匹配。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：复用 `agent_policy.check_tool_access` 做白名单判定 + 其镜像做黑名单排除（保持单一 fnmatch 实现风格），看到绿

## 3. 注入链过滤层 + run()/run_stream() 参数透传

- [x] 3.1 Write failing tests for `run_stream()` Skill 注入过滤（mock `get_async_client_and_config`，skills 目录隔离到 `tmp_path`）：命中的 Skill 名通过 `allowed_skills` 才注入；被 `blocked_skills` 排除则不注入。看到红
- [x] 3.2 Implement：`run_stream()` 在 `match→load` 间插入白/黑名单过滤；新增 `allowed_skills` / `blocked_skills` 参数（类比 `allowed_tools` 邻位透传）。看到绿
- [x] 3.3 Write failing tests for `run()` 路径（若 `run()` 承载 Skill 注入）/ 注入链共享过滤逻辑：白名单命中注入、黑名单排除不注入，与 `run_stream()` 行为一致。看到红
- [x] 3.4 Implement：`run()` 新增 `allowed_skills` / `blocked_skills` 参数并接入同一过滤层，看到绿

## 4. opt-in 默认 posture（行为变更）

- [x] 4.1 Write failing tests：`allowed_skills is None`（未声明）时注入链不加载、不注入任何 Skill，即便用户输入本可关键词命中；显式声明非 `None` 白名单且命中时正常注入。看到红
- [x] 4.2 Implement：注入链将 `allowed_skills is None` 等价于空白名单（不注入）；显式白名单走过滤注入。看到绿

## 5. run_sync 默认 / 未绑定路径

- [x] 5.1 Write failing tests for `run_sync`：无 agent 绑定（`allowed_skills` 默认 `None`）时 opt-in 不注入任何 Skill（CLI 行为变更）。看到红
- [x] 5.2 Implement：`run_sync` 的 `match→load` 链接入同一过滤层，默认 opt-in 不注入；缓解（默认 agent 声明白名单）按 design 列为 Open Question，本次不实现。看到绿

## 6. 收尾

- [x] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求）通过，无回归；`tests/test_skill_registry.py` / `tests/test_agent_loop.py` 覆盖白/黑名单组合、opt-in 默认不注入、含连字符 Skill 名
- [x] 6.2 我的文件 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 未新增错误模式（行长 100、mypy strict）
- [x] 6.3 加回归守卫：未声明 `allowed_skills` 时无论关键词如何命中均不注入任何 Skill（锁定 opt-in posture，防回退到全局注入）
- [x] 6.4 跨域协调结项核对：`agent_store` 的 `allowed_skills` / `blocked_skills` 字段落库由 governance 域（张亮）协同完成；本 change 过滤层按传入参数工作，不阻塞于字段落库时序
