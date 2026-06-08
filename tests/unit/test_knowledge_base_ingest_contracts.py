import inspect

from fleetent.config import KnowledgeBaseSettings


def test_ingest_entrypoints_accept_injected_settings() -> None:
    from fleetent.knowledge_base.ingest import ingest_parsed, ingest_text

    text_hints = inspect.get_annotations(ingest_text, eval_str=True)
    parsed_hints = inspect.get_annotations(ingest_parsed, eval_str=True)

    assert text_hints["settings"] is KnowledgeBaseSettings
    assert parsed_hints["settings"] is KnowledgeBaseSettings


def test_ingest_entrypoints_do_not_read_default_kb_config() -> None:
    from fleetent.knowledge_base.ingest import ingest_parsed, ingest_text

    settings = KnowledgeBaseSettings()
    assert "_kb_config" not in inspect.getsource(ingest_text)
    assert "_kb_config" not in inspect.getsource(ingest_parsed)
    assert "settings=KnowledgeBaseSettings()" not in inspect.getsource(ingest_text)
    assert "settings: KnowledgeBaseSettings | None" not in inspect.getsource(ingest_text)
    assert settings is not None
