def test_real_llm_entity_extraction_smoke_skips_without_opt_in(monkeypatch):
    from fleetent.intelligence.knowledge_base.extraction import real_llm_extraction_smoke

    monkeypatch.delenv("FLEETENT_KB_ENTITY_EXTRACTION_REAL_LLM", raising=False)

    result = real_llm_extraction_smoke()

    assert result.status == "skipped"
    assert "FLEETENT_KB_ENTITY_EXTRACTION_REAL_LLM=1" in result.reason
