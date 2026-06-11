## 1. metadata 归一化 helper（string → 类型）

- [ ] 1.1 写 unit 测试（`tests/unit/test_skill_registry.py`）:`_as_bool_meta("true")/"false"/"x"` → `True/False/None`；`_split_ws("a b  c")` → `["a","b","c"]`、空串 → `[]`；env 归一化 `"API_KEY OPT?"` → `[{"name":"API_KEY","optional":False},{"name":"OPT","optional":True}]`（先见红:helper 尚不存在）
- [ ] 1.2 在 `src/fleetent/skills/registry.py` 实现 `_as_bool_meta` / `_split_ws` / metadata env-var 归一化（`name?` 后缀 = optional，产出与现有 `_as_env_var_list` 同形 dict），运行 1.1 命令见绿

## 2. metadata.fleetent-* 作为权威来源解析进 SkillEntry

- [ ] 2.1 写 unit 测试:某 skill 仅在 `metadata` 下声明 `fleetent-requires-tools: "run_code search_docs"`、`fleetent-disable-model-invocation: "true"`、`fleetent-required-env: "API_KEY OPT?"`，扫描后 `SkillEntry.requires_tools == ["run_code","search_docs"]`、`disable_model_invocation is True`、`required_env_vars` 含必需 `API_KEY` 与 optional `OPT`（先见红:`_scan_dir` 还不读 metadata）
- [ ] 2.2 在 `_scan_dir` 把 `SkillEntry` 各扩展字段取值改为"`metadata.fleetent-<key>` 优先 → 旧顶层 `<key>` 回落 → 缺省"，覆盖 `requires_tools`/`required_env_vars`/`enabled_by_default`/`enabled`/`disable_model_invocation`/`tags`/`platforms`/`version`，运行 2.1 见绿

## 3. 标准优先于旧顶层 + 旧顶层兼容回落

- [ ] 3.1 写 unit 测试:① 同时声明旧顶层 `enabled_by_default: true` 与 `metadata.fleetent-enabled-by-default: "false"` → `SkillEntry.enabled_by_default is False`（标准优先）；② 仅旧顶层 `requires_tools`/`enabled_by_default`/`disable_model_invocation`、无 `metadata` → 旧顶层照常生效（兼容不破坏）（先见红）
- [ ] 3.2 调整 `_scan_dir` 取值顺序确保标准位置覆盖旧顶层、旧顶层在无 metadata 时仍生效，运行 3.1 见绿

## 4. compatibility 识别承载 + 未知 metadata 优雅降级

- [ ] 4.1 写 unit 测试:某 skill frontmatter 含顶层 `compatibility`、`metadata` 下含 `openclaw-foo: "bar"`（非 fleetent 前缀）与 `fleetent-unknown: "x"`（未识别）→ 该 skill 正常进索引、无解析失败报警，`compatibility` 被承载、未知 metadata 键被忽略不报错（先见红:compatibility 未承载 / 需断言不报错）
- [ ] 4.2 在 `SkillEntry` 新增可选只读 `compatibility` 字段（带缺省，不破坏现有构造），`_scan_dir` 解析顶层 `compatibility` 填入；确认非 `fleetent-` 前缀与未识别 `fleetent-*` 键被忽略且不触发 parse 失败，运行 4.1 见绿

## 5. 缺省值回归（既无旧顶层亦无 metadata）

- [ ] 5.1 写 unit 测试:仅声明 `name`+`description` 的 skill，扩展字段全取缺省（`requires_tools=[]`、`required_env_vars=[]`、`disable_model_invocation=False`、`enabled_by_default=True`、`tags=[]`、`platforms=[]`、`version=None`），且 `match`/`load` 行为与现状一致（先见红或确认覆盖目标行为）
- [ ] 5.2 确认 `_scan_dir` 缺省分支覆盖该用例（若 2/3 改动已使其通过，补齐断言确保锁定缺省契约），运行 5.1 见绿

## 6. 内置 skill 存量迁移到标准 metadata.fleetent-*

- [ ] 6.1 写 unit 测试:扫描内置目录（`monkeypatch` `BUILTIN_SKILLS_DIR` 指向 `src/fleetent/builtin_skills`），`getting-started` 的 `SkillEntry.tags`/`version`/`enabled_by_default` 与迁移前等价（`tags` 含 `intro/onboarding/help`、`version=="1.0"`、`enabled_by_default is True`）（先见红:迁移前内置仍是旧顶层，测试按标准形态断言来源——或先写迁移再断言等价）
- [ ] 6.2 把 `src/fleetent/builtin_skills/getting-started/SKILL.md` frontmatter 的 `tags`/`version`/`enabled_by_default` 迁移为 `metadata.fleetent-tags: "intro onboarding help"` / `fleetent-version: "1.0"` / `fleetent-enabled-by-default: "true"`，运行 6.1 见绿（解析结果等价）

## 7. 边界与收尾

- [ ] 7.1 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新增跨包 internal import；`skills` 未 `import fleetent.platform.*`
- [ ] 7.2 冒烟:agent 在无 platform、platform 表不存在环境下 `uv run fleetent agent run`（或等价 CLI 单轮）仍可完成一轮对话且 skill catalog 正常渲染
- [ ] 7.3 `uv run ruff format src tests` + `uv run ruff check src tests` 改动文件、`uv run mypy src` 通过
- [ ] 7.4 `make test-pr` 全绿（对照 main 基线无新增失败）
- [ ] 7.5 `openspec validate skill-frontmatter-agentskills-compliance --strict` 通过
