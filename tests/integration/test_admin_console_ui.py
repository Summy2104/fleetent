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
    for group in ("access", "agents", "resources", "ops"):
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


def test_skill_import_folder_or_zip_dropzone():
    html = ADMIN_HTML
    # single entry: a drop zone accepting a dragged folder or a .zip; click falls back
    # to the hidden webkitdirectory folder picker. Loose individual files are rejected.
    assert 'id="sk-drop"' in html
    assert 'id="sk-import-folder"' in html
    assert "webkitdirectory" in html
    assert "$('sk-import-folder').click()" in html
    assert 'id="sk-import-pick"' in html
    assert "function skDrop" in html
    assert "function skFolderPicked" in html
    assert "function skWalkDir" in html
    assert "webkitGetAsEntry" in html
    # loose-file rejection path is present
    assert "只接受文件夹或 .zip" in html
    # the old multi-file input, zip input, and paste section are gone
    assert 'id="sk-import-files"' not in html
    assert 'id="sk-import-zip"' not in html
    assert "skImportPaste" not in html
    assert 'id="sk-paste-content"' not in html
    up = html.split("async function skDoUpload", 1)[1].split("\n}", 1)[0]
    assert "/skills/import/upload" in up
    assert "SK_PICKED" in up


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
    # card grid + search toolbar replaced the legacy table
    assert 'id="pv-grid"' in html
    assert 'id="pv-filter"' in html
    assert "function pvCardHtml" in html
    assert 'api("GET", "/providers"' in html
    assert "LOADERS.providers" in html


def test_providers_detail_drawer_present():
    html = ADMIN_HTML
    assert 'id="pv-drawer"' in html
    assert "function pvDrawer" in html and "function pvCloseDrawer" in html
    # cards open the drawer; drawer hosts the Test/Edit/Delete actions
    card = html.split("function pvCardHtml", 1)[1].split("function pvCloseDrawer", 1)[0]
    assert "pvDrawer(" in card


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


def test_providers_form_has_vendor_protocol_env_params():
    html = ADMIN_HTML
    # new provider fields: api_key_env, protocol, custom params (JSON)
    for fid in ('id="pv-api-key-env"', 'id="pv-protocol"', 'id="pv-params"'):
        assert fid in html, fid
    form = html.split("function pvFormBody", 1)[1].split("async function pvSave", 1)[0]
    assert "api_key_env" in form
    assert "body.protocol" in form
    assert "body.provider" in form  # vendor from the provider-type radio
    assert "JSON.parse(raw)" in form  # params parsed as JSON


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
    # card grid + toolbar replaced the legacy table
    assert 'id="ag-grid"' in html
    assert 'id="ag-tabs"' in html
    assert 'id="ag-filter"' in html
    assert "function agentCardHtml" in html
    assert 'api("GET", "/agents?include_archived=true")' in html
    assert "LOADERS.agents" in html


def test_agents_detail_drawer_and_binding_sections():
    html = ADMIN_HTML
    # detail drawer replaces the bind/deploy modals
    assert 'id="ag-drawer"' in html
    assert "function agDrawer" in html
    assert 'id="ag-bind-modal"' not in html
    assert 'id="ag-deploy-modal"' not in html
    # every binding section is wired in the drawer
    assert "function agSetSkill" in html
    assert "function agToggleMcp" in html
    assert "function agToggleOauth" in html
    assert "function agAddKb" in html and "function agUnbindKb" in html
    for frag in ("/skills/", "/bindings/mcp/", "/bindings/oauth/", "/kbs"):
        assert frag in html, frag


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
        "function agToggleUser",
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


def test_agent_create_modal_wide_and_template_free():
    html = ADMIN_HTML
    # ag-modal uses the wide modal box
    modal = html.split('id="ag-modal"', 1)[1].split("</div>", 1)[0]
    assert "modal-box wide" in modal
    # the template module was removed: no template picker / template_id anywhere
    assert 'id="ag-template"' not in html
    assert "agTemplatePrefill(" not in html
    assert "template_id" not in html


def test_agents_crud_functions_present():
    html = ADMIN_HTML
    for fn in ("function agCreate", "function agEdit", "function agSave", "function agDelete"):
        assert fn in html, fn


