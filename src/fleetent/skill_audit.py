"""Static prompt-injection audit for SKILL.md content.

A purely static, deterministic rule layer: no LLM, no external services, no
network — so it is unit-testable and never sends skill content off-box. It scans
both the SKILL.md body and the frontmatter description (the two surfaces that
reach the model under read-on-demand: the catalog and read_skill) for known
prompt-injection patterns, returning each match with its severity.
"""

import re
from dataclasses import dataclass

# --- Rule severity literals (kept as plain strings; the rule table is the SoT). ---
SEVERE = "severe"
SUSPICIOUS = "suspicious"


@dataclass(frozen=True)
class _Rule:
    """A single static injection-detection rule.

    `pattern` is a precompiled, case-insensitive regex; `severity` is one of
    SEVERE / SUSPICIOUS; `rule_id` is a stable identifier surfaced in audit logs.
    """

    rule_id: str
    severity: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class Hit:
    """One rule match against a scanned field.

    `field` is "content" (SKILL.md body) or "description" (frontmatter), so an
    audit trail can show which surface carried the injection.
    """

    rule_id: str
    severity: str
    field: str
    match: str


def _rule(rule_id: str, severity: str, pattern: str) -> _Rule:
    """Compile one rule (case-insensitive, DOTALL for multi-line shell snippets)."""
    return _Rule(rule_id, severity, re.compile(pattern, re.IGNORECASE | re.DOTALL))


# Immutable module-level rule table (a tuple — satisfies the no-global-mutable-state
# rule; tests may read it freely but cannot mutate it). Initial coverage targets the
# high-risk classes the docs enumerate; extend by appending rules here. Each class is
# detected on both the body and the description.
_RULES: tuple[_Rule, ...] = (
    # --- Class: instruction override ("ignore previous instructions" family). ---
    _rule(
        "ignore_previous_instructions",
        SEVERE,
        r"(ignore|disregard|forget)\s+(all\s+)?(the\s+)?"
        r"(previous|prior|above|earlier|preceding)\s+(instructions?|prompts?|rules?)",
    ),
    _rule(
        "ignore_previous_instructions_zh",
        SEVERE,
        r"(忽略|无视|忘记|无需理会)(之前|上述|前面|以上|先前)(的)?(所有)?(指令|指示|提示|规则)",
    ),
    # --- Class: impersonated system / role directives embedded in skill content. ---
    _rule(
        "fake_system_directive",
        SEVERE,
        r"</?\s*system\s*>|\bsystem\s*(prompt|message)\s*:",
    ),
    _rule(
        "role_reassignment",
        SEVERE,
        r"you\s+are\s+now\s+(an?\s+)?(unrestricted|jailbroken|dan|developer\s+mode)",
    ),
    # --- Class: shell command injection (pipe-to-shell, eval of remote payloads). ---
    _rule(
        "pipe_to_shell",
        SEVERE,
        r"\b(curl|wget)\b[^\n|]*\|\s*(ba)?sh\b",
    ),
    _rule(
        "remote_eval_exec",
        SEVERE,
        r"\b(eval|exec)\s*\(\s*(requests|urllib|os\.popen|subprocess)",
    ),
    # --- Class: suspicious-but-not-decisive (restriction-lifting phrasing). ---
    _rule(
        "no_restrictions",
        SUSPICIOUS,
        r"\b(no|without|ignore)\s+(restrictions?|limitations?|guardrails?|safety\s+rules?)",
    ),
    _rule(
        "reveal_system_prompt",
        SUSPICIOUS,
        r"\b(reveal|print|repeat|show)\s+(your|the)\s+(system\s+)?(prompt|instructions?)",
    ),
)


def audit(content: str, description: str) -> list[Hit]:
    """Scan SKILL.md body and description for known injection patterns.

    Returns one Hit per (rule, field) match, with each hit's rule id, severity,
    and the field it matched ("content" or "description"). Clean input returns an
    empty list. Purely static — no LLM, no I/O.
    """
    hits: list[Hit] = []
    for field, text in (("content", content), ("description", description)):
        if not text:
            continue
        for rule in _RULES:
            m = rule.pattern.search(text)
            if m is not None:
                hits.append(Hit(rule.rule_id, rule.severity, field, m.group(0)))
    return hits


def has_severe(hits: list[Hit]) -> bool:
    """Return True when any hit is SEVERE — the trigger for audit_blocked."""
    return any(h.severity == SEVERE for h in hits)
