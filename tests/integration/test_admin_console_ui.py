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
    for group in ("access", "agents", "models", "ops"):
        assert f'data-group="{group}"' in html


def test_existing_tabs_still_reachable():
    html = ADMIN_HTML
    for tab in ("users", "kb", "chat"):
        assert f'data-tab="{tab}"' in html


def test_active_tab_persisted_in_hash():
    html = ADMIN_HTML
    # switchTab writes the active tab into the URL hash
    assert "location.hash" in html
    # app entry no longer hardcodes the users tab; it restores from hash
    assert 'switchTab("users")' not in html
    assert "restoreTab" in html


def test_active_tab_restore_falls_back_to_users():
    html = ADMIN_HTML
    body = html.split("function restoreTab", 1)[1].split("}", 1)[0]
    # restore validates against TAB_GROUP and defaults to users
    assert "TAB_GROUP" in body
    assert '"users"' in body


# --- 2. Skills module ---------------------------------------------------------


def test_skills_tab_and_list_wiring():
    html = ADMIN_HTML
    assert 'id="tab-skills"' in html
    assert 'id="sk-grid"' in html  # card grid (replaced the old sk-body table)
    # list endpoint wired
    assert 'api("GET", "/skills' in html
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
        "function skForcePublish",
        "function skPromote",
        "function skDiscard",
        "function skDrawer",
        "function skDoUpload",
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
        "function pvRoutes",
        "function pvSetRoute",
        "function pvPreviewRoute",
    ):
        assert fn in html, fn


def test_providers_endpoints_present():
    html = ADMIN_HTML
    for frag in (
        "/providers/${",
        "/connectivity-test",
        "/observability",
        '"/providers/routes"',
        "/routes/",
        "/preview",
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


def test_agents_crud_modal_and_fields_present():
    html = ADMIN_HTML
    # create/edit modal with the three editable fields
    assert 'id="ag-modal"' in html
    assert 'id="ag-name"' in html
    assert 'id="ag-system-prompt"' in html
    assert 'id="ag-allowed-tools"' in html
    # "New agent" control lives in the (admin-gated) create bar
    bar = html.split('id="ag-create-bar"', 1)[1].split("</span>", 1)[0]
    assert "agCreate(" in bar


def test_agent_create_modal_wide_and_requires_template():
    html = ADMIN_HTML
    # ag-modal uses the wide modal box
    modal = html.split('id="ag-modal"', 1)[1].split("</div>", 1)[0]
    assert "modal-box wide" in modal
    # a template <select> is present and prefills on change
    assert 'id="ag-template"' in html
    assert "agTemplatePrefill(" in html
    # agCreate populates the template select; agSave sends template_id and blocks
    # creating without a chosen template
    agcreate = html.split("function agCreate", 1)[1].split("function agEdit", 1)[0]
    assert "ag-template" in agcreate
    agsave = html.split("function agSave", 1)[1].split("function agDelete", 1)[0]
    assert "template_id" in agsave


def test_agents_crud_functions_present():
    html = ADMIN_HTML
    for fn in ("function agCreate", "function agEdit", "function agSave", "function agDelete"):
        assert fn in html, fn


def test_agents_templates_are_inpage_subtabs():
    html = ADMIN_HTML
    sidebar = html.split('class="sidebar"', 1)[1].split("</nav>", 1)[0]
    # single Agents sidebar item, no separate Templates sidebar tab / section
    assert 'data-tab="templates"' not in sidebar
    assert 'id="tab-templates"' not in html
    # sub-tab switcher + panes live inside the Agents page
    assert "agSubTab(" in html
    assert 'id="ag-pane"' in html
    assert 'id="tmpl-pane"' in html


def test_agents_tab_no_longer_hosts_templates_toggle():
    html = ADMIN_HTML
    # the old inline toggle panel is gone
    assert "tmplToggle" not in html
    assert 'id="ag-templates-panel"' not in html


def test_agent_templates_edit_modal_and_fields_present():
    html = ADMIN_HTML
    assert 'id="tmpl-modal"' in html
    for field_id in ("tmpl-id", "tmpl-display-name", "tmpl-allowed-tools", "tmpl-system-prompt"):
        assert f'id="{field_id}"' in html, field_id


def test_resource_id_inputs_are_readonly():
    html = ADMIN_HTML
    import re

    for input_id in ("tmpl-id", "nkb-id", "pv-id", "oc-id"):
        m = re.search(rf'<input[^>]*id="{input_id}"[^>]*>', html)
        assert m, input_id
        assert "readonly" in m.group(0), input_id


def test_textarea_themed_and_template_editor_roomy():
    html = ADMIN_HTML
    import re

    style = html.split("<style", 1)[1].split("</style>", 1)[0]
    # global form-control rule now covers textarea too
    assert re.search(r"input,\s*select,\s*textarea", style)
    # template modal is wide and the prompt editor is tall
    box = html.split('id="tmpl-modal"', 1)[1].split("</div>", 1)[0]
    assert "modal-box wide" in box
    m = re.search(r'id="tmpl-system-prompt"[^>]*rows="(\d+)"', html)
    assert m and int(m.group(1)) >= 12


def test_genid_helper_and_create_uses_it():
    html = ADMIN_HTML
    assert "function genId" in html
    # template/provider/connector create forms fill the id with a generated value
    assert "genId()" in html
    # not fewer than the create forms that open with a generated id
    assert html.count("genId()") >= 3


def test_agent_templates_crud_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function tmplCreate",
        "function tmplEdit",
        "function tmplSave",
        "function tmplDelete",
    ):
        assert fn in html, fn


