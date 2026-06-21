## 1. read_skill 支持 file_path（registry + 工具）

- [ ] 1.1 写测试（unit, tmp_path）：`registry.read_skill_file(name, rel_path)` 正常读支撑文件、读不存在文件返回错误、路径遍历（`../`）被拒、audit_blocked skill 被拒 —— 运行最窄命令见红
- [ ] 1.2 实现 `registry.read_skill_file`：定位 `skill_dir = Path(_index[name].path).parent`，`resolve()` + 包含断言做遍历防护，越界/不存在返回错误文本，audit_blocked 拒绝 —— 见绿
- [ ] 1.3 写测试（unit）：`read_skill(name, file_path=...)` 工具——带 file_path 走支撑文件路径、省略时字节级同旧、命中后写 `skill_hit` trace —— 见红
- [ ] 1.4 实现：在 `tools/builtin_tools.py` 的 `read_skill` 增加可选 `file_path` 参数，省略时走原逻辑，给出时委托 `read_skill_file` 并复用 trace —— 见绿

## 2. list_skills 按需查询工具（registry + 工具）

- [ ] 2.1 写测试（unit）：`registry.query_skills(keyword, category)` —— keyword 大小写无关命中 name/description/tags、category 按 tags 过滤、无参返回全部、排除 audit_blocked/author-disabled、只含 name+description —— 见红
- [ ] 2.2 实现 `registry.query_skills`：在现有 `list_skills()` 基础上加过滤与资格排除 —— 见绿
- [ ] 2.3 写测试（unit）：`list_skills` 工具包装 query_skills，参数透传、返回结构正确 —— 见红
- [ ] 2.4 实现：在 `tools/builtin_tools.py` 注册 `@tool list_skills(keyword=None, category=None)` —— 见绿

## 3. 配置门控 skill_authoring_enabled（默认关 + schema-build 过滤）

- [ ] 3.1 写测试（unit）：`AgentFile` 默认 `skill_authoring_enabled=False`，可被 agent.yaml 设 true —— 见红
- [ ] 3.2 实现：在 `agent_config.py` 的 `AgentFile` 增 `skill_authoring_enabled: bool = False` —— 见绿
- [ ] 3.3 写测试（unit）：schema 组装时，authoring 关闭的 agent 工具集**不含** `skill_manage`、开启的**含** —— 见红
- [ ] 3.4 实现：在 `runtime/loop.py` schema 组装处（`get_schemas()`/`is_tool_visible` 旁）追加 `skill_manage` 仅当该 agent `skill_authoring_enabled` 为真才保留的过滤 —— 见绿

## 4. skill_manage registry 支撑函数（写/改/删 + 审计 + provenance）

- [ ] 4.1 写测试（unit, tmp_path）：`registry.delete_skill(name)` 删除目录并 reload、删 builtin 项被拒、删不存在返回错误 —— 见红
- [ ] 4.2 实现 `registry.delete_skill`（builtin 只读校验 + 热重载）—— 见绿
- [ ] 4.3 写测试（unit）：`registry.write_skill_file` / `remove_skill_file`（支撑文件增删）——路径遍历被拒、builtin 只读、热重载 —— 见红
- [ ] 4.4 实现 `registry.write_skill_file` / `remove_skill_file`（目录约束 + builtin 校验 + reload）—— 见绿
- [ ] 4.5 写测试（unit）：`registry.patch_skill`（old→new 定向替换），patch 后对最终 SKILL.md 全文重跑注入审计、severe 命中拒绝持久化、回滚保持原状 —— 见红
- [ ] 4.6 实现 `registry.patch_skill`（复用 `_validate_skill_bundle` 写入期审计 + tmp→rename 失败清理 + reload）—— 见绿
- [ ] 4.7 写测试（unit）：create 路径注入 provenance 来源标记 + 传入时间戳（registry 不读系统时钟）、severe content 拒绝写入 —— 见红
- [ ] 4.8 实现：create 复用/扩展 `write_skill` + provenance 注入（`metadata.fleetent.origin=agent_tool` + 传入时间戳）—— 见绿

## 5. skill_manage 工具（动态风险审批 + 多 action 编排 + trace）

- [ ] 5.1 写测试（unit）：`skill_manage` 风险定级为强制审批档（≥medium），经 `approval_policy.risk_for` 裁定（动态 risk callable）—— 见红
- [ ] 5.2 实现：`@tool(risk_level=<callable 返回 medium+>)` 注册 `skill_manage`，所有写 action 触发审批 —— 见绿
- [ ] 5.3 写测试（unit）：六个 action 分派——create/edit/patch/delete/write_file/remove_file 各自委托对应 registry 函数；对不存在 skill（除 create）与 create 已存在返回错误文本；builtin 只读被拒 —— 见红
- [ ] 5.4 实现：`skill_manage(action, name, ...)` action 分派与参数校验，写 per-agent 根（经 tool_context/effective_skill_root）—— 见绿
- [ ] 5.5 写测试（unit）：成功写操作记录一条 agent 侧 observability trace（如 `skill_authored`），不写 platform —— 见红
- [ ] 5.6 实现：写成功后记录 agent 侧 trace（best-effort，不阻塞返回）—— 见绿

## 6. 接线、隔离校验与收尾

- [ ] 6.1 确认三个工具经 `tools/builtin_tools.py` import 副作用注册（`get_schemas()` 可见）；补/跑 `test_builtin_tools_skill.py` 相关断言
- [ ] 6.2 写/跑集成测试（integration）：authoring 开启的 agent 经审批 create→reload→`read_skill` 可读回的端到端写回路（真实文件 + tmp_path 隔离）
- [ ] 6.3 跑模块边界护栏 `scripts/check_module_boundaries.py` + `test_module_dependency_guardrails.py`：确认 `skills/`、`tools/` 无新增 `import fleetent.platform.*`
- [ ] 6.4 收尾门禁：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）+ `uv run ruff check src tests` 改动文件干净
