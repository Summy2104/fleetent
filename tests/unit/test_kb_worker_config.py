from __future__ import annotations


def _set_worker_env(
    monkeypatch,
    *,
    queue_database_url: str,
    substrate_database_url: str,
    embedding_backend: str,
    embedding_endpoint: str,
    embedding_model: str,
    vault_addr: str,
    vault_token: str,
) -> None:
    monkeypatch.setenv("FLEETENT_KB_WORKER_QUEUE_DATABASE_URL", queue_database_url)
    monkeypatch.setenv("FLEETENT_KB_WORKER_SUBSTRATE_DATABASE_URL", substrate_database_url)
    monkeypatch.setenv("FLEETENT_KB_WORKER_EMBEDDING_BACKEND", embedding_backend)
    monkeypatch.setenv("FLEETENT_KB_WORKER_EMBEDDING_ENDPOINT", embedding_endpoint)
    monkeypatch.setenv("FLEETENT_KB_WORKER_EMBEDDING_MODEL", embedding_model)
    monkeypatch.setenv("FLEETENT_KB_WORKER_VAULT_ADDR", vault_addr)
    monkeypatch.setenv("FLEETENT_KB_WORKER_VAULT_TOKEN", vault_token)


def test_loads_kb_worker_env_file(monkeypatch, tmp_path) -> None:
    from fleetent.knowledge_base import worker

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    for name in (
        "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL",
        "FLEETENT_KB_WORKER_SUBSTRATE_DATABASE_URL",
        "FLEETENT_KB_WORKER_EMBEDDING_BACKEND",
        "FLEETENT_KB_WORKER_EMBEDDING_ENDPOINT",
        "FLEETENT_KB_WORKER_EMBEDDING_MODEL",
        "FLEETENT_KB_WORKER_VAULT_ADDR",
        "FLEETENT_KB_WORKER_VAULT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    worker_dir = tmp_path / "kb-worker"
    worker_dir.mkdir()
    (worker_dir / ".env").write_text(
        "\n".join(
            [
                "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=sqlite:////queue/from-file.db",
                "FLEETENT_KB_WORKER_SUBSTRATE_DATABASE_URL=sqlite:////substrate/from-file.db",
                "FLEETENT_KB_WORKER_EMBEDDING_BACKEND=http",
                "FLEETENT_KB_WORKER_EMBEDDING_ENDPOINT=http://embedder.internal/v1/embeddings",
                "FLEETENT_KB_WORKER_EMBEDDING_MODEL=kb-embed-file",
                "FLEETENT_KB_WORKER_VAULT_ADDR=http://vault.internal:8200",
                "FLEETENT_KB_WORKER_VAULT_TOKEN=token-from-file",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = worker.load_config()

    assert loaded.queue_database_url == "sqlite:////queue/from-file.db"
    assert loaded.substrate_database_url == "sqlite:////substrate/from-file.db"
    assert loaded.embedding_backend == "http"
    assert loaded.embedding_endpoint == "http://embedder.internal/v1/embeddings"
    assert loaded.embedding_model == "kb-embed-file"
    assert loaded.vault_addr == "http://vault.internal:8200"
    assert loaded.vault_token == "token-from-file"
    assert loaded.home_dir == tmp_path


def test_process_env_overrides(monkeypatch, tmp_path) -> None:
    from fleetent.knowledge_base import worker

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    _set_worker_env(
        monkeypatch,
        queue_database_url="sqlite:////queue/from-process.db",
        substrate_database_url="sqlite:////substrate/from-process.db",
        embedding_backend="deterministic",
        embedding_endpoint="http://embedder.process/v1/embeddings",
        embedding_model="kb-embed-process",
        vault_addr="http://vault.process:8200",
        vault_token="token-from-process",
    )
    worker_dir = tmp_path / "kb-worker"
    worker_dir.mkdir()
    (worker_dir / ".env").write_text(
        "\n".join(
            [
                "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=sqlite:////queue/from-file.db",
                "FLEETENT_KB_WORKER_SUBSTRATE_DATABASE_URL=sqlite:////substrate/from-file.db",
                "FLEETENT_KB_WORKER_EMBEDDING_BACKEND=http",
                "FLEETENT_KB_WORKER_EMBEDDING_ENDPOINT=http://embedder.file/v1/embeddings",
                "FLEETENT_KB_WORKER_EMBEDDING_MODEL=kb-embed-file",
                "FLEETENT_KB_WORKER_VAULT_ADDR=http://vault.file:8200",
                "FLEETENT_KB_WORKER_VAULT_TOKEN=token-from-file",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = worker.load_config()

    assert loaded.queue_database_url == "sqlite:////queue/from-process.db"
    assert loaded.substrate_database_url == "sqlite:////substrate/from-process.db"
    assert loaded.embedding_backend == "deterministic"
    assert loaded.embedding_endpoint == "http://embedder.process/v1/embeddings"
    assert loaded.embedding_model == "kb-embed-process"
    assert loaded.vault_addr == "http://vault.process:8200"
    assert loaded.vault_token == "token-from-process"


def test_missing_file_falls_back_to_process_env(monkeypatch, tmp_path) -> None:
    from fleetent.knowledge_base import worker

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    _set_worker_env(
        monkeypatch,
        queue_database_url="sqlite:////queue/process-only.db",
        substrate_database_url="sqlite:////substrate/process-only.db",
        embedding_backend="http",
        embedding_endpoint="http://embedder.process-only/v1/embeddings",
        embedding_model="kb-embed-process-only",
        vault_addr="http://vault.process-only:8200",
        vault_token="token-process-only",
    )

    loaded = worker.load_config()

    assert loaded.queue_database_url == "sqlite:////queue/process-only.db"
    assert loaded.substrate_database_url == "sqlite:////substrate/process-only.db"
    assert loaded.embedding_backend == "http"
    assert loaded.embedding_endpoint == "http://embedder.process-only/v1/embeddings"
    assert loaded.embedding_model == "kb-embed-process-only"
    assert loaded.vault_addr == "http://vault.process-only:8200"
    assert loaded.vault_token == "token-process-only"
    assert loaded.home_dir == tmp_path