def test_agent_templates_crud_endpoints_wired():
    html = ADMIN_HTML
    assert 'api("POST", "/agent-templates"' in html
    assert 'api("PATCH", `/agent-templates/${' in html
    assert 'api("DELETE", `/agent-templates/${' in html


def test_agent_templates_write_controls_admin_gated():
    html = ADMIN_HTML
    body = html.split("function tmplRender", 1)[1].split("function tmplCreate", 1)[0]
    assert "IS_VIEWER" in body
    assert "tmplEdit(" in body
    assert "tmplDelete(" in body


_NON_TEMPLATE_FIELDS = (
    "ag-skills-dir",
    "ag-mcp-server-ids",
    "ag-model-overrides",
    "ag-memory-namespace",
)


def test_agents_modal_only_template_backed_fields():
    html = ADMIN_HTML
    # template-backed editable fields remain
    assert 'id="ag-system-prompt"' in html
    assert 'id="ag-allowed-tools"' in html
    # non-template free-form fields are gone
    for field_id in _NON_TEMPLATE_FIELDS:
        assert f'id="{field_id}"' not in html, field_id


def test_agents_save_and_edit_drop_non_template_fields():
    html = ADMIN_HTML
    save = html.split("function agSave", 1)[1].split("function agDelete", 1)[0]
    edit = html.split("function agEdit", 1)[1].split("function agCloseModal", 1)[0]
    for field_id in _NON_TEMPLATE_FIELDS:
        assert field_id not in save, f"agSave still references {field_id}"
        assert field_id not in edit, f"agEdit still references {field_id}"


def test_agents_crud_endpoints_wired():
    html = ADMIN_HTML
    # create = POST /agents, delete = DELETE with confirm header, edit = PATCH
    assert 'api("POST", "/agents"' in html
    assert 'api("PATCH", `/agents/${' in html
    assert 'api("DELETE", `/agents/${' in html
    assert '"X-Confirm": "true"' in html


def test_agents_crud_row_actions_admin_gated():
    html = ADMIN_HTML
    body = html.split("function renderAgents()", 1)[1].split("function agShowTemplates", 1)[0]
    assert "IS_VIEWER" in body
    assert "agEdit(" in body
    assert "agDelete(" in body


