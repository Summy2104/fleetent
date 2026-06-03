"""Re-export shim: skill registry moved to fleetent.skills.registry
(restructure-skills-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes (e.g. BUILTIN_SKILLS_DIR, _index) on
fleetent.skills.registry, not on this shim — ``import *`` copies names, so
patching the shim has no effect.
"""

from fleetent.skills.registry import *  # noqa: F401,F403
