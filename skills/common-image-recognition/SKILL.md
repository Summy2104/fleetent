---
name: common-image-recognition
description: 图片识别与分析。通过 VLM（Vision Language Model）对用户上传的图片进行 OCR、内容分析、数据提取。触发词：识别图片、图片分析、OCR、看图、分析截图
status: active
metadata:
  author: RD Team
  version: 1.0.0
triggers:
  - 识别图片
  - 图片分析
  - OCR
  - 看图
  - 分析截图
  - image recognition
---

# 图片识别（Image Recognition via VLM）

通过内置工具 `analyze_image` 调用 VLM（Vision Language Model）进行图片分析和识别。

**使用场景**：OCR 文字提取、代码截图分析、图表数据分析、产品/设备识别

## 三步流程（按顺序执行）

### 第一步：确定图片文件

用户上传图片后，Slack/Telegram 适配器自动把图片保存到 workspace 的入站目录，可直接用 workspace 相对路径引用：

- 路径格式：`media/inbound/<filename>`
- 文件名格式：`<原始名>_<timestamp>.<ext>`

```python
# 查看最近上传的图片
run_code: import os; print(sorted(os.listdir("media/inbound"))[-3:])
```

### 第二步：调用 VLM 识别

`analyze_image` 直接接受 workspace 相对路径（或 `/exchange/...` 路径），无需做任何宿主机路径拼接。

```
analyze_image(
  image_path="media/inbound/<filename>",
  prompt="<根据用户问题定制的 prompt>"
)
```

### 第三步：结合用户问题回答

VLM 返回识别结果后：
1. 提取与用户问题相关的信息
2. 生成自然语言回答
3. 直接回答，不添加过程性描述（如"我来识别..."）

## 路径处理（重要）

`analyze_image` 在 agent 运行时内执行，直接使用 workspace 相对路径，无需路径转换：

| 用途 | 路径格式 | 说明 |
|------|---------|------|
| 入站图片 | `media/inbound/<filename>` | Slack/Telegram 适配器保存位置 |

**正确示例**：

```
# ✅ 直接用 workspace 相对路径
analyze_image(image_path="media/inbound/invoice.jpg", prompt="...")
```

## 常见场景 Prompt 模板

| 场景 | Prompt 模板 |
|------|------------|
| OCR 文字提取 | "请提取图片中的所有文字信息，以结构化格式输出" |
| 代码分析 | "请分析这段代码的功能、语言，并指出可能的问题或改进建议" |
| 图表分析 | "请分析图表数据趋势，提取关键数值并总结主要发现" |
| 设备识别 | "请识别图片中的设备型号、品牌和主要特征" |
| 发票识别 | "请提取发票中的所有信息：发票号码、日期、金额、税额、购买方、销售方，以结构化格式输出" |
| 通用识别 | "请详细描述图片内容" |

## 注意事项

**文件格式**：
- 支持：JPG, PNG, WEBP, GIF
- 不支持：BMP, TIFF

**性能建议**：
- 建议图片大小 ≤ 10MB
- VLM 响应时间约 2-5 秒（大图可能更长）
- 超大图片建议先压缩

**Prompt 设计**：
- 清晰描述分析任务
- 指定期望输出格式（如"结构化格式"、"表格"等）
- 结合用户问题定制 prompt

## 输出规范（重要）

**禁止过程性描述**：
- ❌ 不要说"我来识别图片"、"我正在分析"、"让我看看"等过程性话语
- ❌ 不要在回复开头添加"我来识别并总结图片内容："之类的前缀
- ✅ 直接返回识别结果和用户问题的答案

**正确示例**：
```
用户：这张发票的税额是多少？
AI 回复：根据发票识别结果，税额为 1,300.00 元。
```

**错误示例**：
```
用户：这张发票的税额是多少？
AI 回复：我来识别并总结图片内容：根据发票识别结果，税额为 1,300.00 元。
（❌ 多余的"我来识别并总结图片内容："）
```
