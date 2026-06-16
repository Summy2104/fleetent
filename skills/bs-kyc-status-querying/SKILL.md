---
name: bs-kyc-status-querying
description: 从 KYC 跟踪表查询客户 KYC 状态。触发词：查 KYC、KYC 状态、KYC 过了吗、KYC 查询、客户准入
status: draft
metadata:
  author: BS Team
  version: 1.1.0
complexity: L1
---

# KYC 状态查询

## 使用场景

- **NL 触发**：
  - "查一下 Alpha Fund 的 KYC 过了吗"
  - "Trading 新客户 XX，先查 KYC"
- **被其他 skill 调用**：M1 主流程节点 C — BS-C03 flow-intent-parsing 识别为客户接入类请求时，前置调用本 skill 作为 gating check

## 前置条件

两张 KYC 跟踪表结构相同、数据分开存放，需同时查询并合并结果。两张表类型不同，读取方式也不同：

- `NS KYC/DD/Name screening 已通过`（原生 Google Sheet）
  - Spreadsheet ID: `11WPhkHxUGgSfA6-0CT1NFfmwLqczCDYFcZXilsuCiZY`
  - 直接用 `google-drive__getGoogleSheetContent` 工具读取（agent loop 发起 MCP 调用）
- `NS 币贷/NET客户`（Drive 中的 xlsx，Sheets API 不支持）
  - fileId: `1uGnrDTzVyUv_CndMHtdg-s7K0NKjfN4-`
  - 用 `google-drive__downloadFile` 工具下载到 `outbound/kyc/{YYYY-MM}/ns-bidai-net.xlsx`（遵循 `common-file-output` 规范），再用 `run_code`（python，预装 `openpyxl`）解析

## 输入

无必填字段。从用户消息中提取任意筛选条件，支持的字段：

| 列 | 字段 |
|----|------|
| A | 客户名称 |
| B | BD |
| C | 业务线 |
| D | DD & KYC 类型 |
| E | 通过日期 |
| F | Review |
| G | 注册地 |
| H | Director |
| I | UBO |
| J | 有权限签字人 |
| K | AR Email |

多个条件同时满足才算匹配。直接执行，不追问。

## 工作流程

### Step 1 读取两张 KYC 跟踪表

两张表并列，需同时读取、合并行（均跳过第 1 行表头）后再做匹配。`source_row` 必须带来源表名（见 Step 3）。

**1a. `NS KYC/DD/Name screening 已通过`（Google Sheet）直接读取**：

由 agent loop 发起 `google-drive__getGoogleSheetContent` 工具调用：

```
google-drive__getGoogleSheetContent
  spreadsheetId: 11WPhkHxUGgSfA6-0CT1NFfmwLqczCDYFcZXilsuCiZY
  range: A1:K500
```

> **权限回退（fleetent 部署）**：`google-drive` MCP（piotr-agier）与 `google-workspace` MCP 用的是**不同的
> Google 身份**。若 `google-drive__getGoogleSheetContent` 返回 `The caller does not have permission`，
> 改用 `google-workspace` MCP（以宿主用户身份）读取同一张表：
> `google-workspace__manage_sheets`（operation=read, spreadsheetId 同上, range=A1:K500）。
> 两条路径均无权访问时，如实告知用户「当前账号无该 KYC 表访问权限，请联系表 owner 共享给 bot 的 Google 账号」，不要编造数据。

**1b. `NS 币贷/NET客户`（xlsx）下载后解析**：

1) **先建目录**（`google-drive__downloadFile` 的 `localPath` 必须是**绝对路径**，且父目录须已存在，否则报
   `localPath must be an absolute path` / `Parent directory does not exist`）。用内置 `run_code`（python）先创建：

```python
import os
from datetime import datetime
out_dir = f"/workspace/outbound/kyc/{datetime.now():%Y-%m}"
os.makedirs(out_dir, exist_ok=True)
print(out_dir)
```

2) agent loop 发起 `google-drive__downloadFile`，`localPath` 用上一步的**绝对路径**：

```
google-drive__downloadFile
  fileId: 1uGnrDTzVyUv_CndMHtdg-s7K0NKjfN4-
  localPath: /workspace/outbound/kyc/{YYYY-MM}/ns-bidai-net.xlsx
```

> 若 `google-drive` 身份无权下载，回退用 `google-workspace__manage_drive`（operation=download / export，
> fileId 同上）取回 xlsx 到同一绝对路径。

