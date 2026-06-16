#!/usr/bin/env python3
"""
render-email.py — 渲染内部白名单邮件草稿

读取 templates/email-{lang}.txt 模版，按传入 JSON 替换占位符 + 多地址行展开，
输出纯文本邮件草稿到 stdout。AI 不做任何字符串拼接判断。

用法:
  render-email.py --lang zh --json '<JSON>'
  render-email.py --lang zh --json-file <path>

JSON 字段（缺值用 null 或省略均可，会替换为占位符兜底）:
  client_company         str        客户公司全称
  business_line          str        业务线
  application_date       str        YYYY-MM-DD（缺则脚本自动用当天）
  client_contact_email   str|null   客户联系人邮箱
  business_group_email   list[str]  业务群组邮箱数组（多个用 ", " 拼接进 cc）
  combos                 list[obj]  币种网络地址三元组数组（每项 {currency, chain_name, wallet_address}），
                                    渲染时按 combos 长度展开模版的"币种行"为 N 行；缺值用占位符替代

示例:
  render-email.py --lang zh --json '{
    "client_company": "Grand Digital Holding Limited",
    "business_line": "量化",
    "application_date": "2026-04-30",
    "client_contact_email": "client@example.com",
    "business_group_email": ["quant@nsdigital.io"],
    "combos": [
      {"currency": "USDT", "chain_name": "ERC20", "wallet_address": "0xabc..."},
      {"currency": "BTC",  "chain_name": "",      "wallet_address": null}
    ]
  }'
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ADDR_FALLBACK = "<待业务/中台确认>"
GROUP_EMAIL_FALLBACK = "<业务群组待补充>"
CONTACT_EMAIL_FALLBACK = "<待客户联系人邮箱>"


def _emit_combo_line(line: str, combo: dict) -> str:
    currency = combo.get("currency") or ADDR_FALLBACK
    chain_name = combo.get("chain_name") or ""
    wallet = combo.get("wallet_address") or ADDR_FALLBACK

    out = line.replace("{currency}", currency).replace("{wallet_address}", wallet)
    if chain_name:
        out = out.replace("{chain_name}", chain_name)
    else:
        # chain 为空时连带去掉包裹的全角/半角括号，避免输出 "BTC（）"
        out = out.replace("（{chain_name}）", "").replace("({chain_name})", "")
        out = out.replace("{chain_name}", "")
    return out


def render(template: str, data: dict) -> str:
    combos = data.get("combos") or []

    out_lines = []
    for line in template.split("\n"):
        # combos 行模版：含 {currency} + {wallet_address} 视为模版行，按 combos 数组展开 N 行
        if "{currency}" in line and "{wallet_address}" in line:
            if combos:
                for c in combos:
                    out_lines.append(_emit_combo_line(line, c))
            else:
                # 没有 combos 时保留原行（占位符不替换）以提示模版有此结构
                out_lines.append(line)
        else:
            out_lines.append(line)

    rendered = "\n".join(out_lines)

    # 标量字段替换
    rendered = rendered.replace("{client_company}", data.get("client_company") or "<客户名称待补>")
    rendered = rendered.replace("{business_line}", data.get("business_line") or "<业务线待补>")
    rendered = rendered.replace(
        "{application_date}",
        data.get("application_date") or date.today().isoformat(),
    )
    rendered = rendered.replace(
        "{client_contact_email}",
        data.get("client_contact_email") or CONTACT_EMAIL_FALLBACK,
    )

    bge = data.get("business_group_email") or []
    if isinstance(bge, list):
        bge_str = ", ".join(bge) if bge else GROUP_EMAIL_FALLBACK
    else:
        bge_str = str(bge) if bge else GROUP_EMAIL_FALLBACK
    rendered = rendered.replace("{business_group_email}", bge_str)

    return rendered


def main() -> int:
    p = argparse.ArgumentParser(
        description="Render internal whitelist email draft from template + JSON.",
    )
    p.add_argument("--lang", default="zh", choices=["zh", "en"], help="Template language (default: zh)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--json", help="JSON string of placeholder values")
    src.add_argument("--json-file", help="Path to JSON file")
    args = p.parse_args()

    if args.json:
        try:
            data = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(f"ERR_JSON_PARSE: {e}", file=sys.stderr)
            return 2
    else:
        try:
            data = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERR_JSON_FILE_READ: {e}", file=sys.stderr)
            return 2

    if not isinstance(data, dict):
        print("ERR_JSON_NOT_OBJECT: top-level JSON must be an object", file=sys.stderr)
        return 2

    template_path = Path(__file__).resolve().parent.parent / "templates" / f"email-{args.lang}.txt"
    if not template_path.exists():
        print(f"ERR_TEMPLATE_NOT_FOUND: {template_path}", file=sys.stderr)
        return 3

    template = template_path.read_text(encoding="utf-8")
    sys.stdout.write(render(template, data))
    if not template.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
