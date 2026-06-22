## 1. 配置开关 ReflectionSettings.auto_apply（D1，TDD）

- [ ] 1.1 写测试（先红）：`tests/unit/` 中针对 `agent_config` 加载——`reflection.auto_apply.allow_low_risk` 默认 false、
  显式 true 可解析、未知字段被 `extra="forbid"` 拒。最窄命令见红。
- [ ] 1.2 实现（绿）：`agent_config.py` 加 `class ReflectionAutoApplySettings(BaseModel)`（extra=forbid,
  `allow_low_risk: bool=False`），`ReflectionSettings` 增 `auto_apply` 字段（default_factory）。见绿。

## 2. 判定改正向白名单（D3 安全修复，TDD）

- [ ] 2.1 写测试（先红）：在 reflection + gate 两处的 `_auto_apply_allowed` 各加用例——
  `mark_stale`+low+policy.allow → True；`suggest_shared_memory_or_kb`+low → **False**；
  `delete/merge/rewrite/compact` → False；policy=None 或 allow_low_risk=False → False。两处各断言。最窄命令见红。
- [ ] 2.2 实现（绿）：两处 `_auto_apply_allowed`（`reflection/reflection.py`、`governance/reflection_gate.py`）
  一致改为正向白名单 `action in _AUTO_APPLY_ACTIONS`（`{"mark_stale"}`）+ risk=="low" + policy.allow_low_risk。见绿。

## 3. run_reflection 内 auto-apply sweep + 舱壁化（D2/D4，TDD）

- [ ] 3.1 写测试（先红）：`run_reflection(scope, auto_policy=AutoMaintenancePolicy(allow_low_risk=True))`——
  生成的 low-risk mark_stale 提案被自动 apply（状态 applied）；非白名单提案保持 pending；
  `auto_policy=None`（默认）时全部保持 pending（向后兼容）。最窄命令见红。
- [ ] 3.2 写测试（先红）：舱壁化——patch `apply_memory_maintenance_proposal` 对某条抛错，断言 run_reflection 不抛、
  该条留 pending、其余照常、有日志记录。见红。
- [ ] 3.3 实现（绿）：`run_reflection` 增 `auto_policy` kwarg；persist 每条 memory 提案后，若 auto_policy 非 None
  则 `apply_memory_maintenance_proposal(proposal.id, auto_policy=auto_policy)`，逐条 try/except + log，
  不中断循环、不外抛。重跑 3.1/3.2 见绿。

## 4. scheduler + agent_app 接线（D2，TDD）

- [ ] 4.1 写测试（先红）：`start_reflection_scheduler(..., auto_policy=...)` 把 policy 透传到 `_reflection_loop`→
  `run_reflection`（可 patch run_reflection 断言收到的 auto_policy）。见红。
- [ ] 4.2 实现（绿）：`scheduler.py` 的 `start_reflection_scheduler` / `_reflection_loop` 增 `auto_policy` 透传；
  `agent_app` boot 处构造 `AutoMaintenancePolicy(allow_low_risk=reflection_settings.auto_apply.allow_low_risk)`
  并传入。见绿。

## 5. spec 文档对齐（archive 时同步）

- [ ] 5.1 `opsx:archive` 同步 `reflection` spec：MODIFIED "No automatic application"（加 opt-in 例外 + 默认 OFF 场景）
  + ADDED "Opt-in low-risk memory auto-apply"（delta 已在 change specs/ 下）。

## 6. 收尾门禁

- [ ] 6.1 `make test-pr` 通过（对照 main 基线无新增失败）。
- [ ] 6.2 `make test-unit-ci` 通过（CI 覆盖率关 coverage --fail-under=76）。
- [ ] 6.3 跑相关单测（reflection + gate + agent_config + scheduler），无新增失败。
- [ ] 6.4 `uv run python scripts/check_module_boundaries.py` 通过。
