from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    os.getenv("FLEETENT_GOOGLE_DRIVE_SMOKE") != "1",
    reason="Google Drive smoke requires FLEETENT_GOOGLE_DRIVE_SMOKE=1",
)
async def test_google_drive_smoke_requires_complete_oauth_configuration():
    required = {
        "FLEETENT_GOOGLE_DRIVE_CREDENTIAL_REF": os.getenv("FLEETENT_GOOGLE_DRIVE_CREDENTIAL_REF"),
        "FLEETENT_GOOGLE_DRIVE_FOLDER_ID": os.getenv("FLEETENT_GOOGLE_DRIVE_FOLDER_ID"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        pytest.skip(f"missing Google Drive smoke configuration: {', '.join(missing)}")

    pytest.skip("real Google Drive client is not wired into default test path")
