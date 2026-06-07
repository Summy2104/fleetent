"""Credential slot helpers shared by the console credential UI and materialize.

A credential slot is one ``*_env`` reference in an agent's materialized definition. Its
*mode* is not stored separately — a slot is ``inject`` iff the platform holds an encrypted
value for it (see [agent_secret_store]), otherwise ``operator`` (the deployment host's
``.env`` supplies the value). env-var names for freshly-authored slots (e.g. a Slack
connector) derive from a stable ``FLEETENT_AGENT_<NAME>_<SLOT>`` scheme; provider/MCP slots
reuse the env names already authored on those entities.
"""

import re

from fleetent.platform.secret_management import agent_secret_store

_ENV_NAME_PREFIX = "FLEETENT_AGENT"


def _upper_snake(value: str) -> str:
    """Uppercase, collapse any run of non-alphanumeric chars to a single underscore."""
    return re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").upper()


def derive_env_name(agent_name: str, slot: str) -> str:
    """Derive a stable env-var name for a freshly-authored credential slot."""
    return f"{_ENV_NAME_PREFIX}_{_upper_snake(agent_name)}_{_upper_snake(slot)}"


def assert_no_env_collisions(env_names: list[str]) -> None:
    """Fail loud when two slots map to the same env-var name."""
    seen: set[str] = set()
    for name in env_names:
        if name in seen:
            raise ValueError(f"duplicate credential env name: {name}")
        seen.add(name)


def slot_mode(agent_id: int, env_name: str) -> str:
    """Return 'inject' when the platform holds a value for this slot, else 'operator'."""
    return "inject" if agent_secret_store.status(agent_id, env_name) == "set" else "operator"
