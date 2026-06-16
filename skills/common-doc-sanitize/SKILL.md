---
name: common-doc-sanitize
description: 文档内容脱敏，自动识别并遮盖敏感信息（姓名、手机号、身份证号、银行卡号、邮箱、地址等），禁止读取文件内容。支持 docx、pdf、图片（jpg/png/jpeg）。触发词：脱敏、文档脱敏、敏感信息处理、隐私处理、打码、遮盖敏感、信息脱敏、redact。
status: active
metadata:
  author: RD Team
  version: 1.0.0
---

# 文档内容脱敏

对输入文档进行敏感信息检测与遮盖，输出脱敏后的文件。**禁止读取文件内容**，只根据文件名和后缀判断格式并调用对应脚本。

## 支持格式

| 格式 | 处理脚本 | 输出 |
|------|----------|------|
| `.docx` | `scripts/redact_docx.py` | 脱敏后的 `.docx` |
| `.pdf` | `scripts/redact_pdf.py` | 脱敏后的 `.pdf` |
| `.jpg` / `.jpeg` / `.png` | `scripts/redact_image.py` | 脱敏后的同格式图片 |

## 默认脱敏规则

| 类型 | 说明 |
|------|------|
| 手机号 | 1[3-9] 开头的 11 位号码 |
| 固定电话 | 0 开头区号 + 7-8 位号码 |
| 邮箱 | 标准邮箱格式 |
| 身份证号 | 18 位含 X |
| 社会信用代码 | 17-19 位字母数字；标签锚点版 |
| 护照号 | E/G/P 开头 7-8 位 |
| 银行卡号 | 6 开头 16-19 位 |
| 银行账号 | 银行账号/账号/卡号标签后的数字串 |
| 开户银行名称 | XX银行XX支行/分行 |
| 金额 | `¥`/`$`/`€`/`£`/`₩` 符号；元/万元/亿元；大写金额；货币代码前置（USD/EUR/GBP/JPY/HKD/SGD/CNY/TWD/KRW/AUD/CAD/CHF/USDT/USDC/BTC/ETH）或后置（含人民币/港币/港元/日元/韩元/韩币/台币/新台币/澳元/欧元/英镑/新加坡元/坡元/加元/瑞郎） |
| 百分比 | `92.5%` 等数字百分比 |
| 日期（中文） | XXXX年XX月XX日 |
| 日期（英文） | `January 1, 2025`、`MM/DD/YYYY`、`YYYY-MM-DD` |
| 中文姓名 | 联系人/法定代表人/项目经理/技术负责人/授权代表标签后 2-4 位中文 |
| 英文姓名（简） | 姓名/顾问/代表/员工标签后的 FirstName LastName |
| 密码 | 密码标签后的 ASCII 字符串（4-20 位） |
| 地址（中文） | 省/市+区/县/路+号/楼/层/室 |
| 楼栋地址 | XX座/栋/幢 + 层/室/号/楼 |
| URL | http/https 链接 |
| 公司名（中文） | 含有限/股份的中文公司名 |
| 公司名（英文） | 以 Inc./LLC/Ltd./Corp./Limited/LLP/PLC 结尾 |
| 编号 | 订单/合同/工单/序列/流水/发票编号标签后的字母数字串 |
| 项目名称 | 核心项目/系统名称/项目名标签后的中文 |
| 字母数字编号 | 大写字母+数字+大写字母组合 |
| 英/美电话 | +1 可选、(区号) 或裸区号、`-`/空格/`.` 分隔的 3-3-4 格式 |
| SSN | 美国社会安全号 `XXX-XX-XXXX` |
| EIN/税号 | 美国雇主税号 `XX-XXXXXXX` |
| IBAN | `IBAN` 标签后的国际银行账号 |
| SWIFT/BIC | `SWIFT`/`BIC`/`Bank Code` 标签后的银行标识码 |
| ABA 路由号 | `ABA Routing` 标签后的 9 位数字 |
| 英文账号 | `Account No./Number/#` 标签后的数字串 |
| 受益方信息 | `Beneficiary('s) Bank Name/Address/SWIFT/Account/Code` 标签后的值 |
| 英文地址 | 门牌号 + 街道名 + Street/Ave/Road/Blvd/Dr/Ln/Ct/Pl 等后缀 |
| 英文合同编号 | Contract/Agreement/Order/Invoice/Reference 标签后的编号 |
| 英文密码 | Password/Pass/PIN/Secret 标签后的字符串 |
| 英文姓名 | Name/Contact/Representative/Signatory/Party/Buyer/Seller 等标签后的姓名 |
| DocuSign UUID | `DocuSign Envelope ID` 后的 UUID |

