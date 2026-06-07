"""Outbound secret redaction for sandbox output (sandbox-output-redaction).

`secrets.build_sandbox_env` filters secrets on the way *into* the container; this is
the symmetric outbound guard: before `run_code`'s stdout/stderr reaches the agent loop
(and thus the model and the persisted session), likely secrets are replaced with a
placeholder. Structured forms (PEM keys, JWTs, vendor key prefixes, URL credentials,
Authorization headers) match with high precision; named ``KEY=VALUE`` assignments match
conservatively (only when the key name itself signals a secret), deliberately excluding
bare ``KEY``/``AUTH`` so ``MONKEY``/``AUTHOR`` are not over-redacted.

Defence-in-depth, not a guarantee: the first line is still "do not inject credentials".
The pattern set is a module-level constant so it can be extended without touching callers.
"""

from __future__ import annotations

import re

PLACEHOLDER = "[REDACTED]"

# Ordered (pattern, replacement) pairs applied in sequence. Structural/specific first.
# Module-level so tests/extensions can append patterns (mirrors secrets.SENSITIVE_TOKENS).
REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # PEM private key blocks (any key type) — redact the whole block.
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        PLACEHOLDER,
    ),
    # JWT: three base64url segments.
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b"),
        PLACEHOLDER,
    ),
    # Known vendor API key / token prefixes.
    (
        re.compile(
            r"\b(?:"
            r"sk-ant-[A-Za-z0-9_-]{8,}"
            r"|sk-[A-Za-z0-9]{20,}"
            r"|ghp_[A-Za-z0-9]{20,}"
            r"|gho_[A-Za-z0-9]{20,}"
            r"|github_pat_[A-Za-z0-9_]{20,}"
            r"|xox[baprs]-[A-Za-z0-9-]{10,}"
            r"|AKIA[0-9A-Z]{16}"
            r"|AIza[0-9A-Za-z_-]{20,}"
            r"|glpat-[A-Za-z0-9_-]{16,}"
            r")\b"
        ),
        PLACEHOLDER,
    ),
    # Authorization header: keep the field name, redact scheme + credential.
    (
        re.compile(
            r"(?i)\b(authorization)(\s*[:=]\s*)(?:bearer|basic|token|digest)\s+[A-Za-z0-9._~+/=-]+"
        ),
        r"\1\2" + PLACEHOLDER,
    ),
    # URL-embedded credentials: redact the password component, keep scheme/user/host.
    (
        re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.\-]*://[^:/?#\s@]+):([^@/?#\s]+)@"),
        r"\1:" + PLACEHOLDER + "@",
    ),
    # Named secret assignments: the key name signals a secret. Bare KEY/AUTH are excluded
    # on purpose (AUTHOR/MONKEY/KEYBOARD must not match). Value may be quoted (with spaces)
    # or bare; redact the value, keep the key + separator.
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_]*"
            r"(?:TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|(?:API|ACCESS|PRIVATE|SECRET)[_-]?KEY)"
            r"[A-Za-z0-9_]*)(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s]+)"
        ),
        r"\1\2" + PLACEHOLDER,
    ),
)


def redact_secrets(text: str) -> str:
    """Replace likely secrets in ``text`` with ``PLACEHOLDER`` before it reaches the model.

    Applies each pattern in order. Conservative by design (structured forms precise,
    named assignments only on secret-signalling key names); not a zero-miss guarantee.
    """
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
