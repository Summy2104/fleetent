"""Tests for the runtime error classification layer."""

from dataclasses import FrozenInstanceError

import httpx
import pytest
from openai import (
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

from fleetent.runtime.error_classifier import (
    CLASSIFICATION_TABLE,
    ErrorCategory,
    ErrorClassification,
    classify,
)

_REQ = httpx.Request("POST", "http://x/v1/chat/completions")


def _api_error(cls: type[APIStatusError], status: int, body: object | None) -> APIStatusError:
    resp = httpx.Response(status_code=status, request=_REQ)
    return cls("err", response=resp, body=body)


# --- 2.1 enum + dataclass ---


def test_error_category_has_all_codes() -> None:
    expected = {
        "rate_limit",
        "context_overflow",
        "tool_timeout",
        "tool_crash",
        "mcp_disconnect",
        "sandbox_oom",
        "sandbox_timeout",
        "auth_failed",
        "llm_timeout",
        "unknown",
    }
    assert {c.value for c in ErrorCategory} == expected


def test_error_category_is_str_enum() -> None:
    assert ErrorCategory.rate_limit == "rate_limit"


def test_classification_has_all_fields() -> None:
    clf = ErrorClassification(
        category=ErrorCategory.unknown,
        should_retry=False,
        should_compress=False,
        should_switch_model=False,
    )
    assert clf.category is ErrorCategory.unknown
    assert clf.should_retry is False
    assert clf.should_compress is False
    assert clf.should_switch_model is False


def test_classification_is_frozen() -> None:
    clf = ErrorClassification(
        category=ErrorCategory.unknown,
        should_retry=False,
        should_compress=False,
        should_switch_model=False,
    )
    with pytest.raises(FrozenInstanceError):
        clf.should_retry = True  # type: ignore[misc]


# --- 2.3 classification table ---


def test_table_covers_all_categories() -> None:
    assert set(CLASSIFICATION_TABLE) == set(ErrorCategory)


def test_table_entry_category_matches_key() -> None:
    for cat, clf in CLASSIFICATION_TABLE.items():
        assert clf.category is cat


def test_rate_limit_flags() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.rate_limit]
    assert clf.should_retry is True
    assert clf.should_switch_model is True
    assert clf.should_compress is False


def test_context_overflow_flags() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.context_overflow]
    assert clf.should_compress is True
    assert clf.should_retry is True
    assert clf.should_switch_model is False


def test_auth_failed_all_false() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.auth_failed]
    assert not (clf.should_retry or clf.should_compress or clf.should_switch_model)


def test_unknown_all_false() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.unknown]
    assert not (clf.should_retry or clf.should_compress or clf.should_switch_model)


def test_tool_crash_all_false() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.tool_crash]
    assert not (clf.should_retry or clf.should_compress or clf.should_switch_model)


def test_tool_timeout_all_false() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.tool_timeout]
    assert not (clf.should_retry or clf.should_compress or clf.should_switch_model)


def test_mcp_disconnect_retries() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.mcp_disconnect]
    assert clf.should_retry is True
    assert clf.should_compress is False
    assert clf.should_switch_model is False


def test_sandbox_oom_all_false() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.sandbox_oom]
    assert not (clf.should_retry or clf.should_compress or clf.should_switch_model)


def test_sandbox_timeout_all_false() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.sandbox_timeout]
    assert not (clf.should_retry or clf.should_compress or clf.should_switch_model)


# --- 3.1 classify() ---


def test_classify_rate_limit_error() -> None:
    exc = _api_error(RateLimitError, 429, {"message": "rate"})
    assert classify(exc).category is ErrorCategory.rate_limit


def test_classify_429_api_status_error() -> None:
    exc = _api_error(APIStatusError, 429, {"message": "too many"})
    assert classify(exc).category is ErrorCategory.rate_limit


def test_classify_503_api_status_error() -> None:
    exc = _api_error(APIStatusError, 503, {"message": "unavailable"})
    assert classify(exc).category is ErrorCategory.rate_limit


def test_classify_401_auth_failed() -> None:
    exc = _api_error(AuthenticationError, 401, {"message": "bad key"})
    assert classify(exc).category is ErrorCategory.auth_failed