def test_agents_row_actions_in_overflow_menu():
    html = ADMIN_HTML
    body = html.split("function renderAgents()", 1)[1].split("function agShowTemplates", 1)[0]
    # actions collapsed into a … overflow menu (reuses shared .menu / toggleMenu pattern)
    assert 'class="menu"' in body
    assert "toggleMenu(" in body
    assert "menu-items" in body
    # all existing actions still reachable from the menu
    for fn in (
        "agObservability(",
        "agVersions(",
        "agEdit(",
        "agOpenBind(",
        "agOpenClone(",
        "agArchive(",
        "agDelete(",
    ):
        assert fn in body, fn
    # admin-only items still gated
    assert "IS_VIEWER" in body


def test_overflow_menu_escapes_scroll_clipping():
    html = ADMIN_HTML
    fn = html.split("function toggleMenu(", 1)[1].split("\n}", 1)[0]
    # dropdown must be positioned via fixed coords so the .table-scroll
    # (overflow-x:auto) container does not clip it
    assert "getBoundingClientRect" in fn
    assert '"fixed"' in fn or "'fixed'" in fn


def test_agents_deploy_action_present():
    html = ADMIN_HTML
    body = html.split("function renderAgents()", 1)[1].split("function agShowTemplates", 1)[0]
    # Deploy menu item
    assert "agDeploy(" in body
    # deploy dialog + handler posting the channel-binding endpoint
    assert 'id="ag-deploy-modal"' in html
    assert "function agDeploy" in html
    deploy = html.split("function agDeploy", 1)[1].split("LOADERS.agents", 1)[0]
    assert "/bindings/channels/" in deploy


def test_bindings_modal_has_skill_mcp_channel_sections():
    html = ADMIN_HTML
    modal = html.split('id="ag-bind-modal"', 1)[1].split("</div>\n  </div>", 1)[0]
    # dedicated containers the loader renders into
    assert 'id="ag-bind-skills"' in modal
    assert 'id="ag-bind-mcp"' in modal
    assert 'id="ag-bind-channels"' in modal


def test_bindings_modal_loads_from_aggregate_endpoints():
    html = ADMIN_HTML
    fn = html.split("function agOpenBind", 1)[1].split("function agCloseBind", 1)[0]
    # opening the modal pulls the aggregate bindings + skills lists
    assert "/bindings`" in fn or "/bindings'" in fn
    assert "/skills`" in fn or "/skills'" in fn


def test_bindings_skill_toggle_wired_to_put():
    html = ADMIN_HTML
    fn = html.split("function agSetSkill", 1)[1].split("\nasync function", 1)[0]
    assert '"PUT"' in fn or "'PUT'" in fn
    assert "/skills/" in fn
    assert "enabled" in fn


def test_bindings_mcp_toggle_wired_to_post_delete():
    html = ADMIN_HTML
    bindfn = html.split("function agBindMcp", 1)[1].split("\nasync function", 1)[0]
    assert '"POST"' in bindfn or "'POST'" in bindfn
    assert "/bindings/mcp/" in bindfn
    unbindfn = html.split("function agUnbindMcp", 1)[1].split("\nasync function", 1)[0]
    assert '"DELETE"' in unbindfn or "'DELETE'" in unbindfn
    assert "/bindings/mcp/" in unbindfn


def test_bindings_write_controls_viewer_gated():
    html = ADMIN_HTML
    # the skill + mcp render helpers gate their toggles behind IS_VIEWER
    render = html.split("function agRenderBindings", 1)[1].split("function agCloseBind", 1)[0]
    assert "IS_VIEWER" in render


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
    assert 'id="oauth-grid"' in html  # card grid (replaced oc-body table)
    # distinct from IM connectors tab which uses /im/connectors
    assert 'data-tab="oauth"' in html
    assert "LOADERS.oauth" in html


