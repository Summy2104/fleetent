import importlib


def test_reflection_split_public_packages_exist() -> None:
    modules = [
        "fleetent.reflection",
        "fleetent.governance.reflection_gate",
        "fleetent.platform.reflection_management",
    ]

    for module_name in modules:
        importlib.import_module(module_name)


def test_reflection_split_internal_modules_exist() -> None:
    modules = [
        "fleetent.reflection.reflection",
        "fleetent.reflection.store",
    ]

    for module_name in modules:
        importlib.import_module(module_name)


def test_intelligence_reflection_path_remains_compatible() -> None:
    from fleetent.intelligence import reflection as legacy_reflection
    from fleetent.reflection.reflection import run_reflection as split_reflection_run

    assert hasattr(legacy_reflection, "run_reflection")
    assert legacy_reflection.run_reflection is split_reflection_run
