import 'i18next'

import type en from '@/i18n/messages'

/**
 * i18next 类型声明合并 —— 以 `en` 权威源为类型源，使 `t('key')` 在编译期获得
 * key 自动补全，调用不存在的 key 直接 `tsc` 报错。`keySeparator: false` 与
 * `config.ts` 对齐，让含点的扁平 key（`nav.agents`）按字面处理。
 */
declare module 'i18next' {
  interface CustomTypeOptions {
    keySeparator: false
    resources: {
      translation: typeof en
    }
  }
}
