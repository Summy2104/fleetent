import re
from pathlib import Path

import pytest

from fleetent.knowledge_base.retrieval.evaluation import (
    REQUIRED_FIXTURE_FIELDS,
    FixtureValidationError,
    RealEmbeddingEvaluationSkipped,
    assert_query_expectations,
    load_fixtures,
    requires_semantic_embedding,
    run_deterministic_fixture,
    run_real_embedding_fixture,
    validate_fixture,
)


def test_fixture_validation_requires_explicit_schema_fields() -> None:
    fixture = {
        "name": "support handbook retrieval",
        "documents": [
            {
                "filename": "support.md",
                "content": "Escalate payroll incidents to HR operations.",
            }
        ],
        "queries": [
            {
                "text": "Who handles payroll incidents?",
                "top_k": 3,
                "expected_chunks": ["payroll incidents"],
                "forbidden_chunks": ["database failover"],
            }
        ],
        "expected_chunks": ["payroll incidents"],
        "forbidden_chunks": ["database failover"],
    }

    validate_fixture(fixture)

    assert set(REQUIRED_FIXTURE_FIELDS) == set(fixture)


@pytest.mark.parametrize("missing_field", sorted(REQUIRED_FIXTURE_FIELDS))
def test_fixture_validation_rejects_missing_required_fields(missing_field: str) -> None:
    fixture = {
        "name": "support handbook retrieval",
        "documents": [
            {
                "filename": "support.md",
                "content": "Escalate payroll incidents to HR operations.",
            }
        ],
        "queries": [
            {
                "text": "Who handles payroll incidents?",
                "expected_chunks": ["payroll incidents"],
                "forbidden_chunks": [],
            }
        ],
        "expected_chunks": ["payroll incidents"],
        "forbidden_chunks": [],
    }
    del fixture[missing_field]

    with pytest.raises(FixtureValidationError):
        validate_fixture(fixture)


def test_fixture_loader_returns_required_knowledge_base_scenarios() -> None:
    fixtures = load_fixtures()

    assert {fixture["name"] for fixture in fixtures} == {
        "support handbook vector retrieval",
        "tenant knowledge isolation",
        "cjk hybrid retrieval",
        "semantic paraphrase retrieval",
    }
    for fixture in fixtures:
        validate_fixture(fixture)


def test_fixture_validation_accepts_the_semantic_embedding_requirement() -> None:
    fixture = _mode_fixture()
    fixture["requires"] = "semantic_embedding"

    validate_fixture(fixture)

    assert requires_semantic_embedding(fixture) is True


def test_fixture_without_requires_does_not_need_semantic_embedding() -> None:
    assert requires_semantic_embedding(_mode_fixture()) is False


def test_fixture_validation_rejects_an_unknown_requirement() -> None:
    fixture = _mode_fixture()
    fixture["requires"] = "a_gpu"

    with pytest.raises(FixtureValidationError, match="requires"):
        validate_fixture(fixture)


