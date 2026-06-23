## 1. 平台：desired-state 下发 per-agent skill 文件

- [x] 1.1 写测试（integration）：pool 放两个 skill 目录（`alpha/SKILL.md`+兄弟文件、`beta/SKILL.md`），agent 经 `agent_skills` 绑定 enabled `alpha`；`GET /nodes/{id}/desired-state` 返回该 agent `skills` 仅含 `alpha`，含 `name`/`version`/`files`（`path`+`content_b64`），base64 解码后内容一致；`beta` 不出现。先见红
- [x] 1.2 写测试（integration）：agent 无任何 `agent_skills` 绑定且 authored `allowed_skills` 为空 → `skills` 含 pool 全部 skill（未收窄=全 pool）；先见红
- [x] 1.3 写测试（integration）：某 skill `global_enabled=0` → 即便在 allowed 集内也 SHALL NOT 出现在任何 agent 的 `skills`；先见红
- [x] 1.4 实现 `materialize.skill_bundles_for_agent(agent)`（复用 `_allowed_skills_for`/`_global_disabled_skills`/`has_any_binding`/`_skill_dir_version`/`_resolve_skills_dir`），`node_desired_state_api.get_desired_state` 每 agent 条目加 `"skills": ...`；令 1.1–1.3 见绿
- [x] 1.5 跑受影响层（integration desired-state 文件）确认无新增失败

## 2. node provider：解析 skills 并经 cache 透传

- [x] 2.1 写测试（unit/node）：`_desired_state_from_payload` 把 payload `skills:[{name,version,files:[{path,content_b64}]}]` 解析进 `DesiredAgent.skills`（`DesiredSkill`/`DesiredSkillFile`）；缺 `skills` 键 → 缺省 `[]`（向前兼容）。先见红
- [x] 2.2 写测试（unit/node）：`fetch` 成功写 cache 时**保留** skills（cache 文件含 skills、仍剔 secrets）；cache 回落 `_read_cache` 还原出 skills；`_overlay_last_live_secrets` 透传 skills。先见红
- [x] 2.3 实现：`DesiredAgent` 加 `skills` 字段 + 新 dataclass；`_desired_state_from_payload` 解析；`_overlay_last_live_secrets` 透传 skills；确认 `_strip_secrets_for_cache` 不剔 skills。令 2.1–2.2 见绿

## 3. node reconcile：skill 落盘 + 变更重启 + 移除清理

- [x] 3.1 写测试（unit/node）：冷拉起含 skills 的期望 agent → `<home>/agents/<name>/skills/<skill>/...` 出现且文件内容＝解码后的 `content_b64`；manifest `.node-skills.json` 写出 `{name:version}`；先见红
- [x] 3.2 写测试（unit/node）：在跑 agent，config hash 不变但 skill version 变（manifest≠desired）→ stop+spawn（重启）且 skill 文件被重写；先见红
- [x] 3.3 写测试（unit/node）：在跑 agent，config 与 skills 均不变（manifest=desired）→ 不 stop 不 spawn；先见红
- [x] 3.4 写测试（unit/node）：desired 移除某 skill（manifest 有、desired 无）→ 该 skill 目录被删、manifest 更新；同目录下一个**非 node 管理**的 skill 目录（不在 manifest）保留不删；先见红
- [x] 3.5 写测试（unit/node）：确认 `backend.spawn` env 仍只含 secrets（不含 `FLEETENT_SKILLS_DIR`）——沿用既有 `spawn_calls` 断言口径，新增断言 env 无该键；先见红
- [x] 3.6 实现：`provider.DesiredAgent.skills` 接入；`reconcile._materialize_skills(name, skills)`（逐 skill rmtree+重写、写 manifest、清理 `prev-desired`）；`_write_home` 改收 `DesiredAgent` 并调 `_materialize_skills`；restart 判定加 `or self._skills_changed(name, desired.skills)`；令 3.1–3.5 见绿

## 4. node reconcile：权威态删除整 home + 缓存安全门控

- [x] 4.1 写测试（unit/node）：`source="remote"` 且某本地 agent 不在期望集 → stop 后其 `<home>/agents/<name>` 整目录被删、ledger 该条目被移除；先见红
- [x] 4.2 写测试（unit/node）：`source="cache"` 且某本地在跑 agent 不在期望集 → MUST NOT stop、MUST NOT 删目录（目录与进程保留）；先见红
- [x] 4.3 写测试（unit/node）：disappear 分支 `backend.stop` 抛异常时被舱壁化（记日志、不传播、仍删 home、reconcile 继续 `_post_status`）；先见红
- [x] 4.4 实现：disappear 分支按 `source=="remote"` 门控；`_remove_home(name)`（舱壁化 rmtree）；`hashes.pop(name, None)`；stop try/except+log。令 4.1–4.3 见绿
- [x] 4.5 跑 `tests/unit/node` 全量，确认既有 reconcile/provider 测试无回归

## 5. 收尾与门禁

- [x] 5.1 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过（确认无 node→platform import、无跨包 internal import 违规）
- [x] 5.2 `make test-pr` 全绿
- [x] 5.3 `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
