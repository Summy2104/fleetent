"""Render the platform OpenAPI schema into a self-contained HTML API report,
grouped by the frontend feature (page) that consumes each endpoint.

Pipeline:
  1. Read the dumped ``openapi.json`` (see ``dump_openapi.py``).
  2. Scan ``frontend/src/features/**`` to learn which feature calls which endpoint.
  3. Merge a small curated map for endpoints reached via dynamic paths / nested
     template literals that the regex scan cannot resolve.
  4. Emit one static HTML file: each frontend feature is a section listing the
     endpoints it uses (purpose, params, request body), with cross-use tags; a
     final section lists backend-only endpoints no frontend page touches.

The report is a personal, gitignored artifact — a readable companion to the type
oracle, not a committed document.

Usage:
    uv run python scripts/gen_api_report.py [input_openapi.json] [output.html]

Defaults: ``frontend/.openapi/openapi.json`` -> ``frontend/.openapi/api-report.html``.
"""

import html
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = REPO_ROOT / "frontend" / ".openapi" / "openapi.json"
DEFAULT_OUT = REPO_ROOT / "frontend" / ".openapi" / "api-report.html"
FEATURES_DIR = REPO_ROOT / "frontend" / "src" / "features"
# The app shell / auth layer lives outside features/; its API calls are bucketed as "auth".
APP_DIR = REPO_ROOT / "frontend" / "src" / "app"

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
METHOD_COLORS = {
    "get": "#1f9d57",
    "post": "#2563eb",
    "put": "#d97706",
    "patch": "#7c3aed",
    "delete": "#dc2626",
}

# Frontend feature -> (display title, what the page does). Order defines report order.
FEATURES: dict[str, tuple[str, str]] = {
    "auth": (
        "Auth · 登录与认证",
        "app shell / 认证层(src/app):登录、登出、当前用户、OIDC 单点登录流程。",
    ),
    "agents": (
        "Agents · Agent 管理",
        "Agent 的增删改查、生命周期(启用/停用/归档/恢复)、克隆、设为默认,"
        "以及技能 / MCP / 知识库 / 用户 / IM 群组的绑定与运行密钥管理。",
    ),
    "chat": (
        "Chat · 对话调试",
        "在控制台里直接和指定 agent 对话(HTTP chat;流式走 WebSocket,不在 OpenAPI 内)。",
    ),
    "skills": (
        "Skills · 技能管理",
        "Skill 内容 / 版本 / diff、提案与 backflow 审核、与 agent 的绑定,"
        "以及启用/停用/恢复/强制发布。",
    ),
    "connectors": (
        "Connectors · MCP 连接器",
        "MCP server 的增删改查、连通性诊断(doctor)、重连、测试、工具列表。",
    ),
    "kb": (
        "Knowledge Base · 知识库",
        "知识库与文档管理、与 agent 的绑定、检索与评估。",
    ),
    "providers": (
        "Providers · 模型供应商",
        "模型 Provider 的配置、密钥与健康检查。",
    ),
    "nodes": (
        "Nodes · 部署节点",
        "托管部署节点的注册、状态上报与期望态管理。",
    ),
    "tenancy": (
        "Tenancy · 租户/团队管理",
        "多租户与团队的管理、成员与分配。",
    ),
    "stats": (
        "Stats · 统计分析",
        "Agent / 用户 / 会话的用量与调用统计、对比、trace 与导出。",
    ),
    "users": (
        "Users · 用户与密钥",
        "用户增删改、角色设置、封禁/解封、改密,以及 API Key 的签发、轮换、吊销。",
    ),
    "profile": (
        "Profile · 个人资料",
        "当前登录用户信息与修改密码。",
    ),
    "teams": (
        "Teams · 团队",
        "团队视图(读取当前用户与用户列表用于成员分配)。",
    ),
    "mcp": (
        "MCP · MCP 页",
        "MCP 相关页面外壳(当前仅读取登录用户做权限判断;server 管理见 Connectors)。",
    ),
    "audit": (
        "Audit · 审计日志",
        "管理操作的审计日志查询。",
    ),
}

