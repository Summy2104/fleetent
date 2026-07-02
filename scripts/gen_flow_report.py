"""Render a per-page "frontend functionality <-> API" flow report to a single HTML file.

Unlike gen_api_report.py (auto-derived from openapi.json), this report is built from a
curated data file assembled by reading each frontend page's code: for every page it maps
each UI action to the hook it triggers, the endpoint it calls, what it does, and the flow /
state transition that follows. Personal, gitignored artifact.

Usage:
    uv run python scripts/gen_flow_report.py [input_flow-data.json] [output.html]

Defaults: frontend/.openapi/flow-data.json -> frontend/.openapi/frontend-flow-report.html

flow-data.json schema:
{
  "pages": [
    {"feature","route","title","summary","pageFlow",
     "functions":[{"uiAction","hook","method","path","purpose","flow"}]}
  ]
}
"""

import html
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = REPO_ROOT / "frontend" / ".openapi" / "flow-data.json"
DEFAULT_OUT = REPO_ROOT / "frontend" / ".openapi" / "frontend-flow-report.html"

METHOD_COLORS = {
    "GET": "#1f9d57",
    "POST": "#2563eb",
    "PUT": "#d97706",
    "PATCH": "#7c3aed",
    "DELETE": "#dc2626",
    "WS": "#0891b2",
}


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def slug(route: str) -> str:
    """Stable anchor id from a route (unique even when two pages share a feature)."""
    s = "".join(c if c.isalnum() else "-" for c in str(route)).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s or "root"


def render_function_rows(functions: list[dict[str, Any]]) -> str:
    rows = ""
    for fn in functions:
        method = str(fn.get("method", "")).upper()
        color = METHOD_COLORS.get(method, "#666")
        path = esc(fn.get("path", ""))
        rows += (
            "<tr>"
            f"<td>{esc(fn.get('uiAction'))}</td>"
            f"<td class='mono hook'>{esc(fn.get('hook'))}</td>"
            f"<td class='ep'><span class='m' style='background:{color}'>{esc(method)}</span>"
            f"<span class='mono'>{path}</span></td>"
            f"<td>{esc(fn.get('purpose'))}</td>"
            f"<td class='flow'>{esc(fn.get('flow'))}</td>"
            "</tr>"
        )
    return rows


def render_page(page: dict[str, Any]) -> str:
    fns = page.get("functions", [])
    anchor = "p-" + slug(page.get("route", page.get("feature", "x")))
    return (
        f"<section id='{anchor}'>"
        f"<div class='phead'><h2>{esc(page.get('title'))}</h2>"
        f"<span class='route mono'>{esc(page.get('route'))}</span>"
        f"<span class='fcount'>{len(fns)} 个接口调用</span></div>"
        f"<p class='summary'>{esc(page.get('summary'))}</p>"
        f"<div class='pageflow'><span class='pf-label'>流程流转</span>{esc(page.get('pageFlow'))}</div>"
        "<table class='t'><thead><tr>"
        "<th>UI 动作</th><th>Hook / 函数</th><th>接口</th><th>作用</th><th>流程流转</th>"
        "</tr></thead><tbody>"
        f"{render_function_rows(fns)}"
        "</tbody></table>"
        "</section>"
    )


def render_html(data: dict[str, Any]) -> str:
    pages = data.get("pages", [])
    total_fns = sum(len(p.get("functions", [])) for p in pages)
    nav = "".join(
        f"<a href='#p-{slug(p.get('route', p.get('feature')))}'>{esc(p.get('title'))}"
        f"<span class='cnt'>{len(p.get('functions', []))}</span></a>"
        for p in pages
    )
    sections = "".join(render_page(p) for p in pages)

    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>fleetent · 前端页面 × 接口 × 流程</title>