async def test_deterministic_runner_ingests_documents_and_validates_top_k(
    tmp_path, monkeypatch
) -> None:
    fixture = {
        "name": "support handbook retrieval",
        "documents": [
            {
                "filename": "payroll.md",
                "content": "Payroll incidents require HR operations escalation.",
            },
            {
                "filename": "database.md",
                "content": "Database failover incidents require platform escalation.",
            },
        ],
        "queries": [
            {
                "text": "payroll incidents HR operations",
                "top_k": 1,
                "expected_chunks": ["Payroll incidents require HR operations escalation"],
                "forbidden_chunks": ["Database failover incidents"],
            }
        ],
        "expected_chunks": ["Payroll incidents require HR operations escalation"],
        "forbidden_chunks": ["Database failover incidents"],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert result.db_path == tmp_path / "knowledge-base-retrieval-eval.db"
    assert result.vector_db_path == tmp_path / "knowledge-base-retrieval-vectors.db"
    assert result.document_count == 2
    assert result.query_results[0].query == "payroll incidents HR operations"
    assert result.metrics.recall_at_k == 1.0
    assert result.metrics.mrr == 1.0
    assert result.query_results[0].ranked_hit is not None
    assert result.query_results[0].ranked_hit.rank == 1
    assert result.query_results[0].ranked_hit.reciprocal_rank == 1.0
    assert_query_expectations(result.query_results[0])


async def test_forbidden_chunks_are_rejected_after_fixture_run(tmp_path, monkeypatch) -> None:
    fixture = {
        "name": "support handbook retrieval",
        "documents": [
            {
                "filename": "support.md",
                "content": "Payroll incidents require HR operations escalation.",
            }
        ],
        "queries": [
            {
                "text": "payroll incidents",
                "top_k": 1,
                "expected_chunks": ["Payroll incidents"],
                "forbidden_chunks": ["Payroll incidents"],
            }
        ],
        "expected_chunks": ["Payroll incidents"],
        "forbidden_chunks": ["Payroll incidents"],
    }

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    with pytest.raises(AssertionError, match="forbidden chunk found"):
        assert_query_expectations(result.query_results[0])


async def test_runner_isolates_sqlite_and_vector_store_from_data_dir(tmp_path, monkeypatch) -> None:
    fixture = load_fixtures()[0]
    data_db = Path("data/fleetent.db").resolve()

    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert result.db_path.parent == tmp_path
    assert result.vector_db_path.parent == tmp_path
    assert result.db_path.resolve() != data_db
    assert result.vector_db_path.resolve() != data_db


async def test_real_embedding_evaluation_skips_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_EVAL_REAL_EMBEDDING", raising=False)

    with pytest.raises(RealEmbeddingEvaluationSkipped):
        await run_real_embedding_fixture(load_fixtures()[0], tmp_path, monkeypatch)


async def test_real_embedding_evaluation_skips_without_provider_credentials(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FLEETENT_EVAL_REAL_EMBEDDING", "1")
    monkeypatch.setenv("FLEETENT_EVAL_EMBEDDING_ENDPOINT", "http://embedding.test/v1")
    monkeypatch.setenv("FLEETENT_EVAL_EMBEDDING_MODEL", "bge-m3")
    monkeypatch.delenv("FLEETENT_EVAL_EMBEDDING_API_KEY", raising=False)

    with pytest.raises(RealEmbeddingEvaluationSkipped):
        await run_real_embedding_fixture(load_fixtures()[0], tmp_path, monkeypatch)


def _deterministic_fixtures() -> list[dict]:
    return [f for f in load_fixtures() if not requires_semantic_embedding(f)]


def _semantic_fixtures() -> list[dict]:
    return [f for f in load_fixtures() if requires_semantic_embedding(f)]


@pytest.mark.parametrize("fixture", _deterministic_fixtures(), ids=lambda fixture: fixture["name"])
async def test_knowledge_base_retrieval_fixture_expectations(
    fixture, tmp_path, monkeypatch
) -> None:
    result = await run_deterministic_fixture(fixture, tmp_path, monkeypatch)

    assert result.metrics.recall_at_k == 1.0
    assert result.metrics.mrr == 1.0
    for query_result in result.query_results:
        assert query_result.ranked_hit is not None
        assert query_result.ranked_hit.rank >= 1
        assert_query_expectations(query_result)


# ── the evaluation set's own teeth ──


def test_the_suite_actually_contains_a_semantic_fixture() -> None:
    """Without this, the guard below would pass over an empty list and prove nothing."""
    assert _semantic_fixtures(), "expected at least one fixture requiring semantic embedding"


def _shared_wording(query: str, target: str) -> set[str]:
    """Wording a keyword matcher could latch onto: shared ASCII words and shared CJK bigrams.

    Deliberately not built from the production tokenizer — this checks a property of the fixture,
    and reusing the tokenizer would make it agree with whatever that tokenizer happens to do.
    The CJK half is restricted to pairs of CJK characters so an English query cannot collide with
    an English target on incidental letter pairs.
    """
    q, t = query.casefold(), target.casefold()
    shared = {word for word in q.split() if word and word in t}
    cjk = "一-鿿"
    for i in range(len(q) - 1):
        pair = q[i : i + 2]
        if all(re.match(f"[{cjk}]", char) for char in pair) and pair in t:
            shared.add(pair)
    return shared


@pytest.mark.parametrize("fixture", _semantic_fixtures(), ids=lambda fixture: fixture["name"])
def test_semantic_fixture_queries_share_no_wording_with_their_target(fixture) -> None:
    """The first way this fixture can rot: a query drifts into reusing its target's words.

    Once it does, word overlap alone answers the query and the fixture stops measuring semantics
    — which is exactly how the pre-existing fixtures ended up scoring 1.000 under every
    embedding, real or not.
    """
    documents = [document["content"] for document in fixture["documents"]]

    for query in fixture["queries"]:
        for snippet in query["expected_chunks"]:
            target = next(content for content in documents if snippet in content)
            shared = _shared_wording(query["text"], target)
            assert not shared, (
                f"query {query['text']!r} shares wording {sorted(shared)} with its target; "
                "word overlap could answer it without any semantic matching"
            )


@pytest.mark.parametrize("fixture", _semantic_fixtures(), ids=lambda fixture: fixture["name"])
def test_semantic_fixture_targets_are_never_the_first_document(fixture) -> None:
    """The second way it can rot: a target sits where a signal-free retriever wins by default.

    With no usable embedding every score ties, and the winner is then decided by the backend's
    tie-break — insertion order on Milvus. A target in first position therefore scores for free.
    Measured: moving one target to the front lifted the deterministic provider from 0.00 to 0.50
    on this fixture without changing a single word of it.
    """
    first_document = fixture["documents"][0]["content"]

    for query in fixture["queries"]:
        for snippet in query["expected_chunks"]:
            assert snippet not in first_document, (
                f"query {query['text']!r} targets the first document, which wins every tie; "
                "move a distractor to the front"
            )


# ── per-query search mode (harness must be able to evaluate hybrid / keyword) ──


def _mode_fixture(**query_overrides: object) -> dict:
    """Minimal single-query fixture; query fields are overridable per test."""
    query: dict = {
        "text": "payroll incidents",
        "top_k": 1,
        "expected_chunks": ["Payroll incidents"],
        "forbidden_chunks": [],
    }
    query.update(query_overrides)
    return {
        "name": "mode fixture",
        "documents": [
            {
                "filename": "payroll.md",
                "content": "Payroll incidents require HR operations escalation.",
            }
        ],
        "queries": [query],
        "expected_chunks": ["Payroll incidents"],
        "forbidden_chunks": [],
    }


@pytest.mark.parametrize("mode", ["vector", "keyword", "hybrid"])
def test_fixture_validation_accepts_supported_query_modes(mode: str) -> None:
    validate_fixture(_mode_fixture(mode=mode))


def test_fixture_validation_rejects_unknown_query_mode() -> None:
    with pytest.raises(FixtureValidationError, match="mode"):
        validate_fixture(_mode_fixture(mode="semantic"))


def test_fixture_validation_rejects_non_boolean_rerank() -> None:
    with pytest.raises(FixtureValidationError, match="rerank"):
        validate_fixture(_mode_fixture(mode="hybrid", rerank="yes"))


def test_fixture_validation_rejects_rerank_outside_hybrid_mode() -> None:
    """Mirrors the runtime constraint: rerank is only supported for hybrid search."""
    with pytest.raises(FixtureValidationError, match="hybrid"):
        validate_fixture(_mode_fixture(mode="vector", rerank=True))


async def test_runner_threads_query_mode_and_rerank_into_search(tmp_path, monkeypatch) -> None:
    """The harness must forward per-query mode/rerank, not silently default to vector."""
    from fleetent.knowledge_base import runtime as kb_runtime

    calls: list[dict] = []

    async def _spy(query, **kwargs):
        calls.append({"query": query, **kwargs})
        return []

    monkeypatch.setattr(kb_runtime, "search", _spy)

    await run_deterministic_fixture(_mode_fixture(mode="hybrid", rerank=True), tmp_path)

    assert len(calls) == 1
    assert calls[0]["mode"] == "hybrid"
    assert calls[0]["rerank"] is True


async def test_runner_defaults_to_vector_mode_when_query_omits_it(tmp_path, monkeypatch) -> None:
    from fleetent.knowledge_base import runtime as kb_runtime

    calls: list[dict] = []

    async def _spy(query, **kwargs):
        calls.append({"query": query, **kwargs})
        return []

    monkeypatch.setattr(kb_runtime, "search", _spy)

    await run_deterministic_fixture(_mode_fixture(), tmp_path)

    assert calls[0]["mode"] == "vector"
    assert calls[0]["rerank"] is False


async def test_hybrid_mode_actually_fuses_with_rrf(tmp_path) -> None:
    """Not a spy: hybrid must really run vector + keyword + RRF.

    Discriminated by score scale rather than a magic threshold: RRF contributes
    1/(k+rank) per list with k=60, so a chunk ranked first by both the vector and the
    keyword leg tops out at 2/61. A cosine score is not bounded that way.
    """
    rrf_ceiling = 2.0 / 61.0

    vector_result = await run_deterministic_fixture(_mode_fixture(mode="vector"), tmp_path / "v")
    hybrid_result = await run_deterministic_fixture(_mode_fixture(mode="hybrid"), tmp_path / "h")

    vector_top = vector_result.query_results[0].chunks[0]
    hybrid_top = hybrid_result.query_results[0].chunks[0]

    assert vector_top.score > rrf_ceiling, "vector mode should report a cosine-scale score"
    assert hybrid_top.score <= rrf_ceiling, "hybrid mode should report an RRF-scale score"
    assert_query_expectations(hybrid_result.query_results[0])


# ── CJK retrieval (the keyword leg is the only one carrying Chinese signal) ──


def _cjk_query_fixture(mode: str) -> dict:
    """The shipped CJK regression fixture, re-pointed at one query in the given mode."""
    fixture = next(f for f in load_fixtures() if f["name"] == "cjk hybrid retrieval")
    return {
        **fixture,
        "queries": [
            {
                "text": "数据库故障",
                "mode": mode,
                "top_k": 3,
                "expected_chunks": ["数据库故障需要联系平台团队处理"],
                "forbidden_chunks": [],
            }
        ],
    }


async def test_runner_defaults_to_the_sqlite_vector_backend(tmp_path) -> None:
    """Backward compatibility: every pre-existing caller passes no backend and must keep sqlite."""
    from fleetent.knowledge_base.retrieval.evaluation import DEFAULT_VECTOR_BACKEND

    assert DEFAULT_VECTOR_BACKEND == "sqlite"

    result = await run_deterministic_fixture(_mode_fixture(), tmp_path)

    assert result.vector_db_path.exists()
    assert_query_expectations(result.query_results[0])


async def test_runner_can_evaluate_against_the_milvus_vector_backend(tmp_path) -> None:
    """The harness must be able to measure the backend a deployment actually runs.

    Retrieval quality is a property of the backend plus the embedding, so a harness locked to
    sqlite cannot answer whether switching either one helped. Asserting the fixture's own
    expectations (rather than just "it ran") is what makes this a retrieval check instead of a
    smoke test.
    """
    pytest.importorskip("pymilvus", reason="Milvus backend requires pymilvus[milvus_lite]")

    result = await run_deterministic_fixture(_mode_fixture(), tmp_path, vector_backend="milvus")

    assert result.query_results[0].ranked_hit is not None
    assert result.query_results[0].ranked_hit.rank == 1
    assert_query_expectations(result.query_results[0])


def test_runner_rejects_an_unknown_vector_backend() -> None:
    from fleetent.knowledge_base.retrieval.evaluation import SUPPORTED_VECTOR_BACKENDS

    assert set(SUPPORTED_VECTOR_BACKENDS) == {"sqlite", "milvus"}


async def test_unknown_vector_backend_fails_fast(tmp_path) -> None:
    with pytest.raises(FixtureValidationError, match="vector backend"):
        await run_deterministic_fixture(_mode_fixture(), tmp_path, vector_backend="qdrant")


# ── rerank must be measurable, not just configurable ──


async def test_runner_leaves_rerank_disabled_by_default(tmp_path) -> None:
    """Rerank stays off unless asked for: a fixture run must not reach out to a reranker."""
    from fleetent.knowledge_base.retrieval.evaluation import DEFAULT_RERANK_BACKEND

    assert DEFAULT_RERANK_BACKEND == "disabled"

    result = await run_deterministic_fixture(_mode_fixture(mode="hybrid", rerank=False), tmp_path)

    assert_query_expectations(result.query_results[0])


async def test_runner_can_evaluate_with_a_reranker_wired_in(tmp_path) -> None:
    """The harness must be able to run the rerank leg, or its effect can never be measured.

    Uses the deterministic reranker so this stays offline: the point is that the rerank stage is
    genuinely reached and its ordering is what comes back, not that a particular model is good.
    """
    result = await run_deterministic_fixture(
        _mode_fixture(mode="hybrid", rerank=True),
        tmp_path,
        rerank_backend="deterministic",
    )

    assert result.query_results[0].ranked_hit is not None
    assert_query_expectations(result.query_results[0])


async def test_rerank_request_without_a_provider_fails_closed_to_fusion_order(tmp_path) -> None:
    """With rerank disabled, asking for it must degrade to the fused order, not crash the run.

    ``_rerank_hybrid_candidates`` catches provider failures and returns the pre-rerank
    candidates. Pinning that here documents it as intended behaviour: a dead reranker degrades
    retrieval quality, it does not take the query down with it.
    """
    result = await run_deterministic_fixture(
        _mode_fixture(mode="hybrid", rerank=True), tmp_path, rerank_backend="disabled"
    )

    assert result.query_results[0].chunks, "a disabled reranker must not empty the result set"
    assert_query_expectations(result.query_results[0])


def test_runner_rejects_an_unknown_rerank_backend() -> None:
    from fleetent.knowledge_base.retrieval.evaluation import SUPPORTED_RERANK_BACKENDS

    assert set(SUPPORTED_RERANK_BACKENDS) == {"disabled", "deterministic", "http"}


async def test_unknown_rerank_backend_fails_fast(tmp_path) -> None:
    with pytest.raises(FixtureValidationError, match="rerank backend"):
        await run_deterministic_fixture(_mode_fixture(), tmp_path, rerank_backend="cohere")


async def test_chinese_query_is_discriminated_by_the_keyword_leg_alone(tmp_path) -> None:
    """Guards the index/query tokenizer agreement that makes Chinese searchable at all.

    The deterministic embedding tokenizes with ``str.split()``, so a Chinese sentence is a
    single opaque token and every document scores exactly 0.0 — vector ordering then falls
    through to the chunk UUID, i.e. a coin flip. The keyword leg is therefore the only source
    of Chinese signal, and it produced nothing until the FTS index stored the same bigram
    terms the query emits. Asserting "keyword isolates exactly one document" rather than
    "hybrid ranks it first" keeps the failure pointed at the tokenizer instead of at RRF.
    """
    vector_chunks = (
        (await run_deterministic_fixture(_cjk_query_fixture("vector"), tmp_path / "vector"))
        .query_results[0]
        .chunks
    )
    keyword_result = await run_deterministic_fixture(
        _cjk_query_fixture("keyword"), tmp_path / "keyword"
    )

    assert {chunk.score for chunk in vector_chunks} == {0.0}, (
        "the vector leg is expected to carry no Chinese signal; if it now does, this test's "
        "premise changed and the assertion below no longer isolates the keyword leg"
    )

    keyword_chunks = keyword_result.query_results[0].chunks
    assert len(keyword_chunks) == 1
    assert keyword_chunks[0].content.startswith("数据库故障需要联系平台团队处理")
    assert_query_expectations(keyword_result.query_results[0])
