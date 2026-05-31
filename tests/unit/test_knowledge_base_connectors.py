from pathlib import Path


def test_connector_boundary_public_api_is_importable():
    from fleetent.intelligence.knowledge_base.connectors import DataSource, DocumentRef

    assert DataSource is not None
    assert DocumentRef is not None


def test_document_ref_contains_connector_document_identity_and_location():
    from fleetent.intelligence.knowledge_base.connectors import DocumentRef

    ref = DocumentRef(
        id="local:runbook.md",
        filename="runbook.md",
        format="markdown",
        path="/allowed/runbook.md",
        url=None,
        metadata={"source_path": "/allowed/runbook.md"},
    )

    assert ref.id == "local:runbook.md"
    assert ref.filename == "runbook.md"
    assert ref.format == "markdown"
    assert ref.path == "/allowed/runbook.md"
    assert ref.url is None
    assert ref.metadata == {"source_path": "/allowed/runbook.md"}


def test_local_directory_source_requires_root_under_explicit_allowlist(tmp_path):
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectoryDataSource

    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    (allowed_root / "runbook.txt").write_text("inside", encoding="utf-8")
    (outside_root / "secret.txt").write_text("outside", encoding="utf-8")

    source = LocalDirectoryDataSource(root_path=allowed_root, allowed_roots=[allowed_root])

    assert [Path(ref.path).name for ref in source.list_documents()] == ["runbook.txt"]
    assert all(str(allowed_root) in ref.path for ref in source.list_documents())
    try:
        LocalDirectoryDataSource(root_path=outside_root, allowed_roots=[allowed_root])
    except ValueError as exc:
        assert "allowlisted root" in str(exc)
    else:
        raise AssertionError("outside local source root was accepted")


def test_local_directory_source_maps_supported_file_extensions(tmp_path):
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectoryDataSource

    root = tmp_path / "docs"
    root.mkdir()
    (root / "notes.txt").write_text("plain", encoding="utf-8")
    (root / "guide.md").write_text("# Guide", encoding="utf-8")
    (root / "page.html").write_text("<h1>Page</h1>", encoding="utf-8")
    (root / "legacy.htm").write_text("<h1>Legacy</h1>", encoding="utf-8")
    (root / "ignored.pdf").write_bytes(b"%PDF")

    source = LocalDirectoryDataSource(root_path=root, allowed_roots=[root])
    refs = source.list_documents()

    assert {ref.filename: ref.format for ref in refs} == {
        "guide.md": "markdown",
        "legacy.htm": "html",
        "notes.txt": "text",
        "page.html": "html",
    }


def test_local_directory_source_fetch_reads_content_and_preserves_path_metadata(tmp_path):
    from fleetent.intelligence.knowledge_base.connectors import LocalDirectoryDataSource

    root = tmp_path / "docs"
    nested = root / "team"
    nested.mkdir(parents=True)
    document_path = nested / "runbook.md"
    document_path.write_text("# Runbook\nRestart service", encoding="utf-8")

    source = LocalDirectoryDataSource(root_path=root, allowed_roots=[root])
    ref = source.list_documents()[0]

    assert ref.path == str(document_path.resolve())
    assert ref.metadata["source_path"] == str(document_path.resolve())
    assert ref.metadata["relative_path"] == "team/runbook.md"
    assert source.fetch(ref) == b"# Runbook\nRestart service"


def test_local_directory_source_fetch_rejects_path_traversal_outside_root(tmp_path):
    from fleetent.intelligence.knowledge_base.connectors import (
        DocumentRef,
        LocalDirectoryDataSource,
    )

    root = tmp_path / "docs"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    outside_path = outside / "secret.md"
    outside_path.write_text("secret", encoding="utf-8")
    source = LocalDirectoryDataSource(root_path=root, allowed_roots=[root])

    try:
        source.fetch(
            DocumentRef(
                id="local:secret.md",
                filename="secret.md",
                format="markdown",
                path=str(outside_path),
                metadata={"source_path": str(outside_path)},
            )
        )
    except ValueError as exc:
        assert "allowlisted root" in str(exc)
    else:
        raise AssertionError("path traversal outside local source root was accepted")
