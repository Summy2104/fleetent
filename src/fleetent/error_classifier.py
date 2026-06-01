"""Runtime error classification layer.

Normalizes runtime exceptions into a fixed set of category codes, each carrying
recovery-strategy flags. The agent loop reads only the flags to decide whether
to switch models / retry / compress — it no longer re-parses exception types or
status codes in the loop body.

This mirrors the termination framework (AR1): a static table is the single
source of truth and `classify()` is a pure lookup. Reserved codes for wave-2
error sources (tool_timeout / mcp_disconnect / sandbox_oom / sandbox_timeout)
are defined here with flags, but `classify()` never produces them until those
error sources are wired in.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from openai import APIStatusError

# Error-body `code` value emitted by OpenAI-compatible backends when the prompt
# exceeds the model's context window. Surfaces as a 400 BadRequestError whose
# `.code` property reads this from the response body.
_CONTEXT_OVERFLOW_CODE = "context_length_exceeded"

# Status codes treated as transient/limiting → switch to a fallback model.
# 429 = rate limited; 503 = service unavailable (folded into rate_limit per design D2).
_RATE_LIMIT_STATUS = frozenset({429, 503})

# Status codes indicating auth/permission failure → no recovery, surface to user.
_AUTH_STATUS = frozenset({401, 403})


class ErrorCategory(StrEnum):
    """Fixed runtime-error categories. str-valued for clean JSONL trace output."""

    rate_limit = "rate_limit"
    context_overflow = "context_overflow"
    auth_failed = "auth_failed"
    tool_crash = "tool_crash"
    unknown = "unknown"
    # Reserved for wave-2 error sources: defined with flags so consumers know the
    # full vocabulary, but classify() never returns these until the corresponding
    # error sources (tool timeout / MCP / sandbox) are wired in.
    tool_timeout = "tool_timeout"
    mcp_disconnect = "mcp_disconnect"
    sandbox_oom = "sandbox_oom"
    sandbox_timeout = "sandbox_timeout"


@dataclass(frozen=True)
class ErrorClassification:
    """A category plus its recovery-strategy flags. The loop reads only flags."""

    category: ErrorCategory
    should_retry: bool
    should_compress: bool
    should_switch_model: bool


def _entry(
    category: ErrorCategory,
    *,
    should_retry: bool = False,
    should_compress: bool = False,
    should_switch_model: bool = False,
) -> ErrorClassification:
    return ErrorClassification(
        category=category,
        should_retry=should_retry,
        should_compress=should_compress,
        should_switch_model=should_switch_model,
    )


# Single source of truth: category → recovery-strategy flags. Module-level and
# immutable (frozen dataclass values); tests reference it read-only.
CLASSIFICATION_TABLE: dict[ErrorCategory, ErrorClassification] = {
    ErrorCategory.rate_limit: _entry(
        ErrorCategory.rate_limit, should_retry=True, should_switch_model=True
    ),
    ErrorCategory.context_overflow: _entry(
        ErrorCategory.context_overflow, should_retry=True, should_compress=True
    ),
    ErrorCategory.auth_failed: _entry(ErrorCategory.auth_failed),
    ErrorCategory.tool_crash: _entry(ErrorCategory.tool_crash),
    ErrorCategory.unknown: _entry(ErrorCategory.unknown),
    # Reserved (wave 2) — flags per design D3.
    ErrorCategory.tool_timeout: _entry(ErrorCategory.tool_timeout),
    ErrorCategory.mcp_disconnect: _entry(ErrorCategory.mcp_disconnect, should_retry=True),
    ErrorCategory.sandbox_oom: _entry(ErrorCategory.sandbox_oom),
    ErrorCategory.sandbox_timeout: _entry(ErrorCategory.sandbox_timeout),
}


def classify(error: Exception) -> ErrorClassification:
    """Normalize a runtime exception to its classification (pure table lookup).

    Recognizes only currently-reachable LLM-call errors; anything else (including
    every wave-2 reserved category) falls through to `unknown`.
    """
    category = _categorize(error)
    return CLASSIFICATION_TABLE[category]


def _categorize(error: Exception) -> ErrorCategory:
    # Tool-call timeout (T2): asyncio.TimeoutError is TimeoutError on 3.11+. The
    # Anthropic SDK's request timeout is APITimeoutError (not a TimeoutError
    # subclass), so this maps only genuine await-layer tool timeouts.
    if isinstance(error, TimeoutError):
        return ErrorCategory.tool_timeout
    if isinstance(error, APIStatusError):
        # Context overflow is identified by the error-body `code`, since it
        # surfaces as a generic 400 indistinguishable from other bad requests
        # by status alone.
        if getattr(error, "code", None) == _CONTEXT_OVERFLOW_CODE:
            return ErrorCategory.context_overflow
        status = error.status_code
        if status in _RATE_LIMIT_STATUS:
            return ErrorCategory.rate_limit
        if status in _AUTH_STATUS:
            return ErrorCategory.auth_failed
    return ErrorCategory.unknown