def test_agents_have_no_template_module():
    html = ADMIN_HTML
    sidebar = html.split('class="sidebar"', 1)[1].split("</nav>", 1)[0]
    assert 'data-tab="templates"' not in sidebar
    assert 'id="tab-templates"' not in html
    # the in-page Templates sub-tab + pane + modal + CRUD are all gone
    for marker in (
        "agSubTab(",
        'id="tmpl-pane"',
        'id="tmpl-modal"',
        "function tmplCreate",
        "tmplToggle",
    ):
        assert marker not in html, marker


def test_resource_id_inputs_are_readonly():
    html = ADMIN_HTML
    import re

    for input_id in ("pv-id", "oc-id"):
        m = re.search(rf'<input[^>]*id="{input_id}"[^>]*>', html)
        assert m, input_id
        assert "readonly" in m.group(0), input_id


def test_kb_base_create_edit_with_description_present():
    html = ADMIN_HTML
    # KB tab hosts a knowledge-base manager (kb_id + short description) + add/edit modal
    assert 'id="kb-modal"' in html
    assert 'id="kb-id"' in html  # kb_id input (create only)
    assert 'id="kb-desc"' in html  # short description input
    for fn in (
        "function loadKbBases",
        "function kbOpenCreate",
        "function kbOpenEdit",
        "function kbSave",
    ):
        assert fn in html, fn
    # the KB list loader runs alongside the connector loader
    loadkb = html.split("async function loadKb", 1)[1].split("}", 1)[0]
    assert "loadKbBases()" in loadkb
    # create posts kb_id + description; edit patches description
    save = html.split("async function kbSave", 1)[1].split("\n}", 1)[0]
    assert "description" in save
    assert '"/kb"' in save  # POST create
    assert "/kb/${" in save  # PATCH edit by id


def test_kb_source_connectors_management_present():
    html = ADMIN_HTML
    # KB tab hosts a source-connector manager (Drive/Confluence) + add/edit modal
    assert 'id="kbc-body"' in html
    assert 'id="kbc-modal"' in html
    assert 'id="kbc-kind"' in html
    assert "function loadKbConnectors" in html
    assert "function kbcSave" in html
    # CRUD + check + dry-run sync wired to the API
    assert 'api("GET", "/kb/connectors")' in html
    assert 'api("POST", "/kb/connectors"' in html
    assert "/check" in html and "/sync" in html
    assert "KBC_FIELDS" in html  # per-kind field defs
    assert "loadKbConnectors()" in html.split("async function loadKb", 1)[1].split("}", 1)[0]
    # free-form custom metadata authored as YAML (parsed server-side), like provider params
    assert 'id="kbc-custom"' in html
    assert "Custom (YAML)" in html
    save = html.split("async function kbcSave", 1)[1].split("async function kbcDelete", 1)[0]
    assert "custom_yaml" in save


def test_textarea_themed():
    html = ADMIN_HTML
    import re

    style = html.split("<style", 1)[1].split("</style>", 1)[0]
    # global form-control rule covers textarea too
    assert re.search(r"input,\s*select,\s*textarea", style)


def test_genid_helper_and_create_uses_it():
    html = ADMIN_HTML
    assert "function genId" in html
    # provider/connector/kb create forms fill the id with a generated value
    assert "genId()" in html
    assert html.count("genId()") >= 2


# Free-form fields the modal never exposes (covered by template / bindings instead).
_NON_TEMPLATE_FIELDS = (
    "ag-skills-dir",
    "ag-mcp-server-ids",
    "ag-memory-namespace",
)


def test_agents_modal_core_and_create_config_fields():
    html = ADMIN_HTML
    # identity fields remain
    assert 'id="ag-system-prompt"' in html
    assert 'id="ag-allowed-tools"' in html
    # new-agent config: structured model overrides + capabilities YAML paste
    assert 'id="ag-model-overrides"' in html
    assert "function agRenderModelOverrides" in html
    assert "function agCollectModelOverrides" in html
    assert 'id="ag-capabilities"' in html
    assert "capabilities_yaml" in html
    # still no free-form skills-dir/mcp/memory inputs
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


def test_agents_drawer_lifecycle_actions_present_and_gated():
    html = ADMIN_HTML
    body = html.split("function agRenderDrawer", 1)[1].split("async function agSetSkill", 1)[0]
    # lifecycle actions live in the drawer, admin-gated behind IS_VIEWER
    assert "IS_VIEWER" in body
    for fn in (
        "agEdit(",
        "agOpenClone(",
        "agArchive(",
        "agRestore(",
        "agDelete(",
        "agActivateVersion(",
    ):
        assert fn in body, fn


