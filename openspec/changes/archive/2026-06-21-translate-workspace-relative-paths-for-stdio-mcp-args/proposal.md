## Why

端到端实测(2026-06-21,#280+#282 部署后)发现:「生成图片→发邮件附件」**仍失败**。这次 agent 传给 `email__send_email` 的附件是**工作区相对路径**:

```json
"attachments": ["generated/5f5b0f1c97c4446c9cb3edd15bad92e5.png"]
```

而 #280 的 `_translate_workspace_arg` **只翻译 `/workspace[/<rel>]` 绝对前缀**(当初故意排除相对路径)。相对路径原样透传给 email(stdio 宿主进程,cwd=`exchange/email`)→ 按 cwd 解析 → 找不到 → `Attachment file not found`。

根因:模型**不确定性**地有时发 `/workspace/generated/x.png`(绝对,#280 已修),有时直接发 image-gen 返回的相对 ref `generated/x.png`(**未覆盖**)。实测确认翻译对相对路径 no-op:`generated/5f5b0f1c…png` → 不变(而该文件真实存在于 `host_workspace_dir/generated/`)。

## What Changes

- **扩展 `_translate_workspace_arg` 覆盖工作区相对路径**:对 stdio server 入参中**不以 `/` 开头**的字符串值,若 `host_workspace_dir / value` **确实是 workspace 内的真实文件**(存在性 + 围栏 containment 双判),翻译为该绝对宿主路径;否则原样保留。
  - 存在性判断消歧:`可爱小狗`、邮件正文(多行)、普通文本等不会误伤(它们不是 workspace 下的真实文件)。
  - 含 `..` 逃逸或解析后落在 `host_workspace_dir` 之外的一律不翻译(防路径穿越)。
  - 含换行的值(正文)直接跳过(路径不含换行,省去无谓 stat)。

不动:`/workspace` 绝对前缀翻译(#280 已有)、http server、结果/输出侧改写。仅在既有翻译上**增补相对路径分支**。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `file-exchange`:在「stdio MCP 入参的容器 /workspace 路径翻译」要求上扩展——除 `/workspace[/<rel>]` 绝对路径外,**工作区相对路径**(解析到 workspace 内真实文件者)同样 SHALL 翻译为宿主绝对路径;非真实文件的相对字符串、`..` 逃逸、http server 不受影响。

## Impact

**owning package**:agent runtime —— `src/fleetent/integrations/mcp/client.py`（`_translate_workspace_arg` 增补相对路径分支）。不 import `fleetent.platform.*`。

**public API surface**:无变化（`_translate_workspace_arg` / `_translate_workspace_args` 私有,签名不变）。

**owned tables**：无（零 schema/迁移）。

**config namespace**：无。

**cross-module dependencies**：复用既有 `host_workspace_dir`（chokepoint 已传入 host_dir）；不新增依赖,不触碰 agent↔platform 边界。

**migration / shim plan**：无。

**受影响代码**：`integrations/mcp/client.py`（`_translate_workspace_arg`）；测试 `tests/unit/test_mcp_exchange_injection.py`（相对路径翻译/存在性消歧/逃逸防护用例）。
