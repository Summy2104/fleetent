# BI Intern 邮件模版转换规则

## 转换目标
将 pandoc 输出的原始 markdown 转换为 AI 可直接无歧义使用的结构化模版，
格式与 common-email-draft 中的模版一致（四段式结构）。

## 规则 A：固定角色识别
参照 conversion-config.yaml 中的 fixed_roles 列表。
这些角色在转换时必须保留原始姓名和邮箱，不得转为 {placeholder}。
遇到未在列表中的人名/邮箱 → 根据语义转为合适的 {role_name} 占位符。

⚠️ 注意：bi-intern 的 fixed_roles 尚未配置，首次转换时所有非明确邮箱的角色
将被转为占位符。请先补充 conversion-config.yaml 中的 fixed_roles 再使用。

## 规则 A.1：收件人 & 抄送转换判断

判断逻辑（优先级从高到低）：

1. **在 fixed_roles 列表中（无论是否有邮箱）** → 固定保留，不转占位符

2. **不在 fixed_roles 列表中，但有具体邮箱地址** → 固定保留，不转占位符
   - 示例：`姓名 <email@nsdigital.io>` → 保留原样

3. **不在 fixed_roles 列表中，无具体邮箱、仅有角色/群组描述** → 转为占位符
   - 示例：`业务邮箱群组` → `{business_group_email}`
   - 示例：`业务负责人` → `{business_leader}`
   - 占位符命名优先使用 conversion-config.yaml 中的 common_placeholders 库
   - 若无匹配的标准名，按语义自行命名（小写下划线格式）

## 规则 B：占位符识别与命名
识别原文中随业务变化的内容（公司名、业务线、日期等）。
命名规范：小写字母 + 下划线，如 {business_line}、{account_entity}。
优先使用 conversion-config.yaml 中 common_placeholders 的标准命名。
新变量命名需语义清晰，一看即懂。

## 规则 C：主题格式规范
从 conversion-config.yaml 的 subject_labels 中匹配最合适的标签。
若 subject_labels 为空，根据邮件内容自行推断合适的标签格式。
主题格式：【{类型标签}】{关键信息1} {关键信息2} {日期}
同时生成"主题示例"行（用具体示例值替换占位符）。

## 规则 D：审批流程识别
识别正文中 @姓名 + 请审批 的模式。
保留 @提及 格式（\@姓名）。
固定审批人按 fixed_roles 保留原名；可变审批人转为占位符。

## 规则 E：四段式结构输出
输出模版必须包含以下四段，缺失内容合理推断补全：

**## 📋 基本信息**
模版 ID（用文件名）、版本（v1）、更新日期（今日）、状态（active）、适用场景

**## 📥 收件人信息**
收件人、抄送（列表格式）、邮件主题（含占位符）、主题示例（含具体值）

**## 📤 邮件正文**
问候语（Dear Team，/ Hi {name}，）、正文内容、审批流程（如有）

**## 💡 使用指南**
变量替换说明表（占位符 | 说明 | 是否必填 | 示例）、固定信息说明、注意事项

## 规则 F：用户自定义规则
{用户反馈后追加的规则写在此处}
