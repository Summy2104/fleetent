## ADDED Requirements

### Requirement: Facts 提取输出 scope 字段

facts 提取 pipeline SHALL 在提取输出中包含 `scope` 字段（`'situational'` | `'always'`），由 LLM 在提取时判断。行为指令（"每次都要执行"、"永远不要做"、格式/风格偏好）SHALL 输出 `scope='always'`；事实性偏好 SHALL 输出 `scope='situational'`。

#### Scenario: Behavioral directive extracted as always
- **WHEN** 用户表达行为指令（如"以后回复我要加 xin"、"永远不要用 Markdown"）
- **THEN** 提取的 fact `scope='always'`

#### Scenario: Factual preference extracted as situational
- **WHEN** 用户表达事实性偏好（如"我喜欢 TypeScript"、"我在北京"）
- **THEN** 提取的 fact `scope='situational'`

#### Scenario: Scope written to facts store
- **WHEN** 提取 pipeline 写入 fact
- **THEN** `facts` 表记录包含正确的 `scope` 值
