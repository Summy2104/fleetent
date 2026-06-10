"""Agent runtime paths derive from the resolver.

Note: ``admin_cli.init_config`` is intentionally excluded — its file/dir lists
are a scaffold layout relative to an operator-chosen ``root`` argument, not
runtime path resolution, so they must stay relative.
"""


def _assert_derivation_in_clean_env(code: str) -> None:
    """Run an import-time derivation assertion in a child interpreter.

    Constants are frozen at import. Comparing an in-process constant against a
    call-time paths.X() is fragile: an ambient FLEETENT_HOME in the developer
    shell freezes a different base than a post-delenv call resolves. A child
    interpreter with FLEETENT_HOME stripped checks constant == derivation under
    one consistent environment.
    """
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "FLEETENT_HOME"}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_runtime_config_paths_derive_from_resolver() -> None:
    _assert_derivation_in_clean_env(
        "from fleetent import agent_config, paths; "
        "assert agent_config.AGENTS_DIR == paths.agents_dir(), agent_config.AGENTS_DIR"
    )