def test_classify_403_auth_failed() -> None:
    exc = _api_error(PermissionDeniedError, 403, {"message": "forbidden"})
    assert classify(exc).category is ErrorCategory.auth_failed


def test_classify_context_overflow_by_code() -> None:
    exc = _api_error(
        BadRequestError,
        400,
        {"message": "maximum context length", "code": "context_length_exceeded"},
    )
    assert classify(exc).category is ErrorCategory.context_overflow


def test_classify_other_400_is_unknown() -> None:
    exc = _api_error(BadRequestError, 400, {"message": "bad", "code": "invalid_value"})
    assert classify(exc).category is ErrorCategory.unknown


def test_classify_generic_exception_is_unknown() -> None:
    assert classify(ValueError("boom")).category is ErrorCategory.unknown


def test_classify_returns_table_entry() -> None:
    exc = _api_error(RateLimitError, 429, {"message": "rate"})
    assert classify(exc) is CLASSIFICATION_TABLE[ErrorCategory.rate_limit]


# --- 3.3 guard: classify() never yields reserved codes for reachable LLM errors ---


def test_classify_never_yields_reserved() -> None:
    reserved = {
        ErrorCategory.tool_timeout,
        ErrorCategory.mcp_disconnect,
        ErrorCategory.sandbox_oom,
        ErrorCategory.sandbox_timeout,
    }
    reachable = [
        _api_error(RateLimitError, 429, {"message": "rate"}),
        _api_error(APIStatusError, 503, {"message": "unavailable"}),
        _api_error(AuthenticationError, 401, {"message": "bad key"}),
        _api_error(PermissionDeniedError, 403, {"message": "forbidden"}),
        _api_error(
            BadRequestError,
            400,
            {"message": "ctx", "code": "context_length_exceeded"},
        ),
        _api_error(BadRequestError, 400, {"message": "bad", "code": "x"}),
        _api_error(APIStatusError, 500, {"message": "boom"}),
        ValueError("boom"),
        RuntimeError("crash"),
    ]
    for exc in reachable:
        assert classify(exc).category not in reserved


def test_timeout_error_classified_as_tool_timeout():
    # T2 wires the reserved tool_timeout code to its error source. asyncio.wait_for
    # raises TimeoutError (asyncio.TimeoutError is an alias for it on 3.11+).
    from fleetent.runtime.error_classifier import CLASSIFICATION_TABLE, ErrorCategory, classify

    c = classify(TimeoutError())
    assert c.category is ErrorCategory.tool_timeout
    # Flags must match the AR5 table entry, not be redefined.
    assert c == CLASSIFICATION_TABLE[ErrorCategory.tool_timeout]


# --- llm_timeout: LLM 请求层超时/连接错误（harden-im-llm-timeout-handling P1）---


def test_llm_timeout_flags_retry_and_switch() -> None:
    clf = CLASSIFICATION_TABLE[ErrorCategory.llm_timeout]
    assert clf.should_retry is True
    assert clf.should_switch_model is True
    assert clf.should_compress is False


def test_classify_httpx_read_timeout_is_llm_timeout() -> None:
    assert classify(httpx.ReadTimeout("read timed out")).category is ErrorCategory.llm_timeout


def test_classify_httpx_timeout_exception_is_llm_timeout() -> None:
    assert classify(httpx.TimeoutException("timed out")).category is ErrorCategory.llm_timeout


def test_classify_openai_api_timeout_is_llm_timeout() -> None:
    from openai import APITimeoutError

    assert classify(APITimeoutError(request=_REQ)).category is ErrorCategory.llm_timeout


def test_classify_openai_api_connection_error_is_llm_timeout() -> None:
    from openai import APIConnectionError

    exc = APIConnectionError(message="conn refused", request=_REQ)
    assert classify(exc).category is ErrorCategory.llm_timeout


def test_classify_llm_timeout_not_unknown() -> None:
    # 回归：超时此前误落 unknown（不重试不切换），现必须归 llm_timeout
    assert classify(httpx.ReadTimeout("x")).category is not ErrorCategory.unknown
