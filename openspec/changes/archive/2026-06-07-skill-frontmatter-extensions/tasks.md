## 1. SkillEntry 三字段 + 解析

- [x] 1.1 Write failing test（unit）：scan 后 SkillEntry 含 disable_model_invocation / requires_tools / required_env_vars 解析值；未声明取默认
- [x] 1.2 运行确认红
- [x] 1.3 实现：SkillEntry 加三字段（默认 False/[]/[]）；_scan_dir 解析（bool / _as_str_list / list[dict] 过滤非 mapping）
- [x] 1.4 运行确认绿

## 2. disable_model_invocation 隐藏 catalog 但 read_skill 可达

- [x] 2.1 Write failing test（unit）：disable_model_invocation=true 的 skill 不在 available_skills_prompt 输出；但 read_skill 仍返回正文
- [x] 2.2 运行确认红
- [x] 2.3 实现：_disabled_reason 加 "model_invocation_disabled"（audit_blocked 之后）；确认 read_skill 不查此 flag
- [x] 2.4 运行确认绿

## 3. requires_tools 渲染期过滤

- [x] 3.1 Write failing test（unit）：available_skills_prompt(available_tools=...) 时 requires_tools 缺工具则隐藏、齐备则显示、None 不过滤
- [x] 3.2 运行确认红
- [x] 3.3 实现：available_skills_prompt 加 available_tools 参数，eligible 过滤叠加 requires_tools 检查；loop.py 两处传可见工具名集
- [x] 3.4 运行确认绿

## 4. required_env_vars + skill_readiness

- [x] 4.1 Write failing test（unit）：skill_readiness(name) 报告缺失非 optional env；optional/已设置不报
- [x] 4.2 运行确认红
- [x] 4.3 实现：skill_readiness(name) -> {"missing": [...]}
- [x] 4.4 运行确认绿

## 5. 验证与收尾

- [x] 5.1 运行 skill registry + builtin tools 测试
- [x] 5.2 运行全套测试：`uv run pytest -q`
- [x] 5.3 运行 lint + 类型检查：ruff + mypy registry.py loop.py
- [x] 5.4 运行测试层级检查
