#!/usr/bin/env python3
"""Render biz_transactions API response to a compact TSV table.

Input  (--input):  JSON file containing the raw response of
                   GET /v1/biz_transactions
                   {header: [...], page_info: {...}, rows: "<json-string>"}

Output (--output): TSV file (tab-separated, one row per record);
                   stdout prints one-line summary.

Why a script: the raw response is huge (header alone is thousands of lines
because one enum field can carry 150+ candidate values). Loading it into
the LLM context wastes tokens. The script handles:
  - parsing the `rows` JSON string (yes, it's a string, not an array)
  - mapping dynamic field names fN -> Chinese display name via header
  - mapping enum id -> name via header[i].attr_value
  - dropping columns where is_used=false or all values in this batch empty
  - sorting columns by header.sort ascending

No external deps; stdlib only.
"""
import argparse
import json
import sys
from pathlib import Path

# Fixed columns prepended to every row (not in header[])
FIXED_COLS = [
    ("#", None),
    ("流程编号", "process_instance_number"),
    ("创建时间", "created_at"),
]


def _is_empty(v):
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _fmt_time(s):
    """2026-04-20T05:27:20Z -> 2026-04-20 05:27:20 (UTC)."""
    if not isinstance(s, str) or len(s) < 19:
        return s or "-"
    return s[:10] + " " + s[11:19]


def _build_header_index(header):
    """Return ordered list of (field_name, display_name, attr_id, enum_map, sort).

    Note: we intentionally do NOT filter by `is_used`. Empirically every field
    in real responses has is_used=false even when the field is clearly
    populated in rows (e.g. 借贷币种, 行为). The meaning of is_used in the
    API is unclear, so we trust the "non-empty in this batch" filter below
    instead, which is a behavior-based signal.
    """
    items = []
    for col in header or []:
        enum_map = {}
        for v in col.get("attr_value") or []:
            if isinstance(v, dict) and v.get("id"):
                enum_map[str(v["id"])] = v.get("name", str(v["id"]))
        items.append({
            "field_name": col.get("field_name"),
            "name": col.get("name", col.get("field_name", "")),
            "attr_id": col.get("attr_id"),
            "enum_map": enum_map,
            "sort": col.get("sort", 9999),
        })
    items.sort(key=lambda x: x["sort"])
    return items


def _render_cell(col_def, raw):
    if _is_empty(raw):
        return "-"
    attr_id = col_def.get("attr_id")
    enum_map = col_def.get("enum_map") or {}
    # attr_id 4 = date
    if attr_id == 4:
        return _fmt_time(raw)
    # attr_id 6 / 7 = enum (behavior / fund tag)
    if attr_id in (6, 7):
        return enum_map.get(str(raw), str(raw))
    return str(raw)


def render(resp, table_name=None, max_rows=50):
    header = resp.get("header") or []
    page_info = resp.get("page_info") or {}
    rows_field = resp.get("rows")
    if isinstance(rows_field, str):
        rows = json.loads(rows_field) if rows_field.strip() else []
    elif isinstance(rows_field, list):
        rows = rows_field
    else:
        rows = []

    cols = _build_header_index(header)

    # Trim to max_rows
    rows = rows[:max_rows]

    # Find which dynamic columns have at least one non-empty value in this batch;
    # drop columns that are entirely empty in the trimmed batch.
    keep = []
    for c in cols:
        fn = c["field_name"]
        if any(not _is_empty(r.get(fn)) for r in rows):
            keep.append(c)

    # Also promote transaction_behavior if it exists in rows but not in kept header
    # (transaction_behavior is technically in header too, covered by loop above)

    # Build table columns (TSV): fixed head + dynamic + trailing 流程标题
    headers = [h for h, _ in FIXED_COLS] + [c["name"] for c in keep] + ["流程标题"]

    def _tsv_escape(v):
        s = "" if v is None else str(v)
        # Strip tabs / newlines so TSV structure isn't broken
        return s.replace("\t", " ").replace("\r", " ").replace("\n", " ")

    lines = [
        "\t".join(_tsv_escape(h) for h in headers)
    ]
    for i, r in enumerate(rows, 1):
        cells = [
            str(i),
            r.get("process_instance_number") or "-",
            _fmt_time(r.get("created_at")),
        ]
        for c in keep:
            cells.append(_render_cell(c, r.get(c["field_name"])))
        title_val = r.get("email_title") or "-"
        if isinstance(title_val, str) and len(title_val) > 60:
            title_val = title_val[:60] + "…"
        cells.append(title_val)
        lines.append("\t".join(_tsv_escape(c) for c in cells))

    tsv = "\n".join(lines) + "\n"
    total = page_info.get("total", "?")
    shown = len(rows)
    title = table_name or "业务流水"
    summary = f"{title} | total={total} | shown={shown} | cols={len(keep)}"
    return tsv, summary


def main(argv=None):
    p = argparse.ArgumentParser(description="Render biz_transactions response to TSV.")
    p.add_argument("--input", required=True, help="Path to raw API response JSON")
    p.add_argument("--output", required=True, help="Path to write TSV")
    p.add_argument("--table-name", default=None, help="Table display name (e.g. 借贷-质押借贷外)")
    p.add_argument("--max-rows", type=int, default=50)
    args = p.parse_args(argv)

    resp = json.loads(Path(args.input).read_text(encoding="utf-8"))
    tsv, summary = render(resp, table_name=args.table_name, max_rows=args.max_rows)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tsv, encoding="utf-8")

    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