def test_overflow_menu_escapes_scroll_clipping():
    html = ADMIN_HTML
    fn = html.split("function toggleMenu(", 1)[1].split("\n}", 1)[0]
    # dropdown must be positioned via fixed coords so the .table-scroll
    # (overflow-x:auto) container does not clip it
    assert "getBoundingClientRect" in fn
    assert '"fixed"' in fn or "'fixed'" in fn


def test_agents_im_binding_in_drawer():
    html = ADMIN_HTML
    # IM channel binding moved into the drawer (deploy modal removed)
    assert 'id="ag-deploy-modal"' not in html
    assert "function agBindChannel" in html
    chfn = html.split("async function agBindChannel", 1)[1].split("async function", 1)[0]
    assert "/bindings/channels/" in chfn


def test_agent_export_yaml_wired():
    html = ADMIN_HTML
    assert "function agExportYaml" in html
    assert "/agent-yaml" in html
    assert "agExportYaml(" in html  # button in the drawer


def test_agent_deploy_wired():
    html = ADMIN_HTML
    assert "function agDeploy" in html
    assert "/deploy" in html
    assert "agDeploy(" in html  # button in the preview


def test_agent_drawer_preview_is_readonly_yaml():
    html = ADMIN_HTML
    # clicking a card opens a read-only agent.yaml preview, not the editable sections
    fn = html.split("async function agDrawer", 1)[1].split("function agRenderPreview", 1)[0]
    assert "/agent-yaml" in fn
    assert "function agRenderPreview" in html
    preview = html.split("function agRenderPreview", 1)[1].split("function agCopyYaml", 1)[0]
    assert 'id="ag-yaml-pre"' in preview
    # A single "Edit" opens the new-agent modal (prefilled); no separate binding button.
    assert "agEdit(" in preview
    assert "Manage bindings" not in preview
    # copy + download the previewed yaml
    assert "function agCopyYaml" in html and "function agDownloadYaml" in html


def test_agent_bindings_are_searchable_multiselect():
    html = ADMIN_HTML
    fn = html.split("async function agLoadCreateBindings", 1)[1].split("function agMsWidget", 1)[0]
    # skills / connectors(mcp+oauth) / im users render as the multi-select widget
    for call in (
        'agMsWidget("agm-skills"',
        'agMsWidget("agm-mcp"',
        'agMsWidget("agm-oauth"',
        'agMsWidget("agm-users"',
        'agMsWidget("agm-kb"',
    ):
        assert call in fn, call
    # the widget supports name filtering + chip selection; classes preserved for save-diff
    widget = html.split("function agMsWidget", 1)[1].split("function agMsOpen", 1)[0]
    assert "ms-search" in widget and "agMsFilter(" in widget
    assert "ms-chips" in widget
    # the old standalone user filter input is gone
    assert 'id="agm-user-filter"' not in html
    assert "agmFilterUsers" not in html
    # an outside click collapses an open panel so it stops covering the form
    assert 'e.target.closest(".ms")' in html
    collapse_panels = (
        'for (const p of document.querySelectorAll(".ms-panel")) p.classList.add("hidden")'
    )
    assert collapse_panels in html


def test_agent_model_overrides_pick_from_providers():
    html = ADMIN_HTML
    render = html.split("function agRenderModelOverrides", 1)[1].split(
        "function agCollectModelOverrides", 1
    )[0]
    # Each level is a provider dropdown sourced from the configured registry —
    # no free-text model / base_url_env inputs.
    assert "AG_PROVIDERS" in render
    assert "agmo-model" not in render
    assert "agmo-baseurl" not in render
    collect = html.split("function agCollectModelOverrides", 1)[1].split("\n}", 1)[0]
    assert "AG_PROVIDERS.find" in collect  # model derived from the chosen provider
    # providers are loaded when the modal opens (create + edit)
    assert 'AG_PROVIDERS = await api("GET", "/providers")' in html
    assert (
        'api("GET", "/providers")'
        in html.split("async function agEdit", 1)[1].split("async function agApplyEditBindings", 1)[
            0
        ]
    )


