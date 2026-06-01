## Context

Reflection currently turns trace events and memory signals into three deterministic finding types:
`memory_candidate`, `memory_conflict`, and `skill_opportunity`. Integration tests prove individual
rules, but there is no fixture-driven evaluation set that can grow with report quality requirements.

This design keeps the first evaluation deterministic. It verifies report contents and transcript
redaction from controlled trace/memory fixtures. It does not ask an LLM to judge report usefulness.

## Fixture Format

Each fixture is a JSON document with explicit input and assertions:

- `name`: stable case identifier.
- `scope`: scope passed to `run_reflection(scope)`.
- `trace_events`: fake observability trace events with id, run_id, event_type, payload, user_id, and
  optional agent_id/session_id.
- `memory_signals`: fake memory-layer results with id, type, content, and optional timestamps.
- `expected_findings`: finding assertions containing `type`, optional `summary_contains`,
  optional `evidence_ids`, and optional `metadata`.
- `forbidden_findings`: finding assertions that must not match.
- `forbidden_persisted_text`: raw transcript snippets that must not appear in persisted
  `findings_json`.

The runner fails fast when required fields are missing or finding assertions are malformed.

## Runner

The evaluation runner loads fixtures from `tests/evaluation/fixtures/reflection_report/`.
For each case it:

1. Creates a tmp SQLite database and applies migrations.
2. Patches `DATABASE_URL` to the tmp database.
3. Patches `observability.query_trace_events()` to return fixture trace events.
4. Patches `memory_layer.search()` to return fixture memory signals.
5. Calls `run_reflection(scope)`.
6. Validates expected and forbidden findings.
7. Reads the saved `reflection_reports.findings_json` and verifies forbidden transcript snippets are
   absent.

The runner uses only tmp storage and fake public API responses. It must not read or write `data/`.

## Optional Real-Route Smoke

The default evaluation must not call external services. A real-route smoke may exist only behind
`FLEETENT_EVAL_REAL_REFLECTION=1`. If enabled but required configuration is absent, it skips.

Because current reflection rules are deterministic and do not require LLM credentials, the smoke
guard should require an explicit fixture or database configuration before running against real local
state. This prevents accidental use of production-like local data.

## Error Handling

Invalid fixture schema raises a dedicated validation error. Expected-finding and forbidden-finding
assertions raise clear assertion messages naming the unmatched rule.

The evaluation should not hide reflection runtime exceptions. If `run_reflection()` fails for a
valid deterministic fixture, that is a behavior regression.

## Testing

Tests follow the project TDD gate:

- Fixture schema tests fail before loader implementation.
- Runner behavior tests fail before fake observability/memory wiring.
- Baseline scenario tests fail before fixtures are accepted.
- Persistence redaction tests fail before tmp SQLite setup and persisted payload checks exist.
- Real-route smoke skip tests fail before opt-in guards exist.

The relevant loop command is `uv run pytest tests/evaluation/test_reflection_report_eval.py -x -q`.
Final verification uses the full project quality gates required by the project workflow.
