from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import get_args, get_origin


def test_knowledge_provider_contract_is_hard_typed() -> None:
    from fleetent import long_term_ctx
    from fleetent.identity import Principal
    from fleetent.knowledge_base.core.models import KnowledgeChunk
    from fleetent.observability import KBRetrievalAuditContext

    alias_args = get_args(long_term_ctx.KnowledgeProvider)
    assert get_origin(long_term_ctx.KnowledgeProvider) is Callable
    assert alias_args[0] == [
        Principal,
        str,
        list[str],
        int,
        KBRetrievalAuditContext | None,
    ]
    assert alias_args[1] == Awaitable[list[KnowledgeChunk]]