# Endpoints reached via dynamic path segments or nested template literals that the
# regex scan cannot resolve. Keys are normalized ("METHOD /path/with/{}"). Verified
# against the frontend action dispatchers (agent/session/skill lifecycle, query builders).
CURATED: dict[str, list[str]] = {
    # Auth flow uses raw fetch / browser navigation (no token yet), which the api.* scan misses.
    "auth": [
        "POST /admin/login",
        "GET /admin/oidc/config",
        "GET /admin/oidc/login",
        "GET /admin/oidc/callback",
    ],
    "agents": [
        "GET /admin/agents",  # also the list backing chat's picker
        "POST /admin/agents/{}/enable",
        "POST /admin/agents/{}/disable",
        "POST /admin/agents/{}/archive",
        "POST /admin/agents/{}/restore",
    ],
    "chat": [
        "GET /admin/agents",
        "POST /admin/agents/{}/chat",
    ],
    "skills": [
        "POST /admin/skills/{}/disable",
        "POST /admin/skills/{}/enable",
        "POST /admin/skills/{}/restore",
    ],
    "stats": [
        "GET /admin/stats/agents/{}/overview",
        "GET /admin/stats/compare",
        "GET /admin/stats/sessions/{}/trace",
    ],
    "kb": [
        "DELETE /admin/kb/{}",
        "DELETE /admin/kb/{}/documents/{}",
    ],
    "audit": [
        "GET /admin/audit",
    ],
}

_CALL_RE = re.compile(
    r"""api\.(get|post|put|patch|delete)\s*(?:<[^(]*>)?\s*\(\s*([`'"])(.*?)\2""",
    re.S,
)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def normalize(path: str) -> str:
    path = re.sub(r"\$\{[^}]*\}", "{}", path)  # ${...} template interpolation
    path = re.sub(r"\{[^}]*\}", "{}", path)  # {param} openapi placeholder
    path = path.split("?")[0]
    return path.rstrip("/") or "/"


def scan_frontend_usage() -> dict[str, set[str]]:
    """Map normalized "METHOD /path" -> set of frontend feature names that call it."""
    usage: dict[str, set[str]] = {}

    def add(key: str, feature: str) -> None:
        usage.setdefault(key, set()).add(feature)

    def scan_dir(root: Path, feature: str) -> None:
        if not root.is_dir():
            return
        for src_file in root.rglob("*"):
            if src_file.suffix not in (".ts", ".tsx") or ".test." in src_file.name:
                continue
            text = src_file.read_text(encoding="utf-8", errors="ignore")
            for method, _q, raw in _CALL_RE.findall(text):
                path = normalize(raw)
                if path.startswith("/"):
                    add(f"{method.upper()} {path}", feature)

    present = set()
    if FEATURES_DIR.is_dir():
        for feature_dir in FEATURES_DIR.iterdir():
            if feature_dir.is_dir():
                present.add(feature_dir.name)
                scan_dir(feature_dir, feature_dir.name)

    scan_dir(APP_DIR, "auth")  # app shell / auth layer
    present.add("auth")  # pseudo-feature, always available

    # Apply curated overrides only for features that still exist in the tree; a curated
    # entry for a deleted feature (e.g. sessions removed on a merge) must NOT resurrect a
    # phantom section — its endpoints fall through to backend-only instead.
    for feature, keys in CURATED.items():
        if feature not in present:
            continue
        for key in keys:
            add(key, feature)
    return usage


