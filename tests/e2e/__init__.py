"""E2E test package marker.

Present so e2e helper packages (e.g. ``slack_autonomous``) are importable by unit
tests via the ``tests.e2e.*`` path, consistent with how ``tests.integration.*`` is
imported in ``tests/conftest.py``.
"""
