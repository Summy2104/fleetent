#!/usr/bin/env python3
"""Render /v1/biz_transactions/stat response to a compact TSV table.

Input  (--input):  JSON file containing the raw response of
                   GET /v1/biz_transactions/stat
                   {list: [{title, header, rows}, ...]}
                   where header / rows are JSON strings (not arrays).

Output (--output): TSV file with multiple sub-tables (income, actual fund
                   source, theoretical fund source) separated by blank lines;
                   stdout prints one-line summary.

Why a script: the raw response carries 130+ fund-tag columns where most are
null for any given project. Loading it into LLM context wastes tokens. The
script:
  - parses header / rows JSON strings
  - drops columns that are entirely null in this batch (per sub-table)
  - keeps 0 / "" / other non-null values intact
  - preserves the income table as-is (few columns, no filtering)

No external deps; stdlib only.
"""
import argparse
import json
import sys
from pathlib import Path


def _is_null(v):
    return v is None


def _parse_json_field(v):
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        return json.loads(s)
    if isinstance(v, list):
        return v
    return []


def _filter_null_columns(header, rows):
    """Drop columns where every row has null at that index. Returns (new_header, new_rows)."""
    if not header or not rows:
        return header, rows
    keep_idx = []
    for i in range(len(header)):
        if any(not _is_null(r[i] if i < len(r) else None) for r in rows):
            keep_idx.append(i)
    new_header = [header[i] for i in keep_idx]
    new_rows = [[r[i] if i < len(r) else None for i in keep_idx] for r in rows]
    return new_header, new_rows


def _tsv_escape(v):
    if v is None:
        return ""
    s = str(v)
    return s.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _render_subtable(title, header, rows, drop_null_cols):
    if drop_null_cols:
        header, rows = _filter_null_columns(header, rows)
    lines = [f"# {title}"]
    if header:
        lines.append("\t".join(_tsv_escape(h) for h in header))
    for r in rows:
        lines.append("\t".join(_tsv_escape(c) for c in r))
    return lines, len(header), len(rows)


# Sub-tables that should drop all-null columns. Match by Chinese title.
DROP_NULL_TITLES = {"实际资金来源", "理论资金来源"}


def render(resp):
    items = resp.get("list") or []
    output_lines = []
    summary_parts = []
    for item in items:
        title = item.get("title") or "-"
        header = _parse_json_field(item.get("header"))
        rows = _parse_json_field(item.get("rows"))
        drop = title in DROP_NULL_TITLES
        block, n_cols, n_rows = _render_subtable(title, header, rows, drop)
        output_lines.extend(block)
        output_lines.append("")  # blank line between sub-tables
        summary_parts.append(f"{title}(cols={n_cols},rows={n_rows})")
    tsv = "\n".join(output_lines).rstrip() + "\n"
    summary = "项目资金来源汇总 | " + " | ".join(summary_parts)
    return tsv, summary


def resolve_project_field(detail: dict) -> str:
    """Return the field_name for '项目编号' from a biz_transaction_header detail response.

    Different business tables define '项目编号' at different positions (f1, f2, ...).
    Always look it up dynamically; never hard-code 'f1'.
    Raises ValueError if not found.
    """
    for h in detail.get("headers", []):
        if h.get("name") == "项目编号":
            field_name = h.get("field_name", "").strip()
            if field_name:
                return field_name
    raise ValueError('No header with name="项目编号" found')


def main(argv=None):
    p = argparse.ArgumentParser(description="Render biz_transactions/stat response to TSV, or resolve project field_name.")
    p.add_argument("--input", required=True, help="Path to raw API response JSON")
    p.add_argument("--output", help="Path to write TSV (omit when using --resolve-field)")
    p.add_argument("--resolve-field", action="store_true",
                   help="Instead of rendering, print the field_name for '项目编号' from a biz_transaction_header detail JSON")
    args = p.parse_args(argv)

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    if args.resolve_field:
        try:
            print(resolve_project_field(data))
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        return 0

    if not args.output:
        print("ERROR: --output is required when not using --resolve-field", file=sys.stderr)
        return 1

    tsv, summary = render(data)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tsv, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
