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
]
