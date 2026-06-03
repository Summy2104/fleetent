"""connector_config submodule of the unified IM module (ex im_connector_config)."""


def test_connector_config_submodule_exposes_public_fns():
    from fleetent.platform.im_gateway_management import connector_config

    for name in (
        "resolve",
        "resolve_masked",
        "set_config",
        "seed_from_env",
        "PLATFORM_CONFIG_KEYS",
    ):
        assert hasattr(connector_config, name), name


def test_masking_preserved():
    from fleetent.platform.im_gateway_management import connector_config

    assert connector_config._mask("abcdefgh") == "****efgh"
    assert connector_config._mask("ab") == "****"


def test_legacy_connector_config_path_reexports_same_objects():
    from fleetent.platform.im_gateway_management import connector_config, im_connector_config

    assert im_connector_config.resolve is connector_config.resolve
    assert im_connector_config.set_config is connector_config.set_config