3) 用内置 `run_code`（python，预装 `openpyxl`）解析（路径与下载的**绝对路径一致**）：

```python
from openpyxl import load_workbook
from datetime import datetime
path = f"/workspace/outbound/kyc/{datetime.now():%Y-%m}/ns-bidai-net.xlsx"
ws = load_workbook(path, read_only=True, data_only=True).active
for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
    if idx == 1:
        continue
    # row[:11] 即 A:K 列，合并到另一张表的结果后统一匹配
```

表结构（第 1 行为表头）：

| 列 | 字段 |
|----|------|
| A | 客户名称 |
| B | BD |
| C | 业务线 |
| D | DD & KYC（KYC 类型） |
| E | 通过日期 |
| F | Review |
| G | 注册地 |
| H | Director |
| I | UBO |
| J | 有权限签字人 |
| K | AR Email |

### Step 2 匹配行

用用户提供的所有筛选条件对应列进行精确匹配，多个条件取交集。

- 无匹配行 → 直接回复未找到，终止
- 有匹配行 → 所有匹配行合并写入一个 TSV 文件，经 `send_file` 投递（每行一条记录）

### Step 3 解析状态

根据 E 列（通过日期）内容判断 `status`：

| E 列内容 | status |
|---------|--------|
| 包含"已关户" | `expired` |
| 有日期（不含"已关户"） | `passed` |
| 空 | `not_found` |

其余字段：
- `kyc_type`：直接取 D 列原始值，不做转换
- `通过日期`：仅 `status=passed` 时返回，取 E 列日期部分，格式转为 ISO 8601（如 `2026-04-13`）
- `source_row`：匹配行的行引用，格式 `{NS KYC/DD/Name screening 已通过|NS 币贷/NET客户}!A{行号}`，用于区分来源

## 输出格式

- 使用 TSV 表格格式输出，第一列为字段名，第二列为值
- 用 `write_file` 写到 workspace 的 `outbound/kyc/{YYYY-MM}/kyc_details.tsv`，再用内置 `send_file` 投递回当前对话（频道→频道 / 私信→私信）；聊天只输出摘要、不重复 TSV 内容、不暴露内部路径

found 时投递文件名 `kyc_details.tsv`，内容：

```
字段\t值
客户名称\t{A列}
BD\t{B列}
业务线\t{C列}
DD & KYC 类型\t{D列}
通过日期\t{E列}
Review\t{F列}
注册地\t{G列}
Director\t{H列}
UBO\t{I列}
有权限签字人\t{J列}
AR Email\t{K列}
KYC 状态\t{passed→✅ 已通过（{ISO日期}）/ expired→🔴 已关户}
来源\t{source_row}
```

空值填 `-`，`\t` 为真实 Tab 字符。

**多值单元格必须转义换行**：Director / UBO / 有权限签字人等列原单元格内常含换行（`\n` 或 `\r\n`），会把一条记录破坏成多行。写入 TSV 前对每个字段值按顺序做如下处理（`openpyxl` 读出的 `None` 先转成空字符串）：

```python
def clean(v):
    if v is None:
        return "-"
    s = str(v)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", " | ")   # 多值合并为 " | " 分隔
    s = s.replace("\t", " ")     # 禁止字段值内含 Tab
    return s.strip() or "-"
```

TSV 中仅行尾保留一个 `\n`，字段值内不得出现原始换行或 Tab。

not_found 时直接回复：`未在 KYC 跟踪表中找到 {customer_name}，请人工核查。`
error 时直接回复：`KYC 跟踪表读取失败（{reason}），请稍后重试。`

## 异常处理

| 触发条件 | 处理方式 |
|----------|----------|
| Google Sheet 读取超时 | 重试一次；仍失败 → `{status: "error", reason: "gsheets_unavailable"}` |
| xlsx 下载超时 | 重试一次；仍失败 → `{status: "error", reason: "download_failed"}` |
| 权限不足 | 立即返回 → `{status: "error", reason: "permission_denied"}` |
| xlsx 解析失败 | 立即返回 → `{status: "error", reason: "xlsx_parse_failed"}` |
| 未找到客户 | 返回 `{status: "not_found"}`，不视为异常 |

## 职责边界

- 仅查 GSheets，不查 NS KYC 系统（v2 范围）
- 只读，不创建或修改 KYC 记录
- 不对外沟通客户（v2 范围：BS-02 customer-onboarding-relaying）
- 精确匹配，不做模糊匹配（v2 范围）
