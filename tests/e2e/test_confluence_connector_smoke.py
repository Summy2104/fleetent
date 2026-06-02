from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    os.getenv("FLEETENT_CONFLUENCE_SMOKE") != "1",
    reason="Confluence smoke requires FLEETENT_CONFLUENCE_SMOKE=1",
)
async def test_confluence_smoke_requires_complete_cloud_api_token_configuration():
    required = {
        "FLEETENT_CONFLUENCE_BASE_URL": os.getenv("FLEETENT_CONFLUENCE_BASE_URL"),
        "FLEETENT_CONFLUENCE_USERNAME": os.getenv("FLEETENT_CONFLUENCE_USERNAME"),
        "FLEETENT_CONFLUENCE_CREDENTIAL_REF": os.getenv("FLEETENT_CONFLUENCE_CREDENTIAL_REF"),
        "FLEETENT_CONFLUENCE_SCOPE": os.getenv("FLEETENT_CONFLUENCE_SCOPE"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        pytest.skip(f"missing Confluence smoke configuration: {', '.join(missing)}")

    pytest.skip("real Confluence client is not wired into default test path")
