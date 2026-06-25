"""Unified per-agent embedded migration list for agent_state.db (Y engine).

One file, one PRAGMA user_version — every store that persists in agent_state.db
appends here rather than carrying its own list.  The Y engine's single-file
user_version stamp means independent lists on the same file would collide.

Version history:
  v1   sessions           (3b-1) session metadata index
  v2   traces             (3b-2) agent run trace event table
  v3   idx_traces_run_id
  v4   idx_traces_user_ts
  v5   idx_traces_agent_ts
  v6   idx_traces_tenant_event_ts
  v7   reflection_reports (3b-2) reflection summary table
  v8   idx_reflection_reports_scope_created
  v9   memory_items       (3b-3) per-user memory records (no namespace col)
  v10  idx_memory_items_user_type
  v11  idx_memory_items_user_expires
  v12  approvals          (3b-4) tool approval requests
  v13  approval_allowlist (3b-4) allow-always grants
  v14  session_anti_flap  (routing-cleanup) compression anti-flap, per session
  v15  sub_agent_runs     (routing-cleanup) sub-agent lifecycle records
  v16  idx_sub_agent_runs_parent
  v17  memory_maintenance_proposals (routing-cleanup) User Memory maintenance proposals
  v18  idx_memory_maintenance_user_status
  v19  skill_proposals    (routing-cleanup) Skill reflection proposals
  v20  idx_skill_proposals_status_updated
  v21  budget_usage       (retire-raw-sqlite-connect) per-agent layered budget counters
  v22  reflection_reports.domain
  v23  reflection_reports.signal_summary_json
  v24  reflection_proposals (unified memory/skill lifecycle)
  v25  drop memory_maintenance_proposals
  v26  drop skill_proposals
  v27  scheduled_tasks    (retire-standalone-fleetent-db)
  v28  drop sessions.agent_name
  v29  scheduled_tasks.task_type
  v30  scheduled_tasks.notify_text
  v31  approvals.approver_user_id
  v32  reflection_proposals.report_id
  v33  drop budget_usage
  v34  unify approval requests
  v35  artifacts          (unified-file-exchange) MCP artifact ledger
  v36  artifacts.scope_key (unified-file-exchange D0) attribution = workspace scope key
  v37  traces.agent_name  (finalize-agent-identity) rename traces.agent_id column
  v38  im_outbound_queue  (im-edge-on-node-outbound) managed async outbound queue
  v39  agent_memory_items (wire-agent-memory) consolidated from standalone agent_memory.db
  v40  idx_agent_memory_status
  v41  idx_agent_memory_source_ref
"""

from __future__ import annotations