> 用户可追加自定义规则（关键词或正则），通过 `custom_rules_json` 参数传入。

---

## 工作流程

### Step 1: 参数确认

从用户消息中提取以下信息（**不要读取或预览文件内容**）：

- `source_path`：文件绝对路径
- `ext`：从文件名提取后缀（`.docx` / `.pdf` / `.jpg` / `.jpeg` / `.png`）
- `output_path`：默认在源文件同目录输出 `{原文件名}_脱敏.{扩展名}`，若已存在则依次追加 `_1`、`_2` …
- `custom_rules_json`：可选，额外规则的 JSON 数组，如 `["内部机密", "PROJ-\\d+"]`
- `style`：可选，`mask`（默认，白底 `***`）或 `block`（纯黑色方块）；仅 PDF/图片有效

若后缀不在支持列表内，直接返回 `UNSUPPORTED_FORMAT` 错误。

---

### Step 2: 依赖检查

用 `run_code`（沙箱内 Python）执行：

```python
import importlib
checks = [('python-docx','docx'),('PyMuPDF','fitz'),('pytesseract','pytesseract'),('Pillow','PIL')]
missing = [pkg for pkg,mod in checks if not importlib.util.find_spec(mod)]
print('MISSING: ' + ' '.join(missing) if missing else 'OK')
```

若有缺失输出安装命令后等待用户安装：

```bash
pip3 install python-docx PyMuPDF pytesseract Pillow
```

图片模式还需 tesseract OCR 引擎：
- macOS: `brew install tesseract tesseract-lang`
- Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-chi-sim`

---

### Step 3: 执行脱敏

脚本目录：本 skill 目录下的 `scripts/`（由 runtime 注入的绝对位置解析后使用；用 `run_code` 在沙箱内运行 Python 脚本）。

无自定义规则时 `custom_rules_json` 传 `null`，`style` 不传默认 `mask`。

#### DOCX

```bash
python3 <本 skill 目录>/scripts/redact_docx.py "<source_path>" "<output_path>" '<custom_rules_json>'
```

#### PDF

```bash
python3 <本 skill 目录>/scripts/redact_pdf.py "<source_path>" "<output_path>" '<custom_rules_json>' <style>
```

#### 图片（JPG / JPEG / PNG）

```bash
python3 <本 skill 目录>/scripts/redact_image.py "<source_path>" "<output_path>" '<custom_rules_json>' <style>
```

---

### Step 4: 输出结果

**成功**时只输出以下内容，**禁止输出文件内容、脱敏前后对比、命中的具体文本**：

```
✅ 脱敏完成

输出文件：{output_path 的文件名部分}
命中数量：{脚本输出的命中数}
```

然后用 `send_file(path="<output_path>")` 把脱敏后的文件发回当前对话（展示文件名使用 `output_path` 的文件名部分，如 `货物买卖合同_脱敏.docx`）。

**失败**：

```
❌ 脱敏失败：{原因}
建议：{排查提示}
```

---

## 异常处理

| 情况 | 处理 |
|------|------|
| 源文件不存在 | 提示 `SOURCE_NOT_FOUND`，请用户确认路径 |
| 不支持的格式 | 提示 `UNSUPPORTED_FORMAT`，列出支持的后缀 |
| 依赖缺失 | 输出 pip 安装命令，等用户安装后重试 |
| 图片 OCR 语言包缺失 | 提示安装 tesseract chi_sim 语言包 |
| PDF 有密码加密 | 提示用户先解密再处理 |
| 无敏感内容命中 | 仍输出文件，注明「未检测到敏感信息，文件已原样输出」 |
