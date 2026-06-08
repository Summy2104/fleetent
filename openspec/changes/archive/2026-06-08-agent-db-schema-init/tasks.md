## 1. traces.py — ensure_schema

- [x] 1.1 Write failing tests for `traces.ensure_schema()`: creates traces table + 4 indices; idempotent on second call
- [x] 1.2 Implement `ensure_schema(db: SQLiteDatabase) -> None` in `traces.py`

## 2. memory/store.py — ensure_schema

- [x] 2.1 Write failing tests for `memory.store.ensure_schema()`: creates memory_items table + 2 indices; idempotent
- [x] 2.2 Implement `ensure_schema(db: SQLiteDatabase) -> None` in `memory/store.py`

## 3. reflection.py — ensure_schema

- [x] 3.1 Write failing tests for `reflection.ensure_schema()`: creates reflection_reports table + 1 index; idempotent
- [x] 3.2 Implement `ensure_schema(db: SQLiteDatabase) -> None` in `reflection.py`

## 4. knowledge_base/operations.py — ensure_schema

- [x] 4.1 Write failing tests for `kb.operations.ensure_schema()`: creates all 4 KB tables (knowledge_bases, knowledge_documents, knowledge_chunks, knowledge_source_states) + FTS5 virtual table + indices; idempotent
- [x] 4.2 Implement `ensure_schema(db: SQLiteDatabase) -> None` in `knowledge_base/operations.py`

## 5. agent_app — _init_agent_db_schema + _start_infra wiring

- [x] 5.1 Write failing tests for `_init_agent_db_schema()`: calls all 4 store ensure_schema functions; tables exist in DB after call
- [x] 5.2 Implement `_init_agent_db_schema(database_url: str) -> None` in `agent_app.py`; call as first line of `_start_infra()`

## 6. Full test suite green

- [x] 6.1 Run `uv run pytest -x -q` and fix any regressions
