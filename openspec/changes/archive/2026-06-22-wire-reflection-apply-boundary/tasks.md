## 1. 接通 skill apply 边界（D1，TDD）

- [x] 1.1 写测试（先红）：在 `tests/unit/test_reflection_gate.py`（或相邻 gate 单测）加用例——构造 `_state_db` **未接**的 fallback 场景，approve→apply 一个 create/update skill 提案，断言**不再抛** `"boundary is not configured"`，且 apply 边界调用到真实现（patch/spy `reflection.reflection.apply_skill_proposal_to_boundary` 验证被调用，或断言 write_skill 被触发）。最窄命令跑出红。
- [x] 1.2 改实现（绿）：`governance/reflection_gate.py` 的本地 `apply_skill_proposal_to_boundary` 删掉 `raise RuntimeError(...)`，改为 `await reflection_api.apply_skill_proposal_to_boundary(proposal)`。重跑 1.1 见绿。
- [x] 1.3 回归：跑 `tests/unit/test_reflection_gate.py` + `tests/unit/test_reflection_gate_additional.py` 全绿（确认真 API 路径未被破坏）。

## 2. dataclass 改名为 MemoryProposal（D2，TDD）

- [x] 2.1 写/改测试（先红）：把测试里对旧 memory proposal dataclass 的引用改为 `MemoryProposal`，先跑相关单测见红（import 失败/未定义即红）。涉及 `tests/unit/test_reflection_engine_contract.py`、`tests/unit/test_reflection_proposals_unit.py`、`tests/unit/test_reflection_gate.py`、`tests/unit/test_coverage_reflection_logic.py`、`tests/unit/test_reflection_gate_additional.py`、`tests/integration/test_memory_reflection_maintenance_unit_migrated.py`。
- [x] 2.2 改实现（绿）：在 `reflection/reflection.py` 重命名 dataclass 定义为 `MemoryProposal`，全量替换 `src/`（`reflection/reflection.py`、`reflection/store.py`、`governance/reflection_gate.py`、`memory/proposal_store.py`）所有引用。**不保留旧名 alias**。重跑 2.1 见绿。
- [x] 2.3 残留自检：`git grep -n "<old memory proposal class name>"` 必须为空（含注释/docstring/字符串）。

## 3. spec 文档对齐（D3）

- [x] 3.1 `opsx:archive` 时同步 `skill-proposal-review` spec：inbox 来源更正为 `reflection_proposals`(domain='skill')，并落地新增的 "Skill proposal application" 需求（delta 已在 change 的 specs/ 下）。

## 4. 收尾门禁

- [x] 4.1 `make test-pr` 通过（对照 main 基线无新增失败）。
- [x] 4.2 跑本 change 相关单测/集成（reflection + gate + memory proposal + `tests/integration/test_memory_reflection_maintenance_unit_migrated.py`），无新增失败。
- [x] 4.3 `uv run python scripts/check_module_boundaries.py` 通过（确认未引入 agent→platform 反向依赖）。