def test_agent_edit_reuses_new_agent_modal_prefilled():
    html = ADMIN_HTML
    fn = html.split("async function agEdit", 1)[1].split("async function agApplyEditBindings", 1)[0]
    # Edit opens the shared ag-modal in edit mode with the create sections visible.
    assert 'dataset.mode = "edit"' in fn
    assert "getElementById" not in fn  # uses $() like the rest
    for shown in ('"ag-create-extra"', '"ag-bind-config"'):
        assert shown in fn
    # prefill: model overrides + capabilities YAML + bindings
    assert "agFillModelOverrides(" in fn
    assert "agToolsToYaml(" in fn
    assert "agLoadCreateBindings(current)" in fn
    # save applies a binding diff (add + remove)
    diff = html.split("async function agApplyEditBindings", 1)[1].split("async function agSave", 1)[
        0
    ]
    assert "DELETE" in diff and "POST" in diff
    assert "capabilities_yaml" in html.split("async function agSave", 1)[1].split("\n}", 1)[0]


def test_drawer_loads_from_aggregate_endpoints():
    html = ADMIN_HTML
    fn = html.split("async function agDrawerManage", 1)[1].split("function agDrawerSection", 1)[0]
    # the manage view pulls every per-agent binding list in one fan-out
    for frag in ("/bindings`", "/skills`", "/kbs`", "/bindings/oauth`", "/versions`"):
        assert frag in fn, frag
    # plus the available-option catalogs
    assert '"/mcp/servers"' in fn and '"/connectors"' in fn and '"/kb"' in fn
    # each binding sub-list degrades to a default on failure so one erroring endpoint
    # (e.g. an unmigrated table -> HTTP 500) can't blank the whole drawer
    for frag in (
        "/bindings`).catch(",
        "/skills`).catch(",
        "/kbs`).catch(",
        "/bindings/oauth`).catch(",
    ):
        assert frag in fn, frag


def test_bindings_skill_toggle_wired_to_put():
    html = ADMIN_HTML
    fn = html.split("function agSetSkill", 1)[1].split("\nasync function", 1)[0]
    assert '"PUT"' in fn or "'PUT'" in fn
    assert "/skills/" in fn
    assert "enabled" in fn


def test_bindings_mcp_and_oauth_toggle_wired_to_post_delete():
    html = ADMIN_HTML
    mcp = html.split("async function agToggleMcp", 1)[1].split("\nasync function", 1)[0]
    assert "POST" in mcp and "DELETE" in mcp and "/bindings/mcp/" in mcp
    oauth = html.split("async function agToggleOauth", 1)[1].split("\nasync function", 1)[0]
    assert "POST" in oauth and "DELETE" in oauth and "/bindings/oauth/" in oauth


def test_bindings_write_controls_viewer_gated():
    html = ADMIN_HTML
    # the drawer render helper gates every binding control behind IS_VIEWER
    render = html.split("function agRenderDrawer", 1)[1].split("async function agSetSkill", 1)[0]
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
    for group in ("access", "agents", "resources", "ops"):
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
    assert html.count("<table>") >= 10


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


def test_im_identity_row_actions_are_limited_to_identity_scope():
    body = _render_users_body(ADMIN_HTML)
    # An IM identity is dependent: its actions are limited to identity scope.
    # It must NOT carry the platform user's lifecycle config (that lives on the
    # user row), so the two menus stay distinct.
    idrows = body[body.index("const idRows ") : body.index("const idBlock ")]
    assert "openBindModal(" in idrows  # reassign which platform user it attaches to
    assert "imBlock(" in idrows
    assert "imRestore(" in idrows
    # No user-lifecycle actions duplicated onto the identity row.
    for forbidden in ("openEditUser(", "setRole(", "resetPassword(", "viewKeys(", "del("):
        assert forbidden not in idrows
    # Identity-scoped edit + delete present.
    assert "openImEdit(" in idrows
    assert "imDelete(" in idrows


def test_im_identity_has_edit_and_delete():
    html = ADMIN_HTML
    # Edit modal edits per-platform METADATA; the handle is read-only/auto-captured.
    assert 'id="im-edit-modal"' in html
    assert 'id="ie-fields"' in html  # dynamic per-platform field container
    assert 'id="ie-head"' in html  # read-only handle summary
    assert "IM_FIELDS" in html  # field schema fetched from the API
    assert '"/im-users/fields"' in html
    # User ID is auto-captured but admin-overridable.
    assert 'id="ie-puid"' in html
    assert "auto-captured, edit to override" in html
    assert "doImEdit(" in html
    assert '"PATCH", `/im-users/${IM_EDIT_ID}`, { platform_user_id, metadata }' in html
    # Delete wired to the DELETE endpoint with a confirm guard.
    assert 'api("DELETE", `/im-users/${id}`)' in html
    assert "confirmDialog(" in html[html.index("async function imDelete") :]


