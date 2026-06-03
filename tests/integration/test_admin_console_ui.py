"""UI-marker assertions for the admin console (static admin.html).

These read the shipped single-file SPA and assert each management module's tab,
controls, and action wiring are present. No server needed — the console is a static
asset; functional behaviour is browser-verified separately.
"""

from pathlib import Path

ADMIN_HTML = (Path(__file__).parents[2] / "src" / "fleetent" / "static" / "admin.html").read_text(
    encoding="utf-8"
)


# --- 1. two-level navigation --------------------------------------------------


def test_grouped_nav_present():
    html = ADMIN_HTML
    assert "switchGroup(" in html
    for group in ("access", "agents", "models", "ops", "audit"):
        assert f'data-group="{group}"' in html


def test_existing_tabs_still_reachable():
    html = ADMIN_HTML
    for tab in ("users", "im", "connectors", "kb", "audit"):
        assert f'data-tab="{tab}"' in html


# --- 2. Skills module ---------------------------------------------------------


def test_skills_tab_and_list_wiring():
    html = ADMIN_HTML
    assert 'id="tab-skills"' in html
    assert "sk-body" in html
    # list endpoint wired
    assert 'api("GET", "/skills"' in html
    assert "LOADERS.skills" in html


def test_skills_actions_wired_to_endpoints():
    html = ADMIN_HTML
    # path fragments for each action endpoint must appear
    for frag in (
        "/skills/${",  # per-skill scoped action paths
        "/disable",
        "/enable",
        '"/skills/reload"',
        "/restore",
        "/agents/",
        "/force-publish",
        "/observability",
        "/provenance/promote",
        "/provenance/discard",
    ):
        assert frag in html, frag


def test_skills_action_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function skCreate",
        "function skEdit",
        "function skEnable",
        "function skDisable",
        "function skReload",
        "function skDelete",
        "function skRestore",
        "function skBindAgents",
        "function skForcePublish",
        "function skObservability",
        "function skPromote",
        "function skDiscard",
    ):
        assert fn in html, fn


def test_skills_proposals_review_wired():
    html = ADMIN_HTML
    assert "/skills/proposals" in html
    assert "/diff" in html
    assert "/approve" in html
    assert "/reject" in html
    assert "function skProposals" in html
    assert "function skApprove" in html
    assert "function skReject" in html


def test_skills_confirm_header_for_high_risk():
    html = ADMIN_HTML
    # force-publish / promote / approve require X-Confirm header
    assert '"X-Confirm": "true"' in html or "'X-Confirm': 'true'" in html


def test_skills_write_controls_admin_gated():
    html = ADMIN_HTML
    # a viewer-hidden container exists for skills write actions
    assert "sk-create-bar" in html


# --- 3. Model Providers module ------------------------------------------------


def test_providers_tab_and_list_wiring():
    html = ADMIN_HTML
    assert 'id="tab-providers"' in html
    assert "pv-body" in html
    assert 'api("GET", "/providers"' in html
    assert "LOADERS.providers" in html


def test_providers_crud_and_actions_wired():
    html = ADMIN_HTML
    for fn in (
        "function pvCreate",
        "function pvEdit",
        "function pvDelete",
        "function pvTest",
        "function pvPricing",
        "function pvObservability",
        "function pvRoutes",
        "function pvSetRoute",
        "function pvPreviewRoute",
        "function pvHealth",
    ):
        assert fn in html, fn


def test_providers_endpoints_present():
    html = ADMIN_HTML
    for frag in (
        "/providers/${",
        "/connectivity-test",
        "/pricing",
        "/observability",
        '"/providers/routes"',
        "/routes/",
        "/preview",
        '"/providers/health"',
    ):
        assert frag in html, frag


def test_providers_secret_field_password_no_prefill():
    html = ADMIN_HTML
    # api_key input must be a password field with autocomplete off
    assert 'id="pv-api-key"' in html
    snippet = html.split('id="pv-api-key"', 1)[1][:120]
    assert 'type="password"' in snippet
    assert "autocomplete" in snippet


def test_providers_write_controls_admin_gated():
    html = ADMIN_HTML
    assert "pv-create-bar" in html


# --- 4. Agents module ---------------------------------------------------------


def test_agents_tab_and_list_wiring():
    html = ADMIN_HTML
    assert 'id="tab-agents"' in html
    assert "ag-body" in html
    assert 'api("GET", "/agents"' in html
    assert "LOADERS.agents" in html
    assert "/agent-templates" in html


def test_agents_lifecycle_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function agEnable",
        "function agDisable",
        "function agArchive",
        "function agRestore",
        "function agClone",
        "function agObservability",
        "function agVersions",
        "function agActivateVersion",
        "function agBindUser",
        "function agUnbindUser",
        "function agBindChannel",
        "function agUnbindChannel",
    ):
        assert fn in html, fn


def test_agents_endpoints_present():
    html = ADMIN_HTML
    for frag in (
        "/agents/${",
        "/enable",
        "/disable",
        "/archive",
        "/restore",
        "/clone",
        "/observability",
        "/versions",
        "/activate",
        "/bindings/users/",
        "/bindings/channels/",
    ):
        assert frag in html, frag


def test_agents_write_controls_admin_gated():
    html = ADMIN_HTML
    assert "ag-create-bar" in html


