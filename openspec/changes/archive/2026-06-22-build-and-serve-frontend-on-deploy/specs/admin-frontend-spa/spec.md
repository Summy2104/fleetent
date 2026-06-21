## ADDED Requirements

### Requirement: Deployed platform serves the built SPA from a resolvable dist

The platform SHALL resolve the admin SPA dist directory in a deployment-robust way: it SHALL honor a `FLEETENT_ADMIN_UI_DIST` environment variable when set, otherwise fall back to the repo-relative `frontend/dist`. When the dist exists, `/admin/ui` SHALL serve it; when it does not, the platform SHALL return a clear "frontend not built" error (503) rather than a blank page, so the failure is diagnosable.

#### Scenario: Serve dist from an overridden location

- **WHEN** `FLEETENT_ADMIN_UI_DIST` points at a directory containing a built SPA
- **THEN** `/admin/ui` serves that build, regardless of the process working directory

#### Scenario: Default resolution serves the built repo dist

- **WHEN** `FLEETENT_ADMIN_UI_DIST` is unset and `frontend/dist` has been built
- **THEN** `/admin/ui` serves the repo's built dist

#### Scenario: Unbuilt dist gives a clear error

- **WHEN** no built dist is found at the resolved location
- **THEN** `/admin/ui` returns a 503 with a clear "frontend not built" message (not a blank/200 page)
