import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { I18nProvider, type MessageKey, useI18n, useT } from '@/i18n'
import i18n from '@/i18n/config'
import { CATALOGS } from '@/i18n/messages'

function Probe(): JSX.Element {
  const { locale, setLocale, toggleLocale } = useI18n()
  const t = useT()
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="title">{t('login.title')}</span>
      <span data-testid="interp">{t('shell.switchToLanguage', { lang: 'X' })}</span>
      <span data-testid="missing">{t('no.such.key' as MessageKey)}</span>
      <button onClick={toggleLocale} type="button">
        toggle
      </button>
      <button onClick={() => setLocale('zh')} type="button">
        to-zh
      </button>
    </div>
  )
}

describe('i18n package', () => {
  beforeEach(async () => {
    window.localStorage.clear()
    // i18next 是单例，跨测试需复位语言，避免顺序依赖。
    await i18n.changeLanguage('en')
  })
  afterEach(() => {
    window.localStorage.clear()
  })

  it('每个 zh 词条都覆盖了 en 的全部 key（无漏翻）', () => {
    expect(Object.keys(CATALOGS.zh).sort()).toEqual(Object.keys(CATALOGS.en).sort())
  })

  it('默认 en（jsdom navigator.language 非 zh）并按 key 翻译', () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    expect(screen.getByTestId('locale')).toHaveTextContent('en')
    expect(screen.getByTestId('title')).toHaveTextContent('Admin Login')
  })

  it('toggle 切到中文后词条更新', async () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    await userEvent.click(screen.getByText('toggle'))
    expect(screen.getByTestId('locale')).toHaveTextContent('zh')
    expect(screen.getByTestId('title')).toHaveTextContent('管理员登录')
  })

  it('{{var}} 占位符按 vars 插值', () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    expect(screen.getByTestId('interp')).toHaveTextContent('Switch to X')
  })

  it('缺失 key 不抛错并回退显示 key 本身', () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    expect(screen.getByTestId('missing')).toHaveTextContent('no.such.key')
  })

  it('切换语言同步 <html lang>', async () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    expect(document.documentElement.lang).toBe('en')
    await userEvent.click(screen.getByText('toggle'))
    expect(document.documentElement.lang).toBe('zh')
  })

  it('选择持久化到 localStorage 并在重新挂载后恢复', async () => {
    const first = render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    await userEvent.click(screen.getByText('to-zh'))
    expect(window.localStorage.getItem('fleetent.admin.locale')).toBe('zh')
    first.unmount()

    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>
    )
    expect(screen.getByTestId('locale')).toHaveTextContent('zh')
  })
})
