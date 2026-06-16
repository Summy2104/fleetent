#!/usr/bin/env python3
"""
render-email.py — 渲染外部白名单邮件草稿

读取 templates/email-{lang}.txt 模版，按传入 JSON 替换 3 个占位符，输出纯文本到 stdout。
AI 不做任何字符串拼接判断，避免胡乱追问用户。

用法:
  render-email.py --lang zh   --json '<JSON>'
  render-email.py --lang en   --json-file <path>
  render-email.py --lang both --json '<JSON>'      # zh + 分隔线 + en

JSON 字段（缺值或留空一律保留 {xxx} 字面量兜底）:
  client_company         str   客户公司全称        → 替换 {client_company}
  business_group_email   str   业务群组邮箱        → 替换 {business_group_email}
  application_date       str   YYYY-MM-DD HH:mm:ss → 替换 {application_date}（缺则脚本自动用当前时间）

设计原则（与 SKILL.md 字段封顶纪律一致）:
  - 已知 3 个占位符缺值 → 保留 {xxx} 字面量，由发件人手填；脚本不抛错
  - 模版中其他未知占位符 → 同样保留原样不报错
  - 模版正文里的空白字段（公司法定名称 / 涉及业务线 / 付款目的 / 注册国家 / 地址 / 币种 / 网络 / 因 xxxxx）
    全部保留空白，由发件人手填，本脚本不动

退出码:
  0  渲染成功
  2  JSON 解析失败或顶层非对象
  3  模版文件缺失

示例:
  render-email.py --lang zh --json '{
    "client_company": "Alpha Fund Limited",
    "business_group_email": "trading@nsdigital.io"
  }'
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def render(template: str, data: dict) -> str:
    rendered = template

    cc = data.get("client_company")
    if cc:
        rendered = rendered.replace("{client_company}", str(cc))

    bge = data.get("business_group_email")
    if bge:
        rendered = rendered.replace("{business_group_email}", str(bge))

    ad = data.get("application_date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rendered = rendered.replace("{application_date}", str(ad))

    return rendered


def load_template(lang: str) -> str:
    path = Path(__file__).resolve().parent.parent / "templates" / f"email-{lang}.txt"
    if not path.exists():
        print(f"ERR_TEMPLATE_NOT_FOUND: {path}", file=sys.stderr)
        sys.exit(3)
    return path.read_text(encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Render external whitelist email draft from template + JSON.",
    )
    p.add_argument(
        "--lang",
        default="zh",
        choices=["zh", "en", "both"],
        help="Template language (default: zh; both = zh 后接分隔线再接 en)",
    )
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

    if args.lang == "both":
        zh = render(load_template("zh"), data)
        en = render(load_template("en"), data)
        out = zh.rstrip() + "\n\n---\n\n" + en
    else:
        out = render(load_template(args.lang), data)

    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
