## 1. 创建即落盘（platform/skill_admin_api）

- [x] 1.1 写测试（integration，真实文件系统 + tmp skills dir）：`POST /admin/skills` 带 `content` 后，`<skills_dir>/<name>/SKILL.md` 内容等于原文，且 `GET /admin/skills/{name}/content` 返回原文、`registry.list_skills()` 能 scan 到该 skill；先见红
- [x] 1.2 写测试（integration）：把该 skill 绑定到某 agent 后，`materialize.skill_bundles_for_agent(agent)` 返回的 bundle 含该 skill 且 files 含 `SKILL.md`（base64 解码等于原文）；先见红
- [x] 1.3 写测试（integration）：verdict 为 `rejected`（quarantine）时 MUST NOT 落盘——`<skills_dir>/<name>/` 不存在；先见红
- [x] 1.4 写测试（integration）：不安全 skill 名（含 `..` / 路径分隔符）返回 422 且不落盘；先见红
- [x] 1.5 实现：`create_skill` 在 `_safe_skill_name` 校验通过、审计非 `rejected` 时，把 `content` 落盘为 `<engine_skills_dir()>/<name>/SKILL.md`（`mkdir` + `write_text`），再走既有 `_publish`/`engine_reload`；令 1.1–1.4 见绿

## 2. 收尾验证

- [x] 2.1 单层收尾：`uv run pytest tests/integration/test_skill_admin_api.py -q` 无新增失败
- [x] 2.2 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败
