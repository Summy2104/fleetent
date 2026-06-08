## Context

`slack-image-upload` 引入的 `_extract_generated_image_paths()` 用正则 `r"image generated: (.+)"` 匹配 `generate_image` 工具结果，提取本地路径后交 `upload_func` 上传 Slack。`write_file` 工具的返回格式为 `f"written {len(content)} bytes to {path}"`，完全不同，所以不被匹配。

`upload_func`（`files_upload_v2`）本身对任何文件类型有效，无需修改。Slack adapter 也无需修改。唯一改动点是 normalizer 里的提取函数。

## Goals / Non-Goals

**Goals:**
- `write_file` 写出的文件自动上传 Slack，与图片行为对齐
- 向后兼容：原有 `generate_image` 路径不受影响

**Non-Goals:**
- 支持 `edit_file`（返回「替换成功」，没有文件路径可提取）
- Telegram 等其他适配器的文件上传（独立 change）

## Decisions

### D1：在同一函数里扩展，不新增函数

`_extract_generated_image_paths` 已被 `route()` 引用，且两个匹配模式语义相近（「agent 本轮产出的本地文件」）。在函数内增加第二个正则，遍历两个模式逐条尝试，保持单一职责且最小改动。函数名暂不改（改名需更新所有引用和测试）。

### D2：两个模式互斥（break after first match）

一条 tool 消息只对应一个工具调用，不可能同时匹配两个格式，`break` 仅是防御性优化。