MIGRATIONS: list[tuple[int, str]] = [
    # ── v1: session metadata (3b-1) ──────────────────────────────────────────
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id    TEXT PRIMARY KEY,
            user_id       TEXT,
            created_at    REAL,
            updated_at    REAL,
            message_count INTEGER,
            agent_name    TEXT
        )
        """,
    ),
    # ── v2-v6: agent run trace events (3b-2) ─────────────────────────────────
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS traces (
            id              TEXT PRIMARY KEY,
            run_id          TEXT NOT NULL,
            span_id         TEXT,
            parent_span_id  TEXT,
            session_id      TEXT,
            user_id         TEXT,
            agent_id        TEXT,
            tenant_id       TEXT NOT NULL DEFAULT 'default',
            event_type      TEXT NOT NULL,
            ts              TEXT NOT NULL,
            payload_json    TEXT NOT NULL
        )
        """,
    ),
    (3, "CREATE INDEX IF NOT EXISTS idx_traces_run_id ON traces (run_id)"),
    (4, "CREATE INDEX IF NOT EXISTS idx_traces_user_ts ON traces (user_id, ts)"),
    (5, "CREATE INDEX IF NOT EXISTS idx_traces_agent_ts ON traces (agent_id, ts)"),
    (
        6,
        "CREATE INDEX IF NOT EXISTS idx_traces_tenant_event_ts"
        " ON traces (tenant_id, event_type, ts)",
    ),
    # ── v7-v8: reflection reports (3b-2) ─────────────────────────────────────
    (
        7,
        """
        CREATE TABLE IF NOT EXISTS reflection_reports (
            id                  TEXT PRIMARY KEY,
            scope               TEXT NOT NULL,
            time_window_start   TEXT NOT NULL,
            time_window_end     TEXT NOT NULL,
            findings_json       TEXT NOT NULL,
            created_at          TEXT NOT NULL
        )
        """,
    ),
    (
        8,
        "CREATE INDEX IF NOT EXISTS idx_reflection_reports_scope_created"
        " ON reflection_reports (scope, created_at)",
    ),
    # ── v9-v11: user memory items (3b-3) ─────────────────────────────────────
    (
        9,
        """
        CREATE TABLE IF NOT EXISTS memory_items (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            type        TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            expires_at  TEXT
        )
        """,
    ),
    (10, "CREATE INDEX IF NOT EXISTS idx_memory_items_user_type ON memory_items (user_id, type)"),
    (
        11,
        "CREATE INDEX IF NOT EXISTS idx_memory_items_user_expires"
        " ON memory_items (user_id, expires_at)",
    ),
    # ── v12-v13: approval requests + allow-always grants (3b-4) ──────────────
    (
        12,
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id                TEXT PRIMARY KEY,
            session_id        TEXT NOT NULL,
            requester_user_id TEXT NOT NULL,
            risk_level        TEXT NOT NULL,
            tool_name         TEXT NOT NULL,
            tool_args         TEXT NOT NULL,
            status            TEXT NOT NULL,
            approver_actor    TEXT,
            created_at        TEXT NOT NULL,
            resolved_at       TEXT
        )
        """,
    ),
    (
        13,
        """
        CREATE TABLE IF NOT EXISTS approval_allowlist (
            fingerprint TEXT PRIMARY KEY,
            scope_key   TEXT NOT NULL,
            tool_name   TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            created_by  TEXT
        )
        """,
    ),
    # ── v14: compression anti-flap state (routing-cleanup) ───────────────────
    # Lifted verbatim from runtime/context.init_anti_flap_db so the per-session
    # circuit-breaker state lands in agent_state.db, not the shared management DB.
    (
        14,
        """
        CREATE TABLE IF NOT EXISTS session_anti_flap (
          session_id        TEXT PRIMARY KEY,
          recent_savings    TEXT NOT NULL,
          turns_since       INTEGER NOT NULL,
          auto_disabled     INTEGER NOT NULL
        )
        """,
    ),
    # ── v15-v16: sub-agent lifecycle records (routing-cleanup) ───────────────
    # Lifted verbatim from runtime/sub_agent_lifecycle.init_db.
    (
        15,
        """
        CREATE TABLE IF NOT EXISTS sub_agent_runs (
          run_id            TEXT PRIMARY KEY,
          parent_session_id TEXT NOT NULL,
          name              TEXT NOT NULL,
          state             TEXT NOT NULL,
          timeout_seconds   INTEGER NOT NULL,
          created_at        TEXT NOT NULL,
          started_at        TEXT,
          ended_at          TEXT,
          error             TEXT
        )
        """,
    ),
    (
        16,
        "CREATE INDEX IF NOT EXISTS idx_sub_agent_runs_parent ON sub_agent_runs(parent_session_id)",
    ),
    # ── v17-v18: User Memory maintenance proposals (routing-cleanup) ─────────
    # Lifted from Alembic migration 010 (management-DB orphan); column set and
    # index preserved so the agent-side store reads/writes identically.
    (
        17,
        """
        CREATE TABLE IF NOT EXISTS memory_maintenance_proposals (
          id                      TEXT PRIMARY KEY,
          user_id                 TEXT NOT NULL,
          action                  TEXT NOT NULL,
          target_memory_ids_json  TEXT NOT NULL,
          proposed_content        TEXT,
          metadata_patch_json     TEXT NOT NULL,
          risk                    TEXT NOT NULL,
          reason                  TEXT NOT NULL,
          evidence_ids_json       TEXT NOT NULL,
          status                  TEXT NOT NULL,
          created_at              DATETIME NOT NULL,
          updated_at              DATETIME NOT NULL,
          expires_at              DATETIME
        )
        """,
    ),
    (
        18,
        "CREATE INDEX IF NOT EXISTS idx_memory_maintenance_user_status"
        " ON memory_maintenance_proposals (user_id, status, updated_at)",
    ),
    # ── v19-v20: Skill reflection proposals (routing-cleanup) ────────────────
    # Lifted from Alembic migration 028 (management-DB orphan).
    (
        19,
        """
        CREATE TABLE IF NOT EXISTS skill_proposals (
          id                  TEXT PRIMARY KEY,
          type                TEXT NOT NULL,
          target_skill        TEXT NOT NULL,
          reason              TEXT NOT NULL,
          evidence_refs_json  TEXT NOT NULL,
          risk_level          TEXT NOT NULL,
          suggested_draft     TEXT,
          suggested_diff      TEXT,
          status              TEXT NOT NULL,
          reviewer_user_id    TEXT,
          reviewed_at         TEXT,
          rejection_reason    TEXT,
          actor_user_id       TEXT,
          applied_at          TEXT,
          created_at          TEXT NOT NULL,
          updated_at          TEXT NOT NULL
        )
        """,
    ),
    (
        20,
        "CREATE INDEX IF NOT EXISTS idx_skill_proposals_status_updated"
        " ON skill_proposals (status, updated_at)",
    ),
    # ── v21: per-agent layered budget counters (retire-raw-sqlite-connect) ───────
    # Lifted verbatim from runtime/layered_budget.init_db so cross-run budget
    # usage lands in agent_state.db, not the shared management DB.
    (
        21,
        """
        CREATE TABLE IF NOT EXISTS budget_usage (
          scope     TEXT NOT NULL,
          key       TEXT NOT NULL,
          period    TEXT NOT NULL,
          turns     INTEGER NOT NULL,
          tokens    INTEGER NOT NULL,
          PRIMARY KEY (scope, key, period)
        )
        """,
    ),
    # ── v22-v26: unified self-evolution reports/proposals ───────────────────
    (
        22,
        """
        ALTER TABLE reflection_reports
        ADD COLUMN domain TEXT
        """,
    ),
    (
        23,
        """
        ALTER TABLE reflection_reports
        ADD COLUMN signal_summary_json TEXT
        """,
    ),
    (
        24,
        """
        CREATE TABLE IF NOT EXISTS reflection_proposals (
          id                TEXT PRIMARY KEY,
          domain            TEXT NOT NULL,
          kind              TEXT NOT NULL,
          subject_user_id   TEXT,
          target_ref        TEXT,
          payload_json      TEXT NOT NULL,
          reason            TEXT NOT NULL,
          evidence_json     TEXT NOT NULL,
          risk              TEXT NOT NULL,
          status            TEXT NOT NULL,
          reviewer_user_id  TEXT,
          reviewed_at       TEXT,
          rejection_reason  TEXT,
          actor_user_id     TEXT,
          applied_at        TEXT,
          expires_at        TEXT,
          created_at        TEXT NOT NULL,
          updated_at        TEXT NOT NULL
        )
        """,
    ),
    (25, "DROP TABLE IF EXISTS memory_maintenance_proposals"),
    (26, "DROP TABLE IF EXISTS skill_proposals"),
    # ── v27: scheduled tasks (retire-standalone-fleetent-db) ─────────────────
    # Lifted verbatim from schedule_store._TABLE_DDL; one agent per process so
    # there is no agent_name column — routing is implicit to the process's agent.
    (
        27,
        "CREATE TABLE IF NOT EXISTS scheduled_tasks ("
        "id TEXT PRIMARY KEY, "
        "name TEXT, "
        "schedule_kind TEXT NOT NULL DEFAULT 'cron', "
        "cron_expr TEXT, "
        "run_at TEXT, "
        "interval_seconds INTEGER, "
        "anchor TEXT, "
        "timezone TEXT, "
        "user_id TEXT, "
        "message TEXT, "
        "session_id TEXT, "
        "origin TEXT, "
        "deliver TEXT, "
        "enabled INTEGER NOT NULL DEFAULT 1, "
        "source TEXT, "
        "created_at TEXT, "
        "last_run_at TEXT, "
        "last_status TEXT, "
        "last_error TEXT, "
        "next_run_at TEXT"
        ")",
    ),
    (28, "ALTER TABLE sessions DROP COLUMN agent_name"),
    # typed-scheduled-task-delivery: notify/generate/action typing + frozen notify copy.
    # Existing rows default to 'generate' (closest to the prior run-and-deliver behavior).
    (
        29,
        "ALTER TABLE scheduled_tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'generate'",
    ),
    (30, "ALTER TABLE scheduled_tasks ADD COLUMN notify_text TEXT"),
    # ── v31: unify-identity-column-naming ────────────────────────────────────
    (31, "ALTER TABLE approvals RENAME COLUMN approver_actor TO approver_user_id"),
    # ── v32: reflection proposal provenance ──────────────────────────────────
    (32, "ALTER TABLE reflection_proposals ADD COLUMN report_id TEXT"),
    (33, "DROP TABLE IF EXISTS budget_usage"),
]

MIGRATIONS.append(
    (
        MIGRATIONS[-1][0] + 1,
        """
        CREATE TABLE approval_requests (
            id                TEXT PRIMARY KEY,
            subject_type      TEXT NOT NULL,
            subject_id        TEXT NOT NULL,
            requester_user_id TEXT,
            risk              TEXT NOT NULL,
            status            TEXT NOT NULL,
            approver_user_id  TEXT,
            decided_at        TEXT,
            reason            TEXT,
            routing_key       TEXT NOT NULL,
            created_at        TEXT NOT NULL,
            expires_at        TEXT
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id                TEXT PRIMARY KEY,
            session_id        TEXT NOT NULL,
            requester_user_id TEXT NOT NULL,
            risk_level        TEXT NOT NULL,
            tool_name         TEXT NOT NULL,
            tool_args         TEXT NOT NULL,
            status            TEXT NOT NULL,
            approver_user_id  TEXT,
            created_at        TEXT NOT NULL,
            resolved_at       TEXT
        );
        CREATE TABLE IF NOT EXISTS approval_allowlist (
            fingerprint TEXT PRIMARY KEY,
            scope_key   TEXT NOT NULL,
            tool_name   TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            created_by  TEXT
        );
        INSERT INTO approval_requests (
            id, subject_type, subject_id, requester_user_id, risk, status,
            approver_user_id, decided_at, reason, routing_key, created_at, expires_at
        )
        SELECT
            id,
            'tool_call',
            session_id,
            requester_user_id,
            risk_level,
            CASE status WHEN 'timeout' THEN 'expired' ELSE status END,
            approver_user_id,
            resolved_at,
            NULL,
            tool_name,
            created_at,
            NULL
        FROM approvals;
        INSERT INTO approval_requests (
            id, subject_type, subject_id, requester_user_id, risk, status,
            approver_user_id, decided_at, reason, routing_key, created_at, expires_at
        )
        SELECT
            id,
            CASE domain
                WHEN 'memory' THEN 'memory_proposal'
                WHEN 'skill' THEN 'skill_proposal'
                ELSE 'skill_proposal'
            END,
            id,
            NULL,
            risk,
            CASE status WHEN 'timeout' THEN 'expired' ELSE status END,
            reviewer_user_id,
            reviewed_at,
            rejection_reason,
            CASE domain
                WHEN 'memory' THEN 'reflection_memory_proposal'
                WHEN 'skill' THEN 'reflection_skill_proposal'
                ELSE 'reflection_' || domain || '_proposal'
            END,
            created_at,
            expires_at
        FROM reflection_proposals;
        ALTER TABLE reflection_proposals DROP COLUMN status;
        ALTER TABLE reflection_proposals DROP COLUMN reviewer_user_id;
        ALTER TABLE reflection_proposals DROP COLUMN reviewed_at;
        ALTER TABLE reflection_proposals DROP COLUMN rejection_reason;
        ALTER TABLE reflection_proposals DROP COLUMN expires_at;
        ALTER TABLE approval_allowlist RENAME TO tool_auto_approvals;
        DROP TABLE approvals;
        """,
    )
)

# ── v35-v36: unified-file-exchange — MCP artifact ledger (reconcile: renumbered
# after Bitbucket's v32-v34 since both mains independently used v32/v33). The ledger
# is governance metadata, never a model interface: it records provenance + ownership
# for files produced by MCP servers under the /exchange namespace and drives
# attribution access control, the per-scope view, and audit. v36 adds `scope_key`
# (D0): the visibility/ownership key (session_id when workspace_scope is `session`,
# agent_name when `agent`; same source as the /workspace mount). session_id/user_id
# become audit-only columns.
MIGRATIONS.append(
    (
        MIGRATIONS[-1][0] + 1,
        "CREATE TABLE IF NOT EXISTS artifacts ("
        "artifact_id TEXT PRIMARY KEY, "
        "server_id TEXT NOT NULL, "
        "rel_path TEXT NOT NULL, "
        "session_id TEXT, "
        "user_id TEXT, "
        "filename TEXT, "
        "mime TEXT, "
        "size INTEGER, "
        "created_at TEXT"
        ")",
    )
)
MIGRATIONS.append((MIGRATIONS[-1][0] + 1, "ALTER TABLE artifacts ADD COLUMN scope_key TEXT"))
MIGRATIONS.append(
    (
        MIGRATIONS[-1][0] + 1,
        """
        CREATE TABLE IF NOT EXISTS traces (
            id              TEXT PRIMARY KEY,
            run_id          TEXT NOT NULL,
            span_id         TEXT,
            parent_span_id  TEXT,
            session_id      TEXT,
            user_id         TEXT,
            agent_id        TEXT,
            tenant_id       TEXT NOT NULL DEFAULT 'default',
            event_type      TEXT NOT NULL,
            ts              TEXT NOT NULL,
            payload_json    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_traces_run_id ON traces (run_id);
        CREATE INDEX IF NOT EXISTS idx_traces_user_ts ON traces (user_id, ts);
        CREATE INDEX IF NOT EXISTS idx_traces_agent_ts ON traces (agent_id, ts);
        CREATE INDEX IF NOT EXISTS idx_traces_tenant_event_ts ON traces (tenant_id, event_type, ts);
        ALTER TABLE traces RENAME COLUMN agent_id TO agent_name;
        """,
    )
)
MIGRATIONS.append(
    (
        MIGRATIONS[-1][0] + 1,
        """
        CREATE TABLE IF NOT EXISTS im_outbound_queue (
            id            TEXT PRIMARY KEY,
            platform      TEXT NOT NULL,
            address_json  TEXT NOT NULL,
            payload_json  TEXT NOT NULL,
            dedup_key     TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'pending',
            attempts      INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL,
            sent_at       TEXT
        )
        """,
    )
)

# ── v39-v41: agent_memory_items (wire-agent-memory) ──────────────────────────
# Consolidated from the standalone agent_memory.db / agent_memory_migrations.py.
# Isolation is per-agent physical DB (one agent_state.db per agent) — no scope columns.
MIGRATIONS.append(
    (
        MIGRATIONS[-1][0] + 1,
        """
        CREATE TABLE IF NOT EXISTS agent_memory_items (
            id          TEXT NOT NULL PRIMARY KEY,
            type        TEXT NOT NULL,
            content     TEXT NOT NULL,
            status      TEXT NOT NULL,
            source      TEXT NOT NULL,
            source_ref  TEXT,
            created_by  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
        """,
    )
)
MIGRATIONS.append(
    (
        MIGRATIONS[-1][0] + 1,
        "CREATE INDEX IF NOT EXISTS idx_agent_memory_status ON agent_memory_items (status)",
    )
)
MIGRATIONS.append(
    (
        MIGRATIONS[-1][0] + 1,
        "CREATE INDEX IF NOT EXISTS idx_agent_memory_source_ref"
        " ON agent_memory_items (source, source_ref)",
    )
)

# ── v42-v46: user memory facts (user-memory-v2) ──────────────────────────────
# Three-tuple (subject, relation, object) facts replace free-text memory_items.
# facts_migrations.py holds the schema; appended here to share the single
# PRAGMA user_version stamp on agent_state.db.
from fleetent.memory.facts_migrations import FACTS_MIGRATIONS as _FACTS_MIGRATIONS  # noqa: E402

for _label, _sql in _FACTS_MIGRATIONS:
    MIGRATIONS.append((MIGRATIONS[-1][0] + 1, _sql))
