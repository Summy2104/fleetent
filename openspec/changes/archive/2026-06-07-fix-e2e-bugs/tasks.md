## 1. Bug 1 — allowed_tools 空列表语义修正

- [x] 1.1 Write failing tests for allowed_tools empty list semantics in normalizer and agent_app
- [x] 1.2 Fix normalizer.py: convert empty allowed_tools list to None
- [x] 1.3 Fix agent_app.py /chat route: convert empty allowed_tools list to None

## 2. Bug 3 — skills rglob 不跟随 symlink

- [x] 2.1 Write failing test for skill scan with symlinked skill directory
- [x] 2.2 Fix registry.py: add follow_symlinks=True to rglob call

## 3. Bug 2 — approvals.id 列类型修正

- [x] 3.1 Write failing integration test for approval creation with UUID string id
- [x] 3.2 Add migration 060_fix_approvals_id_to_text.py to change approvals.id from Integer to String

## 4. Bug 4 — standalone agent 缺少 approval 端点

- [x] 4.1 Write failing tests for GET /approvals and POST /approvals/{id}/resolve in agent_app
- [x] 4.2 Add approval endpoints to agent_app.py build_app()
