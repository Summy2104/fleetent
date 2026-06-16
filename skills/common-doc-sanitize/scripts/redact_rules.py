#!/usr/bin/env python3
"""
共享脱敏规则，供 redact_pdf.py / redact_docx.py / redact_image.py 共用。

格式: (name, pattern, use_group, block_scoped, replacement)
  use_group    = True  → 只脱敏 capture group(1)，保留标签前缀可见
  block_scoped = True  → 仅 PDF 生效：只在单个文本 block 内匹配，防止跨表格单元格
  replacement         → 替换文本（如 "[手机号]"）；"keep" 表示不脱敏；
                        image 脚本忽略此字段（仅做视觉遮盖）
"""
import json
import sys

# ──────────────────────────────────────────────────────────────────────
# 主规则表（顺序影响匹配优先级，IBAN/SWIFT 必须在通用字母数字编号之前）
# ──────────────────────────────────────────────────────────────────────
RULES = [
    # ── 联系方式 ──────────────────────────────────────────────────────
    ("手机号",       r'(?<!\d)1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}(?!\d)',                               False, False, "[手机号]"),
    ("固定电话",     r'(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)',                                        False, False, "[固定电话]"),
    ("邮箱",         r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}',                                             False, False, "[邮箱]"),

    # ── 证件 ──────────────────────────────────────────────────────────
    ("身份证",       r'\d{3}[-\s]?\d{3}[-\s]?(?:19|20)\d{2}[-\s]?\d{2}[-\s]?\d{2}[-\s]?\d{3}[-\s]?[\dXx]', False, False, "[身份证号]"),
    ("社会信用代码", r'(?<![A-Z0-9a-z])[0-9A-Za-z]{17,19}(?![A-Z0-9a-z])',                         False, False, "[统一社会信用代码]"),
    ("社会信用标签", r'(?:统一)?社会信用代码\s*[：:]\s*([0-9A-Za-z][0-9A-Za-z\s]{6,22}[0-9A-Za-z])', True, False, "[统一社会信用代码]"),
    ("护照号",       r'[EGP]\d{7,8}',                                                              False, False, "[护照号]"),

    # ── 银行 ──────────────────────────────────────────────────────────
    ("银行卡",       r'6\d{15,18}',                                                                 False, False, "[银行卡号]"),
    ("银行账号标签", r'(?:银行账号|账号|卡号)[：:]\s*([\d\s\-]{10,30})',                             True,  False, "[银行账号]"),
    ("开户银行名称", r'[\u4e00-\u9fa5]{2,10}银行[\u4e00-\u9fa5]{2,15}(?:支行|分行)',                False, False, "[开户银行]"),

    # ── 金额 ──────────────────────────────────────────────────────────
    ("金额¥",        r'(?:¥|￥)[\d,\.]+',                                                           False, False, "[金额]"),
    ("金额$",        r'(?:US|HK|AU|CA|SG|NZ)?\$\s*[\d,\.]+',                                          False, False, "[金额]"),
    ("金额€£₩",     r'[€£₩][\d,\.]+',                                                              False, False, "[金额]"),
    ("金额元",       r'[\d,]+(?:\.\d+)?\s*万?元(?:整)?',                                            False, False, "[金额]"),
    ("大写金额",     r'[零壹贰叁肆伍陆柒捌玖拾佰仟万亿]+(?:元|万元|亿元)整?',                       False, False, "[大写金额]"),
    ("金额货币前缀", r'(?:USD|EUR|GBP|JPY|HKD|SGD|CNY|TWD|KRW|AUD|CAD|CHF|USDT|USDC|BTC|ETH|RMB)\s*[\d,\.]+', False, False, "[金额]"),
    ("金额货币后缀", r'[\d,\.]+\s*(?:USD|EUR|GBP|JPY|HKD|SGD|CNY|TWD|KRW|AUD|CAD|CHF|USDT|USDC'
                    r'|美金|美元|人民币|港币|港元|日元|韩元|韩币|台币|新台币|澳元|欧元|英镑|新加坡元|坡元|加元|瑞郎|yuan|RMB)', False, False, "[金额]"),
    ("百分比",       r'\d+(?:\.\d+)?\s*%',                                                          False, False, "keep"),

    # ── 日期 ──────────────────────────────────────────────────────────
    ("日期中文",     r'\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日',                                  False, False, "[日期]"),

    # ── 姓名 ──────────────────────────────────────────────────────────
    ("中文姓名",     r'(?:联系人|项目经理|技术负责人|法定代表人|授权代表)(?:（[^）]*）|\([^\)]*\))?\s*[：:]\s*([\u4e00-\u9fa5]{2,4})', True, True, "[姓名]"),
    ("英文姓名简",   r'(?:姓名|顾问|代表|员工)[：:]\s*([A-Z][a-z]+ [A-Z][a-z]+)',                   True, False, "[姓名]"),

    # ── 密码 ──────────────────────────────────────────────────────────
    ("密码中文",     r'(?:密码)[：:]\s*([A-Za-z0-9!@#\$%^&*()\[\]{}\-_+=]{4,20})',                  True, False, "[密码]"),

    # ── 地址 ──────────────────────────────────────────────────────────
    ("地址",         r'[\u4e00-\u9fa5]+(?:省|市)[\u4e00-\u9fa5]+(?:区|县|路|街道|大街)[^\n，。；]{2,20}(?:号|楼|层|室)', False, False, "[地址]"),
    ("楼栋地址",     r'[\u4e00-\u9fa5A-Za-z\d\s]{2,30}(?:座|栋|幢)\s*\d{1,4}\s*(?:层|室|号|楼)',   False, False, "[地址]"),

    # ── 税务 ──────────────────────────────────────────────────────────
    ("税务登记号",   r'(?:税务登记号?|税登字|纳税人识别号)(?:（[^）]*）)?\s*[：:\s]?\s*([0-9A-Za-z]{14,18})', True, False, "[税务登记号]"),
    ("英文税务号",   r'(?:Tax\s+Registration\s+(?:No\.?|Number|#))\s*[:\-\.\s]\s*(\d{14,18})',    True,  False, "[Tax Reg. No.]"),

    # ── 其他 ──────────────────────────────────────────────────────────
    ("URL",          r'https?://[^\s\u201c\u201d\n]+',                                             False, False, "[URL]"),
    ("公司名",       r'[\u4e00-\u9fa5]{2,15}(?:有限|股份)(?:责任)?公司',                           False, True,  "[公司名称]"),
    ("编号",         r'(?:订单|合同|工单|序列|流水|发票)(?:编号|号码)?[：:（(]如?\s*([A-Za-z0-9,、\s]+)', True,  True,  "[编号]"),
    ("项目名称",     r'(?:核心项目|系统名称|项目名)[：:]\s*([\u4e00-\u9fa5]+)',                      True,  True,  "[项目名称]"),

    # ── English ───────────────────────────────────────────────────────
    # （IBAN/SWIFT 放在通用字母数字编号之前，避免被提前截断）
    ("英/美电话",    r'(?<!\d)(?:\+1\s*)?(?:\(\d{3}\)|\d{3})[-\s\.]\d{3}[-\s\.]\d{4}(?!\d)',   False, False, "[Phone]"),
    ("SSN",          r'(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)',                                         False, False, "[SSN]"),
    ("EIN/税号",     r'(?<!\d)\d{2}-\d{7}(?!\d)',                                                False, False, "[EIN]"),
    ("英文日期月",   r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}', False, False, "[Date]"),
    ("日期MMDDYYYY", r'(?<!\d)\d{1,2}[\/\-]\d{1,2}[\/\-](?:19|20)\d{2}(?!\d)',                 False, False, "[Date]"),
    ("ISO日期",      r'(?<!\d)(?:19|20)\d{2}-\d{2}-\d{2}(?!\d)',                                False, False, "[Date]"),
    ("IBAN",         r'(?:IBAN)\s*[:\-]?\s*([A-Z]{2}\d{2}[A-Z0-9]{11,30})',                     True,  False, "[IBAN]"),
    ("SWIFT/BIC",    r'(?:SWIFT|BIC|Bank\s*Code)\s*[:\-]?\s*([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)', True, False, "[SWIFT/BIC]"),
    ("ABA路由号",    r'(?:Bank\s+)?ABA\s*Routing\s*(?:NO\.?|No\.?|Number)?\s*[:\.\-]?\s*(\d{9})', True,  False, "[ABA Routing No.]"),
    ("英文账号",     r'Account\s*(?:No\.?|Number|#)\s*[：:\-]\s*([\d\s\-]{6,20})',               True,  False, "[Account No.]"),
    ("受益方信息",   r"Beneficiary(?:['\u2018\u2019]s|\s+s\b)?\s+(?:Bank\s+)?(?:Name|Address|SWIFT|Account|Code)\s*[：:\-]\s*([A-Za-z0-9\s\.,&'#\-/]{3,200}?)(?=Beneficiary|[：:]|$)", True, False, "[Beneficiary Info]"),
    ("英文姓名",     r'(?:Authorized\s+)?(?:Name|Print(?:ed)?\s+Name|Full\s+Name|Contact|Representative|Signatory|Director|Officer|Party|Buyer|Seller|Vendor|Client|Customer|Signed\s+by|By)\s*[:\-]\s*([A-Z][a-z\-\']+(?:\s+[A-Z][a-z\-\']+){0,3})', True, True, "[Name]"),
    ("英文密码",     r'(?:Password|Pass|PIN|Secret)\s*[:\-]\s*([A-Za-z0-9!@#\$%^&*()\[\]{}\-_+=]{4,20})', True, False, "[Password]"),
    ("英文地址",     r'\d+\s+[A-Za-z0-9\s]{3,40}\b(?:Street|Ave(?:nue)?|Road|Boulevard|Drive|Lane|Way|Court|Place|St|Rd|Blvd|Dr|Ln|Ct|Pl)\b\.?(?:\s+(?:Suite|Ste|Apt|Unit|Floor|#)\s*[\w\d]+)?', False, True, "[Address]"),
    ("英文地址Ste",  r'\d+[A-Za-z0-9\s,\.]{3,60}(?:Suite|Ste|Apt|Unit|Fl(?:oor)?)\s*[A-Za-z0-9]+,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5}', False, True, "[Address]"),
    ("英文公司名",   r'(?-i:[A-Z])[A-Za-z0-9\s\.,&\'-]{2,40}\b(?:Inc\.|LLC|Ltd\.|Corp\.|Limited|Corporation|LLP|PLC)(?![a-zA-Z0-9])', False, True,  "[Company Name]"),
    ("英文合同编号", r'(?:Contract|Agreement|Purchase\s+Order|PO|Order|Invoice|Reference|Ref\b\.?|Exhibit|Annex|Schedule|Amendment)\s*(?:No\.?|Number|#)?\s*[:\-]?\s*(?=[A-Za-z0-9\-\/]*\d)([A-Z0-9][A-Z0-9\-\/]{2,30})', True, True, "[Contract No.]"),
    ("英文大写金额", r'\(in\s+words?\s*[：:]\s*((?:RMB\s+)?[A-Za-z][A-Za-z\s\-,]+Only)\)',             True, False, "[Amount in Words]"),
    ("DocuSign",     r'(?:Docusign|DocuSign)\s+Envelope\s+ID\s*[:\-]?\s*([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})', True, False, "[DocuSign ID]"),
    ("英文银行支行", r'[A-Za-z][A-Za-z\s]{2,40}(?:Bank|Trust)\s+[A-Za-z\s]{2,35}Sub-?[Bb]ranch\b', False, True,  "[Bank Branch]"),
    ("订单编号纯数字", r'(?<![A-Za-z0-9])[A-Z]{2}\d{10,14}(?![A-Za-z0-9])',                      False, False, "[Order No.]"),
    ("字母数字编号", r'[A-Z]{1,4}\d{2,}[A-Z]{2,}|(?<![A-Za-z0-9])[A-Z]{2,4}-\d{4}-\d{2,}(?![A-Za-z0-9])', False, False, "[Ref. No.]"),
]


def build_rules(custom_rules_json=None):
    """返回完整规则列表（PDF/DOCX 使用，含所有字段）。"""
    rules = list(RULES)
    if custom_rules_json and custom_rules_json.strip() not in ("", "null", "[]"):
        try:
            extras = json.loads(custom_rules_json)
            if isinstance(extras, list):
                for pattern in extras:
                    rules.append(("自定义", pattern, False, False, "[已脱敏]"))
        except Exception as e:
            print(f"[警告] 自定义规则解析失败，已跳过: {e}", file=sys.stderr)
    return rules


def build_patterns(custom_rules_json=None):
    """返回 pattern 字符串列表（image 使用，use_group 通过 m.lastindex 自动生效）。"""
    patterns = [pattern for _, pattern, _, _, _ in RULES]
    if custom_rules_json and custom_rules_json.strip() not in ("", "null", "[]"):
        try:
            extras = json.loads(custom_rules_json)
            if isinstance(extras, list):
                patterns.extend(extras)
        except Exception as e:
            print(f"[警告] 自定义规则解析失败，已跳过: {e}", file=sys.stderr)
    return patterns