# --- 5. Statistics module -----------------------------------------------------


def test_stats_tab_and_per_user_wiring():
    html = ADMIN_HTML
    assert 'id="tab-stats"' in html
    assert "st-body" in html
    assert "/stats/per-user" in html
    assert "LOADERS.stats" in html


def test_stats_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function stPerUser",
        "function stOverview",
        "function stCompare",
        "function stTools",
        "function stUserRequests",
        "function stRequest",
        "function stTrace",
        "function stExport",
        "function stReport",
    ):
        assert fn in html, fn


def test_stats_endpoints_present():
    html = ADMIN_HTML
    for frag in (
        "/stats/agents/",
        "/overview",
        "/stats/compare",
        "/tools",
        "/stats/users/",
        "/requests",
        "/stats/requests/",
        "/sessions/",
        "/trace",
        "/stats/export",
        "/stats/reports",
    ):
        assert frag in html, frag


# --- 6. Monitoring + Alerts module --------------------------------------------


def test_monitoring_tab_and_metrics_wiring():
    html = ADMIN_HTML
    assert 'id="tab-monitoring"' in html
    assert "mon-rules-body" in html
    assert "/monitoring/metrics" in html
    assert "LOADERS.monitoring" in html


def test_monitoring_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function monMetrics",
        "function monRules",
        "function monCreateRule",
        "function monDisableRule",
        "function monDeleteRule",
        "function monAlerts",
        "function monAck",
        "function monSilence",
        "function monMaintenance",
    ):
        assert fn in html, fn


def test_monitoring_endpoints_present():
    html = ADMIN_HTML
    for frag in (
        '"/alerts/rules"',
        "/alerts/rules/",
        "/disable",
        '"/alerts"',
        "/ack",
        "/silence",
        '"/alerts/maintenance"',
    ):
        assert frag in html, frag


def test_monitoring_write_controls_admin_gated():
    html = ADMIN_HTML
    assert "mon-create-bar" in html


# --- 7. Sessions module -------------------------------------------------------


def test_sessions_tab_and_list_wiring():
    html = ADMIN_HTML
    assert 'id="tab-sessions"' in html
    assert "sess-body" in html
    assert 'api("GET", "/sessions"' in html
    assert "LOADERS.sessions" in html


def test_sessions_control_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function sessTakeover",
        "function sessRelease",
        "function sessInject",
        "function sessForceEnd",
        "function sessClear",
        "function sessReset",
        "function sessBulk",
        "function sessStart",
        "function sessMessage",
        "function sessPin",
        "function sessExport",
    ):
        assert fn in html, fn


def test_sessions_endpoints_present():
    html = ADMIN_HTML
    for frag in (
        "/sessions/${",
        "/takeover",
        "/release",
        "/inject",
        "/force-end",
        "/clear",
        "/reset",
        '"/sessions/bulk"',
        '"/chat/start"',
        "/chat/${",
        "/message",
        "/pin",
        "/export",
    ):
        assert frag in html, frag


def test_sessions_write_controls_admin_gated():
    html = ADMIN_HTML
    assert "sess-create-bar" in html


# --- 8. OAuth Connectors + MCP module -----------------------------------------


def test_oauth_mcp_tab_distinct_from_im_connectors():
    html = ADMIN_HTML
    assert 'id="tab-oauth"' in html
    assert "oc-body" in html
    # distinct from IM connectors tab which uses /im/connectors
    assert 'data-tab="oauth"' in html
    assert "LOADERS.oauth" in html


def test_oauth_mcp_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function ocConnectors",
        "function ocCreate",
        "function ocEdit",
        "function ocGrants",
        "function ocRevoke",
        "function ocOffboarding",
        "function ocLifecycle",
        "function mcpDoctor",
        "function mcpServers",
        "function mcpTools",
        "function mcpReconnect",
    ):
        assert fn in html, fn


def test_oauth_mcp_endpoints_present():
    html = ADMIN_HTML
    for frag in (
        "/connectors/grants",
        "/connectors/${",
        "/lifecycle",
        "/revoke",
        "/connectors/offboarding/",
        '"/mcp/doctor"',
        '"/mcp/servers"',
        "/tools",
        "/reconnect",
    ):
        assert frag in html, frag


def test_oauth_secret_field_password_no_prefill():
    html = ADMIN_HTML
    assert 'id="oc-client-secret"' in html
    snippet = html.split('id="oc-client-secret"', 1)[1][:120]
    assert 'type="password"' in snippet
    assert "autocomplete" in snippet


def test_oauth_write_controls_admin_gated():
    html = ADMIN_HTML
    assert "oc-create-bar" in html


# --- 9. AskIt module ----------------------------------------------------------


def test_askit_tab_and_list_wiring():
    html = ADMIN_HTML
    assert 'id="tab-askit"' in html
    assert "ak-tasks-body" in html
    assert "/askit/series" in html
    assert "LOADERS.askit" in html


def test_askit_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function akSeries",
        "function akTasks",
        "function akRun",
        "function akTaskDetail",
    ):
        assert fn in html, fn


def test_askit_endpoints_present():
    html = ADMIN_HTML
    for frag in (
        '"/askit/series"',
        '"/askit/run"',
        '"/askit/tasks"',
        "/askit/tasks/${",
    ):
        assert frag in html, frag