def test_oauth_mcp_functions_present():
    html = ADMIN_HTML
    for fn in (
        "function loadOauthConnectors",
        "function loadMcpConnectors",
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


# --- agent-scoped OAuth/MCP: owner column + agent filter ----------------------


def test_oauth_connectors_card_shows_owner():
    html = ADMIN_HTML
    card = html.split("function oauthCardHtml", 1)[1].split("function ", 2)[0]
    assert "Global" in card and "Agent:" in card  # owner shown on the card


def test_mcp_servers_rendered_as_cards():
    html = ADMIN_HTML
    assert "function mcpCardHtml" in html
    assert 'id="mcp-grid"' in html


def test_oauth_connectors_render_owner_cell():
    html = ADMIN_HTML
    body = html.split("function oauthCardHtml", 1)[1].split("function ", 2)[0]
    assert "c.agent_id" in body  # owner derived from agent_id


def test_mcp_servers_render_owner_cell_and_colspan():
    html = ADMIN_HTML
    body = html.split("async function mcpServers()", 1)[1].split("async function mcpTools", 1)[0]
    assert "s.agent_id" in body
    assert 'colspan="5"' in body


# --- 9. AskIt module removed --------------------------------------------------


def test_askit_module_removed():
    html = ADMIN_HTML
    for frag in (
        'id="tab-askit"',
        'data-tab="askit"',
        "LOADERS.askit",
        "/askit/series",
        "/askit/run",
        "/askit/tasks",
        "function akSeries",
        "function akTasks",
        "function akRun",
        "function akTaskDetail",
    ):
        assert frag not in html, frag


# --- Redesign: design tokens --------------------------------------------------


def test_design_tokens_present():
    html = ADMIN_HTML
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    # token families: surfaces, spacing, radius, elevation, text/border
    for tok in (
        "--surface",
        "--bg-0",
        "--border",
        "--text",
        "--text-muted",
        "--sp-1",
        "--sp-4",
        "--r-1",
        "--shadow-1",
    ):
        assert tok in style, tok


def test_components_reference_tokens_not_hardcoded():
    html = ADMIN_HTML
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    # spacing/surface usage goes through tokens
    assert "var(--surface)" in style
    assert "var(--sp-" in style


# --- Redesign: sidebar shell --------------------------------------------------


def test_sidebar_present_and_grouped():
    html = ADMIN_HTML
    assert 'class="sidebar"' in html
    # grouped section headings inside sidebar
    for group in ("access", "agents", "models", "ops"):
        assert f'data-group="{group}"' in html
    # contract preserved
    assert "switchGroup(" in html
    assert "switchTab(" in html


def test_sidebar_all_modules_reachable():
    html = ADMIN_HTML
    sidebar = html.split('class="sidebar"', 1)[1].split("</nav>", 1)[0]
    for tab in (
        "users",
        "agents",
        "skills",
        "kb",
        "chat",
        "providers",
        "oauth",
        "stats",
        "monitoring",
        "sessions",
    ):
        assert f'data-tab="{tab}"' in sidebar, tab


# --- Redesign: page header ----------------------------------------------------


def test_page_header_primitive_present():
    html = ADMIN_HTML
    assert 'class="page-header"' in html
    assert "ph-title" in html
    assert "ph-actions" in html


def test_page_header_applied_to_each_module():
    html = ADMIN_HTML
    # every module section carries a page header (one per top-level module tab)
    assert html.count('class="page-header"') >= 10


# --- Redesign: toast + confirm dialog -----------------------------------------


def test_toast_and_confirm_helpers_present():
    html = ADMIN_HTML
    assert 'id="toast-host"' in html
    assert "function toast" in html
    assert "function confirmDialog" in html


def test_no_native_blocking_dialogs():
    html = ADMIN_HTML
    # native alert()/confirm() replaced by in-app toast()/confirmDialog()
    assert "alert(" not in html
    assert "confirm(" not in html


# --- Redesign: table scroll + empty/loading -----------------------------------


def test_tables_wrapped_in_scroll_container():
    html = ADMIN_HTML
    # every data table lives inside a horizontal scroll container
    assert html.count('class="table-scroll"') >= html.count("<table>")
    assert html.count("<table>") >= 13


def test_empty_and_loading_state_helpers_present():
    html = ADMIN_HTML
    assert "function loadingRow" in html
    assert "function emptyRow" in html
    # styling hooks
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    assert ".empty" in style
    assert ".loading" in style


# --- Redesign: responsive + a11y ----------------------------------------------


def test_responsive_sidebar_controls():
    html = ADMIN_HTML
    assert 'class="hamburger' in html
    assert "nav-open" in html
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    assert "@media (max-width:860px)" in style


def test_a11y_markers_present():
    html = ADMIN_HTML
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    assert ":focus-visible" in style
    assert 'aria-label="Admin navigation"' in html
    # dialogs are labelled and keyboard-dismissable across all modals
    assert 'role="dialog"' in html
    assert "function escCloseModals" in html


# --- Redesign: role gating + secrets preserved under new shell -----------------


def test_viewer_hidden_write_containers_intact():
    html = ADMIN_HTML
    for cid in (
        "create-bar",
        "kb-create-card",
        "sk-create-bar",
        "pv-create-bar",
        "ag-create-bar",
        "st-report-bar",
        "mon-create-bar",
        "mon-maint-bar",
        "sess-create-bar",
        "sess-bulk-bar",
    ):
        assert f'id="{cid}"' in html, cid
    # the enterApp viewer-gate still references every container
    gate = html.split("if (IS_VIEWER) {", 1)[1].split("}", 1)[0]
    for cid in ("sk-create-bar", "pv-create-bar", "sess-bulk-bar"):
        assert cid in gate, cid


def test_secret_fields_masked_no_prefill():
    html = ADMIN_HTML
    for fid in ("pv-api-key", "oc-client-secret"):
        snippet = html.split(f'id="{fid}"', 1)[1][:140]
        assert 'type="password"' in snippet, fid
        assert "autocomplete" in snippet, fid
    # edit paths explicitly blank the secret before showing the form
    assert '$("pv-api-key").value = "";' in html


# --- unified User-centric axis: single Users tab -----------------------------


def _render_users_body(html):
    return html.split("function renderUsers()", 1)[1].split("function closeMenus", 1)[0]


def test_no_standalone_im_tab():
    html = ADMIN_HTML
    assert 'data-tab="im"' not in html
    assert 'id="tab-im"' not in html
    assert 'id="im-groups"' not in html
    assert "LOADERS.im" not in html
    assert "async function loadIm" not in html
    tab_group = html.split("const TAB_GROUP", 1)[1].split("}", 1)[0]
    assert "im:" not in tab_group
    group_default = html.split("const GROUP_DEFAULT_TAB", 1)[1].split("}", 1)[0]
    assert '"im"' not in group_default and "'im'" not in group_default


def test_access_group_only_users_tab():
    html = ADMIN_HTML
    access = html.split('data-group="access"', 1)[1].split("</div>", 1)[0]
    assert 'data-tab="users"' in access
    assert 'data-tab="im"' not in access


def test_separate_connectors_tab_removed():
    html = ADMIN_HTML
    # neither the legacy connectors tab nor the IM tab exist as standalone tabs
    assert 'data-tab="connectors"' not in html
    assert 'id="tab-connectors"' not in html
    assert 'data-tab="im"' not in html
    assert 'id="tab-im"' not in html


# --- Task 2: foldable IM identities per User ----------------------------------


def test_loaders_users_fetches_three_endpoints():
    html = ADMIN_HTML
    loader = html.split("async function loadUsers()", 1)[1].split("function renderUsers", 1)[0]
    assert '"/users"' in loader
    assert '"/im-users"' in loader
    assert '"/im/connectors"' in loader
    assert "IM_BY_USER" in loader
    assert "CONN_BY_OWNER" in loader


def test_render_users_joins_im_identities_by_user():
    body = _render_users_body(ADMIN_HTML)
    # IM identities joined by user_id and folded under their User
    assert "IM_BY_USER[" in body
    # expander control + per-identity actions live in the per-user child region
    assert "toggleUserRow(" in body
    assert "openBindModal(" in body
    assert "imBlock(" in body
    assert "imRestore(" in body
    assert "platform_user_id" in body


# --- Task 3: connectors grouped under owning User -----------------------------


def test_render_users_groups_connectors_by_owner():
    body = _render_users_body(ADMIN_HTML)
    assert "CONN_BY_OWNER[" in body
    assert "connEnable(" in body
    assert "connDisable(" in body


def test_add_connection_per_user_row():
    html = ADMIN_HTML
    # no top-level "Add connection" bar — the action lives on each User row
    assert "conn-create-bar" not in html
    body = _render_users_body(html)
    # per-row add targets that User as the connector owner, admin-gated
    assert "openConnModal('" in body
    assert "IS_VIEWER" in body


def test_connector_modal_retained():
    html = ADMIN_HTML
    assert 'id="conn-modal"' in html
    assert "function openConnModal" in html
    assert "function createConn" in html
    assert "const CONN_FIELDS" in html


def test_im_connector_create_targets_selected_owner():
    html = ADMIN_HTML
    create = html.split("async function createConn()", 1)[1].split("async function connEnable", 1)[
        0
    ]
    # owner flows from the per-row target (CONN_OWNER set by openConnModal), not a
    # free-text form field; creation stays admin-gated server-side.
    assert "owner_id" in create
    assert "CONN_OWNER" in create


# --- Task 4: source filter + badge --------------------------------------------


def test_source_filter_control_in_users_tab():
    html = ADMIN_HTML
    users_section = html.split('id="tab-users"', 1)[1].split("</section>", 1)[0]
    assert 'id="source-filter"' in users_section


def test_source_classification_and_badge():
    body = _render_users_body(ADMIN_HTML)
    # IM-origin detection (bound identities OR {platform}:{id} name pattern) + badge
    assert "imOrigin" in body
    assert "source-filter" in body


# --- User list pagination -----------------------------------------------------


def test_user_list_pagination_controls_present():
    html = ADMIN_HTML
    users_section = html.split('id="tab-users"', 1)[1].split("</section>", 1)[0]
    assert 'id="users-pager"' in users_section


def test_render_users_paginates_filtered_list():
    body = _render_users_body(ADMIN_HTML)
    # current page slice of the filtered list
    assert "USERS_PAGE" in body
    assert "USERS_PAGE_SIZE" in body
    assert ".slice(" in body
    # pager nav wiring
    assert "usersGoto(" in body


def test_filter_change_resets_to_first_page():
    html = ADMIN_HTML
    # changing any filter jumps back to page 1
    assert "function usersFilterChanged" in html
    reset = html.split("function usersFilterChanged", 1)[1].split("}", 1)[0]
    assert "USERS_PAGE = 1" in reset
    # filter inputs route through the reset wrapper, not renderUsers directly
    users_section = html.split('id="tab-users"', 1)[1].split("</section>", 1)[0]
    assert "usersFilterChanged()" in users_section


# --- Task 5: distinct block semantics -----------------------------------------


def test_distinct_block_semantics_labels():
    body = _render_users_body(ADMIN_HTML)
    # whole-User disable vs single-identity block rendered with distinct labels
    assert "Disable user" in body
    assert "Block identity" in body
    # user-level wires /users/.../block|unblock; identity-level wires /im-users/.../block
    assert "block(" in body
    assert "imBlock(" in body