def test_bind_modal_is_searchable_user_picker():
    html = ADMIN_HTML
    # Redesigned bind flow: a searchable user picker, not a bare <select>.
    assert 'id="bind-user-select"' not in html
    assert 'id="bind-search"' in html
    assert 'id="bind-user-list"' in html
    assert "bindFilterUsers(" in html
    assert "bindRenderUsers(" in html
    # Modal shows which identity is being reassigned + its current owner.
    assert 'id="bind-im-summary"' in html
    assert "Currently linked to" in html
    # Clicking a user row links it directly (id passed to doBindIm).
    assert "doBindIm('" in html or "doBindIm(`" in html
    # Platform icons for friendlier context.
    assert "PLATFORM_ICON" in html


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


def test_edit_user_profile_modal_and_wiring():
    html = ADMIN_HTML
    # edit modal with name + email fields
    assert 'id="edit-user-modal"' in html
    assert 'id="eu-name"' in html and 'id="eu-email"' in html
    # functions present and wired to PATCH /users/{id}
    for fn in ("function openEditUser", "function closeEditUser", "function saveUser"):
        assert fn in html, fn
    save = html.split("async function saveUser", 1)[1].split("async function setRole", 1)[0]
    assert 'api("PATCH", `/users/${id}`' in save
    # admin-gated Edit action on each user row
    body = _render_users_body(html)
    assert "openEditUser('" in body and "IS_VIEWER" in body


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


# --- legacy module search (unify-legacy-console-modules) -----------------------


def _section(html, tab):
    start = html.index(f'<section id="tab-{tab}"')
    nxt = html.find('<section id="tab-', start + 10)
    return html[start : nxt if nxt > 0 else start + 8000]


def test_agent_icon_picker_present():
    html = ADMIN_HTML
    assert 'id="ag-icon"' in html and 'id="ag-icon-palette"' in html
    assert "function agSetIcon" in html and "function agRenderIconPalette" in html
    # save sends icon; card renders the chosen icon
    save = html.split("function agSave", 1)[1].split("function agDelete", 1)[0]
    assert "icon" in save
    card = html.split("function agentCardHtml", 1)[1].split("function ", 2)[0]
    assert "a.icon" in card


def test_chat_session_history_present():
    html = ADMIN_HTML
    # per-user session history sidebar in the chat module
    assert 'id="chat-history-list"' in html
    assert "function chatLoadHistory" in html
    assert "function chatOpen" in html and "function chatDelete" in html
    assert 'api("GET", "/chat/sessions")' in html
    # delete + open hit the per-session endpoints
    assert "/chat/${encodeURIComponent(sid)}" in html


def test_api_error_message_handles_object_detail():
    html = ADMIN_HTML
    # object/array FastAPI `detail` (e.g. the "agent still bound" 409) renders
    # readably instead of "[object Object]"
    assert "function apiErrorMessage" in html
    assert "apiErrorMessage(data.detail)" in html
    fn = html.split("function apiErrorMessage", 1)[1].split("async function doLogin", 1)[0]
    assert "Array.isArray" in fn and ".error" in fn


def test_api_helper_retries_on_network_failure():
    html = ADMIN_HTML
    fn = html.split("async function api(", 1)[1].split("async function doLogin", 1)[0]
    # the shared api() rides over a transient fetch failure (dev --reload bounce)
    assert "failed to fetch" in fn.lower()
    assert "setTimeout" in fn
    assert "attempt" in fn


def test_legacy_modules_have_search_in_page_header():
    html = ADMIN_HTML
    # each legacy list module fills its .ph-filter slot with a search input
    for tab, fid in [
        ("sessions", "sess-filter"),
        ("monitoring", "mon-filter"),
        ("stats", "st-filter"),
    ]:
        sec = _section(html, tab)
        filt = sec.split('class="ph-filter"', 1)[1].split("</div>", 1)[0]
        assert f'id="{fid}"' in filt, f"{tab}: search input missing from .ph-filter"


def test_legacy_module_search_filters_rows():
    html = ADMIN_HTML
    # render/filter functions reference their search value, so typing narrows rows
    for fid, fn in [
        ("sess-filter", "function renderSessions"),
        ("mon-filter", "function renderMonAlerts"),
        ("st-filter", "function renderStatsRows"),
    ]:
        assert fn in html, f"missing render fn {fn}"
        body = html.split(fn, 1)[1][:1400]
        assert fid in body, f"{fn} does not consult #{fid}"