<style>
  :root {{ --bg:#0f1115; --panel:#171a21; --line:#262b36; --txt:#e6e9ef; --mut:#9aa4b2; --acc:#4f8cff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt); font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif; }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  header {{ padding:20px 28px; border-bottom:1px solid var(--line); background:var(--panel); position:sticky; top:0; z-index:5; }}
  header h1 {{ margin:0 0 4px; font-size:18px; }}
  header .meta {{ color:var(--mut); font-size:13px; }}
  header .notes {{ margin-top:8px; font-size:12.5px; color:var(--mut); }}
  #search {{ margin-top:12px; width:100%; max-width:520px; padding:8px 12px; background:#0c0e12; border:1px solid var(--line); border-radius:8px; color:var(--txt); font-size:14px; }}
  .wrap {{ display:flex; align-items:flex-start; }}
  nav {{ position:sticky; top:150px; width:210px; flex:0 0 210px; padding:18px 10px 40px 18px; max-height:calc(100vh - 150px); overflow:auto; }}
  nav a {{ display:flex; justify-content:space-between; gap:8px; padding:6px 10px; border-radius:6px; color:var(--mut); text-decoration:none; font-size:13px; }}
  nav a:hover {{ background:var(--panel); color:var(--txt); }}
  nav .cnt {{ color:#5b6472; font-size:11px; }}
  main {{ flex:1; padding:18px 28px 80px; min-width:0; }}
  section {{ margin-bottom:38px; }}
  .phead {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; border-bottom:1px solid var(--line); padding-bottom:6px; }}
  .phead h2 {{ font-size:16px; color:var(--acc); margin:0; }}
  .route {{ font-size:13px; color:#cbb24f; background:#222732; padding:1px 8px; border-radius:5px; }}
  .fcount {{ font-size:12px; color:#5b6472; margin-left:auto; }}
  .summary {{ color:var(--txt); font-size:13.5px; margin:10px 0 8px; }}
  .pageflow {{ background:#12161d; border:1px solid var(--line); border-left:3px solid var(--acc); border-radius:8px; padding:10px 14px; font-size:13px; color:#c8d0dc; margin-bottom:14px; }}
  .pf-label {{ display:inline-block; font-size:11px; letter-spacing:.08em; color:var(--acc); text-transform:uppercase; margin-right:8px; }}
  table.t {{ width:100%; border-collapse:collapse; font-size:13px; table-layout:fixed; }}
  table.t th {{ text-align:left; color:var(--mut); font-weight:500; border-bottom:1px solid var(--line); padding:7px 9px; }}
  table.t td {{ border-bottom:1px solid #1d212b; padding:8px 9px; vertical-align:top; word-break:break-word; }}
  table.t th:nth-child(1),td:nth-child(1) {{ width:15%; }}
  table.t th:nth-child(2),td:nth-child(2) {{ width:14%; }}
  table.t th:nth-child(3),td:nth-child(3) {{ width:22%; }}
  table.t th:nth-child(4),td:nth-child(4) {{ width:20%; }}
  table.t th:nth-child(5),td:nth-child(5) {{ width:29%; }}
  .m {{ color:#fff; font-weight:700; font-size:10px; padding:1px 6px; border-radius:4px; margin-right:6px; }}
  .ep .mono {{ font-size:12px; word-break:break-all; }}
  .hook {{ color:#7fd0ff; font-size:12px; }}
  .flow {{ color:#b9c2cf; }}
  .hidden {{ display:none; }}
</style>
</head>
<body>
<header>
  <h1>fleetent · 前端页面 × 接口 × 流程流转</h1>
  <div class="meta">{len(pages)} 个页面 · {total_fns} 条「UI 动作 → 接口」映射 · 由逐页阅读前端代码整理</div>
  <div class="notes">每页含一段整体<b>流程流转</b>叙述,下表逐条对应:UI 动作 → 触发的 Hook → 后端接口 → 作用 → 调用后的流程/状态流转。</div>
  <input id="search" placeholder="搜索：动作 / hook / 路径 / 作用…" oninput="filter(this.value)"/>
</header>
<div class="wrap">
  <nav>{nav}</nav>
  <main>{sections}</main>
</div>
<script>
  function filter(q) {{
    q = q.trim().toLowerCase();
    document.querySelectorAll('table.t tbody tr').forEach(tr => {{
      tr.classList.toggle('hidden', q && !tr.textContent.toLowerCase().includes(q));
    }});
    document.querySelectorAll('section').forEach(s => {{
      const any = [...s.querySelectorAll('tbody tr')].some(tr => !tr.classList.contains('hidden'));
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
        print(f"error: {in_path} not found", file=sys.stderr)
        return 1
    data = json.loads(in_path.read_text(encoding="utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(data), encoding="utf-8")
    pages = data.get("pages", [])
    fns = sum(len(p.get("functions", [])) for p in pages)
    print(f"wrote {out_path} ({len(pages)} pages, {fns} action->endpoint mappings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
