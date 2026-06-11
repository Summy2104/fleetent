## 1. 统一两表 schema（agent_state.db · Y）

- [ ] 1.1 写测试（integration）：统一 MIGRATIONS 打开新 `agent_state.db` 后含 `reflection_reports`(带 `domain`/`signal_summary_json`)与 `reflection_proposals`(完整生命周期列)，且不含 `memory_maintenance_proposals`/`skill_proposals` —— 见红
- [ ] 1.2 在 `runtime/agent_state_migrations.py`(版本取当前 max+1)：给 `reflection_reports` 加 `domain`/`signal_summary_json`、新建 `reflection_proposals`、drop `memory_maintenance_proposals`/`skill_proposals` —— 见绿
- [ ] 1.3 新增 alembic 迁移 forward-drop `kb_reflection_reports`（027 孤儿），downgrade 重建 —— 见红→见绿

## 2. 统一 proposal store + 生命周期（memory/skill 两域 · 按域分派）

- [ ] 2.1 写测试（integration）：统一 store 的 create/list/approve/reject 对 memory/skill 两域行为一致；`list` 一次返回跨域 pending、可按 domain 筛 —— 见红
- [ ] 2.2 实现统一 `reflection_proposals` store + 生命周期（status 转移 + reviewer/applied 审计），域特定载荷 `payload_json` 经 dataclass ser/de —— 见绿
- [ ] 2.3 写测试 + 实现：apply 按 `domain` 分派 `_APPLY_HANDLERS`（memory→memory mutation API；skill→见组 4），跨域隔离（一域 handler 不认他域 kind） —— 见红→见绿
- [ ] 2.4 写测试 + 实现：提案进入 pending 时，经 **agent-owned** `agent_config.resolve_approvers` 解析配置审批人（memory→owner；skill→team/tenant 负责人；**非 requester**）+ `permission_gate._notify_approvers` 外呼 DM；找不到审批人 → default-closed（保持 pending、不 auto-apply）；全 agent 侧、不调 platform console —— 见红→见绿

## 3. report 统一（三域，含 KB）+ memory/skill 提案迁到统一表

- [ ] 3.1 写测试（integration）：`run_reflection`/`run_kb_reflection_report` 都写统一 `reflection_reports`（带正确 domain，KB→`domain=knowledge_base`），KB report 不再落 `kb_reflection_reports`（修 #4）；KB 仍只产 report、不产提案 —— 见红
- [ ] 3.2 reflection.py：report 写入带 domain；`_save_kb_reflection_report` 改写统一表（KB 保持只读，不进 proposal） —— 见绿
- [ ] 3.3 memory/skill 提案改写统一 `reflection_proposals`（保留 `generate_memory_*`/`generate_skill_*`、`approve_*`/`reject_*`/`apply_*` 作 domain wrapper，行为不变）；命名对齐(risk/evidence_json/kind) —— 见红→见绿

## 4. Skill 自进化 apply（全 bundle · agent-local · 接通历史 stub）

- [ ] 4.1 在 `skills/` 模块加公共边界 `write_skill(name, files, provenance)`：原子写整棵文件树到 `<agent home>/skills/<name>/`（临时目录 + SKILL.md 注入扫描 → rename 换入），写 frontmatter（source/proposal_id/applied_at），`registry.reload()` 热更新 —— 见红→见绿
- [ ] 4.2 写测试（integration）：approved `create_skill` 提案 apply → 整个 bundle（SKILL.md + 脚本）写入该 agent 自己的 skills 目录、立即可用、不触及其它 agent；SKILL.md 命中 severe 注入 → 拒绝 apply —— 见红
- [ ] 4.3 实现 skill apply handler：调 `write_skill`；`update_skill` 全树覆盖；`deprecate_skill` 置 frontmatter `enabled: false`（软禁用、模型不再发现）—— 见绿
- [ ] 4.4 写测试：deprecate 后该 skill 从 catalog 排除、`match`/auto-inject 不再选中它（模型不误用） —— 见红→见绿

## 5. 文档与收尾

- [ ] 5.1 同步 `docs/architecture/data-model.md` §3.3：reflection 域收口为 `reflection_reports`（三域观察）+ `reflection_proposals`（两域 memory/skill）；移除 §3.5 中 `kb_reflection_reports` 的相关注记
- [ ] 5.2 同步 `docs/capabilities/reflection.md`：2 表内核（report 三域 / proposal 两域）、skill apply 写 agent-local bundle（含脚本，三层安全）、审批走 agent-owned 外呼（非 console）、KB 仅产 report（mutation/remediation 在平台/摄取面，独立 change）
- [ ] 5.3 grep 自查：仓内无残留"skill/KB → platform console 审批"描述（已由 self-evolution-split delta 对齐）；platform console 仅作只读投影
- [ ] 5.4 验证基线：无 platform、管理库表不存在下 `fleetent agent run` 正常；report 三域 / proposal 两域 落 agent 自己的 `agent_state.db`，skill 自写自用
- [ ] 5.5 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
