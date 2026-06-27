"""User memory facts schema migrations (for agent_state.db).

These entries are appended to AGENT_STATE_MIGRATIONS in
runtime/agent_state_migrations.py.  Import FACTS_MIGRATIONS and extend
MIGRATIONS from there — do not call migrate() directly from this file.

Version history (relative offsets, resolved at append time):
  +0  facts               three-tuple user memory records
  +1  fact_edges          supersedes chain between facts
  +2  relation_clusters   canonical relation wordlist + cardinality
  +3  idx_facts_user_rel  query index for cardinality gate
  +4  seed relation_clusters with preset relation vocabulary
"""

from __future__ import annotations

from fleetent.memory.facts_models import Cardinality

# Canonical preset relation wordlist seeded into relation_clusters.  Kept broad so
# the merge gate (cosine >= 0.90) has anchors to land on, reducing long-tail
# fragmentation early when the wordlist is still sparse (design risk R2).
# single = a new value supersedes the old; multi = values coexist.
SEED_RELATIONS: list[tuple[str, Cardinality]] = [
    # ── identity / role (single — one current value) ──
    ("name", "single"),
    ("is_role", "single"),
    ("works_at", "single"),
    ("located_in", "single"),
    ("timezone", "single"),
    ("seniority_level", "single"),
    ("team", "single"),
    # ── single-valued attributes (numbers, durations, current state) ──
    ("years_of_experience", "single"),
    ("primary_language", "single"),  # the ONE main language (a new one replaces it)
    # ── preferences / habits (multi — accumulate) ──
    # prefers_language is multi: a user can prefer several languages at once.
    ("prefers_language", "multi"),
    ("prefers_tool", "multi"),
    ("prefers_style", "multi"),
    ("dislikes", "multi"),
    ("likes", "multi"),
    # ── skills / knowledge (multi) ──
    ("has_skill", "multi"),
    ("speaks_language", "multi"),
    ("learning", "multi"),
    ("interested_in", "multi"),
    ("familiar_with", "multi"),
    # ── activities / work (multi) ──
    ("works_on_project", "multi"),
    ("uses", "multi"),
    ("responsible_for", "multi"),
    ("goal", "multi"),
]

# Relations whose facts are long-term from the moment they are written
# (expires_at = NULL), bypassing the default 30-day short-term TTL.  These are
# stable identity facts — who the user/agent is — that should not silently expire
# while waiting to clear the access-count upgrade bar.  Preferences, interests,
# skills and activities stay short-term and earn long-term status through use.
LONG_TERM_RELATIONS: frozenset[str] = frozenset(
    {
        "name",
        "is_role",
        "works_at",
        "located_in",
        "timezone",
        "seniority_level",
        "team",
        "primary_language",
        "years_of_experience",
    }
)

FACTS_MIGRATIONS: list[tuple[str, str]] = [
    (
        "facts",
        """
        CREATE TABLE IF NOT EXISTS facts (
            fact_id             TEXT PRIMARY KEY,
            user_id             TEXT NOT NULL,
            subject             TEXT NOT NULL,
            relation            TEXT NOT NULL,
            object              TEXT NOT NULL,
            cardinality         TEXT NOT NULL CHECK (cardinality IN ('single', 'multi')),
            status              TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'superseded', 'archived', 'retracted')),
            access_count        INTEGER NOT NULL DEFAULT 0,
            first_accessed_at   TEXT,
            last_accessed_at    TEXT,
            expires_at          TEXT,
            valid_until         TEXT,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            source_turn         TEXT
        )
        """,
    ),
    (
        "fact_edges",
        """
        CREATE TABLE IF NOT EXISTS fact_edges (
            edge_id         TEXT PRIMARY KEY,
            from_fact_id    TEXT NOT NULL REFERENCES facts(fact_id),
            to_fact_id      TEXT NOT NULL REFERENCES facts(fact_id),
            edge_type       TEXT NOT NULL DEFAULT 'supersedes',
            created_at      TEXT NOT NULL
        )
        """,
    ),
    (
        "relation_clusters",
        """
        CREATE TABLE IF NOT EXISTS relation_clusters (
            relation    TEXT PRIMARY KEY,
            cardinality TEXT NOT NULL CHECK (cardinality IN ('single', 'multi')),
            embedding   BLOB,
            created_at  TEXT NOT NULL
        )
        """,
    ),
    (
        "idx_facts_user_rel",
        "CREATE INDEX IF NOT EXISTS idx_facts_user_rel"
        " ON facts (user_id, subject, relation, status)",
    ),
    (
        "seed_relation_clusters",
        "INSERT OR IGNORE INTO relation_clusters (relation, cardinality, created_at) VALUES\n"
        + ",\n".join(
            f"            ('{rel}', '{card}', datetime('now'))" for rel, card in SEED_RELATIONS
        ),
    ),
    # statement: an LLM-generated natural-language rendering of the triple, used
    # verbatim at injection time so the model reads an unambiguous sentence
    # ("用户的名字是 Xin" / "用户希望助手回答简洁") instead of a machine-joined line.
    # Triples still drive retrieval/dedup/supersede; statement drives injection.
    (
        "facts_statement",
        "ALTER TABLE facts ADD COLUMN statement TEXT",
    ),
    # scope: 'situational' = recalled by vector similarity (default); 'always' =
    # unconditionally injected into every prompt regardless of query.  Used for
    # behavioral directives (response_style, never_do, etc.) that must never be
    # missed due to low semantic overlap with the current query.
    (
        "facts_scope",
        "ALTER TABLE facts ADD COLUMN scope TEXT NOT NULL DEFAULT 'situational'",
    ),
    # Backfill: known always-relations get scope='always'.  Conservative: only
    # relations in the explicit soft/hard lists; unknowns stay 'situational'.
    (
        "facts_scope_backfill",
        "UPDATE facts SET scope = 'always' WHERE relation IN ("
        "'response_style', 'tone', 'format', 'language', 'output_format',"
        "'never_do', 'always_do', 'security', 'approval_required'"
        ") AND status = 'active'",
    ),
]
