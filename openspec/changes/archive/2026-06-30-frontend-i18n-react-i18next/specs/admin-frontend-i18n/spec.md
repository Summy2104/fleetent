## ADDED Requirements

### Requirement: admin SPA 多语言能力由 react-i18next 承载

React admin SPA SHALL 提供中英双语能力，由 `i18next` + `react-i18next` 承载，并经 `src/i18n` 的公开出口 `useT()` / `useI18n()` / `I18nProvider` 对组件公开；该出口签名 SHALL 保持稳定，使既有调用点（`t('key')` 形式）无需改动。

- 词条 SHALL 以 `en` / `zh` 两份扁平点分 key 目录提供，`en` 为权威源；i18next SHALL 以 `keySeparator: false` 将含字面点的 key（如 `nav.agents`）视为扁平 key。
- 插值 SHALL 使用 i18next 原生 `{{name}}` 语法，调用点经 `t('key', { name })` 传值。
- 缺失 key 时运行时 SHALL NOT 抛错，SHALL 回退返回 key 本身；开发模式下 SHALL 在控制台告警。

#### Scenario: 取词与插值

- **WHEN** 组件调用 `useT()` 得到的 `t('shell.switchToLanguage', { lang: '中文' })`
- **THEN** 按当前语言返回对应文案并将 `{{lang}}` 插值为 `中文`

#### Scenario: 缺失 key 安全回退

- **WHEN** 调用 `t` 传入词条目录中不存在的 key
- **THEN** 运行时不抛错、返回该 key 字符串；开发模式下控制台告警

### Requirement: 语言探测、切换与持久化

SPA SHALL 在首次加载时探测语言：优先读取 localStorage（key `fleetent.admin.locale`），否则按浏览器语言（`zh-*` 归一到 `zh`，其余回退 `en`）。运行时切换语言后 SHALL 持久化到同一 localStorage key，并 SHALL 同步 `document.documentElement.lang`。

#### Scenario: 首次按浏览器语言探测

- **WHEN** 用户首次访问且 localStorage 无记录、浏览器语言为 `zh-CN`
- **THEN** SPA 以 `zh` 渲染

#### Scenario: 切换并持久化

- **WHEN** 用户经语言切换器切到另一语言
- **THEN** 界面即时切换，选择写入 localStorage（key `fleetent.admin.locale`），`<html lang>` 同步更新；刷新后保持该语言

### Requirement: 编译期类型安全

i18n 子域 SHALL 在编译期保障两类正确性：调用点 key 必须存在，且 `zh` 必须覆盖 `en` 的全部 key。

- 经 `i18next` 声明合并（以 `en` 为类型源），`t('不存在的key')` SHALL 在 `tsc` 报错并提供 key 自动补全。
- `zh` 词条 SHALL 以 `Messages` 类型对齐 `en`；漏翻任一 key SHALL 在 `tsc` 报错。

#### Scenario: 调用未定义 key 编译期报错

- **WHEN** 代码调用 `t('nope.missing')` 且该 key 不在词条目录
- **THEN** `pnpm typecheck` 报错

#### Scenario: zh 漏翻编译期报错

- **WHEN** `en` 新增一个 key 而 `zh` 未补
- **THEN** `pnpm typecheck` 报错
