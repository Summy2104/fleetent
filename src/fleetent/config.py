import logging

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    slack_bot_token: str = ""
    slack_app_token: str = ""
    telegram_bot_token: str = ""
    permission_gate_medium_timeout_seconds: int = 300
    permission_gate_high_timeout_seconds: int = 3600
    context_max_tokens: int = 200_000
    context_tmax_ratio: float = 0.8
    context_tretained_ratio: float = 0.6
    context_keep_recent: int = 10
    # Upper bound on leading user messages kept whole as the initial intent in the
    # compression head (AR13 D2). 2 covers the common "lead-in + real ask" split
    # opening, especially on IM channels. Optional; default preserves existing
    # deployments.
    compression_initial_intent_max: int = 2
    session_ttl_days: int = 30
    session_max_total_mb: int = 1024
    session_max_count: int = 10000
    # How often the internal save()-triggered maintenance may run a full cleanup
    # scan (seconds). Time-gated so the rglob stays cheap under message volume.
    session_cleanup_interval_seconds: float = 3600.0
    agent_max_turns: int = 50
    agent_max_consecutive_failures: int = 3
    # Per sub-agent wall-clock timeout (AR20). A sub-agent runs a full agent_loop
    # round (multi-turn LLM + tools), an order longer than a single tool call, so
    # this guard is orthogonal to the main task budget. 300s balances "fits a real
    # sub-task" against "surfaces a hang fast".
    sub_agent_timeout_seconds: int = 300
    # Two-dimensional iteration budget (AR2). max_turns reuses agent_max_turns
    # above (the step dimension is folded into the budget). -1 = unlimited; the
    # token dimension defaults to unlimited so existing deployments keep
    # behaving as a pure step budget until configured.
    agent_max_tokens: int = -1
    # Grace Call reserved budget (AR2 D3): on budget exhaustion the loop spends a
    # last LLM call summarizing progress, capped at max(round(max_tokens*ratio),
    # min_tokens). Floor guards a tiny main budget from reserving ~0 tokens.
    agent_grace_call_token_ratio: float = 0.05
    agent_grace_call_min_tokens: int = 512
    # Coarse loop detection (AR4): how many times one tool may repeat (same args,
    # signal A; or same successful result, signal B) within the detection window
    # before a hit. First hit warns the model; a repeat after that force-stops with
    # `loop_detected`. The detection window is derived from this and not separately
    # configurable, so the observable threshold semantics cannot drift.
    agent_loop_repeat_threshold: int = 3
    # AR10 per-call guardrail: strict back-to-back identical calls before tripping.
    # Aligned with agent_loop_repeat_threshold so ops reason about one repeat count.
    guardrail_repeat_threshold: int = 3
    # Optional escape hatch: top-level argument keys stripped before computing the
    # signal-A fingerprint (e.g. a volatile timestamp/attempt counter). Empty by
    # default; signal B already covers volatile-argument blind spots.
    loop_detect_ignore_arg_keys: list[str] = []
    provider_failure_threshold: int = 3
    provider_cooldown_seconds: int = 60
    log_format: str = "console"
    default_agent_name: str | None = None
    disabled_skills: list[str] = []
    # Self-hosted, OpenAI-compatible images endpoint (e.g. SD-WebUI / ComfyUI /
    # Flux behind a compat layer). Empty = unconfigured; the generate_image tool
    # returns an explicit failure rather than silently succeeding. Cloud-hosted
    # proprietary services (DALL·E / Midjourney) are forbidden by data sovereignty.
    image_gen_url: str = ""
    image_gen_model: str = "default"
    # Self-hosted, OpenAI-compatible vision endpoint (any VLM behind a compat
    # layer). Empty = unconfigured; the analyze_image tool returns an explicit
    # failure rather than silently succeeding. Cloud-hosted proprietary VLMs are
    # forbidden by data sovereignty.
    vision_url: str = ""
    vision_model: str = "default"


def configure_logging(settings: Settings) -> None:
    # NOTE: structlog.stdlib.add_logger_name reads `logger.name`, which only exists
    # on stdlib loggers — the PrintLogger from PrintLoggerFactory below has none, so
    # including it crashed every log call at emit time. It is intentionally omitted.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )
