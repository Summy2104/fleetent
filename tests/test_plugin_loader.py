"""Tests for the plugin loader (AR7): scan PLUGINS_DIR, namespace-load enabled plugins."""

import dataclasses
import sys
import textwrap
from pathlib import Path

import pytest

from fleetent import plugin_loader, tool_registry


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tool_registry globals so plugin (un)registration never leaks across tests."""
    monkeypatch.setattr(tool_registry, "_registry", dict(tool_registry._registry))
    monkeypatch.setattr(tool_registry, "_risk_levels", dict(tool_registry._risk_levels))


def _write_plugin(
    root: Path,
    name: str,
    *,
    manifest: str | None = None,
    init_py: str | None = None,
) -> Path:
    """Create a plugin package dir under `root` with a plugin.yaml and optional __init__.py."""
    pkg = root / name
    pkg.mkdir(parents=True)
    if manifest is None:
        manifest = f"name: {name}\nenabled: true\n"
    (pkg / "plugin.yaml").write_text(manifest, encoding="utf-8")
    if init_py is not None:
        (pkg / "__init__.py").write_text(textwrap.dedent(init_py), encoding="utf-8")
    return pkg


@pytest.fixture
def plugins_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tmp plugins dir wired to PLUGINS_DIR and importable on sys.path."""
    root = tmp_path / "plugins"
    root.mkdir()
    monkeypatch.setattr(plugin_loader, "PLUGINS_DIR", str(root))
    monkeypatch.syspath_prepend(str(root))
    # Drop any modules imported by a prior test so importlib re-runs the @tool side effects.
    for mod in list(sys.modules):
        if mod.split(".")[0].endswith("_plugin") or mod.startswith("p_"):
            del sys.modules[mod]
    return root


# --- 2.1 PLUGINS_DIR + PluginMeta ------------------------------------------


def test_plugins_dir_defaults_to_local_plugins() -> None:
    assert plugin_loader.PLUGINS_DIR == "./plugins"


def test_resolve_dir_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_PLUGINS_DIR", "/custom/plugins")
    assert plugin_loader._resolve_plugins_dir(None) == "/custom/plugins"


def test_resolve_dir_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEETENT_PLUGINS_DIR", raising=False)
    monkeypatch.setattr(plugin_loader, "PLUGINS_DIR", "./plugins")
    assert plugin_loader._resolve_plugins_dir(None) == "./plugins"


def test_plugin_meta_fields() -> None:
    meta = plugin_loader.PluginMeta(name="crm_tools", enabled=True, path="/x/crm_tools")
    assert meta.name == "crm_tools"
    assert meta.enabled is True
    assert meta.path == "/x/crm_tools"


def test_plugin_meta_is_frozen() -> None:
    meta = plugin_loader.PluginMeta(name="crm_tools", enabled=True, path="/x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        meta.name = "other"  # type: ignore[misc]


# --- 2.3 directory scan -----------------------------------------------------


def test_missing_dir_returns_empty_no_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin_loader, "PLUGINS_DIR", "/nonexistent/plugins/dir")
    assert plugin_loader.load_plugins() == []


def test_only_subdirs_with_manifest_recognised(plugins_root: Path) -> None:
    (plugins_root / "not_a_plugin").mkdir()  # no plugin.yaml
    (plugins_root / "loose_file.txt").write_text("x", encoding="utf-8")
    _write_plugin(
        plugins_root,
        "p_alpha",
        init_py="""
        from fleetent.tool_registry import tool

        @tool
        def ping() -> str:
            "ping"
            return "pong"
        """,
    )
    metas = plugin_loader.load_plugins()
    assert [m.name for m in metas] == ["p_alpha"]


# --- 3.1 enabled filter -----------------------------------------------------


def test_enabled_false_plugin_skipped_not_imported(plugins_root: Path) -> None:
    _write_plugin(
        plugins_root,
        "p_disabled",
        manifest="name: p_disabled\nenabled: false\n",
        init_py="raise RuntimeError('must not be imported')\n",
    )
    metas = plugin_loader.load_plugins()
    # Manifest parsed (so it is reported), but disabled -> never imported.
    assert [m.name for m in metas] == ["p_disabled"]
    assert metas[0].enabled is False
    assert "p_disabled" not in sys.modules


def test_enabled_missing_defaults_to_disabled(plugins_root: Path) -> None:
    _write_plugin(
        plugins_root,
        "p_default",
        manifest="name: p_default\n",
        init_py="raise RuntimeError('must not be imported')\n",
    )
    metas = plugin_loader.load_plugins()
    assert metas[0].enabled is False
    assert "p_default" not in sys.modules


# --- 3.3 namespacing --------------------------------------------------------


def test_enabled_plugin_tool_is_namespaced(plugins_root: Path) -> None:
    _write_plugin(
        plugins_root,
        "p_crm",
        init_py="""
        from fleetent.tool_registry import tool

        @tool(risk_level="medium")
        def lookup(account: str) -> str:
            "look up a CRM account"
            return account
        """,
    )
    plugin_loader.load_plugins()
    names = {s["function"]["name"] for s in tool_registry.get_schemas()}
    assert "p_crm__lookup" in names
    assert "lookup" not in names
    assert tool_registry.get_risk_level("p_crm__lookup") == "medium"


def test_indirect_import_does_not_namespace_foreign_tools(
    plugins_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A plugin whose __init__.py imports a *separate* registration-side-effect
    # module (defining @tool functions not yet registered) must namespace only
    # its own tools — the foreign module's freshly registered keys stay bare,
    # because they belong to a different __module__ (D1 owner filter).
    helper_root = tmp_path / "helpers"
    helper_root.mkdir()
    (helper_root / "foreign_side_effect.py").write_text(
        textwrap.dedent(
            """
            from fleetent.tool_registry import tool

            @tool
            def foreign_tool(x: str) -> str:
                "foreign"
                return x
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(helper_root))
    sys.modules.pop("foreign_side_effect", None)

    _write_plugin(
        plugins_root,
        "p_indirect",
        init_py="""
        import foreign_side_effect  # noqa: F401 — registers foreign_tool as a side effect

        from fleetent.tool_registry import tool

        @tool
        def own(x: str) -> str:
            "own tool"
            return x
        """,
    )
    plugin_loader.load_plugins()
    names = {s["function"]["name"] for s in tool_registry.get_schemas()}
    assert "p_indirect__own" in names
    # The foreign module's tool is new but not owned by the plugin package, so it
    # is left bare and NOT pulled into the plugin namespace.
    assert "foreign_tool" in tool_registry._registry
    assert "p_indirect__foreign_tool" not in tool_registry._registry


# --- 4.1 / 4.3 fault tolerance ---------------------------------------------


def _good_plugin(root: Path, name: str) -> None:
    _write_plugin(
        root,
        name,
        init_py=f"""
        from fleetent.tool_registry import tool

        @tool
        def act(x: str) -> str:
            "{name} act"
            return x
        """,
    )


def test_invalid_yaml_skipped_others_load(plugins_root: Path) -> None:
    _write_plugin(plugins_root, "p_bad", manifest="name: [unclosed\n")
    _good_plugin(plugins_root, "p_good")
    metas = plugin_loader.load_plugins()
    assert [m.name for m in metas] == ["p_good"]
    assert "p_good__act" in tool_registry._registry


def test_non_mapping_manifest_skipped(plugins_root: Path) -> None:
    _write_plugin(plugins_root, "p_list", manifest="- just\n- a\n- list\n")
    _good_plugin(plugins_root, "p_good")
    metas = plugin_loader.load_plugins()
    assert [m.name for m in metas] == ["p_good"]


def test_missing_name_skipped(plugins_root: Path) -> None:
    _write_plugin(plugins_root, "p_noname", manifest="enabled: true\n")
    _good_plugin(plugins_root, "p_good")
    metas = plugin_loader.load_plugins()
    assert [m.name for m in metas] == ["p_good"]


def test_import_failure_skipped_others_load(plugins_root: Path) -> None:
    _write_plugin(
        plugins_root,
        "p_boom",
        init_py="raise RuntimeError('boom on import')\n",
    )
    _good_plugin(plugins_root, "p_good")
    metas = plugin_loader.load_plugins()
    assert [m.name for m in metas] == ["p_good"]
    assert "p_good__act" in tool_registry._registry


def test_one_bad_plugin_does_not_block_others(plugins_root: Path) -> None:
    _write_plugin(plugins_root, "p_aaa_bad", init_py="raise ValueError('nope')\n")
    _good_plugin(plugins_root, "p_zzz_good")
    plugin_loader.load_plugins()
    assert "p_zzz_good__act" in tool_registry._registry


# --- 4.5 namespace uniqueness (D6) -----------------------------------------


def test_plugin_name_colliding_with_builtin_skipped(plugins_root: Path) -> None:
    # Register a fake builtin whose bare name collides with the plugin name.
    @tool_registry.tool
    def crmx(x: str) -> str:
        "fake builtin"
        return x

    _write_plugin(
        plugins_root,
        "p_crmx",
        manifest="name: crmx\nenabled: true\n",
        init_py="""
        from fleetent.tool_registry import tool

        @tool
        def lookup(x: str) -> str:
            "lookup"
            return x
        """,
    )
    metas = plugin_loader.load_plugins()
    assert metas == []
    # The existing builtin key is untouched; no namespaced rewrite happened.
    assert "crmx" in tool_registry._registry
    assert "crmx__lookup" not in tool_registry._registry


def test_plugin_name_colliding_with_mcp_server_skipped(
    plugins_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import mcp_client

    monkeypatch.setattr(mcp_client, "_server_registry", {"crm_mcp": object()})
    _write_plugin(
        plugins_root,
        "p_crm_mcp",
        manifest="name: crm_mcp\nenabled: true\n",
        init_py="""
        from fleetent.tool_registry import tool

        @tool
        def lookup(x: str) -> str:
            "lookup"
            return x
        """,
    )
    metas = plugin_loader.load_plugins()
    assert metas == []
    assert "crm_mcp__lookup" not in tool_registry._registry


def test_two_plugins_same_name_second_skipped(plugins_root: Path) -> None:
    _write_plugin(
        plugins_root,
        "p_first",
        manifest="name: dup\nenabled: true\n",
        init_py="""
        from fleetent.tool_registry import tool

        @tool
        def alpha(x: str) -> str:
            "alpha"
            return x
        """,
    )
    _write_plugin(
        plugins_root,
        "p_second",
        manifest="name: dup\nenabled: true\n",
        init_py="""
        from fleetent.tool_registry import tool

        @tool
        def beta(x: str) -> str:
            "beta"
            return x
        """,
    )
    metas = plugin_loader.load_plugins()
    assert [m.name for m in metas] == ["dup"]
    assert "dup__alpha" in tool_registry._registry
    assert "dup__beta" not in tool_registry._registry


# --- 5.3 expand_plugin_patterns + schema-filter authorization --------------


def test_expand_plugin_patterns() -> None:
    assert plugin_loader.expand_plugin_patterns(["crm_tools"]) == ["crm_tools__*"]
    assert plugin_loader.expand_plugin_patterns(["a", "b"]) == ["a__*", "b__*"]
    assert plugin_loader.expand_plugin_patterns([]) == []


def test_plugin_tool_visible_only_when_namespace_allowed(plugins_root: Path) -> None:
    from fleetent.agent_policy import check_tool_access

    _write_plugin(
        plugins_root,
        "p_crm2",
        init_py="""
        from fleetent.tool_registry import tool

        @tool
        def lookup(x: str) -> str:
            "lookup"
            return x
        """,
    )
    plugin_loader.load_plugins()
    schemas = tool_registry.get_schemas()

    # Authorized: expanded plugin pattern admits the namespaced tool.
    allowed = plugin_loader.expand_plugin_patterns(["p_crm2"])
    visible: set[str] = {
        s["function"]["name"] for s in schemas if check_tool_access(s["function"]["name"], allowed)
    }
    assert "p_crm2__lookup" in visible

    # Unauthorized: a different agent (no p_crm2 in plugins) cannot see it.
    other: list[str] = ["search"]
    hidden: set[str] = {
        s["function"]["name"] for s in schemas if check_tool_access(s["function"]["name"], other)
    }
    assert "p_crm2__lookup" not in hidden