def render_type(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "any"
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema or "oneOf" in schema:
        members = schema.get("anyOf") or schema.get("oneOf") or []
        nullable = any(m.get("type") == "null" for m in members)
        rendered = [render_type(m) for m in members if m.get("type") != "null"]
        joined = " | ".join(dict.fromkeys(rendered)) or "any"
        return f"{joined} | null" if nullable else joined
    if "enum" in schema:
        return "enum(" + " | ".join(esc(v) for v in schema["enum"]) + ")"
    typ = schema.get("type")
    if typ == "array":
        return f"{render_type(schema.get('items'))}[]"
    if typ == "object":
        return "object"
    return typ or "any"


def resolve_ref(spec: dict[str, Any], schema: dict[str, Any] | None) -> dict[str, Any] | None:
    if schema and "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return spec.get("components", {}).get("schemas", {}).get(name)
    return schema


def field_rows(spec: dict[str, Any], body_schema: dict[str, Any]) -> list[dict[str, str]]:
    resolved = resolve_ref(spec, body_schema) or {}
    props = resolved.get("properties", {})
    required = set(resolved.get("required", []))
    rows = []
    for name, prop in props.items():
        default = prop.get("default")
        rows.append(
            {
                "name": name,
                "type": render_type(prop),
                "required": "必填" if name in required else "可选",
                "required_cls": "req" if name in required else "opt",
                "default": "" if default is None else json.dumps(default, ensure_ascii=False),
                "desc": prop.get("description", ""),
            }
        )
    return rows


def build_operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    ops = []
    for path, item in spec.get("paths", {}).items():
        for method in HTTP_METHODS:
            op = item.get(method)
            if not op:
                continue
            params = [
                p
                for p in op.get("parameters", [])
                if not (p.get("name") == "authorization" and p.get("in") == "header")
            ]
            needs_auth = any(
                p.get("name") == "authorization" and p.get("in") == "header"
                for p in op.get("parameters", [])
            )
            body_schema = (
                op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            )
            ok = op.get("responses", {}).get("200") or op.get("responses", {}).get("201") or {}
            ok_schema = ok.get("content", {}).get("application/json", {}).get("schema", {})
            untyped_resp = bool(ok) and (
                ok_schema.get("additionalProperties") is True
                or (ok_schema.get("type") == "object" and "properties" not in ok_schema)
                or not ok_schema
            )
            ops.append(
                {
                    "method": method,
                    "path": path,
                    "key": f"{method.upper()} {normalize(path)}",
                    "summary": op.get("summary", ""),
                    "description": op.get("description", ""),
                    "needs_auth": needs_auth,
                    "params": params,
                    "body_rows": field_rows(spec, body_schema) if body_schema else [],
                    "untyped_resp": untyped_resp,
                }
            )
    return ops


def render_params(params: list[dict[str, Any]]) -> str:
    if not params:
        return ""
    rows = ""
    for p in params:
        rows += (
            "<tr>"
            f"<td class='mono'>{esc(p.get('name'))}</td>"
            f"<td><span class='loc loc-{esc(p.get('in'))}'>{esc(p.get('in'))}</span></td>"
            f"<td class='mono'>{esc(render_type(p.get('schema')))}</td>"
            f"<td class='{'req' if p.get('required') else 'opt'}'>{'必填' if p.get('required') else '可选'}</td>"
            "</tr>"
        )
    return (
        "<div class='sub'>参数</div><table class='t'><thead><tr>"
        "<th>名称</th><th>位置</th><th>类型</th><th>必填</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def render_body(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    trs = ""
    for r in rows:
        default = f"<code>{esc(r['default'])}</code>" if r["default"] else ""
        trs += (
            "<tr>"
            f"<td class='mono'>{esc(r['name'])}</td>"
            f"<td class='mono'>{esc(r['type'])}</td>"
            f"<td class='{r['required_cls']}'>{r['required']}</td>"
            f"<td>{default}</td>"
            f"<td>{esc(r['desc'])}</td>"
            "</tr>"
        )
    return (
        "<div class='sub'>请求体 (JSON)</div><table class='t'><thead><tr>"
        "<th>字段</th><th>类型</th><th>必填</th><th>默认</th><th>说明</th></tr></thead>"
        f"<tbody>{trs}</tbody></table>"
    )


def render_card(op: dict[str, Any], co_features: list[str]) -> str:
    color = METHOD_COLORS.get(op["method"], "#666")
    auth = (
        "<span class='auth' title='需要 Authorization: Session &lt;token&gt;'>🔒 Session</span>"
        if op["needs_auth"]
        else ""
    )
    shared = (
        f"<span class='shared' title='多个前端页面共用'>也用于 {esc('、'.join(co_features))}</span>"
        if co_features
        else ""
    )
    desc = f"<p class='desc'>{esc(op['description'])}</p>" if op["description"] else ""
    resp_note = (
        "<div class='note'>响应：<code>object</code>（后端未声明 response_model，类型未知）</div>"
        if op["untyped_resp"]
        else ""
    )
    search_key = esc(f"{op['method']} {op['path']} {op['summary']}".lower())
    return (
        f"<div class='card' data-search='{search_key}'>"
        f"<div class='line'><span class='m' style='background:{color}'>{op['method'].upper()}</span>"
        f"<span class='path mono'>{esc(op['path'])}</span>{auth}{shared}</div>"
        f"<div class='purpose'>{esc(op['summary'] or '—')}</div>"
        f"{desc}{render_params(op['params'])}{render_body(op['body_rows'])}{resp_note}"
        "</div>"
    )


def backend_group(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return "root"
    if parts[0] == "admin":
        return parts[1] if len(parts) > 1 else "admin"
    return parts[0]


def backend_kind(path: str) -> str:
    """Classify a backend-only endpoint.

    'internal' = machine-to-machine / not meant for the admin SPA: node forwarder
    (/nodes/*), agent & external OAuth credential exchange (/mcp/*, /oauth/*),
    inbound webhooks (/webhook/*), health probe (/health), the agent approval-gate
    poll (/approvals), and the SPA's own asset host (/admin/ui*).
    'todo-ui' = an /admin/* control-plane endpoint with no frontend page yet.
    """
    if not path.startswith("/admin") or path.startswith("/admin/ui"):
        return "internal"
    return "todo-ui"


def render_html(spec: dict[str, Any]) -> str:
    ops = build_operations(spec)
    usage = scan_frontend_usage()
    by_key = {op["key"]: op for op in ops}  # note: last op wins per shape; fine for display

    # feature -> [ops], preserving each op object; also track which features hit each key.
    feat_ops: dict[str, list[dict[str, Any]]] = {name: [] for name in FEATURES}
    used_keys: set[str] = set()
    for op in ops:
        features = sorted(usage.get(op["key"], set()), key=lambda f: list(FEATURES).index(f) if f in FEATURES else 999)
        if not features:
            continue
        used_keys.add(op["key"])
        for feat in features:
            if feat in feat_ops:
                feat_ops[feat].append((op, [f for f in features if f != feat]))

    used_count = len(used_keys)
    backend_only = [op for op in ops if op["key"] not in used_keys]

    # ---- nav + feature sections ----
    nav_parts, sections = [], ""
    for name, (title, blurb) in FEATURES.items():
        entries = feat_ops.get(name, [])
        if not entries:
            continue
        nav_parts.append(
            f"<a href='#f-{esc(name)}'>{esc(title)} <span class='cnt'>{len(entries)}</span></a>"
        )
        entries.sort(key=lambda e: (e[0]["path"], e[0]["method"]))
        cards = "".join(render_card(op, co) for op, co in entries)
        sections += (
            f"<section id='f-{esc(name)}'><h2>{esc(title)} <span class='gcnt'>{len(entries)}</span></h2>"
            f"<p class='blurb'>{esc(blurb)}</p>{cards}</section>"
        )

    # ---- backend-only, split into "todo-ui" (should have a page) vs "internal" ----
    todo = [op for op in backend_only if backend_kind(op["path"]) == "todo-ui"]
    internal = [op for op in backend_only if backend_kind(op["path"]) == "internal"]

    def render_backend(anchor: str, cls: str, heading: str, blurb: str, group_ops: list[dict[str, Any]]) -> str:
        if not group_ops:
            return ""
        nav_parts.append(
            f"<a href='#{esc(anchor)}' class='nav-be'>◦ {esc(heading)} <span class='cnt'>{len(group_ops)}</span></a>"
        )
        groups: dict[str, list[dict[str, Any]]] = {}
        for op in group_ops:
            groups.setdefault(backend_group(op["path"]), []).append(op)
        blocks = ""
        for gname in sorted(groups):
            gops = sorted(groups[gname], key=lambda o: (o["path"], o["method"]))
            blocks += f"<h3 class='beh'>{esc(gname)} <span class='gcnt'>{len(gops)}</span></h3>"
            blocks += "".join(render_card(op, []) for op in gops)
        return (
            f"<section id='{esc(anchor)}' class='{cls}'><h2>{esc(heading)} "
            f"<span class='gcnt'>{len(group_ops)}</span></h2>"
            f"<p class='blurb'>{esc(blurb)}</p>{blocks}</section>"
        )

    sections += render_backend(
        "f-todo",
        "backend todo",
        "该接 UI · 还没接的管理端点",
        "存在于 /admin 控制面、当前没有任何前端页面调用——是候选待接入的管理功能"
        "(如 webhook 源管理、KB 检索/评估/绑定、observability、stats 导出等)。",
        todo,
    )
    sections += render_backend(
        "f-internal",
        "backend",
        "真内部 · 非 UI 端点",
        "机器对机器 / 非 admin SPA 使用:node forwarder(/nodes/*)、agent 与外部 OAuth "
        "凭据交换(/mcp/*、/oauth/*)、入站 webhook(/webhook/*)、健康探针(/health)、"
        "审批门轮询(/approvals)、以及托管前端资源的 /admin/ui。",
        internal,
    )

    info = spec.get("info", {})
    title = esc(info.get("title", "API"))
    version = esc(info.get("version", ""))
    total = len(ops)

    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title} · API 报告(按前端页面)</title>
<style>
  :root {{ --bg:#0f1115; --panel:#171a21; --line:#262b36; --txt:#e6e9ef; --mut:#9aa4b2; --acc:#4f8cff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt); font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif; }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  header {{ padding:20px 28px; border-bottom:1px solid var(--line); background:var(--panel); position:sticky; top:0; z-index:5; }}
  header h1 {{ margin:0 0 4px; font-size:18px; }}
  header .meta {{ color:var(--mut); font-size:13px; }}
  header .notes {{ margin-top:10px; font-size:12.5px; color:var(--mut); }}
  header .notes code {{ background:#222732; padding:1px 5px; border-radius:4px; }}
  #search {{ margin-top:12px; width:100%; max-width:520px; padding:8px 12px; background:#0c0e12; border:1px solid var(--line); border-radius:8px; color:var(--txt); font-size:14px; }}
  .wrap {{ display:flex; align-items:flex-start; }}
  nav {{ position:sticky; top:158px; width:236px; flex:0 0 236px; padding:18px 10px 40px 18px; max-height:calc(100vh - 158px); overflow:auto; }}
  nav a {{ display:flex; justify-content:space-between; gap:8px; padding:5px 10px; border-radius:6px; color:var(--mut); text-decoration:none; font-size:13px; }}
  nav a:hover {{ background:var(--panel); color:var(--txt); }}
  nav a.nav-be {{ margin-top:8px; border-top:1px solid var(--line); padding-top:10px; color:#7c8392; }}
  nav .cnt {{ color:#5b6472; font-size:11px; }}
  main {{ flex:1; padding:18px 28px 80px; min-width:0; }}
  section {{ margin-bottom:34px; }}
  section h2 {{ font-size:15px; color:var(--acc); border-bottom:1px solid var(--line); padding-bottom:6px; }}
  section.backend h2 {{ color:#7c8392; }}
  .beh {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--mut); margin:18px 0 4px; }}
  .blurb {{ color:var(--mut); font-size:13px; margin:6px 0 4px; }}
  .gcnt {{ color:#5b6472; font-size:12px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:12px 0; }}
  .line {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
  .m {{ color:#fff; font-weight:700; font-size:11px; padding:2px 8px; border-radius:5px; letter-spacing:.04em; }}
  .path {{ font-size:14px; word-break:break-all; }}
  .auth {{ font-size:11px; color:#cbb24f; border:1px solid #4a431f; padding:1px 7px; border-radius:20px; }}
  .shared {{ font-size:11px; color:#6fb3ff; border:1px solid #244; padding:1px 7px; border-radius:20px; }}
  .purpose {{ margin-top:8px; font-weight:600; }}
  .desc {{ margin:4px 0 0; color:var(--mut); font-size:13px; white-space:pre-wrap; }}
  .sub {{ margin:12px 0 5px; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--mut); }}
  table.t {{ width:100%; border-collapse:collapse; font-size:13px; }}
  table.t th {{ text-align:left; color:var(--mut); font-weight:500; border-bottom:1px solid var(--line); padding:5px 8px; }}
  table.t td {{ border-bottom:1px solid #1d212b; padding:5px 8px; vertical-align:top; }}
  table.t code {{ background:#222732; padding:1px 5px; border-radius:4px; }}
  .req {{ color:#f0a; }} .opt {{ color:var(--mut); }}
  .loc {{ font-size:11px; padding:1px 6px; border-radius:4px; background:#222732; }}
  .loc-path {{ color:#d97706; }} .loc-query {{ color:#1f9d57; }} .loc-header {{ color:#7c3aed; }} .loc-cookie {{ color:#2563eb; }}
  .note {{ margin-top:10px; font-size:12px; color:#7c8392; }}
  .note code {{ background:#222732; padding:1px 5px; border-radius:4px; }}
  .hidden {{ display:none; }}
</style>
</head>
<body>
<header>
  <h1>{title} · API 报告 <span style="color:var(--mut);font-weight:400">按前端页面分类</span></h1>
  <div class="meta">version {version} · 共 {total} 个 HTTP 端点 · 前端使用 {used_count} · 该接UI {len(todo)} · 真内部 {len(internal)} · 数据源 openapi.json</div>
  <div class="notes">
    🔒 = 需 <code>Authorization: Session &lt;token&gt;</code>(已从参数表省略)·
    <span class="shared" style="display:inline">也用于 …</span> = 多个前端页面共用 ·
    不含 WebSocket <code>/admin/agents/{{agent_name}}/ws</code> ·
    响应多为 <code>object</code>(后端未用 response_model)
  </div>
  <input id="search" placeholder="搜索：方法 / 路径 / 作用…" oninput="filter(this.value)"/>
</header>
<div class="wrap">
  <nav>{"".join(nav_parts)}</nav>
  <main>{sections}</main>
</div>
<script>
  function filter(q) {{
    q = q.trim().toLowerCase();
    document.querySelectorAll('.card').forEach(c => {{
      c.classList.toggle('hidden', q && !c.dataset.search.includes(q));
    }});
    document.querySelectorAll('section').forEach(s => {{
      const any = [...s.querySelectorAll('.card')].some(c => !c.classList.contains('hidden'));
      s.classList.toggle('hidden', !any);
    }});
  }}
</script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    in_path = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_IN
    out_path = Path(argv[2]).resolve() if len(argv) > 2 else DEFAULT_OUT
    if not in_path.exists():
        print(f"error: {in_path} not found — run `pnpm openapi:dump` first", file=sys.stderr)
        return 1
    spec = json.loads(in_path.read_text(encoding="utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(spec), encoding="utf-8")

    ops = build_operations(spec)
    usage = scan_frontend_usage()
    used = sum(1 for op in ops if op["key"] in usage)
    print(f"wrote {out_path} ({len(ops)} endpoints, {used} used by frontend, {len(ops) - used} backend-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
