## ADDED Requirements

### Requirement: run_code 返回前对 stdout/stderr 脱敏

`run_code` 返回给 agent loop 的 stdout 与 stderr SHALL 在返回前经过密钥脱敏：疑似密钥被替换为占位符，非敏感上下文（如头名、键名、URL 协议与主机）予以保留。脱敏 SHALL 覆盖至少以下形态：PEM 私钥块、JWT、常见厂商 API key 前缀（如 `sk-`、`ghp_`、`AKIA…`）、`Authorization` 头中的凭证、URL 内嵌的 `user:pass@` 凭证、以及键名表明是密钥的 `KEY=VALUE` 赋值。脱敏 MUST 在输出截断之前进行，使密钥不因截断在边界处逃逸。trace 记录的输出字节大小 SHALL 仍按原始输出计（脱敏不改变大小语义）。

#### Scenario: stdout 中的 API key 被脱敏
- **WHEN** 容器 stdout 含一个厂商 API key（如 `sk-` 或 `ghp_` 前缀）
- **THEN** `run_code` 返回值中该 key 被占位符替换，不再出现原始 key

#### Scenario: 连接串中的密码被脱敏
- **WHEN** 输出含形如 `postgres://user:secret@host/db` 的连接串
- **THEN** 返回值中密码段被占位符替换，协议与主机保留

#### Scenario: 私钥块被整段脱敏
- **WHEN** 输出含 `-----BEGIN ... PRIVATE KEY-----` 私钥块
- **THEN** 返回值中该私钥块被占位符替换

#### Scenario: Authorization 头凭证被脱敏而保留头名
- **WHEN** stderr 含 `Authorization: Bearer <token>`
- **THEN** 返回值保留 `Authorization` 头名，凭证被占位符替换

### Requirement: 脱敏保守且可扩展，不误伤普通输出

脱敏 SHALL 保守——不含密钥的普通文本（散文、数字、普通标识符）MUST NOT 被改动。脱敏模式集 SHALL 为可扩展的模块级常量，便于后续按需补充而无需改动调用方。

#### Scenario: 普通输出原样返回
- **WHEN** 输出为不含任何密钥的普通文本（如计算结果、日志行）
- **THEN** `run_code` 返回值与原始输出在内容上一致（除截断外不被改动）

#### Scenario: 模式集可扩展
- **WHEN** 向脱敏模块的模式集追加一个新模式
- **THEN** 后续脱敏调用即按新模式生效，调用方无需改动
