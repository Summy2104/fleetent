---
name: common-office-reader
description: 读取并提取 Office/PDF 文档结构化内容（pptx/docx/xlsx/pdf）。触发词：总结PPT、解读文档、读取Excel、提取文档内容、分析报告、读取PDF、summarize PPT、read docx、extract xlsx、read pdf
status: active
metadata:
  author: RD Team
  version: 1.1.0
---

# Office / PDF 文档读取

解析用户上传的 Office 或 PDF 文档，提取结构化内容后完成用户任务（总结、提取数据、回答问题等）。

## 支持格式

| 格式 | 扩展名 | 结构 |
|------|--------|------|
| PowerPoint | `.pptx` | 按幻灯片分组，每张幻灯片含文本列表 |
| Word | `.docx` | 段落（含标题层级）+ 表格 |
| Excel | `.xlsx` | 按 Sheet 分组，每个 Sheet 含行列数据 |
| PDF | `.pdf` | 按页分组，每页含文本列表；扫描版自动 OCR |

## 工作流程

### Step 1: 定位文件路径

从用户消息或附件元数据中提取文件的**绝对路径**。沙箱内附件路径通常为 `/workspace/media/inbound/<uuid>.<ext>`。

### Step 2: 在沙箱内调用解析脚本

用 `run_code`（沙箱内 Python）执行随 skill 附带的解析脚本 `scripts/parse_office.py`（pptx/docx/xlsx 用 python-pptx/python-docx/openpyxl，pdf 用 PyMuPDF，扫描版自动 OCR）。例如以 `bash_exec` 运行：

```bash
python3 $SKILLS_DIR/common-office-reader/scripts/parse_office.py "<file_path>"
```

脚本将结构化 JSON 输出到 stdout（`run_code`/`bash_exec` 的标准输出）。

### Step 3: 基于结构完成用户任务

根据 JSON 内容以自然语言完成用户请求：
- **总结**: 逐幻灯片/逐章节提炼要点
- **提取数据**: 从表格/行列中定位目标字段
- **回答问题**: 基于文档内容直接作答

**输出规范：**
- 禁止将原始 JSON 直接输出给用户
- 文件超过 50 页/Sheet 行时，先输出整体摘要，提示用户可追问细节

## 异常处理

| 情况 | 处理 |
|------|------|
| 格式不支持（如 `.xls`） | 告知用户本 skill 支持 `.pptx` `.docx` `.xlsx` `.pdf`，不继续 |
| 文件路径不存在 | 提示用户确认附件路径，或要求重新上传 |
| 解析异常（脚本 stderr 非空） | 输出错误信息，建议用户重新上传文件 |
