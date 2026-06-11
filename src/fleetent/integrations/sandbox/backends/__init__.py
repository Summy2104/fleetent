"""Concrete sandbox backends (Docker, microsandbox).

Each backend subclasses `fleetent.integrations.sandbox.backend.BaseSandboxBackend`.
The factory selects one per configuration; cross-package callers import the public
API from `fleetent.integrations.sandbox`, not from here.
"""
