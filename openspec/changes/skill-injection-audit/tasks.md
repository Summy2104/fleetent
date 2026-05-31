## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 Skill 注入是「正文原样拼入 system prompt」（`run_sync()` 行 414-415、`run_stream()` 行 453；`run()` 行 234 不注入），确认审计闸门须在「纳入可注入集合」前
- [ ] 1.2 核实 `scan` / 索引构建路径（skill_registry.py 行 31-56）；若 SK4 已抽出 `_build_index`，确认审计应接在该统一构建逻辑内以覆盖重扫
- [ ] 1.3 确认 structlog 审计日志字段（参照 SK2 的 `{path, reason}` 风格），定审计条目字段为 `{path, rule_id, severity, disposition}`

## 2. 审计规则表与数据结构（skill_audit.py）

- [ ] 2.1 Write failing tests for `Severity` / `AuditRule` / `AuditFinding` / `AUDIT_RULES`：`tests/test_skill_audit.py` 断言严重度枚举含 `suspicious`/`severe`；规则表非空且每条规则含 `rule_id`+`pattern`+`severity`。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `Severity`（StrEnum）、`AuditRule`/`AuditFinding`（frozen dataclass）、`AUDIT_RULES`（模块级不可变元组，含代表性注入模式 + 严重度）。看到绿

## 3. audit() 纯函数检测

- [ ] 3.1 Write failing tests for `audit(content)`：含「忽略之前的所有指令」类语句的正文命中 severe；含伪装 system 指令 / shell 注入短语命中对应规则；干净正文返回空命中；返回值为命中清单（含 rule_id+severity）。看到红
- [ ] 3.2 Implement `audit(content) -> list[AuditFinding]`：逐条规则匹配返回全部命中，纯函数无副作用。看到绿

## 4. 接入索引构建：severe 拒绝 / suspicious 记录

- [ ] 4.1 Write failing tests：命中 severe 的 SKILL.md 不进入可注入索引（`match`/注入链不会注入其内容），并记审计日志（disposition=拒绝）；**但 `load()` 按名仍返回该 severe Skill 的原文**（与 SK6 的 `load` 契约对齐，`load` 是审计与禁用共同的安全出口）；命中 suspicious 的 Skill 仍可被匹配注入，但记审计日志 + 启动告警；干净 Skill 不产生审计日志。skills 目录隔离 `tmp_path`，structlog 断言。看到红
- [ ] 4.2 Implement：在索引构建路径对每个正文 `audit()`；severe → 不纳入可注入集合 + 审计日志；suspicious → 纳入 + 审计日志 + 启动告警；无命中 → 正常纳入。看到绿

## 5. 重扫路径覆盖（与 SK4 协同）

- [ ] 5.1 Write failing tests：经重扫（或统一构建逻辑）纳入的 Skill 同样经过审计——重扫引入的 severe Skill 不可注入。看到红
- [ ] 5.2 Implement：确保审计接在统一构建逻辑内（若 SK4 已合入则复用 `_build_index`），扫描与重扫均覆盖。看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误
