## MODIFIED Requirements

### Requirement: Admin CLI package split
系统 SHALL expose the admin CLI through `platform.admin_cli` canonical package paths only; the legacy
`fleetent.admin` shim SHALL NOT remain importable. The `fleetent-admin` console script SHALL point to the
deprecation shim `fleetent._shims:fleetent_admin_shim` (which forwards to `fleetent admin`), not directly to
`fleetent.platform.admin_cli.main:main`. `platform.admin_cli.main.main` SHALL remain importable as the
canonical implementation that both `fleetent admin` and the shim delegate to.

#### Scenario: New admin CLI package entrypoint exists
- **WHEN** 调用方导入 `fleetent.platform.admin_cli.main.main`
- **THEN** 导入成功

#### Scenario: Legacy admin entrypoint is removed
- **WHEN** 调用方导入 `fleetent.admin`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Console script points to deprecation shim
- **WHEN** 查看 `pyproject.toml`
- **THEN** `fleetent-admin` 指向 `fleetent._shims:fleetent_admin_shim`
