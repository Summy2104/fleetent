# tasks

## 1. OpenSpec proposal

- [ ] 1.1 创建 proposal、design、tasks 和 reflection spec delta
- [ ] 1.2 运行 `openspec validate 2026-06-02-skill-reflection-proposals --strict`

## 2. Models and persistence

- [ ] 2.1 Write failing tests：public API 可导入 `SkillProposal`、`generate_skill_proposals`、approve/reject/apply APIs
- [ ] 2.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 2.3 Implement：新增 models、status/type constants 和 public exports
- [ ] 2.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 2.5 Write failing tests：Alembic upgrade 后存在 `skill_proposals`，payload 不保存完整 transcript
- [ ] 2.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [ ] 2.7 Implement：新增 migration 和 proposal store
- [ ] 2.8 Verify green：运行 `uv run pytest tests/integration -x -q`

## 3. Proposal generation rules

- [ ] 3.1 Write failing tests：重复任务 / skill_opportunity finding 生成 `create_skill` proposal
- [ ] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.3 Implement：实现 create proposal rule
- [ ] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.5 Write failing tests：高触发但失败的现有 skill 生成 `update_skill` proposal
- [ ] 3.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.7 Implement：实现 update proposal rule
- [ ] 3.8 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.9 Write failing tests：长期未使用或重复 skill 生成 `deprecate_skill` proposal
- [ ] 3.10 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.11 Implement：实现 deprecate proposal rule
- [ ] 3.12 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.13 Write failing tests：普通单次任务不生成 proposal
- [ ] 3.14 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.15 Implement：补 noise guard
- [ ] 3.16 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. Review lifecycle and apply boundary

- [ ] 4.1 Write failing tests：pending proposal 可以 approve/reject，rejected 不可 apply
- [ ] 4.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 4.3 Implement：实现 approve / reject
- [ ] 4.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 4.5 Write failing tests：只有 approved proposal 可以 apply，apply 通过 skill public boundary，不直接任意写文件
- [ ] 4.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [ ] 4.7 Implement：实现 apply adapter 和 guard
- [ ] 4.8 Verify green：运行 `uv run pytest tests/integration -x -q`
- [ ] 4.9 Write failing tests：apply 后 proposal 状态变为 applied，并记录 actor/timestamp
- [ ] 4.10 Verify red：运行 `uv run pytest tests/integration -x -q`
- [ ] 4.11 Implement：补 apply state update
- [ ] 4.12 Verify green：运行 `uv run pytest tests/integration -x -q`

## 5. Draft generation and evaluation

- [ ] 5.1 Write failing tests：deterministic draft/diff skeleton 包含 reason、evidence、target name 且通过 schema validation
- [ ] 5.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 5.3 Implement：实现 deterministic generator
- [ ] 5.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 5.5 Write failing tests：真实 LLM draft generation 未设置 env 时 skip
- [ ] 5.6 Verify red：运行相关 evaluation / smoke test
- [ ] 5.7 Implement：新增 opt-in guard
- [ ] 5.8 Verify green：运行相关 evaluation / smoke test
- [ ] 5.9 Write failing tests：evaluation 覆盖 create/update/deprecate、noise guard 和 persisted redaction
- [ ] 5.10 Verify red：运行 `uv run pytest tests/evaluation -x -q`
- [ ] 5.11 Implement：新增 evaluation fixture / runner
- [ ] 5.12 Verify green：运行 `uv run pytest tests/evaluation -x -q`

## 6. Documentation and verification

- [ ] 6.1 Write failing tests：capability docs / roadmap 说明 skill proposal 只生成 pending，不自动改 skill
- [ ] 6.2 Verify red：运行相关文档测试
- [ ] 6.3 Implement：更新 `docs/capabilities/reflection.md`、`docs/capabilities/skill.md` 和 roadmap
- [ ] 6.4 Verify green：运行相关文档测试
- [ ] 6.5 运行 `uv run ruff format src tests`
- [ ] 6.6 运行 `uv run ruff check src tests`
- [ ] 6.7 运行 `uv run mypy src`
- [ ] 6.8 运行 `uv run pytest -x -q`
- [ ] 6.9 运行 `openspec validate 2026-06-02-skill-reflection-proposals --strict`
- [ ] 6.10 运行 `git diff --check`
