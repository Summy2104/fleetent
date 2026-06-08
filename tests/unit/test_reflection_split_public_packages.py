import importlib


def test_reflection_split_public_packages_exist() -> None:
    modules = [
        "fleetent.reflection",
        "fleetent.governance.reflection_gate",
        "fleetent.platform.reflection_management",
    ]

    for module_name in modules:
        importlib.import_module(module_name)
